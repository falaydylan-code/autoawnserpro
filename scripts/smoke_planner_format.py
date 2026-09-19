"""Opt-in live planner format check; spends at most the supplied $0.10 run cap.

Run manually against the hosted backend. Never part of automatic pytest runs.
"""
import json
import argparse
import uuid
import httpx


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--inspection', action='store_true', help='Check on-demand inspection targeting instead of a checkbox plan.')
    mode.add_argument('--cashflow', action='store_true', help='Check one plan using already discovered dropdown choices.')
    args = parser.parse_args()
    backend = 'https://positive-tranquility-production-9fdc.up.railway.app'
    with httpx.Client(base_url=backend, timeout=70) as client:
        auth = client.post('/api/guest')
        auth.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + auth.json()['token']
        body = {
            'run_id': 'format-smoke-' + uuid.uuid4().hex,
            'request_id': uuid.uuid4().hex,
            'spend_limit': 0.10,
            'observation': {
                'question_key': 'format-smoke', 'observation_id': 'obs-smoke',
                'document_id': 'doc-smoke',
                'question': 'Select all even integers from 2, 3, and 4.',
                'completeness': {'complete': True},
                'slots': [{'slot_key': 'format-smoke/choices', 'kind': 'choice_set',
                           'label': 'Even integers', 'options': ['2', '3', '4'], 'current': []}],
            },
        }
        if args.inspection:
            body['observation'].update(
                question='Select the dropdown option matching the requested category. Its exact option labels are not yet visible; inspect them before planning.',
                completeness={'complete':False, 'note':'Missing dropdown option labels. Request inspect_options for the supplied selection slot.'},
                slots=[{'slot_key':'format-smoke/row-1/category', 'kind':'selection',
                        'label':'Row 1 category dropdown', 'options':[], 'current':''}])
        if args.cashflow:
            rows=['Cash paid for dividends','Cash collected from customers','Cash received when signing a note payable',
                  'Cash paid to employees','Cash paid to purchase equipment','Cash received from issuing stock']
            body['observation'].update(
                question='For each cash flow, select Operating, Investing or Financing. Use the word in parentheses for a cash outflow; without parentheses for an inflow. The harness has already opened every dropdown and supplied its exact options.',
                slots=[{'slot_key':f'format-smoke/row-{i}/activity','kind':'selection','label':label,'current':'',
                        'options':['Operating','(Operating)','Investing','(Investing)','Financing','(Financing)']} for i,label in enumerate(rows)])
        response = client.post('/api/agent/plan', json=body)
        data = response.json()
        print(json.dumps({k: data.get(k) for k in
                          ['model', 'output_format', 'finish_reason', 'cost', 'input_tokens',
                           'output_tokens', 'detail', 'raw_reply']}, indent=2))
        response.raise_for_status()
        plan = data['response']
        assert plan['question_key'] == 'format-smoke' and plan['observation_id'] == 'obs-smoke'
        if args.inspection:
            assert plan['kind'] == 'request_inspection'
            inspection = plan['inspection']
            assert inspection['slot_key'] in ('', 'format-smoke/row-1/category')
            assert inspection['slot_key'] or all(r == 'inspect_question' for r in inspection['requests'])
            print('PASS: real provider requested valid on-demand inspection; no script or browser action executed.')
            return
        if args.cashflow:
            assert plan['kind']=='plan' and len(plan['tasks'])==6
            actual={t['slot_key']:t['desired']['label'] for t in plan['tasks']}
            expected=['(Financing)','Operating','Financing','(Operating)','(Investing)','Financing']
            assert all(actual[f'format-smoke/row-{i}/activity']==label for i,label in enumerate(expected))
            print('PASS: one complete cash-flow plan from supplied options, exact parentheses, no further inspection requested.')
            return
        assert len(plan['tasks']) == 1
        task = plan['tasks'][0]
        assert task['operation'] == 'set_choice_set'
        assert task['slot_key'] == 'format-smoke/choices'
        assert set(task['desired']['labels']) == {'2', '4'}
        print('PASS: real provider returned a complete, correctly bound checkbox plan.')


if __name__ == '__main__':
    main()
