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
# A reservation still pending this long after it was made belongs to a call that
# can no longer be in flight (planner.REQUEST_DEADLINE_MAX is 300 s): it is
# charged at its reserved worst case, so budgets stay safe and no identity stays
# frozen on 'prior provider cost is unconfirmed' (M3-9 9:13 PM: a 60 s timeout
# left one such row, and nothing in the code could ever clear it).
STALE_RESERVATION_SECONDS = 360
def planner_tables(con):
    con.execute('CREATE TABLE IF NOT EXISTS planner_runs (id TEXT PRIMARY KEY, owner TEXT, cap REAL NOT NULL, cost REAL NOT NULL DEFAULT 0)')
    con.execute('CREATE TABLE IF NOT EXISTS planner_calls (id TEXT PRIMARY KEY, run_id TEXT, question TEXT, phase TEXT, reserved REAL, cost REAL, status TEXT, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, latency REAL DEFAULT 0, model TEXT)')
    if 'budget_owner' not in {r[1] for r in con.execute('PRAGMA table_info(planner_runs)')}:
        con.execute('ALTER TABLE planner_runs ADD COLUMN budget_owner TEXT')
        con.execute('UPDATE planner_runs SET budget_owner=owner')
    if 'created' not in {r[1] for r in con.execute('PRAGMA table_info(planner_calls)')}:
        con.execute('ALTER TABLE planner_calls ADD COLUMN created REAL')   # NULL = made before this column existed: stale

def reserve_plan(owner, run_id, request_id, question, phase, cap, amount, model, budget_owner=None):
    import math
    if not math.isfinite(amount) or amount<0:raise ValueError('BUDGET_EXHAUSTED: invalid price reservation.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');planner_tables(con);_reconcile_stale(con)
        run=con.execute('SELECT owner,cap,cost,budget_owner FROM planner_runs WHERE id=?',(run_id,)).fetchone()
        if run and run[0]!=owner:raise ValueError('GUARD_REJECTED: run belongs to a different user.')
        if not run:
            budget_owner=budget_owner or owner
            con.execute('INSERT INTO planner_runs(id,owner,cap,budget_owner) VALUES(?,?,?,?)',(run_id,owner,cap,budget_owner));run=(owner,cap,0,budget_owner)
        # Run authorization uses the session; its allowance is pinned on creation.
        budget_owner=run[3] or owner
        if con.execute('SELECT 1 FROM planner_calls WHERE id=?',(request_id,)).fetchone():raise ValueError('REPEATED_STATE: request already reserved; do not replay it.')
        con.execute('INSERT OR IGNORE INTO usage(owner) VALUES(?)',(budget_owner,))
        calls,cost,unknown=con.execute('SELECT calls,cost,unknown FROM usage WHERE owner=?',(budget_owner,)).fetchone()
        if unknown:raise ValueError('BUDGET_EXHAUSTED: prior provider cost is unconfirmed; reconcile usage before another call.')
        if calls>=int(setting('MAX_CALLS_PER_INVITE','100')):raise ValueError('BUDGET_EXHAUSTED: the call allowance for this invite is used up.')
        if cost+amount>float(setting('MAX_COST_PER_INVITE','2')):raise ValueError(f'BUDGET_EXHAUSTED: the worst-case cost of this call (${amount:.2f}) exceeds the remaining allowance for this invite (${max(0,float(setting("MAX_COST_PER_INVITE","2"))-cost):.2f}).')
        if run[2]+amount>min(cap,run[1]):raise ValueError(f"BUDGET_EXHAUSTED: the worst-case cost of this call (${amount:.2f}; a screenshot reserves the full model context) exceeds what is left of the run spend limit (${max(0,min(cap,run[1])-run[2]):.2f} of ${min(cap,run[1]):.2f}). Raise the spend limit in the panel for this model.")
        count=con.execute('SELECT COUNT(*) FROM planner_calls WHERE run_id=? AND question=? AND phase=?',(run_id,question,phase)).fetchone()[0]
        if count >= ({'repair':2,'plan':3,'inspection_correction':1,'format_correction':1,'visual':125,'verify':4}.get(phase,0)):raise ValueError('BUDGET_EXHAUSTED: question model-call budget reached.')
        import time
        con.execute('INSERT INTO planner_calls(id,run_id,question,phase,reserved,status,model,created) VALUES(?,?,?,?,?,?,?,?)',(request_id,run_id,question,phase,amount,'pending',model,time.time()))
        con.execute('UPDATE usage SET calls=calls+1,unknown=unknown+1 WHERE owner=?',(budget_owner,))

def _settle(con,request_id,run_id,budget_owner,cost,record,status):
    con.execute('UPDATE planner_calls SET cost=?,status=?,tokens_in=?,tokens_out=?,latency=? WHERE id=?',
                (cost,status,record.get('input_tokens',0),record.get('output_tokens',0),record.get('latency',0),request_id))
    con.execute('UPDATE planner_runs SET cost=cost+? WHERE id=?',(cost,run_id))
    con.execute('UPDATE usage SET cost=cost+?,unknown=MAX(0,unknown-1) WHERE owner=?',(cost,budget_owner))

def settle_plan(owner,request_id,cost,record,status='settled'):
    """status 'settled': the provider reported this cost. 'charged_worst_case': the cost could not be confirmed
    (timeout, transport failure, malformed reply) and the reserved amount is charged instead -- never less."""
    if cost is None:return
    with connect() as con:
        planner_tables(con)
        row=con.execute('SELECT c.run_id,c.status,r.budget_owner FROM planner_calls c JOIN planner_runs r ON r.id=c.run_id WHERE c.id=? AND r.owner=?',(request_id,owner)).fetchone()
        if not row or row[1]!='pending':return
        _settle(con,request_id,row[0],row[2] or owner,cost,record,status)

def _reconcile_stale(con,now=None):
    import time
    now=time.time() if now is None else now
    rows=con.execute('SELECT c.id,c.run_id,c.reserved,r.budget_owner,r.owner FROM planner_calls c JOIN planner_runs r ON r.id=c.run_id '
                     'WHERE c.status=? AND (c.created IS NULL OR c.created<?)',('pending',now-STALE_RESERVATION_SECONDS)).fetchall()
    for request_id,run_id,reserved,budget_owner,run_owner in rows:_settle(con,request_id,run_id,budget_owner or run_owner,reserved or 0,{},'charged_worst_case')
    return len(rows)

def reconcile_stale_plans(now=None):
    """Startup and per-reservation sweep: pending reservations older than any call could still be are charged at their
    reserved worst case. Returns how many were reconciled."""
    with connect() as con:
        con.execute('BEGIN IMMEDIATE');planner_tables(con)
        return _reconcile_stale(con,now)

def save_access(token, identity, expires):
    import hashlib
    import time
    with connect() as con:
        con.execute('CREATE TABLE IF NOT EXISTS access_sessions (digest TEXT PRIMARY KEY, identity TEXT, expires REAL)')
        con.execute('DELETE FROM access_sessions WHERE expires<?',(time.time()-86400,))
        con.execute('INSERT INTO access_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identity,expires))

def read_access(token):
    import hashlib
    if not token:return None
    with connect() as con:
        con.execute('CREATE TABLE IF NOT EXISTS access_sessions (digest TEXT PRIMARY KEY, identity TEXT, expires REAL)')
        return con.execute('SELECT identity,expires FROM access_sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()

def plan_status(owner,run_id):
    with connect() as con:
        planner_tables(con)
        run=con.execute('SELECT owner,cap,cost FROM planner_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run[0]!=owner:return None
        rows=con.execute('SELECT id,question,phase,reserved,cost,status,tokens_in,tokens_out,latency,model FROM planner_calls WHERE run_id=? ORDER BY rowid',(run_id,)).fetchall()
        keys=('request_id','question_key','phase','reserved','cost','status','input_tokens','output_tokens','latency','model')
        return {'run_id':run_id,'cap':run[1],'cost':run[2],'calls':[dict(zip(keys,row)) for row in rows]}
