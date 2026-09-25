"""Our own answer, shown back with the site's marking, is not a new question.

McGraw SmartBook (2026-09-24 9:20 PM, 0.10.48): the question was answered correctly, the confidence bar submitted
it, and SmartBook re-rendered the SAME question in review mode. The run took that for a new question, planned it,
and the model was handed the revealed answer key -- its own reason said "as confirmed by the correct answer shown
on the page". Nothing was answered wrongly (the answer was already in), but the key reached the model, which the
project forbids outright.

Three guards should have caught it and each was blind for its own reason:
  * "are my verified answers still in the same boxes" matches a box by its element key, and SmartBook RENAMES the
    input on the review page (mcinput_..._XXX -> _scoring), so the box is never found;
  * the review-page guard reads feedback, grade state and result icons, and SmartBook writes its marking INTO the
    option text ("...accounting equation correct", "Reason: ...") rather than into any element the feedback
    selector looks at, so there was no feedback and no known grade;
  * the question key moved, because the heading changed too.

The signal added here needs neither the box key nor feedback markup: after OUR OWN submission, a page showing a
value that BEGINS WITH an answer we just submitted and is STRICTLY LONGER than it is that answer with the site's
marking added -- the review of the question we just did. It is never planned, the submission is confirmed, and the
loop goes on to look for Next on that page.

Strictly longer is the part that protects a mark: a genuinely new question that arrives pre-selected with the same
short answer is an EQUAL match, and must fall through and be answered rather than skipped
(`test_a_new_question_preselected_with_the_same_answer_is_not_a_review`).

Known limit, pinned below: a site that shows the answer back UNCHANGED is not caught by this signal
(`test_a_review_page_that_appends_nothing_is_not_caught`).
"""
import json
import pytest
from test_extension_coverage import extension  # noqa: F401
from test_ordering_visual import navigate

ANSWER = 'has at least two effects on the basic accounting equation'


def run(worker, tid, config=None, multi=()):
    """Scripted planner: answer the accounting option, then let the model pick Medium Confidence as answer_submit."""
    return worker.evaluate('''async ({id,config,answer,multi})=>{
      const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();
      bridge.config=async()=>({advance:true,check_work:true,auto_submit:false,spend_limit:3,model:'test',...config});
      const calls=[];bridge.request=async(phase,body)=>{
        calls.push({phase,body});
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        if(phase==='navigation'){
          const c=body.candidates.find(x=>/Medium/.test(x.label))||body.candidates[0];
          const action=body.requested_actions.includes('advance')?'advance':(c.kind==='unknown'?'answer_submit':c.kind);
          return {cost:.001,response:{kind:'action',question_key:body.observation.question_key,
            observation_id:body.observation.observation_id,candidate_id:c.candidate_id,action,
            reason:'Medium reflects the supplied pre-submission reasoning.'}};
        }
        const o=body.observation;
        if(multi.length){
          const slot=o.slots.find(s=>s.kind==='choice_set')||o.slots[0];
          const labels=multi.map(m=>(slot.options||[]).find(x=>x.includes(m))).filter(Boolean);
          return {cost:.001,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,
            tasks:[{task_id:'t1',slot_key:slot.slot_key,operation:'set_choice_set',desired:{labels},depends_on:[]}],
            reason:'These three are the cash flow categories.',parts_declared:1}};
        }
        const slot=o.slots.find(s=>(s.options||[]).some(x=>x.includes(answer)))||o.slots[0];
        const label=(slot.options||[]).find(x=>x.includes(answer));
        return {cost:.001,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,
          tasks:[{task_id:'t1',slot_key:slot.slot_key,operation:'choose_one',desired:{label},depends_on:[]}],
          reason:'Every transaction affects at least two elements of the accounting equation.',parts_declared:1}};
      };
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());
      const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({detail:e.detail,failure_code:e.failure_code||null})),
        plans:calls.filter(c=>c.phase==='plan').map(c=>JSON.stringify(c.body.observation)),
        phases:calls.map(c=>c.phase)};
    }''', dict(id=tid, config=config or {}, answer=ANSWER, multi=list(multi)))


def details(result):
    return [e['detail'] for e in result['events']]


def leaked(result):
    """Did any planning request carry the page's marking -- the revealed answer key?"""
    return [p for p in result['plans'] if 'correct' in p or 'Reason:' in p]


# --- the fix -------------------------------------------------------------------------------------------

def test_the_review_page_is_recognised_and_never_planned(extension):
    page, w, tid = navigate(extension, 'smartbook_review.html')
    result = run(w, tid)
    assert not leaked(result), 'the revealed answer key reached the model: ' + leaked(result)[0][:400]
    assert len(result['plans']) == 1, 'the review page was planned as a new question'
    assert any('showing the submitted answer back' in d for d in details(result)), details(result)[-4:]
    assert page.evaluate('window.clicks') == ['Medium', 'next'], page.evaluate('window.clicks')


def test_the_run_continues_through_next_after_the_review_page(extension):
    page, w, tid = navigate(extension, 'smartbook_review.html')
    result = run(w, tid)
    assert result['status'] == 'completed', details(result)[-4:]
    assert page.evaluate('window.stage') == 'done'


def test_the_answer_is_still_entered_and_submitted_once(extension):
    page, w, tid = navigate(extension, 'smartbook_review.html')
    result = run(w, tid)
    assert page.evaluate('window.planted') == [ANSWER]
    assert result['phases'].count('navigation') >= 1


# --- the guard that protects a mark --------------------------------------------------------------------

def test_a_new_question_preselected_with_the_same_answer_is_not_a_review(extension):
    """An EQUAL match is ambiguous: it may be a genuinely new question that happens to arrive pre-selected. It must
    be answered, not skipped -- skipping is the one failure here that costs marks rather than just stopping."""
    page, w, tid = navigate(extension, 'smartbook_review.html?review=prefilled')
    result = run(w, tid)
    assert not any('showing the submitted answer back' in d for d in details(result))
    assert len(result['plans']) == 2, 'the second question must be planned, not skipped: ' + str(details(result)[-4:])
    assert result['status'] == 'completed', details(result)[-4:]   # answered, submitted, and the assignment ended
    assert page.evaluate('window.planted') == [ANSWER, ANSWER]     # both questions were actually answered


# --- the known limit, pinned -----------------------------------------------------------------------------

def test_a_review_page_that_appends_nothing_is_not_caught(extension):
    """A site that shows the answer back UNCHANGED gives this signal nothing to see: the value is equal, not longer.
    It falls through to the existing guard. Recorded so the gap is a decision, not a surprise."""
    page, w, tid = navigate(extension, 'smartbook_review.html?review=equal')
    result = run(w, tid)
    assert not any('showing the submitted answer back' in d for d in details(result))


# --- an ordinary new question is unaffected ---------------------------------------------------------------

def test_a_genuinely_new_question_still_advances_and_is_planned(extension):
    page, w, tid = navigate(extension, 'smartbook_review.html?review=none')
    result = run(w, tid)
    assert not any('showing the submitted answer back' in d for d in details(result))
    assert len(result['plans']) == 2, details(result)[-4:]
    assert result['status'] == 'completed', details(result)[-4:]
    assert page.evaluate('window.stage') == 'done'


# --- multi-select: the 11:11 PM Q5 shape --------------------------------------------------------------

MULTI = ['cash flows from financing activities', 'cash flows from investing activities',
         'cash flows from operating activities']


def test_a_multi_select_review_page_is_recognised_and_never_planned(extension):
    """Three answers submitted at once. The harness records them as ONE comma-joined string, while the review page
    shows them one per option with ' correct' appended -- so comparing against the joined string never matched and
    the graded page was planned. Each submitted label is now compared on its own."""
    page, w, tid = navigate(extension, 'smartbook_review.html?type=multi')
    result = run(w, tid, multi=MULTI)
    assert not leaked(result), 'the revealed answer key reached the model: ' + leaked(result)[0][:400]
    assert len(result['plans']) == 1, 'the review page was planned as a new question'
    assert any('showing the submitted answer back' in d for d in details(result)), details(result)[-4:]
    assert page.evaluate('window.planted') == [MULTI]


def test_a_multi_select_review_page_only_partly_marked_is_not_a_review(extension):
    """EVERY submitted answer has to come back longer. If a site marks only some of them, this is not proven to be
    our graded page and we fall through to the existing guard -- no worse than before the signal existed, and it is
    what stops one familiar option being enough to call a page a review."""
    page, w, tid = navigate(extension, 'smartbook_review.html?type=multi&mark=partial')
    result = run(w, tid, multi=MULTI)
    assert not any('showing the submitted answer back' in d for d in details(result))
    assert page.evaluate('window.planted') == [MULTI]      # the answers were still entered correctly
