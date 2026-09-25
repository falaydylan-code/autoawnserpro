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
    """0.10.48: this used check=stem -- the SAME question reworded, its answer still in the box. That is now, rightly,
    the same question (see the answers-in-place tests below). What this test protects is a Check that lands on a
    DIFFERENT question: its box is empty, so the answers prove nothing, and the run must stop with nothing typed."""
    page, w, tid = navigate(extension, 'transitions.html?check=different')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = stale(result)[0]
    assert stop['detail'].startswith('TARGET_STALE: Question identity changed after Check ('), stop['detail']
    assert 'stem' in stop['detail'] and 'a verified box now holds something else' in stop['detail'], stop['detail']
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
    page, w, tid = navigate(extension, 'transitions.html?check=different')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = stale(result)[0]
    assert stop['detail'].startswith('TARGET_STALE: Question identity changed after Check'), stop['detail']
    assert 'stem' in stop['detail'], stop['detail']                                                   # not hidden behind "frames"
    assert stop['failure_data']['answers_in_place']['same'] is False
    assert page.evaluate('window.answers') == {'1': '42'}                                              # nothing entered into the new page
    assert page.evaluate('window.clicks') == ['check']


# ---------------------------------------------------------------------------------------------------------------
# After our own Check, judge the page by the ANSWERS, not the words (0.10.48)
#
# McGraw Ch.3 Q1 (2026-09-24 7:10 PM, 0.10.47): past the frame fix, the run stopped again after a correct, graded
# answer -- TARGET_STALE (stem); the new stem hash 811c9dc5 is hash(''). Read live on the study copy: McGraw's
# accounting tool runs $("body").addClass("pregrade-mode") when Check grades, the body is that frame's question
# root, and [class*=grade] in the text exclusions dropped the ENTIRE question text. Two changes, both general:
#   * planner_content.js: the page-mode words (grade/score/saved/attempt) drop an element's text only when it holds
#     no answer control; feedback/result/correct stay unconditional so a reveal can never leak into question text.
#   * planner_runtime.js: grading is SUPPOSED to change the words, so after our own Check the question is the same
#     one when the answers just verified are still in the same boxes. That also covers a banner no rule recognises
#     and a page that rewords itself when it grades. A Check that lands on a different question, or that wipes the
#     answers, still stops -- and says why.
# ---------------------------------------------------------------------------------------------------------------


def test_a_body_switched_to_pregrade_mode_keeps_its_question_text(extension):
    """McGraw's own code, on Check. On 0.10.47 this emptied the whole question text and stopped the run."""
    page, w, tid = navigate(extension, 'transitions.html?check=pregrade&bare=1')                     # root = <body>, as live
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and not stale(result)
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}


def test_an_unrecognised_grade_banner_is_judged_by_the_answers(extension):
    """A banner with no feedback markup changes the question text; the answer still in the box proves it is the same one."""
    page, w, tid = navigate(extension, 'transitions.html?check=banner')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert not stale(result) and result['questions'] == 3
    kept = details(result, 'The graded page reads differently')
    assert len(kept) == 3 and all('still in the same boxes' in e['detail'] for e in kept), [e['detail'] for e in kept]


def test_a_page_that_rewords_itself_when_graded_is_still_the_same_question(extension):
    for mode in ['stem', 'rebuildstem']:                                                   # reloaded, and rebuilt
        page, w, tid = navigate(extension, 'transitions.html?check=' + mode)
        result = run(w, tid)
        assert result['status'] == 'finished', (mode, result['events'][-3:])
        assert not stale(result) and result['questions'] == 3, mode
        assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}, mode


def test_a_graded_page_that_reads_differently_and_lost_the_answers_is_not_vouched_for(extension):
    """The answers are the evidence, so a page that changed AND no longer holds them proves nothing: stop, say why,
    and never press Next past it. (A page that only clears the box keeps its fingerprint -- typed values are not part
    of it -- so there is nothing to judge and the run carries on as it always has; check=wipe exercises that.)"""
    page, w, tid = navigate(extension, 'transitions.html?check=wipebanner')
    result = run(w, tid)
    assert result['status'] == 'needs_review', result['events'][-3:]
    stop = stale(result)[0]
    assert 'answers not proven in place' in stop['detail'] and 'holds something else' in stop['detail'], stop['detail']
    assert not details(result, 'The graded page reads differently')
    assert page.evaluate('window.clicks') == ['check']


def test_graded_pages_that_read_alike_do_not_overwrite_each_others_record(extension):
    """When grading strips the question wording, every question's graded page can share ONE key (same address, same
    box ids, no text). Adopting that key must not move each question's record onto it, or each overwrites the last --
    the finished-question count the harness uses for enumeration and resume would drop from 3 to 1."""
    page, w, tid = navigate(extension, 'transitions.html?check=verdictonly')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert len(details(result, 'The graded page reads differently')) == 3
    assert result['questions'] == 3, 'graded pages that read alike merged three questions into one record'
    assert page.evaluate('window.answers') == {'1': '42', '2': '42', '3': '42'}


# ---------------------------------------------------------------------------------------------------------------
# After our own Check, a graded view with NO answer controls left is the question we just checked (0.10.50)
#
# McGraw Ch.3 Q2 (2026-09-24 11:09 PM, 0.10.49): four answers entered and verified, Check pressed, and the run died
# "Check replaced the page's document but it did not settle within 15 s". Reproduced on the study copy: the tool reloads
# its frame into a read-only review sheet -- td.responseCell 4 -> 0, verdict in div.correctAnswer_progressbar, which no
# feedback rule reads -- so the wait for "answer controls back, or locked/complete" could never end. Such a page is now
# accepted when a reloaded frame repeats the question's wording, or (its text erased by the page-mode rule) when it
# still shows a table unchanged for 4 s. Nothing is planned on it; the run goes on to Next.
# ---------------------------------------------------------------------------------------------------------------


def graded_view(result):
    return details(result, 'The graded page shows no answer boxes')


def test_a_read_only_graded_sheet_is_the_question_just_checked(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=readonly&bare=1')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and not stale(result)
    assert page.evaluate('window.clicks') == ['check', 'next', 'check', 'next', 'check']
    seen = graded_view(result)
    assert len(seen) == 3 and all("repeats the question's wording" in e['detail'] for e in seen), [e['detail'] for e in seen]
    assert len(result['bodies']) == 3                                               # the graded sheets were never planned


def test_a_graded_sheet_whose_text_was_erased_is_accepted_by_its_table(extension):
    """Without McGraw's hidden helper textarea, pregrade-mode erases the frame's text to its title; its table remains."""
    page, w, tid = navigate(extension, 'transitions.html?check=readonlyerased&bare=1')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['questions'] == 3 and not stale(result)
    seen = graded_view(result)
    assert len(seen) == 3 and all('its table unchanged for 4 s' in e['detail'] for e in seen), [e['detail'] for e in seen]


def test_a_brief_loading_screen_is_not_taken_for_the_graded_view(extension):
    for mode in ['spinner', 'slowspinner']:                                          # 1 s, and longer than the 4 s hold
        page, w, tid = navigate(extension, 'transitions.html?bare=1&check=' + mode)
        result = run(w, tid)
        assert result['status'] == 'finished', (mode, result['events'][-3:])
        assert result['questions'] == 3 and not stale(result), mode
        assert not graded_view(result), mode                                         # the real graded page, boxes and all


def test_a_frame_that_stays_blank_after_check_stops_and_says_what_it_saw(extension):
    page, w, tid = navigate(extension, 'transitions.html?check=emptyforever&bare=1')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = result['events'][-1]
    assert stop['failure_code'] == 'INPUT_NO_EFFECT' and 'did not settle' in stop['detail'], stop
    look = stop['failure_data']['last_look']
    assert look['answer_controls'] == 0 and look['document_moved'] and look['reloaded_frame_tables'] == [0], look
    assert page.evaluate('window.clicks') == ['check']                              # never pressed Next past it

