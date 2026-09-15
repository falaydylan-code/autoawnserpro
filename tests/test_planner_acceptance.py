"""SOP section 17 acceptance cases proven directly against the loaded extension.

The executor suite already exercises radios, checkbox sets, twenty dropdowns,
reused menu nodes, frames, ordering, graphs, enumeration-gated submission,
cancellation and resume. Two named cases lived only in the code, not a test:

  - a *disabled* desired option must be refused, not silently skipped;
  - a focus annotation such as "[active]" in a cell's readback must not defeat
    verification.

Both run through the real Engine with a scripted provider, no model calls.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def boot(worker, tid, label):
    """Attach input and script a one-task plan that selects `label` in the cell."""
    return worker.evaluate('''async ({id,label})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.calls=[];
      bridge.request=async(phase,body)=>{globalThis.calls.push(phase);
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        return {cost:.001,response:{kind:'plan',
        question_key:body.observation.question_key,observation_id:body.observation.observation_id,
        tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());await engine.observe();return true;}''',
      {'id': tid, 'label': label})


def test_focus_annotation_in_readback_still_verifies(extension):
    """The cell shows "Asset [active]" once chosen; verification reads past the
    marker and confirms the answer rather than treating it as a mismatch."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    boot(w, tid, 'Asset')
    result = w.evaluate('()=>engine.run()')
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#cell').get_attribute('data-value') == 'Asset'
    assert '[active]' in page.locator('.dropdownValue').inner_text()   # the annotation really was present
    q = next(iter(result['questions'].values()))
    assert q['completed'] and all(p['entry_verified'] for p in q['completed'].values())
    assert w.evaluate('calls').count('plan') == 1


def test_disabled_desired_option_is_refused(extension):
    """Planning the disabled "Liability" option stops with GUARD_REJECTED and
    leaves the cell unanswered, instead of choosing a disabled control."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    boot(w, tid, 'Liability')
    result = w.evaluate('()=>engine.run()')
    assert result['status'] == 'needs_review'
    assert result['events'][-1]['failure_code'] == 'GUARD_REJECTED', result['events'][-1]
    assert (page.locator('#cell').get_attribute('data-value') or '') == ''


# ── Greptile PR #7 findings, locked as regressions ──────────────────────────

def test_dropdown_ownership_via_activation_without_aria_link(extension):
    """Finding 4: a custom menu with NO aria-labelledby/aria-controls is still
    answered — ownership falls back to the one cell marked aria-expanded by the
    activation the runtime just performed, instead of WRONG_MENU_OWNER."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    # strip the ARIA link the fixture would otherwise provide, leaving only the
    # cell's aria-expanded activation evidence
    page.evaluate("()=>{const orig=openMenu;window.openMenu=c=>{orig(c);document.querySelector('ul')?.removeAttribute('aria-labelledby')}}")
    boot(w, tid, 'Asset')
    result = w.evaluate('()=>engine.run()')
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#cell').get_attribute('data-value') == 'Asset'


def test_dynamic_answer_state_text_does_not_change_identity(extension):
    """Finding 3: a "completed / attempt / saved" annotation appearing after the
    answer must NOT fork the question key (which would abandon the verified
    answer as TARGET_STALE). Tested with a platform id, and without one."""
    page, w, tid = navigate(extension, 'planner_standard.html')
    key = 'async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});return (await e.observe()).question_key}'
    before = w.evaluate(key, tid)
    page.evaluate("()=>{const d=document.createElement('div');d.className='feedback';d.setAttribute('aria-live','polite');d.textContent='Completed — Attempt 2 of 3 — Saved';document.querySelector('main').append(d)}")
    assert w.evaluate(key, tid) == before, 'platform-id identity drifted under dynamic answer-state text'
    # now with no platform id: identity leans on stable control structure + a
    # feedback-stripped stem, and the same annotation must not change it either
    page.evaluate("()=>document.querySelector('main').removeAttribute('data-question-id')")
    no_id = w.evaluate(key, tid)
    page.evaluate("()=>{const d=document.createElement('div');d.className='result';d.textContent='Correct! Attempt 3 of 3';document.querySelector('main').append(d)}")
    assert w.evaluate(key, tid) == no_id, 'no-platform identity drifted under dynamic answer-state text'


def test_ambiguous_duplicate_frames_do_not_abort_a_readable_question(extension):
    """Finding 2: two iframes sharing one src (or an unrelated widget) used to
    abort the whole observation with FRAME_UNREADABLE. They are now excluded,
    and the readable question still runs to completion."""
    from test_planner_executor import BOOT
    page, w, tid, _, origin = extension
    page.goto(origin + '/planner_standard.html')
    w.evaluate('(id)=>__assignmentHarness.injectAll(id)', tid)
    page.evaluate("url=>{for(let i=0;i<2;i++){const f=document.createElement('iframe');f.src=url;f.style='width:120px;height:60px';document.querySelector('main').append(f)}}", origin + '/ordering.html')
    page.wait_for_timeout(300)
    w.evaluate(BOOT, tid)
    result = w.evaluate('()=>engine.run()')
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#amount').input_value() == '42'


def test_model_authored_page_script_extraction_feeds_the_plan(extension):
    """The 'run a page script' reach, like Claude-in-Chrome: the plan first asks
    to run a read-only JS extraction; the harness runs it in the page through the
    debugger, feeds the JSON result back as evidence, and the model then plans and
    finishes. Proves the model can reach into the DOM to measure/enumerate."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.calls=[];globalThis.evidenceSeen=null;let planned=false;
      bridge.request=async(phase,body)=>{globalThis.calls.push(phase);
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        if(!planned){planned=true;return {cost:.001,response:{kind:'request_inspection',
          question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          inspection:{question:'How many answer cells are there?',script:'return document.querySelectorAll("td.responseCell").length'}}};}
        globalThis.evidenceSeen=body.observation.evidence;
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',
            desired:{label:s.label.includes('Statement')?'Balance Sheet':'Asset'},depends_on:[]}))}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());return engine.run();}''', tid)
    assert result['status'] == 'finished', result['events'][-3:]
    ev = w.evaluate('evidenceSeen')
    assert ev and any(e.get('operation') == 'script' and e.get('result') == 20 for e in ev), ev
    assert page.locator('td[data-value]').count() == 20


def test_extraction_script_read_only_boundary(extension):
    """The page-script channel enforces read-only in code: network, storage,
    navigation, submission, and DOM-mutation scripts are refused before they run;
    a plain read returns its value and the page is untouched."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    out = w.evaluate('''async id=>{await AssignmentVisual.attach(id);
      return {
        cookie:await AssignmentVisual.evaluate(id,'return document.cookie'),
        net:await AssignmentVisual.evaluate(id,'return fetch("/x")'),
        mutate:await AssignmentVisual.evaluate(id,'document.querySelector("td").textContent="HACKED";return 1'),
        submit:await AssignmentVisual.evaluate(id,'return document.querySelector("input").click()'),
        read:await AssignmentVisual.evaluate(id,'return document.querySelectorAll("td.responseCell").length')};}''', tid)
    assert out['cookie']['ok'] is False and 'read-only' in out['cookie']['detail']
    assert out['net']['ok'] is False and out['mutate']['ok'] is False and out['submit']['ok'] is False
    assert out['read']['ok'] and out['read']['value'] == 20
    assert page.locator('td').first.inner_text() == 'Accounts Payable'   # the refused mutation never ran


def test_second_witness_screenshot_rejects_then_reenters(extension):
    """The confirming screenshot has teeth: when it reports an answer isn't
    visible, the harness drops that answer and re-enters it before finishing,
    instead of trusting the DOM readback alone."""
    from test_planner_executor import BOOT
    page, w, tid = navigate(extension, 'planner_standard.html')
    w.evaluate(BOOT, tid)
    result = w.evaluate('''async()=>{const plan=engine.b.request;globalThis.vseen=0;
      engine.b.request=async(phase,body)=>{
        if(phase==='verify'){vseen++;if(vseen===1){const slot=body.expected.find(e=>e.value==='42').slot_key;
          return {cost:.001,response:{kind:'mismatch',mismatches:[slot],reason:'text box looked blank'}};}
          return {cost:.001,response:{kind:'verified'}};}
        return plan(phase,body);};
      return engine.run();}''')
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#amount').input_value() == '42'
    assert w.evaluate('vseen') >= 2, 'the screenshot rejection did not trigger a re-check'
    assert any(e.get('failure_code') == 'VALUE_MISMATCH' and e['phase'] == 'LOCAL_RECOVERY' for e in result['events'])


def test_legacy_gate_blocks_unplanned_graph_before_submit(extension):
    """Finding 1: the legacy 0.8 hand-in gate no longer exempts a graph, so an
    unplanned canvas/graph answer blocks auto submission instead of being handed
    in blank."""
    _, w, _, _, _ = extension
    refusal = w.evaluate('''()=>{
      const C=new AssignmentCoverage.Coverage();
      const page={question_hint:'',part_tabs:[],warnings:[],elements:[
        {ref:1,key:'k:text',role:'textbox',name:'Answer',box:{x:0,y:0,w:50,h:20}},
        {ref:2,key:'k:graph',role:'graph',name:'Graph',box:{x:0,y:30,w:200,h:200}},
        {ref:3,key:'k:submit',role:'button',control:'terminal',name:'Submit Assignment',box:{x:0,y:240,w:80,h:20}}]};
      C.read({question:'Q',parts:[{id:'t',what:'the value',answer:'5',ref:1}]},page);
      const p=C.current.parts.get('t');p.entered=true;p.verified=true;
      return C.gate({action:'click',ref:3},page,{auto_submit:true,advance:true});
    }''')
    assert refusal and 'unplanned' in refusal.lower() and 'graph' in refusal.lower(), refusal
