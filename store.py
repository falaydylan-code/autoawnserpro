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
