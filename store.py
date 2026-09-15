import json
import sqlite3
from pathlib import Path
from settings import ROOT, setting


def connect():
    folder = Path(setting('DATA_DIR', str(ROOT / 'data')))
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / 'agent.db')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT, payload TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS usage (owner TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0, unknown INTEGER NOT NULL DEFAULT 0)')
    return con


def save(run):
    payload = run.public(include_live=False)
    with connect() as con:
        con.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?)', (run.id, run.owner, json.dumps(payload)))


def history(owner):
    with connect() as con:
        rows = con.execute('SELECT payload FROM runs WHERE owner=? ORDER BY rowid DESC LIMIT 50', (owner,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def recover():
    with connect() as con:
        for rid, payload in con.execute('SELECT id,payload FROM runs').fetchall():
            item = json.loads(payload)
            if item['status'] not in ['closed', 'expired', 'interrupted']:
                item['status'] = 'interrupted'
                item['message'] = 'Server restarted. Start a new browser session; previous answers remain below.'
                con.execute('UPDATE runs SET payload=? WHERE id=?', (json.dumps(item), rid))


def reserve_call(owner):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('INSERT OR IGNORE INTO usage(owner) VALUES (?)', (owner,))
        calls, cost, unknown = con.execute('SELECT calls,cost,unknown FROM usage WHERE owner=?', (owner,)).fetchone()
        if unknown:
            raise ValueError('A previous API call has unconfirmed cost. Ask the operator to reconcile usage before continuing.')
        if calls >= int(setting('MAX_CALLS_PER_INVITE', '100')) or cost >= float(setting('MAX_COST_PER_INVITE', '2')):
            raise ValueError('Tester usage limit reached. Ask the operator for more allowance.')
        # Pessimistically reserve unknown cost: crashes/cancellation cannot hide spend.
        con.execute('UPDATE usage SET calls=calls+1, unknown=unknown+1 WHERE owner=?', (owner,))


def settle_call(owner, cost):
    if cost is not None:
        with connect() as con:
            con.execute('UPDATE usage SET cost=cost+?, unknown=MAX(0,unknown-1) WHERE owner=?', (cost, owner))

# Planner reservations survive backend restart; pending provider charges never
# disappear because a client disconnected. Legacy metering remains unchanged.
def planner_tables(con):
    con.execute('CREATE TABLE IF NOT EXISTS planner_runs (id TEXT PRIMARY KEY, owner TEXT, cap REAL NOT NULL, cost REAL NOT NULL DEFAULT 0)')
    con.execute('CREATE TABLE IF NOT EXISTS planner_calls (id TEXT PRIMARY KEY, run_id TEXT, question TEXT, phase TEXT, reserved REAL, cost REAL, status TEXT, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, latency REAL DEFAULT 0, model TEXT)')

def reserve_plan(owner, run_id, request_id, question, phase, cap, amount, model):
    import math
    if not math.isfinite(amount) or amount<0:raise ValueError('BUDGET_EXHAUSTED: invalid price reservation.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');planner_tables(con)
        run=con.execute('SELECT owner,cap,cost FROM planner_runs WHERE id=?',(run_id,)).fetchone()
        if run and run[0]!=owner:raise ValueError('GUARD_REJECTED: run belongs to a different user.')
        if not run:
            con.execute('INSERT INTO planner_runs(id,owner,cap) VALUES(?,?,?)',(run_id,owner,cap));run=(owner,cap,0)
        if con.execute('SELECT 1 FROM planner_calls WHERE id=?',(request_id,)).fetchone():raise ValueError('REPEATED_STATE: request already reserved; do not replay it.')
        con.execute('INSERT OR IGNORE INTO usage(owner) VALUES(?)',(owner,))
        calls,cost,unknown=con.execute('SELECT calls,cost,unknown FROM usage WHERE owner=?',(owner,)).fetchone()
        if unknown:raise ValueError('BUDGET_EXHAUSTED: prior provider cost is unconfirmed; reconcile usage before another call.')
        if calls>=int(setting('MAX_CALLS_PER_INVITE','100')) or cost+amount>float(setting('MAX_COST_PER_INVITE','2')) or run[2]+amount>min(cap,run[1]):
            raise ValueError('BUDGET_EXHAUSTED: remaining allowance cannot cover the maximum request cost.')
        count=con.execute('SELECT COUNT(*) FROM planner_calls WHERE run_id=? AND question=? AND phase=?',(run_id,question,phase)).fetchone()[0]
        if count >= ({'repair':2,'plan':3,'visual':125,'verify':4}.get(phase,0)):raise ValueError('BUDGET_EXHAUSTED: question model-call budget reached.')
        con.execute('INSERT INTO planner_calls(id,run_id,question,phase,reserved,status,model) VALUES(?,?,?,?,?,?,?)',(request_id,run_id,question,phase,amount,'pending',model))
        con.execute('UPDATE usage SET calls=calls+1,unknown=unknown+1 WHERE owner=?',(owner,))

def settle_plan(owner,request_id,cost,record):
    if cost is None:return
    with connect() as con:
        planner_tables(con)
        row=con.execute('SELECT run_id,status FROM planner_calls WHERE id=?',(request_id,)).fetchone()
        if not row or row[1]!='pending':return
        con.execute('UPDATE planner_calls SET cost=?,status=?,tokens_in=?,tokens_out=?,latency=? WHERE id=?',
                    (cost,'settled',record.get('input_tokens',0),record.get('output_tokens',0),record.get('latency',0),request_id))
        con.execute('UPDATE planner_runs SET cost=cost+? WHERE id=?',(cost,row[0]))
        con.execute('UPDATE usage SET cost=cost+?,unknown=MAX(0,unknown-1) WHERE owner=?',(cost,owner))

def plan_status(owner,run_id):
    with connect() as con:
        planner_tables(con)
        run=con.execute('SELECT owner,cap,cost FROM planner_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run[0]!=owner:return None
        rows=con.execute('SELECT id,question,phase,reserved,cost,status,tokens_in,tokens_out,latency,model FROM planner_calls WHERE run_id=? ORDER BY rowid',(run_id,)).fetchall()
        keys=('request_id','question_key','phase','reserved','cost','status','input_tokens','output_tokens','latency','model')
        return {'run_id':run_id,'cap':run[1],'cost':run[2],'calls':[dict(zip(keys,row)) for row in rows]}
