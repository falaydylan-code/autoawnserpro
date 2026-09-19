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


def test_question_stem_in_parent_frame_reaches_the_model(extension):
    """The instructions live in the parent page; every answer cell lives in an
    iframe. The plan payload's `question` must carry the parent's stem, not only
    the iframe's table text -- the frame-filtering gap that left the model to
    guess the task ("solve for the missing amounts" never reached it)."""
    page, w, tid = navigate(extension, 'stem_parent_iframe.html')
    page.frame_locator('iframe').locator('#amount').wait_for()
    obs = w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});
      const o=await e.observe();return {question:o.question,slots:o.slots.length,frames:o.frames.length}}''', tid)
    assert obs['slots'] == 3 and obs['frames'] == 2            # answers found in the iframe, both frames read
    assert 'solve for the missing amounts' in obs['question']  # the parent-frame stem is in the payload
    assert 'balance sheet' in obs['question']
    assert 'Choose B' in obs['question']                       # the iframe's own text is still there too


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

def test_capture_hides_the_caret_and_puts_it_back(extension):
    """Two captures of an unchanged page must hash equal, so the blinking text
    caret is hidden for the picture like the pointer is. It is restored after
    the capture, and a detach mid-way never leaves the page without a caret."""
    page, w, tid = navigate(extension, 'navigates.html')      # a text field and no ticking clock in the fixture
    page.focus('input')
    state = "()=>({caret:document.documentElement.style.caretColor,marked:document.documentElement.hasAttribute('data-assignment-lab-caret')})"
    out = w.evaluate('''async id=>{await AssignmentVisual.attach(id);
      const a=await AssignmentVisual.screenshot(id),b=await AssignmentVisual.screenshot(id);
      return {same:(await AssignmentVisual.pixels(a.dataUrl))===(await AssignmentVisual.pixels(b.dataUrl))};}''', tid)
    assert out['same'], 'two captures of an unchanged focused page hashed differently'
    assert page.evaluate(state) == {'caret': '', 'marked': False}          # restored after the capture
    w.evaluate('''async id=>{await AssignmentVisual.attach(id);
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.documentElement.style.caretColor='transparent';document.documentElement.setAttribute('data-assignment-lab-caret','')}});
      await AssignmentVisual.detach();}''', tid)
    assert page.evaluate(state) == {'caret': '', 'marked': False}          # detach restores it too

def test_log_records_the_model_the_backend_ran_not_only_the_requested_one(extension):
    """Two live runs both printed `model: ""` -- the field was what the extension
    sent, so a silent fallback to the backend default (MiniMax) read as a Grok
    run. The PLAN/VERIFY events must carry the model the backend reports it ran,
    the provider, and the requested value separately."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    result = w.evaluate('''async ({id,label})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:''});
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,model:'minimax/minimax-m3',provider:'MiniMax',response:{kind:'verified'}};
        return {cost:.001,model:'minimax/minimax-m3',provider:'MiniMax',response:{kind:'plan',
          question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());return engine.run();}''', {'id': tid, 'label': 'Asset'})
    assert result['status'] == 'finished', result['events'][-3:]
    plan = next(e for e in result['events'] if e['phase'] == 'PLAN' and e.get('model_calls'))
    assert plan['model'] == 'minimax/minimax-m3' and plan['provider'] == 'MiniMax'   # what the backend ran
    assert plan['requested_model'] == ''                                              # what was asked for
    verify = next(e for e in result['events'] if e['phase'] == 'VERIFY' and e.get('model_calls'))
    assert verify['model'] == 'minimax/minimax-m3'

def test_log_shows_how_much_the_model_thought(extension):
    """The thinking count the backend reports (reasoning_tokens) reaches the event and the panel's tokens line, so
    'did the model actually reason?' is read off the log instead of inferred from output size."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    result = w.evaluate('''async ({id,label})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:''});
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,input_tokens:100,output_tokens:20,reasoning_tokens:0,model:'m',response:{kind:'verified'}};
        return {cost:.001,input_tokens:500,output_tokens:1700,reasoning_tokens:1234,model:'m',response:{kind:'plan',
          question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events,log:h.state.log.map(x=>x.tokens).filter(Boolean)};}''', {'id': tid, 'label': 'Asset'})
    assert result['status'] == 'finished', result['events'][-3:]
    plan = next(e for e in result['events'] if e['phase'] == 'PLAN' and e.get('model_calls'))
    assert plan['reasoning_tokens'] == 1234
    assert '500 in / 1700 out (1234 thinking)' in result['log']
    assert '100 in / 20 out' in result['log']                       # no thinking -> no suffix



def test_a_reply_that_was_all_thinking_is_retried_away_from_the_provider_then_without_thinking(extension):
    """M3-9 (2:19 PM): the plan call came back as 9,000 tokens of thinking and no answer on a provider that ignored the
    thinking cap, and the run stopped. Now the coordinator retries inside the plan budget: first asking the router to
    avoid that provider, then with thinking off; the hints travel on the request. A third failure stops, named."""
    page, w, tid = navigate(extension, 'planner_selection.html')
    result = w.evaluate('''async ({id,label})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planCalls=[];
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planCalls.push({avoid:body.avoid_providers||[],mode:body.reasoning_mode||''});
        if(globalThis.planCalls.length<=2)return {cost:.012,provider:globalThis.planCalls.length===1?'Venice':'Parasail',reasoning_tokens:9000,output_tokens:9000,detail:'TRUNCATED_BY_THINKING: reply cut off -- 9000 of 9000 output tokens went to thinking, none to the answer (provider Venice).'};
        return {cost:.004,provider:'Together',reasoning_tokens:300,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,calls:globalThis.planCalls,events:r.events.map(e=>e.detail)};}''', {'id': tid, 'label': 'Asset'})
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['calls'] == [{'avoid': [], 'mode': ''}, {'avoid': ['Venice'], 'mode': ''}, {'avoid': ['Venice'], 'mode': 'off'}]
    assert page.locator('#cell').get_attribute('data-value') == 'Asset'
    assert any('retrying without provider Venice' in d for d in result['events']) and any('retrying with thinking off' in d for d in result['events'])


def test_model_wait_is_excluded_from_the_question_and_progress_clocks(extension):
 """A large token allowance may take minutes to answer. That wait used to count as 'no progress' (90 s) and against the
 5-minute question deadline. Recovery.exclude() takes it back out; without it the same wait trips the clock."""
 _,w,tid=navigate(extension,'planner_standard.html')
 result=w.evaluate("""async id=>{const L=AssignmentPlanner.LIMITS,saved={noProgress:L.noProgress,question:L.question};L.noProgress=1000;L.question=1500;
   const bridge=__assignmentHarness.plannerBridge();bridge.request=async()=>{await new Promise(r=>setTimeout(r,1300));return {cost:0}};
   const engine=new AssignmentPlanner.Engine(bridge,id,{});engine.current={recovery:new AssignmentPlanner.Recovery()};
   const out={};
   try{const before=engine.current.recovery.started;await engine.modelCall('plan',{});out.shifted=engine.current.recovery.started-before;
       try{engine.current.recovery.check();out.withExclusion='ok'}catch(e){out.withExclusion=e.code}
       const plain=new AssignmentPlanner.Recovery();await new Promise(r=>setTimeout(r,1300));
       try{plain.check();out.withoutExclusion='ok'}catch(e){out.withoutExclusion=e.code}}
   finally{Object.assign(L,saved)}
   return out}""",tid)
 assert result['shifted']>=1300 and result['withExclusion']=='ok', result
 assert result['withoutExclusion'] in ('REPEATED_STATE','BUDGET_EXHAUSTED'), result


def test_extension_waits_as_long_as_the_backend_advertises_and_names_the_wait_when_it_gives_up(extension):
 """The request deadline is the backend's (request_wait_seconds from /api/capabilities) plus a margin, never a number
 chosen in the extension; a request that outlives it is reported with the actual wait and what happened to the charge."""
 _,w,tid=navigate(extension,'planner_standard.html')
 result=w.evaluate("""async id=>{
   await chrome.storage.local.set({armed:true,backend:'http://backend.test'});
   const Original=AssignmentPlanner.Engine,originalFetch=fetch,h=__assignmentHarness,before=h.requestWaitMs;
   AssignmentPlanner.Engine=class {constructor(){this.ledger={}}async run(){}};
   globalThis.fetch=async(u,opts={})=>{u=String(u);
     if(u.includes('/api/capabilities'))return new Response(JSON.stringify({protocol:4,request_wait_seconds:240,features:['task_plans','stable_slots','typed_verification','bounded_repair','frame_scoped_inspection','interaction_classification']}));
     if(u.includes('/api/guest'))return new Response(JSON.stringify({token:'t'}));
     return new Promise((_,reject)=>opts.signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));};   // the plan never answers
   const out={};
   try{await h.startSelected(id);out.fromCapabilities=h.requestWaitMs;
       h.setRequestWait(1500);const t=Date.now();
       try{await h.plannerBridge().request('plan',{},new AbortController().signal);out.error='none'}catch(e){out.error=e.message;out.waited=Date.now()-t}}
   finally{AssignmentPlanner.Engine=Original;globalThis.fetch=originalFetch;h.setRequestWait(before)}
   return out}""",tid)
 assert result['fromCapabilities']==240*1000+15000, result
 assert 'No answer from the backend within 2 seconds' in result['error'] and 'reserved worst case' in result['error'], result
 assert 1400<=result['waited']<4000, result
