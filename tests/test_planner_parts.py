"""Multi-part questions (the E1-9 shape): a tab strip inside the question, only the selected part visible.

Before this, "question" meant "the answer controls visible at the first observe": E1-9's run filled the three
Income Statement cells, declared itself finished, and never touched the Balance Sheet tab. Now the harness
reveals every part by clicking its tab (what a student does), observes each while visible, plans across the
union, switches to a part before acting in it, and refuses to finish when the wording names more parts than
it could reveal or when new answer controls appear after the planned ones were entered.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

VALUES = {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700', 'Cash': '34800', 'Total Assets': '103200'}


def observe(w, tid):
    return w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      return {question_key:o.question_key,parts:o.parts.map(p=>({part_id:p.part_id,label:p.label,selected:p.selected})),slots:o.slots.map(s=>({label:s.label,part_id:s.part_id||null})),question:o.question}}''', tid)


def run(w, tid, values, parts_declared=1):
    """Scripted planner: one enter_value per slot, labels looked up in `values`; records what it was shown."""
    return w.evaluate('''async ({id,values,declared})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const ops={choice:'choose_one',choice_set:'set_choice_set',value:'enter_value',selection:'set_selection',ordering:'set_order',position:'place_points'};
        const tasks=body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:ops[s.kind],desired:s.kind==='value'?{value:values[s.label]??'1'}:s.kind==='choice'?{label:'B'}:s.kind==='selection'?{label:s.label.includes('Statement')?'Balance Sheet':'Asset'}:{labels:['A']},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:declared}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,part_id:e.part_id||null})),bodies:globalThis.planBodies};}''',
      {'id': tid, 'values': values, 'declared': parts_declared})


def test_observe_reports_the_parts_and_identity_survives_switching_tabs(extension):
    page, w, tid = navigate(extension, 'tabs_parts.html')
    first = observe(w, tid)
    assert [p['label'] for p in first['parts']] == ['Income Statement', 'Balance Sheet']
    assert [p['selected'] for p in first['parts']] == [True, False]
    assert [s['label'] for s in first['slots']] == ['Total Revenues', 'Operating Expenses', 'Net Income']   # only the visible part
    assert all(s['part_id'] == first['parts'][0]['part_id'] for s in first['slots'])
    page.click('#tab-bs')
    second = observe(w, tid)
    assert second['question_key'] == first['question_key']                     # same question, other tab
    assert [s['label'] for s in second['slots']] == ['Cash', 'Total Assets'] and all(s['part_id'] == first['parts'][1]['part_id'] for s in second['slots'])
    assert 'Prepare the balance sheet' in second['question'] and 'Prepare an income statement' not in second['question']
    # no platform id: identity leans on structure + stem, and the tab panels are left out of both
    page.click('#tab-is'); page.evaluate("()=>document.querySelector('main').removeAttribute('data-question-id')")
    a = observe(w, tid)['question_key']; page.click('#tab-bs'); b = observe(w, tid)['question_key']
    assert a == b, 'switching tabs forked the question identity'


def test_run_reveals_every_part_and_fills_all_of_them(extension):
    page, w, tid = navigate(extension, 'tabs_parts.html')
    result = run(w, tid, VALUES, parts_declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    for cell, value in [('#rev', '139000'), ('#exp', '91300'), ('#net', '47700'), ('#cash', '34800'), ('#assets', '103200')]:
        assert page.locator(cell).input_value() == value, cell
    assert any(e['detail'].startswith('Revealed part "Balance Sheet"') for e in result['events'])
    body = result['bodies'][0]                                                   # what the model was shown
    assert len(body['slots']) == 5 and len(body['parts']) == 2 and sum(p['slots'] for p in body['parts']) == 5
    assert 'Prepare an income statement' in body['question'] and 'Prepare the balance sheet' in body['question']
    assert 'Part "Balance Sheet"' in body['question']
    assert len(result['bodies']) == 1                                            # one paid plan across both parts
    assert page.evaluate('tabClicks')[-1] == 'tab-bs' or page.evaluate('tabClicks').count('tab-bs') >= 1


def test_part_whose_controls_are_built_on_click_is_still_revealed(extension):
    page, w, tid = navigate(extension, 'tabs_parts.html?lazy=1')
    assert page.locator('#cash').count() == 0                                    # not in the DOM until the tab is clicked
    result = run(w, tid, VALUES, parts_declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#cash').input_value() == '34800' and page.locator('#assets').input_value() == '103200'


def test_finish_is_refused_when_the_wording_names_more_parts_than_were_revealed(extension):
    """No tab strip on this page, but the model read "Part 2" in the wording: the harness must not finish quietly."""
    page, w, tid = navigate(extension, 'planner_standard.html')
    result = run(w, tid, {}, parts_declared=2)
    assert result['status'] == 'needs_review'
    assert any('PART_UNREACHABLE' in e['detail'] and e['failure_code'] == 'QUESTION_INCOMPLETE' for e in result['events']), result['events'][-2:]


def test_controls_that_appear_after_the_answers_are_planned_in_a_further_round(extension):
    """A part that only shows up once the first answers are in (here: a Dividends box appears after the three income
    lines are filled). The harness notices it before finishing, pays for one more plan covering only the new control,
    enters it, and finishes with everything filled -- instead of declaring victory at the first observe's slots."""
    page, w, tid = navigate(extension, 'tabs_parts.html?sequential=1')
    result = run(w, tid, dict(VALUES, Dividends='0'), parts_declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#div').input_value() == '0'                             # the late control was planned and filled
    assert any('appeared after the planned answers; planning them' in e['detail'] for e in result['events'])
    assert len(result['bodies']) == 2 and [s['label'] for s in result['bodies'][1]['slots']] == ['Dividends']   # second plan: only the new slot
    assert 'Prepare an income statement' in result['bodies'][1]['question']      # with the whole question's text


def test_cells_that_reuse_ids_across_tabs_stay_distinct(extension):
    """The live E1-9 run: each tab's jSheet numbers its cells 0_table0_cell_c1_rN, so Cash (part 2, r4) had the same
    id as Operating Expenses (part 1, r4). Keyed by id alone they merged into one slot and Cash silently vanished
    from the plan. Slot keys now carry the part, so both survive and each gets its own value in its own tab."""
    page, w, tid = navigate(extension, 'tabs_parts.html?dupids=1')
    assert page.locator('#rev').count() == 2                                    # the collision is real in this fixture
    result = run(w, tid, VALUES, parts_declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    shown = result['bodies'][0]['slots']
    assert len(shown) == 5 and len({s['slot_key'] for s in shown}) == 5
    assert sorted(s['label'] for s in shown) == sorted(['Total Revenues', 'Operating Expenses', 'Net Income', 'Cash', 'Total Assets'])
    values = page.evaluate("()=>[...document.querySelectorAll('input')].map(i=>[i.closest('label').textContent.trim().split(' ').slice(0,2).join(' '),i.value])")
    assert dict(values) == {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700', 'Cash': '34800', 'Total Assets': '103200'}



def test_confirmed_sheet_cells_survive_the_tab_being_rebuilt(extension):
    """The live E1-9 failure (8:51 PM, Qwen and Grok alike): cells were identified on tab 1, the harness visited tab 2
    and came back, and the sheet had been rebuilt -- the "editor confirmed" memory was pinned to the old nodes, every
    cell read as unresolved again, and the first keystroke died with GUARD_REJECTED. The memory now hangs on the slot
    key (question + part + cell id), so a rebuilt cell with the same id in the same part is still identified."""
    page, w, tid = navigate(extension, 'tabs_sheet.html')
    node_before = page.evaluate("()=>{window.__c=document.getElementById('0_table0_cell_c1_r3');return true}")
    result = run(w, tid, {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700', 'Cash': '34800', 'Accounts Receivable': '26100', 'Supplies': '42300'}, parts_declared=2)
    assert page.evaluate("()=>document.getElementById('0_table0_cell_c1_r3')!==window.__c")   # the sheet really was rebuilt on return
    assert page.evaluate('builds')['panel-1'] >= 2
    assert result['status'] == 'finished', result['events'][-3:]
    assert not any(e['failure_code'] == 'GUARD_REJECTED' for e in result['events'])
    commits = {(c['panel'], c['id']): c['raw'] for c in page.evaluate('commits')}
    assert commits == {('panel-1', '0_table0_cell_c1_r3'): '139000', ('panel-1', '0_table0_cell_c1_r4'): '91300', ('panel-1', '0_table0_cell_c1_r5'): '47700',
                       ('panel-2', '0_table0_cell_c1_r4'): '34800', ('panel-2', '0_table0_cell_c1_r5'): '26100', ('panel-2', '0_table0_cell_c1_r6'): '42300'}


def test_dropdown_inside_a_part_is_chosen_after_its_owner_is_confirmed(extension):
    """M3-2 live (1:38 PM): the title-row date dropdown opened by geometry, then the owner re-check refused to pick
    -- it rebuilt the owning cell's name without the part while the menu carried the part-qualified name. The
    re-check now reads the cell's recorded slot key. Two parts, each with an unlabelled date-line dropdown and
    three amounts; every one of the eight controls must land in its own tab."""
    page, w, tid = navigate(extension, 'tabs_sheet.html?dateline=1')
    values = {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700', 'Cash': '34800', 'Accounts Receivable': '26100', 'Supplies': '42300'}
    result = w.evaluate('''async ({id,values})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        const tasks=body.observation.slots.map((s,i)=>s.kind==='selection'?{task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label:'For the Month Ended March 31'},depends_on:[]}
          :{task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label.split(' blank')[0].split(' input')[0].replace(/ [\d,$.]+$/,'')]??'1'},depends_on:[]});
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:2}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null}))};}''', {'id': tid, 'values': values})
    assert result['status'] == 'finished', result['events'][-3:]
    assert not any(e['failure_code'] == 'WRONG_MENU_OWNER' for e in result['events'])
    commits = {(c['panel'], c['id']): c['raw'] for c in page.evaluate('commits')}
    assert commits[('panel-1', '0_table0_cell_c0_r2')] == 'For the Month Ended March 31' and commits[('panel-2', '0_table0_cell_c0_r2')] == 'For the Month Ended March 31'
    assert len(commits) == 8
