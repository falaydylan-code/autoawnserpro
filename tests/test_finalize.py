"""The behaviours the finalizing spec names, each driven through the loaded
extension. The two run-loop tests script the backend inside the worker so the
real `run()` executes end to end without a model.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


# --------------------------------------------------------------------------
# dropdown table: menus outside the table, arrow triggers, ownership
# --------------------------------------------------------------------------

def test_twenty_cells_with_menus_outside_the_table_and_arrow_triggers(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    page.evaluate('document.getElementById("arrow_2_1").click()')     # menu open, appended to <body>
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    cells = [e for e in observed['elements'] if e['dropdown']]
    assert len(cells) == 20
    cell = next(e for e in cells if e['key'].endswith('#cell_2_1'))
    assert cell['expanded'] is True
    arrow = next(e for e in observed['elements'] if e['key'].endswith('#arrow_2_1'))
    assert arrow['trigger'] is True and arrow['owner_ref'] == cell['ref'], 'the arrow belongs to its cell'
    options = [e for e in observed['elements'] if e['role'] == 'option']
    assert len(options) == 2 and all(o['owner_ref'] == cell['ref'] for o in options), 'options outside the table still know their cell'


def test_opening_through_the_arrow_button_is_the_same_as_opening_the_cell(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const cell=p.elements.find(e=>e.key.endsWith('#cell_4_0')),arrow=p.elements.find(e=>e.key.endsWith('#arrow_4_0'));
      h.coverage.read({question:'Classify',parts:[{id:'np',what:'Notes Payable type',answer:'Liability',ref:cell.ref}]},p);
      const r=await h.executeAction(id,{action:'click',ref:arrow.ref},p,{});
      return {r,pending:h.pendingMenu,cellKey:cell.key};}''', tid)
    assert out['r']['ok'] and out['r'].get('preparation'), out['r']
    assert out['pending']['cellKey'] == out['cellKey'] and out['pending']['part'] == 'np'
    assert page.locator('ul[role=listbox] li').count() == 5


def test_a_correctly_owned_option_is_accepted_with_no_pending_menu_state(extension):
    """The failure from the live logs: 'Action is not bound to a planned answer
    or drag pairing'. The menu was opened outside the worker's own path, so
    pendingMenu was empty. DOM ownership is enough."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    page.evaluate('document.getElementById("cell_6_0").click()')     # opened by the page, not the worker
    out = w.evaluate('''async id=>{const h=__assignmentHarness;h.setPendingMenu(null);const p=await h.observeAllFrames(id);
      const cell=p.elements.find(e=>e.key.endsWith('#cell_6_0'));
      h.coverage.read({question:'Classify',parts:[{id:'re',what:'Retained Earnings type',answer:"Stockholders' Equity",ref:cell.ref}]},p);
      const option=p.elements.find(e=>e.role==='option'&&e.name==="Stockholders' Equity");
      const r=await h.executeAction(id,{action:'click',ref:option.ref},p,{});     // no part_id, no pendingMenu
      await h.refreshEvidence(id,await h.observeAllFrames(id));return {r,ledger:h.coverage.ledger()[0]};}''', tid)
    assert out['r']['ok'] and out['r'].get('needsVerification'), out['r']
    assert page.locator('#cell_6_0').inner_text().strip() == "Stockholders' Equity"
    assert out['ledger']['entered'] and out['ledger']['target_key'].endswith('#cell_6_0')


def test_an_option_from_another_fields_menu_is_rejected_with_the_owner_named(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    page.evaluate('document.getElementById("cell_0_0").click()')
    out = w.evaluate('''async id=>{const h=__assignmentHarness;h.setPendingMenu(null);const p=await h.observeAllFrames(id);
      const target=p.elements.find(e=>e.key.endsWith('#cell_5_0'));
      h.coverage.read({question:'Classify',parts:[{id:'cash',what:'Cash type',answer:'Asset',ref:target.ref}]},p);
      const option=p.elements.find(e=>e.role==='option'&&e.name==='Asset');
      return h.executeAction(id,{action:'click',ref:option.ref,part_id:'cash'},p,{});}''', tid)
    assert out['ok'] is False and 'belongs to the cell' in out['detail'] and 'Accounts Payable' in out['detail'], out
    assert page.locator('#cell_5_0').inner_text().strip() == ''


# --------------------------------------------------------------------------
# graph points: nothing in the DOM, screenshot-based dragging
# --------------------------------------------------------------------------

def test_three_graph_points_are_placed_by_visual_drag_and_verified_from_the_page(extension):
    page, w, tid = navigate(extension, 'graph_points.html')
    # the graph is listed as a control the model can name; its points are not
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    graph = next(e for e in observed['elements'] if e['role'] == 'graph')
    assert not [e for e in observed['elements'] if e['role'] == 'point'], 'canvas points have no DOM presence'
    box = page.locator('#graph').bounding_box()
    SIZE, PAD, UNIT = 400, 40, (400 - 80) / 5
    def frac(gx, gy):
        return {'x': (box['x'] + PAD + gx * UNIT) / 1500, 'y': (box['y'] + SIZE - PAD - gy * UNIT) / 1100}
    plan = [('A', 1, 2), ('B', 3, 1), ('C', 4, 4)]
    w.evaluate('''async ({id,ref})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      h.coverage.read({question:'Plot the three points',parts:[{id:'A',what:'point A at (1,2)',answer:'(1,2)',ref},{id:'B',what:'point B at (3,1)',answer:'(3,1)',ref},{id:'C',what:'point C at (4,4)',answer:'(4,4)',ref}]},p);}''', {'id': tid, 'ref': graph['ref']})
    for name, gx, gy in plan:
        current = page.evaluate(f'window.points.{name}')
        out = w.evaluate('''async ({id,name,from,to})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
          const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);
          return h.executeAction(id,{action:'visual_drag',point:from,destination:to,part_id:name,purpose:'answer',observation_id:snap.id},p,{});}''',
          {'id': tid, 'name': name, 'from': frac(current['x'], current['y']), 'to': frac(gx, gy)})
        assert out['ok'] and out.get('needsVerification'), (name, out)
        assert page.evaluate(f'window.points.{name}') == {'x': gx, 'y': gy}, f'{name} did not land'
    # the DOM cannot read a canvas: the parts wait for the screenshot witness
    ledger = w.evaluate('''async id=>{const h=__assignmentHarness;await h.refreshEvidence(id,await h.observeAllFrames(id));return h.coverage.ledger();}''', tid)
    assert all(p['entered'] and not p['verified'] for p in ledger), ledger
    page.click('#tryit')
    assert page.locator('#feedback').inner_text() == 'Your Answer: correct'


def test_a_visual_drag_outside_the_planned_graph_is_refused(extension):
    page, w, tid = navigate(extension, 'graph_points.html')
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),graph=p.elements.find(e=>e.role==='graph');
      h.coverage.read({question:'Plot',parts:[{id:'A',what:'A',answer:'(1,2)',ref:graph.ref}]},p);
      const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);
      return h.executeAction(id,{action:'visual_drag',point:{x:0.95,y:0.95},destination:{x:0.97,y:0.97},part_id:'A',purpose:'answer',observation_id:snap.id},p,{});}''', tid)
    assert out['ok'] is False and 'outside the graph' in out['detail'], out


# --------------------------------------------------------------------------
# ordering: an already-correct list needs no drag
# --------------------------------------------------------------------------

def test_an_already_correct_order_is_verified_without_a_drag(extension):
    page, w, tid = navigate(extension, 'ordering.html')
    page.evaluate('''()=>{const o=document.getElementById('order');o.append(o.querySelector('#net'));}''')   # Revenues, Expenses, Net Income
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Order',parts:[{id:'o',what:'order',kind:'ordering',answer:'ordered',ref:ref('order'),order:['revenue','expense','net'].map(ref),sequence:['Revenues','Expenses','Net Income']}]},p);
      await h.refreshEvidence(id,p);return h.coverage.ledger()[0];}''', tid)
    assert result['verified'] is True


# --------------------------------------------------------------------------
# page states: locked feedback advances; editable feedback allows a retry
# --------------------------------------------------------------------------

def test_locked_feedback_is_recognised_retires_the_part_and_lets_next_through(extension):
    page, w, tid = navigate(extension, 'feedback_states.html?mode=locked')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;let p=await h.observeAllFrames(id);
      const opt=p.elements.find(e=>e.key.endsWith('#optA'));
      h.coverage.read({question:'Which account is a liability?',parts:[{id:'a',what:'the liability',answer:'Cash',ref:opt.ref}]},p);
      await h.executeAction(id,{action:'click',ref:opt.ref,part_id:'a'},p,{});
      p=await h.observeAllFrames(id);
      await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.name==='Check').ref},p,{advance:true});
      p=await h.observeAllFrames(id);await h.refreshEvidence(id,p);
      const before={state:p.page_state,feedback:p.feedback,attempts:p.attempts_left,summary:h.coverage.summary()};
      const retired=h.coverage.retire('incorrect',p.feedback);
      // a re-answer on a disabled control is refused, not attempted
      const reanswer=await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.key.endsWith('#optB')).ref,part_id:'a'},p,{advance:true});
      const next=await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.name==='Next Question').ref},p,{advance:true});
      return {before,retired,reanswer,next,outstanding:h.coverage.outstanding(),answered:null};}''', tid)
    assert result['before']['state'] == 'locked', result['before']
    assert 'Incorrect' in result['before']['feedback'] and result['before']['attempts'] == 0
    assert result['retired'] == [], 'a part the DOM verified as entered is not retired'  # optA is checked: entered+verified
    assert result['reanswer']['ok'] is False and 'disabled' in result['reanswer']['detail']
    assert result['next']['ok'], result['next']
    assert result['outstanding'] == []
    assert page.evaluate('window.answered') == ['Cash'] and page.evaluate('window.advanced') == 1


def test_editable_feedback_allows_a_retry_and_a_revised_plan(extension):
    page, w, tid = navigate(extension, 'feedback_states.html?mode=retry')
    result = w.evaluate('''async id=>{const h=__assignmentHarness;let p=await h.observeAllFrames(id);
      const opt=p.elements.find(e=>e.key.endsWith('#optA'));
      h.coverage.read({question:'Which account is a liability?',parts:[{id:'a',what:'the liability',answer:'Cash',ref:opt.ref}]},p);
      await h.executeAction(id,{action:'click',ref:opt.ref,part_id:'a'},p,{});
      p=await h.observeAllFrames(id);
      await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.name==='Check').ref},p,{});
      p=await h.observeAllFrames(id);
      const state={state:p.page_state,feedback:p.feedback,attempts:p.attempts_left};
      h.coverage.allowRetry(p.feedback);
      await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.name==='Try again').ref},p,{});
      p=await h.observeAllFrames(id);
      h.coverage.read({question:'Which account is a liability?',parts:[{id:'a',what:'the liability',answer:'Accounts Payable',ref:p.elements.find(e=>e.key.endsWith('#optB')).ref}]},p);
      const second=await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.key.endsWith('#optB')).ref,part_id:'a'},p,{});
      p=await h.observeAllFrames(id);await h.executeAction(id,{action:'click',ref:p.elements.find(e=>e.name==='Check').ref},p,{});
      p=await h.observeAllFrames(id);return {state,second,after:p.page_state,feedback:p.feedback};}''', tid)
    assert result['state']['state'] == 'editable_feedback' and result['state']['attempts'] == 1, result['state']
    assert result['second']['ok']
    assert result['feedback'].startswith('Correct') and result['after'] == 'locked'
    assert page.evaluate('window.answered') == ['Cash', 'Accounts Payable']


def test_a_completed_assignment_is_recognised(extension):
    page, w, tid = navigate(extension, 'feedback_states.html?mode=complete')
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    assert observed['page_state'] == 'complete'


# --------------------------------------------------------------------------
# the run is bound to its tab: another tab in front changes nothing
# --------------------------------------------------------------------------

def test_the_run_continues_in_the_original_tab_while_another_tab_is_active(extension):
    page, w, tid, context, origin = extension
    page.goto(origin + '/mcq_buttons.html')
    w.evaluate('(id)=>__assignmentHarness.injectAll(id)', tid)
    other = context.new_page(); other.goto('about:blank'); other.bring_to_front()
    assert w.evaluate('(id)=>chrome.tabs.get(id).then(t=>t.active)', tid) is False, 'the assignment tab is in the background'
    result = w.evaluate('''async id=>{const h=__assignmentHarness;const p=await h.observeAllFrames(id);
      const shot=await h.capture(id,p,true);
      const opt=p.elements.find(e=>e.key.endsWith('#optC'));
      h.coverage.read({question:'Which account',parts:[{id:'a',what:'option',answer:'Deferred Revenue',ref:opt.ref},{id:'b',what:'balance',answer:'900',ref:p.elements.find(e=>e.key.endsWith('#balance')).ref}]},p);
      const click=await h.executeAction(id,{action:'click',ref:opt.ref,part_id:'a'},p,{});
      const p2=await h.observeAllFrames(id);await h.refreshEvidence(id,p2);
      const fill=await h.executeAction(id,{action:'fill',ref:p2.elements.find(e=>e.key.endsWith('#balance')).ref,text:'900',part_id:'b'},p2,{});
      return {shot:shot.slice(0,22),shotLen:shot.length,click,fill,verified:h.coverage.ledger()[0].verified,active:(await chrome.tabs.get(id)).active};}''', tid)
    assert result['shot'].startswith('data:image/png;base64,') and result['shotLen'] > 5000, 'a real screenshot of the background tab'
    assert result['click']['ok'] and 'browser input' in result['click']['detail'], result['click']
    assert page.locator('#optC').get_attribute('aria-pressed') == 'true', 'the click landed in the background tab'
    assert result['fill']['ok'], result['fill']
    assert page.locator('#balance').input_value() == '900', 'typing landed in the background tab'
    assert result['active'] is False, 'focus was not stolen back'
    other.close()


def test_closing_the_assignment_tab_ends_the_run_and_input(extension):
    page, w, tid, context, origin = extension
    page.goto(origin + '/mcq_buttons.html')
    w.evaluate('(id)=>__assignmentHarness.injectAll(id)', tid)
    keeper = context.new_page(); keeper.goto('about:blank')      # so the context survives the close
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const opt=p.elements.find(e=>e.key.endsWith('#optC'));
      await AssignmentVisual.attach(id);
      await chrome.tabs.remove(id);await new Promise(r=>setTimeout(r,300));
      try{const r=await AssignmentVisual.click(id,{x:10,y:10});return {r};}catch(e){return {threw:e.message,attached:AssignmentVisual.attachedTab};}}''', tid)
    assert 'threw' in result and result['attached'] is None, result


# --------------------------------------------------------------------------
# the whole loop: a long assignment, and a stuck one
# --------------------------------------------------------------------------

FAKE_BACKEND = '''
  const real=globalThis.fetch;const json=o=>new Response(JSON.stringify(o),{status:200,headers:{'Content-Type':'application/json'}});
  globalThis.__calls=0;globalThis.__spent=0;
  globalThis.fetch=async (url,opts)=>{
    const u=String(url);
    if(u.endsWith('/api/capabilities'))return json({protocol:3,extension:'0.8.0',features:['parts','ordering','visual_input','visual_verification','browser_input','page_states','no_step_ceiling']});
    if(u.endsWith('/api/guest'))return json({token:'fake'});
    if(u.endsWith('/api/agent/step')){globalThis.__calls++;globalThis.__spent+=0.001;const obs=JSON.parse(opts.body);return json({action:POLICY(obs),cost:0.001,input_tokens:1,output_tokens:1,raw:''});}
    return real(url,opts);
  };
'''

def run_with_policy(w, tid, origin, policy_js, extra_settings=None):
    settings = {'backend': 'http://fake.test', 'model': 'fake', 'advance': True, 'auto_submit': False, 'badges': False, 'double_check': True, 'spend_limit': 5, 'note': ''}
    settings.update(extra_settings or {})
    return w.evaluate('''async ({id,origin,settings})=>{
      await chrome.storage.local.set(settings);
      const POLICY=''' + policy_js + ''';
      ''' + FAKE_BACKEND + '''
      const h=__assignmentHarness;h.reset(origin);
      try{await h.run(id);}finally{globalThis.fetch=real;}
      return {state:{...h.state,log:h.state.log.filter(r=>['stop','error','question','warn'].includes(r.kind)).map(r=>r.kind+': '+r.message.slice(0,140)+(r.detail?' | '+String(r.detail).slice(0,100):''))},calls:globalThis.__calls,spent:globalThis.__spent};}''',
      {'id': tid, 'origin': origin, 'settings': settings})


ANSWER_THE_LETTER = '''(obs)=>{
      // the letter to pick is in the page text; the radios are named by letter
      const want=(obs.text.match(/Pick the letter ([A-D])/)||[])[1];
      const radio=obs.elements.find(e=>e.role==='radio'&&e.name.trim()===want);
      const byName=n=>obs.elements.find(e=>e.name===n&&!e.disabled);
      // a verify turn shows only the screenshot, as it does a real model; this
      // fake one "reads" the letter it planned, the way the model reads the page
      if(obs.phase==='verify')return {action:'verify',part_id:obs.verification.part_id,observation_id:obs.observation_id,status:'confirmed',observed:globalThis.__want||''};
      if(obs.phase==='read_check'){
        if(obs.page_state==='complete'||!want)return {action:'read_check',has_question:false,reason:'no question'};
        globalThis.__want=want;
        return {action:'read_check',has_question:true,question:'Pick the letter '+want,parts:radio?[{id:'a',what:'the letter',answer:want,ref:radio.ref}]:[]};
      }
      const part=(obs.ledger||[])[0];
      if(obs.page_state==='locked'&&byName('Next Question'))return {action:'click',ref:byName('Next Question').ref};
      if(part&&!part.verified&&radio)return {action:'click',ref:radio.ref,part_id:'a'};
      if(byName('Check'))return {action:'click',ref:byName('Check').ref};
      if(byName('Next Question'))return {action:'click',ref:byName('Next Question').ref};
      return {action:'look'};
    }'''

def test_a_long_assignment_is_worked_to_completion_with_no_global_ceiling(extension):
    page, w, tid, context, origin = extension
    page.goto(origin + '/long_assignment.html?total=18')
    w.evaluate('(id)=>__assignmentHarness.injectAll(id)', tid)
    result = run_with_policy(w, tid, origin, ANSWER_THE_LETTER)
    log = result['state']['log']
    assert any('reports it is complete' in line for line in log), log[-6:]
    assert result['state']['questions'] == 18, (result['state']['questions'], log[-8:])
    assert result['state']['steps'] > 90, 'far beyond any per-run step ceiling that used to stop healthy runs'
    assert page.locator('h1').inner_text() == 'Assignment complete'
    assert page.evaluate('document.body.innerText').find('18 / 18') > 0, 'every answer was right'


ONLY_PRESS_HINT = '''(obs)=>{
      const hint=obs.elements.find(e=>e.name==='Show hint');
      const radio=obs.elements.find(e=>e.role==='radio');
      if(obs.phase==='verify')return {action:'verify',part_id:obs.verification.part_id,observation_id:obs.observation_id,status:'uncertain',observed:''};
      if(obs.phase==='read_check')return {action:'read_check',has_question:true,question:'Pick the letter',parts:[{id:'a',what:'the letter',answer:'Z',ref:radio.ref}]};
      return hint?{action:'click',ref:hint.ref}:{action:'look'};
    }'''

def test_repeated_no_progress_stops_without_runaway_spending(extension):
    page, w, tid, context, origin = extension
    page.goto(origin + '/long_assignment.html?total=3')
    w.evaluate('(id)=>__assignmentHarness.injectAll(id)', tid)
    result = run_with_policy(w, tid, origin, ONLY_PRESS_HINT)
    log = result['state']['log']
    # either bounded guard is a correct outcome: the stall limit, or the
    # oscillation detector catching the same click four times first
    assert any('No verified progress' in line or 'Repeated the same action' in line for line in log), log
    assert result['state']['steps'] <= 12, result['state']['steps']
    assert result['spent'] < 0.02
    assert page.evaluate('window.hints') >= 3, 'the clicks were real, they just did not help'
