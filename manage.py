"""Operator-only local usage reconciliation; never exposes invite codes."""
import getpass
import hashlib
import math
import sys
import store

if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'usage'
    code = getpass.getpass('Tester invite code (hidden): ')
    owner = hashlib.sha256(code.encode()).hexdigest()
    with store.connect() as con:
        row = con.execute('SELECT calls,cost,unknown FROM usage WHERE owner=?', (owner,)).fetchone()
        if not row:
            print('No usage found for that invite.')
            raise SystemExit(0)
        print(f'Calls: {row[0]}; recorded model cost: ${row[1]:.6f}; unconfirmed calls: {row[2]}')
        if command == 'reconcile' and row[2]:
            print('Look up ALL unconfirmed calls in OpenRouter first. Do not guess their cost.')
            amount = float(input('Actual combined cost of those unconfirmed calls, USD: '))
            if not math.isfinite(amount) or amount < 0:
                raise SystemExit('Enter a finite nonnegative amount.')
            if input('Type RECONCILE after verifying provider records: ') == 'RECONCILE':
                con.execute('UPDATE usage SET cost=cost+?,unknown=0 WHERE owner=?', (amount,owner))
                print('Usage reconciled. Historical rows retain their original unconfirmed marker for audit.')
