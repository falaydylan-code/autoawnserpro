"""Numeric spreadsheet entry, proven against a fixture that behaves like the live McGraw jSheet
(`sheet_numeric.html`): the in-place editor swallows select-all, reformats committed amounts
($ and thousands commas), and discards the edit on Escape.

The 6:28 PM live run (E1-9, MiniMax): the plan was right ($139,000 / $91,300 / $47,700) and every
click hit its cell, yet the run died on Operating Expenses. Two harness bugs compounded:
  - the readback "91,300" was compared as a string to "$91,300" -> VALUE_MISMATCH;
  - the retry's Ctrl+A did not clear the editor, so typing appended: "91300"+"91300" -> "9,130,091,300",
    and the harness committed it blind.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def plan(w, tid, values):
    """Boot an engine whose scripted plan enters `values` (by cell label) as the model spelled them."""
    return w.evaluate('''async ({id,values})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        const tasks=body.observation.slots.filter(s=>values[s.label.split(' blank')[0].split(' input')[0].replace(/ [\\d,$.]+$/,'')]!==undefined)
          .map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label.split(' blank')[0].split(' input')[0].replace(/ [\\d,$.]+$/,'')]},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());return engine.run();}''', {'id': tid, 'values': values})


def test_amount_typed_as_the_model_spelled_it_verifies_against_the_formatted_cell(extension):
    """"$91,300" planned; digits typed; the page shows "91,300" (no $ on that row) and "$139,000" (styleNumber row);
    both verify because amounts are compared as numbers, not strings."""
    page, w, tid = navigate(extension, 'sheet_numeric.html')
    result = plan(w, tid, {'Total Revenues': '$139,000', 'Operating Expenses': '$91,300', 'Net Income': '$47,700'})
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#rev').inner_text() == '$139,000' and page.locator('#exp').inner_text() == '91,300' and page.locator('#net').inner_text() == '47,700'
    assert [c['raw'] for c in page.evaluate('commits')] == ['139000', '91300', '47700']   # digits only reached the number cells
    assert not any(e.get('failure_code') == 'VALUE_MISMATCH' for e in result['events'])


def test_existing_text_is_cleared_key_by_key_when_select_all_is_swallowed(extension):
    """A cell already holding 91,300 gets a new amount. The editor ignores Ctrl+A (as the live widget did), so the
    harness deletes the old text key by key before typing: 47,700 -- never 9,130,047,700."""
    page, w, tid = navigate(extension, 'sheet_numeric.html')
    page.evaluate("()=>{document.getElementById('exp').textContent='91,300'}")
    result = plan(w, tid, {'Total Revenues': '139000', 'Operating Expenses': '47700', 'Net Income': '91300'})
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#exp').inner_text() == '47,700'
    assert [c['raw'] for c in page.evaluate('commits')] == ['139000', '47700', '91300']
    assert any('Cleared existing text key by key' in e['detail'] for e in result['events'])


def test_nothing_is_committed_when_the_editor_does_not_hold_the_planned_value(extension):
    """A widget that drops keystrokes: the editor ends up with the wrong text. The harness must NOT press Tab on it;
    it cancels with Escape and reports INPUT_NO_EFFECT with both values, leaving the cell exactly as it was."""
    page, w, tid = navigate(extension, 'sheet_numeric.html')
    page.evaluate("()=>{window.mangle=true;document.getElementById('exp').textContent='91,300'}")
    result = plan(w, tid, {'Total Revenues': '139000', 'Operating Expenses': '47700', 'Net Income': '91300'})
    assert result['status'] != 'finished'
    assert page.locator('#exp').inner_text() == '91,300' and page.locator('#rev').inner_text() == ''   # untouched
    assert page.evaluate('commits') == []                          # nothing was committed
    assert any(e.get('failure_code') == 'INPUT_NO_EFFECT' for e in result['events'])
    assert any('nothing committed' in e['detail'] for e in result['events']), [e['detail'] for e in result['events'][-4:]]


def test_amounts_compare_as_numbers_only_when_both_sides_are_amounts(extension):
    page, w, tid = navigate(extension, 'sheet_numeric.html')
    cases = w.evaluate('''()=>{const P=AssignmentPlanner;return [
      P.sameValue('$91,300','91300'), P.sameValue('91,300','$91,300'), P.sameValue('(1,200)','-1200'), P.sameValue('47,700.00','47700'),
      P.sameValue('12 %','12'), P.sameValue('91,300','9,130,091,300'), P.sameValue('','0'), P.sameValue('Cash','cash'), P.sameValue('Cash','Cash'),
      P.plainDigits('$91,300'), P.plainDigits('(1,200)'), P.plainDigits('Cash'), P.numeric('abc'), P.numeric('1,2,3')]}''')
    assert cases == [True, True, True, True, True, False, False, False, True, '91300', '-1200', 'Cash', None, 123]


def test_a_cell_that_stays_locked_is_left_out_of_the_plan_and_named_at_the_finish(extension):
    """M3-9 (2:19 PM): two amount cells could not be clicked -- the harness read them as unresolved, correctly -- but the
    rules then made the question unplannable (a plan had to cover every slot, and never an unresolved one). Now a
    still-unresolved slot is not required; the run finishes and says which locations stayed locked."""
    page, w, tid = navigate(extension, 'sheet_numeric.html?locked=forever')
    result = w.evaluate('''async ({id,values})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const tasks=body.observation.slots.filter(s=>s.kind!=='unresolved').map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label.split(' blank')[0].split(' input')[0].replace(/ [\d,$.]+$/,'')]??'1'},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,not_answerable:e.not_answerable||null})),bodies:globalThis.planBodies};}''',
      {'id': tid, 'values': {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700'}})
    assert result['status'] == 'finished', result['events'][-3:]
    shown = result['bodies'][0]['slots']
    assert [s['kind'] for s in shown if 'Retained' in s['label']] == ['unresolved']          # the model still sees it, marked
    finish = next(e for e in result['events'] if e['phase'] == 'FINISH')
    assert finish['not_answerable'] == ['Retained Earnings'] and 'stayed locked' in finish['detail']
    assert [c['raw'] for c in page.evaluate('commits')] == ['139000', '91300', '47700']
    assert page.locator('#ret').inner_text() == ''


def test_a_cell_that_unlocks_after_another_answer_is_planned_in_the_next_round(extension):
    """Statement builders unlock an amount cell once its row is set up. The post-batch re-check identifies the newly
    unlocked cell (fresh identification budget) and a further plan round fills it -- one extra paid plan, no restart."""
    page, w, tid = navigate(extension, 'sheet_numeric.html?locked=until_revenue')
    result = w.evaluate('''async ({id,values})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const tasks=body.observation.slots.filter(s=>s.kind!=='unresolved').map((s,i)=>({task_id:'r'+globalThis.planBodies.length+'_'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label.split(' blank')[0].split(' input')[0].replace(/ [\d,$.]+$/,'')]??'1'},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,not_answerable:e.not_answerable||null})),bodies:globalThis.planBodies};}''',
      {'id': tid, 'values': {'Total Revenues': '139000', 'Operating Expenses': '91300', 'Net Income': '47700', 'Retained Earnings': '52000'}})
    assert result['status'] == 'finished', result['events'][-3:]
    assert len(result['bodies']) == 2 and [s['label'].split(' blank')[0] for s in result['bodies'][1]['slots']] == ['Retained Earnings']   # second plan: only the unlocked cell
    assert page.locator('#ret').inner_text() == '52,000'
    finish = next(e for e in result['events'] if e['phase'] == 'FINISH')
    assert finish['not_answerable'] is None and 'stayed locked' not in finish['detail']


def test_a_slow_first_click_does_not_starve_identification_and_is_reported_once(extension):
    """M3-9 5:11 PM: from one moment on, every click took ~5 s to be accepted. The identification loop counted that
    against its own 5 s window, so the typeable cell never got its double-click, the dropdowns never got their arrow
    click, no progress was made for 90 s, and the run stopped before any plan request -- with nothing in the log
    saying the clicks were slow. Now the window starts after the click returns, and the slowness is named once."""
    page, w, tid = navigate(extension, 'sheet_numeric.html?slow=5200')
    result = plan(w, tid, {'Total Revenues': '$139,000', 'Operating Expenses': '$91,300', 'Net Income': '$47,700'})
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#rev').inner_text() == '$139,000' and page.locator('#exp').inner_text() == '91,300' and page.locator('#net').inner_text() == '47,700'
    clicks = [e for e in result['events'] if e.get('click_details')]
    assert clicks[0]['click_details']['timing']['input_ms'] >= 5000, clicks[0]['click_details']['timing']   # the held click is measured
    assert all(isinstance(c['click_details']['timing']['dom_ms'], int) for c in clicks)
    assert [e['detail'] for e in result['events'] if e['detail'] == 'Answer interaction remains unresolved'] == []   # the double-click still happened
    slow = [e for e in result['events'] if e.get('slow_input')]
    assert len(slow) == 1 and slow[0]['input_ms'] >= 5000 and 'Browser input is slow' in slow[0]['detail'], slow
    assert 'FINISH' in [e['phase'] for e in result['events']]


def test_a_planned_empty_amount_clears_a_filled_cell_and_skips_an_empty_one(extension):
 """Grok also sent enter_value "" for the amount cell of a spare row. A filled cell is cleared and committed empty;
 an empty one already matches and is skipped."""
 page,w,tid=navigate(extension,'sheet_numeric.html')
 page.evaluate("()=>{const c=document.getElementById('exp');c.dispatchEvent(new Event('dblclick'));const e=document.querySelector('.jSheetInPlaceEdit');e.value='91300';e.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab'}))}")
 assert page.locator('#exp').inner_text()=='91,300'
 result=plan(w,tid,{'Total Revenues':'$139,000','Operating Expenses':'','Net Income':'$47,700'})
 assert result['status']=='finished',result['events'][-3:]
 assert page.locator('#exp').inner_text()=='' and page.locator('#rev').inner_text()=='$139,000'
 assert [c['raw'] for c in page.evaluate('commits')][-3:]==['139000','','47700'] or [c['raw'] for c in page.evaluate('commits')][-2:]==['139000','47700'] and '' in [c['raw'] for c in page.evaluate('commits')]
 clicks=[e for e in result['events'] if e.get('click_details',{}).get('slot_key','').endswith('exp') and e['click_details'].get('purpose')=='focus_text']
 assert clicks, 'the filled cell was opened to be cleared'
 result=plan(w,tid,{'Total Revenues':'$139,000','Operating Expenses':'','Net Income':'$47,700'})
 assert result['status']=='finished' and page.locator('#exp').inner_text()==''
 assert not any(e.get('click_details',{}).get('slot_key','').endswith('exp') for e in result['events'])   # already empty: no click
