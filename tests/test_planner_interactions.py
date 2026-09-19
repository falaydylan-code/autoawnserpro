"""Classify by evidence; execute shared editors with real CDP input, no model fees."""
import pytest
from test_extension_coverage import extension
from test_ordering_visual import navigate
from test_planner_executor import BOOT


def test_decorative_noninteractive_canvas_is_not_classified_as_a_graph(extension):
    # Live Khan Academy failure: a plain MCQ with an inert, pointer-events:none celebration canvas
    # mounted inline in the content. The old bare-tag match ('canvas' alone) turned it into a fake
    # 'position' slot, which the runtime then tried to visually measure before any plan existed,
    # dying on GUARD_REJECTED / 'An overlay blocks the exact target' at zero cost, zero model calls.
    page,w,tid=navigate(extension,'planner_decorative_graphic.html')
    obs=w.evaluate(BOOT,tid)
    assert [s['kind'] for s in obs['slots']]==['choice']
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',[e.get('detail') for e in result['events']]
    assert page.locator('#optB').get_attribute('aria-checked')=='true'
    calls=w.evaluate('calls')
    assert all(c['phase']!='visual' for c in calls)  # never tried to visually measure the canvas


def test_real_overlay_still_refused_and_now_reports_what_was_hit(extension):
    # A genuine occlusion (unlike the decorative canvas above) must still refuse the click -- and the
    # guard's diagnostic data, captured but previously discarded at the top-level catch, now reaches
    # the run's event log instead of leaving 'An overlay blocks the exact target' unexplained.
    page,w,tid=navigate(extension,'planner_overlay_blocked.html')
    w.evaluate(BOOT,tid)
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='needs_review'
    failure=next(e for e in result['events'] if e.get('failure_code'))
    assert failure['failure_code']=='GUARD_REJECTED'
    assert failure['failure_data']['hit_info']['id']=='blocker'
    assert failure['failure_data']['target_info']['id']=='optB'


@pytest.mark.parametrize('framed', [False, True])
def test_mixed_sheet_dropdown_and_native_fields_one_plan(extension, framed):
    page,w,tid=navigate(extension,'spreadsheet_text.html')
    if framed:
        page.goto(page.url.replace('spreadsheet_text.html','planner_standard.html'))
        page.evaluate("()=>document.body.innerHTML='<iframe src=spreadsheet_text.html style=\"margin:25px;width:1100px;height:850px\"></iframe>'")
        frame=page.frame_locator('iframe');frame.locator('#ordinary').wait_for()
    else: frame=page
    frame.locator('body').evaluate('e=>e.ownerDocument.defaultView.editorDelay=120')
    initial=w.evaluate(BOOT,tid)
    assert len(initial['slots'])==12
    assert [s['kind'] for s in initial['slots']].count('unresolved')==9
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-4:]
    assert frame.locator('td.response').all_text_contents()==['42']*9
    assert frame.locator('#contained input').input_value()=='42'
    assert frame.locator('#ordinary').input_value()=='42'
    assert frame.locator('#category span').inner_text()=='Asset'
    assert len(frame.locator('body').evaluate('e=>e.ownerDocument.defaultView.entries'))==9
    plans=[c for c in w.evaluate('calls') if c['phase']=='plan']
    assert len(plans)==1
    slots=plans[0]['body']['observation']['slots']
    assert len(slots)==12 and [s['kind'] for s in slots].count('value')==11
    assert {s['slot_key'] for s in slots}=={s['slot_key'] for s in initial['slots']}
    assert next(s for s in slots if s['dom_id']=='category')['kind']=='selection'
    assert all(s['current']=='' for s in slots)  # discovery never enters answers
    assert len(result['questions'])==1
    assert len(next(iter(result['questions'].values()))['completed'])==12


def test_empty_generic_cell_is_not_assumed_text(extension):
    page,w,tid=navigate(extension,'spreadsheet_text.html')
    page.evaluate("()=>document.querySelector('main').innerHTML='<h1>Unknown widget</h1><table><tr><td id=unknown class=responseCell tabindex=0 aria-label=Answer></td></tr></table>'")
    initial=w.evaluate(BOOT,tid)
    assert initial['slots'][0]['kind']=='unresolved'
    result=w.evaluate('''async()=>{const obs=await engine.observe();engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};
      const fresh=await engine.resolveInteractions(obs);try{await engine.execute({slot_key:fresh.slots[0].slot_key,operation:'enter_value',desired:{value:'42'}})}catch(e){return {kind:fresh.slots[0].kind,code:e.code,events:engine.ledger.events}}}''')
    assert result['kind']=='unresolved' and result['code']=='GUARD_REJECTED'
    assert len([e for e in result['events'] if e.get('action_executed')])==1
    assert page.locator('#unknown').inner_text()==''


@pytest.mark.parametrize('mode', ['duplicate', 'wrong_cell', 'stop'])
def test_floating_editor_ownership_and_stop_before_typing(extension, mode):
    page,w,tid=navigate(extension,'spreadsheet_text.html');initial=w.evaluate(BOOT,tid)
    w.evaluate('''async()=>{const obs=await engine.observe();engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};await engine.resolveInteractions(obs)}''')
    page.evaluate('''mode=>{const cell=document.getElementById('value-0-0');cell.addEventListener('dblclick',()=>setTimeout(()=>{
      const editor=document.querySelector('.jSheetInPlaceEdit');
      if(mode==='duplicate')editor.after(editor.cloneNode(true));
      if(mode==='wrong_cell'){cell.classList.remove('jSheetCellActive');document.getElementById('value-0-1').classList.add('jSheetCellActive')}
    },0))}''',mode)
    result=w.evaluate('''async mode=>{if(mode==='stop'){const click=AssignmentVisual.click;AssignmentVisual.click=async(...a)=>{const r=await click(...a);engine.stop();return r}}
      const obs=await engine.observe(),s=obs.slots[0];try{await engine.execute({task_id:'test',slot_key:s.slot_key,operation:'enter_value',desired:{value:'42'}});return {ok:true}}catch(e){return {code:e.code}}}''',mode)
    assert result.get('code') in ('GUARD_REJECTED','TARGET_MISSING','TARGET_STALE','CANCELLED'),result
    assert page.evaluate('entries')==[]
    assert page.locator('td.response').all_text_contents()==['']*9


def test_generic_cell_waits_for_positive_dropdown_evidence(extension):
    page,w,tid=navigate(extension,'spreadsheet_text.html')
    page.evaluate('''()=>{document.querySelectorAll('td.response').forEach(c=>c.closest('tr').remove());document.getElementById('contained').closest('tr').remove();document.getElementById('ordinary').remove();
      category.classList.remove('dropDownList');const old=category.onclick;category.onclick=()=>setTimeout(old,150)}''')
    initial=w.evaluate(BOOT,tid)
    assert len(initial['slots'])==1 and initial['slots'][0]['kind']=='unresolved'
    result=w.evaluate('()=>engine.run()')
    assert result['status']=='finished',result['events'][-3:]
    assert page.locator('#category span').inner_text()=='Asset'
    slot=next(c for c in w.evaluate('calls') if c['phase']=='plan')['body']['observation']['slots'][0]
    assert slot['kind']=='selection' and slot['slot_key']==initial['slots'][0]['slot_key']


def test_same_sheet_nodes_on_new_question_require_new_evidence(extension):
    page,w,tid=navigate(extension,'spreadsheet_text.html');w.evaluate(BOOT,tid)
    old=w.evaluate('''async()=>{const obs=await engine.observe();engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};return engine.resolveInteractions(obs)}''')
    assert sum(s['kind']=='value' for s in old['slots'])==11
    page.locator('h1').evaluate("e=>e.textContent='A different question using the same cells'")
    new=w.evaluate('()=>engine.observe()')
    assert new['question_key']!=old['question_key']
    assert sum(s['kind']=='unresolved' for s in new['slots'])==9


def test_cancelled_identification_keeps_action_budget_on_resume(extension):
    page,w,tid=navigate(extension,'spreadsheet_text.html');w.evaluate(BOOT,tid)
    result=w.evaluate('''async()=>{const obs=await engine.observe();engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};
      const click=AssignmentVisual.click;AssignmentVisual.click=async(...a)=>{const r=await click(...a);engine.stop();return r};
      let code;try{await engine.resolveInteractions(obs)}catch(e){code=e.code}AssignmentVisual.click=click;
      const actions=JSON.parse(JSON.stringify(engine.current.interactionActions));
      const resumed=new AssignmentPlanner.Engine(engine.b,engine.tabId,engine.config);resumed.current={key:obs.question_key,document:obs.document_id,interactionActions:JSON.parse(JSON.stringify(actions)),recovery:new AssignmentPlanner.Recovery()};
      await resumed.resolveInteractions(await resumed.observe());return {code,actions,events:resumed.ledger.events};}''')
    assert result['code']=='CANCELLED'
    assert next(iter(result['actions'].values()))=={'activate':True}
    clicks=[e['click_details'] for e in result['events'] if e.get('click_details')]
    assert clicks[0]['purpose']=='identify_editor'  # no replay of the first activation
    assert page.evaluate('entries')==[]
