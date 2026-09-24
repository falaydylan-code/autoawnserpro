"""A page change the harness caused on purpose is not a stale target (expected transitions).

McGraw Ch.1 Q1 (2026-09-21 8:39 PM, 0.10.44): all twelve answers entered and verified, Check work pressed
"Check my work", and the first look 150 ms later ended the run `TARGET_STALE: Document was replaced.` -- guard()
asserts the frame documents pinned at the start of the question before every look and every input, and McGraw
answers a Check by reloading the frame that holds the question. Next reloads it too. What changes, all general:
  * guard() lifts the frame pins only while settle() is waiting out a change the harness caused itself (Check, Next,
    Submit, and the first look after a finished answer). The new page is judged by the question -- key, feedback,
    page state -- on two consecutive agreeing polls, never by the document ids it carries; a frame caught between
    documents is neither settled nor fatal. The pins return the moment the wait ends.
  * After Check, the graded page is accepted only as the SAME question: same key on a new document -> the documents
    it holds now are pinned and the run carries on to Next; a different key is named (stem / structure / position /
    tabs / frames) and stops the run rather than being guessed at.
  * A document change the harness did NOT cause, mid-entry, stays fatal -- and the log now names the frame and how
    it moved (stopped responding / holds a new document) instead of a bare "Document was replaced."
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def run(w, tid, config=None, on_finish=None):
    """Scripted planner: enter_value '42' on every slot; Check work and Auto Continue on unless overridden.
    on_finish: a URL loaded into the question frame when the first question's FINISH event is emitted (the site redrawing itself, once)."""
    return w.evaluate('''async ({id,config,on_finish})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:true,auto_submit:false,check_work:true,spend_limit:2,model:'test',...config});
      const emit=bridge.emit;let fired=false;bridge.emit=row=>{emit(row);if(on_finish&&!fired&&row.phase==='FINISH'&&/All observed answers entered/.test(row.message)){fired=true;chrome.scripting.executeScript({target:{tabId:id},func:src=>{document.getElementById('frame').src=src},args:[on_finish]})}};
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const tasks=body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:'42'},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:1}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,questions:Object.keys(r.questions).length,
        events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,failure_data:e.failure_data||null,purpose:e.click_details?.purpose||null,document_replaced:e.document_replaced||false})),
        bodies:globalThis.planBodies.map(o=>({question:o.question,slots:o.slots.length}))}}''',
      {'id': tid, 'config': config or {}, 'on_finish': on_finish})


def details(result, prefix):
    return [e for e in result['events'] if e['detail'].startswith(prefix)]


def stale(result):
    return [e for e in result['events'] if e['failure_code'] == 'TARGET_STALE']


def test_check_that_reloads_the_question_frame_is_waited_out_and_next_reaches_every_question(extension):
    page, w, tid = navigate(extension, 'transitions.html')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and len(result['bodies']) == 3 and not stale(result)
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}
    assert page.evaluate('window.clicks') == ['check', 'next', 'check', 'next', 'check']
    feedback = details(result, 'Website feedback received')
    assert len(feedback) == 3 and all(e['document_replaced'] for e in feedback)                        # each Check reloaded the frame
    assert len(details(result, 'The page replaced its document while moving on')) == 2                 # each Next reloaded it
    assert page.evaluate('window.loads') == ['?q=1', '?q=1&graded=1', '?q=2', '?q=2&graded=1', '?q=3', '?q=3&graded=1']
    assert [e['purpose'] for e in result['events'] if e['purpose'] in ('check_work', 'advance')] == ['check_work', 'advance'] * 2 + ['check_work']
    assert result['events'][-1]['detail'].startswith('Observed question complete')                      # Q3's Next is disabled


def test_check_that_redraws_in_place_and_next_that_swaps_in_place_are_unchanged(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=redraw&next=swap')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and not stale(result)
    feedback = details(result, 'Website feedback received')
    assert len(feedback) == 3 and not any(e['document_replaced'] for e in feedback)
    assert not details(result, 'The page replaced its document')
    assert page.evaluate('window.loads') == ['?q=1']                                                    # one document for the whole run


def test_feedback_shown_outside_the_question_frame_still_counts(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=top&next=swap')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert len(details(result, 'Website feedback received')) == 3 and not stale(result)


def test_a_late_and_half_loaded_reload_is_waited_for_not_settled_on(extension):
    page, w, tid = navigate(extension, 'transitions.html?delay=700&slow=1')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and not stale(result)
    assert all(e['document_replaced'] for e in details(result, 'Website feedback received'))
    assert not [e for e in result['events'] if e['failure_code'] in ('INPUT_NO_EFFECT', 'FRAME_UNREADABLE')]


def test_check_that_changes_the_question_stops_with_the_ingredient_named(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=stem')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = stale(result)[0]
    assert stop['detail'].startswith('TARGET_STALE: Question identity changed after Check (stem)'), stop['detail']
    assert stop['failure_data']['document_replaced'] is True
    assert page.evaluate('window.answers') == {'1': '42'} and page.evaluate('window.clicks') == ['check']   # nothing entered into the new page


def test_check_with_no_effect_is_still_reported_once(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=none')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    assert result['events'][-1]['failure_code'] == 'INPUT_NO_EFFECT' and 'no new feedback' in result['events'][-1]['detail']
    assert page.evaluate('window.clicks') == ['check']


def test_next_that_reloads_the_same_question_is_no_effect_and_says_the_document_moved(extension):
    page, w, tid = navigate(extension, 'transitions.html?next=same')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    last = result['events'][-1]
    assert last['failure_code'] == 'INPUT_NO_EFFECT' and last['detail'].startswith("INPUT_NO_EFFECT: Next replaced the page's document but no different question settled"), last['detail']
    assert page.evaluate('window.clicks') == ['check', 'next'] and page.evaluate('window.loads') == ['?q=1', '?q=1&graded=1', '?q=1']


def test_a_document_replaced_while_entering_is_still_fatal_and_names_the_frame(extension):
    page, w, tid = navigate(extension, 'transitions.html?stray=1')
    result = run(w, tid)
    assert result['status'] == 'needs_review', result['events'][-3:]
    stop = stale(result)[0]
    assert stop['detail'].startswith('TARGET_STALE: Document was replaced (frame '), stop['detail']
    assert stop['failure_data']['frame_id'] != 0 and stop['failure_data']['reason'] in ('replaced', 'unreachable')
    assert page.evaluate('window.clicks') == []                                                          # never reached Check


def test_a_page_that_replaces_its_document_after_the_verified_answer_is_repinned_and_checked(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=redraw&next=swap')
    result = run(w, tid, on_finish='transitions_q.html?q=1')                                              # the site redraws its frame on its own, once
    assert result['status'] == 'finished', result['events'][-3:]
    assert details(result, 'The page replaced its document after the verified answer') and not stale(result)
    assert page.evaluate('window.loads')[:2] == ['?q=1', '?q=1'] and len(details(result, 'Website feedback received')) == 3
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}


def test_the_guard_names_the_frame_and_how_it_moved(extension):
    page, w, tid = navigate(extension, 'transitions.html')
    out = w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      e.current={key:o.question_key,document:o.document_id,identity:o.identity,recovery:new AssignmentPlanner.Recovery(),frameDocuments:o.frames.map(f=>({frame_id:f.frame_id,document_id:f.document_id}))};
      const child=o.frames.find(f=>f.frame_id!==0).frame_id;
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.getElementById('frame').src='transitions_q.html?q=1'}});await new Promise(r=>setTimeout(r,400));
      try{await e.guard();return {ok:true}}catch(x){return {message:x.message,data:x.actual,child}}}''', tid)
    assert out['message'].startswith(f"TARGET_STALE: Document was replaced (frame {out['child']} ") and out['data']['frame_id'] == out['child']
    assert out['data']['reason'] in ('replaced', 'unreachable') and out['data']['was']


# ---------------------------------------------------------------------------------------------------------------
# A Check that DESTROYS the question iframe and builds a new one (0.10.47)
#
# McGraw Connect Ch.3 Q1 (2026-09-24 12:10 AM, 0.10.46): twelve cells across two tabs entered and verified, the page
# graded it "Answer is complete and correct", and the run died on its own Check click:
#   TARGET_STALE: Question identity changed after Check (frames [1747] -> [1752]); the graded page was not entered.
# check=reload above NAVIGATES the same iframe element, so Chrome keeps its frame id and this file passed -- McGraw
# REPLACES the element, and a new element gets a new id. The id was inside the question key (planner_runtime.js :151)
# and inside every slot key (:155). It is a handle for sending a message to the frame right now, never an identity:
# each frame's own key already holds its address, question text and answer layout.
# ---------------------------------------------------------------------------------------------------------------


def test_a_check_that_rebuilds_the_question_frame_keeps_the_question_and_moves_on(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=rebuild')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('window.rebuilds') == 3                                                       # the element really was replaced each time
    assert result['questions'] == 3 and not stale(result)
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}
    assert len(details(result, 'Website feedback received')) == 3                                      # each graded page adopted, not refused
    assert page.evaluate('window.clicks') == ['check', 'next', 'check', 'next', 'check']


def test_next_that_rebuilds_the_frame_still_reaches_every_question(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=rebuild&next=rebuild')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('window.rebuilds') == 5 and result['questions'] == 3 and not stale(result)
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}


def test_a_rebuilt_frame_holding_a_different_question_still_stops_and_says_everything_that_moved(extension):
    """The guard is kept, only its input is fixed: a rebuild that brings a DIFFERENT question must still stop, nothing
    typed into it. And the message must name every ingredient that moved -- it used to return at the first difference,
    so a frame change hid whether the question's own text had changed too."""
    page, w, tid = navigate(extension, 'transitions.html?check=rebuildstem')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = stale(result)[0]
    assert stop['detail'].startswith('TARGET_STALE: Question identity changed after Check'), stop['detail']
    assert 'stem' in stop['detail'], stop['detail']                                                   # not hidden behind "frames"
    assert page.evaluate('window.answers') == {'1': '42'}                                              # nothing entered into the new page
    assert page.evaluate('window.clicks') == ['check']
