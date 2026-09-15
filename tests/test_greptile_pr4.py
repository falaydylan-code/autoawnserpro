"""Greptile's four findings on the 0.7.1 upload, each driven through the loaded
extension, plus the two-witness verification rule Dylan asked for.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


# --------------------------------------------------------------------------
# 1. a gesture must die when the page navigates under it
# --------------------------------------------------------------------------

def test_a_gesture_is_abandoned_when_the_tab_navigates_mid_drag(extension):
    page, w, tid = navigate(extension, 'ordering.html')
    before = page.locator('li').all_text_contents()
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Order',parts:[{id:'o',what:'Order',kind:'ordering',answer:'ordered',ref:ref('order'),order:['revenue','expense','net'].map(ref),sequence:['Revenues','Expenses','Net Income']}]},p);
      // after the fourth mouse move, the tab reports a different document
      const realGet=chrome.tabs.get,realSend=chrome.debugger.sendCommand;let moves=0,swapped=false;
      chrome.debugger.sendCommand=async (t,m,params)=>{if(params?.type==='mouseMoved'&&++moves===4)swapped=true;return realSend(t,m,params);};
      chrome.tabs.get=async (i)=>{const t=await realGet(i);return swapped?{...t,url:t.url.replace('ordering','elsewhere')}:t;};
      try{return await h.executeAction(id,{action:'reorder',ref:ref('net'),to:ref('expense'),placement:'after',part_id:'o'},p,{});}
      catch(e){return {threw:e.message};}finally{chrome.tabs.get=realGet;chrome.debugger.sendCommand=realSend;}}''', tid)
    assert 'threw' in result and 'navigated' in result['threw'], result
    assert page.locator('li').all_text_contents() == before, 'nothing moved on the page that was left'


# --------------------------------------------------------------------------
# 2. a visual point must hit the part's own control
# --------------------------------------------------------------------------

def test_a_visual_click_aimed_at_a_different_cell_is_refused_and_names_the_planned_one(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const planned=p.elements.find(e=>e.key.endsWith('#cell_0_0')),other=p.elements.find(e=>e.key.endsWith('#cell_5_1'));
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Accounts Payable Account Type',answer:'Liability',ref:planned.ref}]},p);
      const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);const v=snap.viewport;
      const at=b=>({x:(b.x+b.w/2)/v.width,y:(b.y+b.h/2)/v.height});
      const wrong=await h.executeAction(id,{action:'visual_click',purpose:'open',part_id:'a',observation_id:snap.id,point:at(other.box)},p,{});
      const snap2=await h.makeSnapshot(id,await h.observeAllFrames(id));h.setSnapshot(snap2);
      const right=await h.executeAction(id,{action:'visual_click',purpose:'open',part_id:'a',observation_id:snap2.id,point:at(planned.box)},await h.observeAllFrames(id),{});
      return {wrong,right,plannedRef:planned.ref};}''', tid)
    assert result['wrong']['ok'] is False and f"ref {result['plannedRef']}" in result['wrong']['detail'], result['wrong']
    assert page.locator('#cell_5_1').inner_text() == '', 'the other cell was never touched'
    assert result['right']['ok'], result['right']


# --------------------------------------------------------------------------
# 3. a finished question never absorbs the next one
# --------------------------------------------------------------------------

def test_a_page_that_reuses_one_input_across_questions_gets_a_new_question_each_time(extension):
    """MathPapa's shape. Question 1 is answered and verified in #balance; question 2
    arrives with a different stem and the same input. It must not merge into
    question 1 -- that adopted the old part and tripped the plan-change guard."""
    page, w, tid = navigate(extension, 'mcq_buttons.html')
    # MathPapa does not name its questions; the same input simply gets reused
    page.evaluate('for(const f of document.querySelectorAll("[data-question-id]"))f.removeAttribute("data-question-id")')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;let p=await h.observeAllFrames(id);
      const ref=()=>p.elements.find(e=>e.key.endsWith('#balance')).ref;
      h.coverage.read({question:'Question 8. Enter the closing balance.',parts:[{id:'q8',what:'closing balance',answer:'900',ref:ref()}]},p);
      await h.executeAction(id,{action:'fill',ref:ref(),text:'900',part_id:'q8'},p,{});
      p=await h.observeAllFrames(id);await h.refreshEvidence(id,p);
      const q1Verified=h.coverage.ledger()[0].verified;
      try{h.coverage.read({question:'Question 9. Enter the opening balance.',parts:[{id:'q9',what:'opening balance',answer:'450',ref:ref()}]},p);}
      catch(e){return {threw:e.message};}
      return {q1Verified,questions:h.coverage.questions.size,current:h.coverage.ledger()};}''', tid)
    assert 'threw' not in result, result
    assert result['q1Verified'] is True
    assert result['questions'] == 2, 'a finished question and a new stem is a new question'
    assert result['current'][0]['answer'] == '450'


def test_a_page_that_names_its_questions_is_believed_over_the_controls(extension):
    """Two questions sharing every control but carrying different
    data-question-id values are two questions, unfinished or not."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    page.evaluate('document.querySelector("table").setAttribute("data-question-id","q-one")')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;let p=await h.observeAllFrames(id);
      const cell=()=>p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref;
      h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'AP type',answer:'Liability',ref:cell()}]},p);return null;}''', tid)
    page.evaluate('document.querySelector("table").setAttribute("data-question-id","q-two")')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;const p=await h.observeAllFrames(id);
      const cell=p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref;
      try{h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'AP type',answer:'Asset',ref:cell}]},p);}catch(e){return {threw:e.message};}
      return {questions:h.coverage.questions.size};}''', tid)
    assert 'threw' not in result, result
    assert result['questions'] == 2


# --------------------------------------------------------------------------
# 4. only evidenced widgets are answer controls
# --------------------------------------------------------------------------

def test_decorative_custom_elements_are_not_listed_and_do_not_block_hand_in(extension):
    page, w, tid = navigate(extension, 'closed_dropdown.html')
    # a component-built page: header shell, icon, footer, all closed-shadow
    page.evaluate('''()=>{
      for(const [tag,where] of [['app-header','afterbegin'],['ui-icon','afterbegin'],['site-footer','beforeend']]){
        if(!customElements.get(tag))customElements.define(tag,class extends HTMLElement{constructor(){super();this.attachShadow({mode:'closed'}).innerHTML='<div style="height:40px;width:600px">shell</div>';}});
        document.body.insertAdjacentHTML(where,'<'+tag+'></'+tag+'>');
      }}''')
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    widgets = [e for e in observed['elements'] if e['role'] == 'widget']
    assert len(widgets) == 1 and widgets[0]['key'].endswith('ANSWER-BOX') or widgets[0]['name'] == '' , widgets
    assert all(not e['key'].lower().endswith(t) for e in widgets for t in ('app-header', 'ui-icon', 'site-footer'))
    # and the shell elements never count as unplanned answers
    gate = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),wd=p.elements.find(e=>e.role==='widget');
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Type',answer:'Liability',ref:wd.ref}]},p);
      const part=h.coverage.current.parts.get('a');part.domVerified=null;part.visualConfirmed=true;h.settle(part);
      // no terminal control on this fixture; ask the gate directly with a fake one
      const fake={ref:9999,control:'terminal',key:'fake'};return h.coverage.gate({action:'click',ref:9999},{...p,elements:[...p.elements,fake]},{auto_submit:true});}''', tid)
    assert gate == '', gate


# --------------------------------------------------------------------------
# two witnesses: DOM read-back and a screenshot, both, when switched on
# --------------------------------------------------------------------------

def test_with_double_check_on_a_dom_verified_answer_waits_for_the_screenshot(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;h.setDoubleCheck(true);let p=await h.observeAllFrames(id);
      const cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'AP type',answer:'Liability',ref:cell.ref}]},p);
      await h.executeAction(id,{action:'click',ref:cell.ref,part_id:'a',purpose:'open'},p,{});
      p=await h.observeAllFrames(id);const option=p.elements.find(e=>e.role==='option'&&e.name==='Liability');
      await h.executeAction(id,{action:'click',ref:option.ref,part_id:'a',purpose:'answer'},p,{});
      p=await h.observeAllFrames(id);await h.refreshEvidence(id,p);
      const part=h.coverage.current.parts.get('a');
      const afterDom={domVerified:part.domVerified,verified:part.verified};
      part.visualConfirmed=true;h.settle(part);const afterBoth=part.verified;
      part.domVerified=false;h.settle(part);const domSaysNo=part.verified;
      h.setDoubleCheck(false);return {afterDom,afterBoth,domSaysNo};}''', tid)
    assert page.locator('#cell_0_0').inner_text() == 'Liability'
    assert result['afterDom'] == {'domVerified': True, 'verified': False}, 'DOM alone is not enough with double-check on'
    assert result['afterBoth'] is True, 'DOM and screenshot together verify'
    assert result['domSaysNo'] is False, 'a DOM no always wins, whatever the screenshot said'


def test_with_double_check_off_the_dom_alone_verifies(extension):
    page, w, tid = navigate(extension, 'mcq_buttons.html')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;h.setDoubleCheck(false);let p=await h.observeAllFrames(id);
      const opt=p.elements.find(e=>e.key.endsWith('#optC'));
      h.coverage.read({question:'Which account',parts:[{id:'a',what:'option',answer:'Deferred Revenue',ref:opt.ref}]},p);
      await h.executeAction(id,{action:'click',ref:opt.ref,part_id:'a'},p,{});
      await h.refreshEvidence(id,await h.observeAllFrames(id));return h.coverage.ledger()[0].verified;}''', tid)
    assert result is True


# --------------------------------------------------------------------------
# one revision of a committed answer is taken; the second is the oscillation
# --------------------------------------------------------------------------

def test_a_change_of_an_entered_answer_is_taken_once_then_refused(extension):
    """Once a field has been entered, the first change of its answer is taken and
    reported (the field is reset to re-enter); a second change is the flip-flop
    the guard stops. Before entry, changes are free (see test_smoke_findings)."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    result = w.evaluate("""async id=>{const h=__assignmentHarness;let p=await h.observeAllFrames(id);
      const cellRef=()=>p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref;
      h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'AP type',answer:'Liability',ref:cellRef()}]},p);
      await h.executeAction(id,{action:'click',ref:cellRef(),part_id:'a',purpose:'open'},p,{});
      p=await h.observeAllFrames(id);const opt=p.elements.find(e=>e.role==='option'&&e.name==='Liability');
      await h.executeAction(id,{action:'click',ref:opt.ref,part_id:'a',purpose:'answer'},p,{});
      p=await h.observeAllFrames(id);await h.refreshEvidence(id,p);
      const entered=h.coverage.ledger()[0].entered;
      const read=answer=>h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'AP type',answer,ref:p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref}]},p);
      read('Asset');const first={revised:[...h.coverage.revised],answer:h.coverage.ledger()[0].answer,entered:h.coverage.ledger()[0].entered};
      try{read('Revenue');return {entered,first,second:'accepted'};}catch(e){return {entered,first,second:e.message};}}""", tid)
    assert result['entered'] is True
    assert result['first']['revised'] and 'Liability' in result['first']['revised'][0]
    assert result['first']['answer'] == 'Asset' and result['first']['entered'] is False, 'first change taken, part reset'
    assert 'Plan changed again' in result['second'], 'the second is refused'
