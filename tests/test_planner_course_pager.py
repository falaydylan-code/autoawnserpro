"""A known control wrapped in the site's own wording is still that control.

Khan Academy (2026-09-24 7:34 PM, 0.10.47): Choice D was chosen correctly, verified by DOM and by a confirming
screenshot, and the question then ended `QUESTION_INCOMPLETE: Answer controls remain unresolved`. The unresolved
thing was the left sidebar's course pager -- two plain buttons, "Previous in course" and "Next in course" --
discovered as a candidate answer group, unclassifiable (its own scope text says neither pick-one nor pick-many),
and an unresolved leftover fails the finish gate at `planner_runtime.js:920`.

The whole-group chrome rule shipped in 0.10.47 should have caught it and did not: it needs EVERY label to be a
recognised workflow word, and "Next in course" matches nothing -- the advance pattern matches a whole label
("Next", "Next question", "Next part", "Continue"), not a phrase inside one.

The fix here strips the phrase the group's labels share -- the same helper the mirror rule uses -- and tests what
is left, so "Previous in course"/"Next in course" becomes "Previous"/"Next", both already recognised. No wording
is added to any list.

This does NOT make the rule vocabulary-free, and `test_a_pager_whose_words_are_absent_still_gets_through` pins
that honestly: a pager reading "Forward"/"Backward" still becomes an unresolved leftover and still ends a
correctly answered question. The general fix for that is at the finish gate -- a group the harness merely GUESSED
at is not evidence of an unanswered control -- which lives in planner_runtime.js and is not this change.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

ANSWER = 'A sustained increase in real GDP per capita over time'
CHROME = 'every label is a workflow or auxiliary control'


def observe(w, tid):
    return w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      return {suppressed:o.frames.flatMap(f=>f.suppressed_groups||[]),
        slots:o.slots.map(s=>({kind:s.kind,label:s.label,options:s.options,adapter:s.interaction?.adapter||null}))}}''', tid)


def run(w, tid):
    """Scripted planner: choose the option whose text contains ANSWER; plan nothing else."""
    return w.evaluate('''async ({id,answer})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        const slots=body.observation.slots.filter(s=>s.kind==='choice'&&(s.options||[]).some(o=>o.includes(answer)));
        const tasks=slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'choose_one',
          desired:{label:s.options.find(o=>o.includes(answer))},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:1}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({detail:e.detail,failure_code:e.failure_code||null,failure_data:e.failure_data||null}))}}''',
      {'id': tid, 'answer': ANSWER})


def options(seen):
    return [o for s in seen['slots'] for o in (s['options'] or [])]


def answer_group(seen):
    return [s for s in seen['slots'] if any(ANSWER in o for o in (s['options'] or []))]


# --- the fix -----------------------------------------------------------------------------------------------

def test_a_wrapped_course_pager_is_not_offered_as_an_answer_group(extension):
    page, w, tid = navigate(extension, 'course_pager.html')
    seen = observe(w, tid)
    assert 'Previous in course' not in options(seen) and 'Next in course' not in options(seen), seen['slots']
    assert [g['reason'] for g in seen['suppressed']] == [CHROME]
    assert sorted(seen['suppressed'][0]['labels']) == ['Next in course', 'Previous in course']
    # The answer group is still offered. Its kind is 'unresolved' on a RAW observe -- a discovered group is only
    # typed once classify_choices has run -- so what matters here is that it survived with its options intact;
    # test_the_run_now_finishes_instead_of_dying_on_the_leftover proves it becomes answerable.
    assert len(answer_group(seen)) == 1 and answer_group(seen)[0]['adapter'] == 'candidate_choices'


def test_the_run_now_finishes_instead_of_dying_on_the_leftover(extension):
    page, w, tid = navigate(extension, 'course_pager.html')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('window.picked') == [ANSWER]
    assert page.evaluate('window.paged') == [], 'the harness must never press a course pager'


def test_a_plain_pager_is_still_suppressed(extension):
    """Bare "Previous"/"Next" never even forms a group: "Next" is a navigation word the pool filter already
    removes one control at a time, and a lone survivor is not a group. Nothing is suppressed because there is
    nothing to suppress -- what matters is that neither label reaches the model as an answer option."""
    page, w, tid = navigate(extension, 'course_pager.html?pager=plain')
    seen = observe(w, tid)
    assert 'Next' not in options(seen) and 'Previous' not in options(seen), seen['slots']
    assert not seen['suppressed'], 'the pair never became a group, so there is nothing to record'
    assert len(answer_group(seen)) == 1


# --- the limit, pinned honestly ----------------------------------------------------------------------------

def test_a_pager_whose_words_are_absent_still_gets_through(extension):
    """Forward/Backward are in no list, so stripping the shared phrase leaves nothing recognised. The group is
    still offered, still unresolved, and still ends a correctly answered question. This is the case the finish
    gate has to answer, not the vocabulary."""
    page, w, tid = navigate(extension, 'course_pager.html?pager=unworded')
    seen = observe(w, tid)
    assert not seen['suppressed']
    assert 'Forward in course' in options(seen)
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    last = result['events'][-1]
    assert last['failure_code'] == 'QUESTION_INCOMPLETE' and 'remain unresolved' in last['detail']
    assert page.evaluate('window.picked') == [ANSWER], 'the answer is still entered correctly before the stop'


# --- markup outranks labels --------------------------------------------------------------------------------

def test_markup_on_the_pager_keeps_it(extension):
    page, w, tid = navigate(extension, 'course_pager.html?pager=marked')
    seen = observe(w, tid)
    assert not seen['suppressed'], 'a group the page marks up as answer controls is never withheld by its labels'
    assert 'Previous in course' in options(seen)


def test_a_real_answer_group_that_reads_as_workflow_is_kept_by_its_markup(extension):
    """"Previous year"/"Next year" strip to "Previous"/"Next", which are both workflow words. Only the page's own
    markup separates this from a pager, which is why the markup check comes first."""
    page, w, tid = navigate(extension, 'course_pager.html?answers=opposite&pager=none')
    seen = observe(w, tid)
    assert not seen['suppressed'], seen['suppressed']
    assert 'Previous year' in ' '.join(options(seen))


def test_no_pager_no_suppression(extension):
    page, w, tid = navigate(extension, 'course_pager.html?pager=none')
    assert not observe(w, tid)['suppressed']
