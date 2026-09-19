"""Table source fidelity through the real inspector, request and copy-log path."""
import json
import pytest
import planner
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


@pytest.mark.parametrize('framed', [False, True])
def test_source_table_reaches_planner_and_log_without_changing_execution(extension, framed):
    page, worker, tid = navigate(extension, 'structured_financial_table.html')
    if framed:
        page.goto(page.url.replace('structured_financial_table.html', 'planner_standard.html'))
        page.evaluate('''()=>document.body.innerHTML='<iframe src="structured_financial_table.html" style="width:1100px;height:800px"></iframe>' ''')
        page.frame_locator('iframe').locator('#financial').wait_for()
    initial = worker.evaluate(BOOT, tid)
    assert len(initial['slots']) == 9
    table = initial['tables'][0]
    assert table['frame_id'] > 0 if framed else table['frame_id'] == 0
    assert table['caption'] == 'Financial statement amounts'
    assert [[c['text'] for c in r['cells']] for r in table['rows']][7:] == [
        ['Total Expenses', '65', '40', '210'],
        ['Total Liabilities', '40', '40', '360'],
        ['Total Revenues', '80', '70', '320']]
    assert [c['column'] for c in table['rows'][3]['cells']] == [0, 1, 2, 3]
    assert all(c['answer'] and c['text'] == '' for c in table['rows'][3]['cells'][1:])
    result = worker.evaluate('()=>engine.run()')
    assert result['status'] == 'finished', result['events'][-3:]
    calls = worker.evaluate('calls')
    plans = [c for c in calls if c['phase'] == 'plan']
    assert len(plans) == 1
    body = plans[0]['body']['observation']
    assert 'Amounts in thousands' in body['question']
    assert body['tables'] == initial['tables']
    parsed = planner.PlanObservation.model_validate(body)
    assert json.loads(planner.build_plan_text(parsed.model_dump()))['tables'][0]['rows'][9]['cells'][1]['text'] == '80'
    snapshot = next(e for e in result['events'] if e.get('dom_observation') and e['request_id'] == plans[0]['body']['request_id'])
    assert json.loads(snapshot['dom_observation'])['tables'] == body['tables']
    final = worker.evaluate('()=>engine.observe()')
    assert final['question_key'] == initial['question_key']
    assert [s['slot_key'] for s in final['slots']] == [s['slot_key'] for s in initial['slots']]
    assert final['tables'] == initial['tables']  # typed answers remain separate from givens


def test_merged_cells_hidden_columns_nested_layout_and_offscreen_tables(extension):
    page, worker, tid = navigate(extension, 'planner_standard.html')
    page.evaluate('''()=>document.querySelector('main').innerHTML=`<h1>Read the table</h1><input id=answer aria-label=Answer>
      <table role=presentation><tr><td>Layout</td><td>Not data</td></tr><tr><td>x</td><td>y</td></tr></table>
      <div style="height:2000px"></div><table id=wrapper><tr><td><table id=data>
      <caption>Visible caption<span hidden>SECRET CAPTION</span></caption>
      <thead><tr><th rowspan=99 scope=col>Account</th><th colspan=2>Companies</th></tr>
      <tr><th scope=col>A</th><th scope=col>B</th></tr></thead>
      <tbody><tr><th rowspan=0 scope=rowgroup>Expenses</th><td></td><td>(65)</td></tr>
      <tr><td style="display:none">SECRET</td><td>0</td></tr></tbody></table></td></tr></table>
      <table hidden><tr><td>HIDDEN</td><td>1</td></tr><tr><td>2</td><td>3</td></tr></table>`''')
    obs = worker.evaluate(BOOT, tid)
    assert [t['dom_id'] for t in obs['tables']] == ['data']
    assert obs['tables'][0]['caption'] == 'Visible caption'
    rows = obs['tables'][0]['rows']
    assert rows[0]['cells'][0]['row_span'] == 2
    assert rows[0]['cells'][1]['column_span'] == 2
    assert [c['column'] for c in rows[1]['cells']] == [1, 2]
    assert rows[2]['cells'][0]['row_span'] == 2
    assert [(c['column'], c['text']) for c in rows[2]['cells']][1:] == [(1, ''), (2, '(65)')]
    assert [(c['column'], c['text']) for c in rows[3]['cells']] == [(2, '0')]
    assert page.evaluate('scrollY') == 0
    assert 'SECRET' not in json.dumps(obs['tables'])
    planner.PlanObservation.model_validate(worker.evaluate('async()=>engine.publicObservation(await engine.observe())'))


def test_table_limits_report_incomplete_and_non_table_question_unchanged(extension):
    page, worker, tid = navigate(extension, 'planner_standard.html')
    worker.evaluate(BOOT, tid)
    before = worker.evaluate('async()=>engine.publicObservation(await engine.observe())')
    assert 'tables' not in before
    page.evaluate('''()=>{const t=document.createElement('table');t.innerHTML='<tr><th>A</th><th>B</th></tr>'+Array.from({length:180},()=>'<tr><td>1</td><td>2</td></tr>').join('');document.querySelector('main').append(t)}''')
    after = worker.evaluate('async()=>engine.publicObservation(await engine.observe())')
    assert not after['table_context_complete']
    assert not after['tables'][0]['complete']
    assert sum(len(r['cells']) for r in after['tables'][0]['rows']) == 300
    assert after['slots'] == before['slots']
    planner.PlanObservation.model_validate(after)
