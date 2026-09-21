"""Screen readback for choice groups with no DOM selected-state (0.10.41).

Quizlet's "Select all that apply" cards (5:01 PM): the group was found, read as pick-many, the model chose the
right five, and the harness refused to click because the cards carry no aria-pressed/checked/selected -- nothing
to read a selection back from. On such a group the SCREEN is the readback: the clicked member's own pixels
before vs after (pointer parked off the group first, so a hover glow cannot pass for a selection) and the page's
counter when it shows one ("(5 left)"). The harness remembers what it confirmed and serves that back as the
slot's state. Used only when the DOM offers nothing; attribute and result-icon groups keep their paths.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate
from test_planner_executor import BOOT
from test_planner_choice_mode import resolve

A = '(Choice A) — Net exports and employment will decrease.'
B = '(Choice B) — Net exports will increase, but employment will be unaffected.'
C = '(Choice C) — Net exports will decrease, but employment will be unaffected.'
D = '(Choice D) — Net exports and employment will increase.'
SELECTED = "[...document.querySelectorAll('ul[role=list] button.selected')].map(b=>b.getAttribute('aria-label'))"


def run_visual(w, tid, labels):
    return w.evaluate('''async labels=>{globalThis.moves=[];const move=AssignmentVisual.move;AssignmentVisual.move=async(tab,pt,stopped)=>{moves.push(pt);return move(tab,pt,stopped)};
      engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};
        const o=body.observation,g=o.slots.find(s=>s.kind==='choice_set');
        return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,tasks:[{task_id:'t0',slot_key:g.slot_key,operation:'set_choice_set',desired:{labels},depends_on:[]}]}}};
      try{const r=await engine.run();return {status:r.status,moves:moves.length,verifies:calls.filter(c=>c.phase==='verify').length,
        events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,pixels:e.pixels_changed||null,counter:e.counter||null,readback:e.readback||null,option:e.matched_option||null}))}}
      finally{AssignmentVisual.move=move}}''', labels)


def test_a_group_with_no_dom_state_is_answered_and_confirmed_from_the_screen(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=visual')
    w.evaluate(BOOT, tid)
    slot = resolve(w)['slots'][0]
    assert slot['kind'] == 'choice_set' and slot['evidence']['verification'] == 'visual_change' and slot['evidence']['counter'] == 3
    result = run_visual(w, tid, [A, B, D])
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('clicks') == ['(Choice A)', '(Choice B)', '(Choice D)']
    assert page.evaluate(SELECTED) == ['(Choice A)', '(Choice B)', '(Choice D)']
    confirmed = [e for e in result['events'] if e['detail'] == 'Screen readback confirmed the click']
    assert [e['option'] for e in confirmed] == [A, B, D]
    assert all(float(e['pixels'].rstrip('%')) >= 1 for e in confirmed)
    assert [e['counter'] for e in confirmed] == ['3 -> 2', '2 -> 1', '1 -> 0']
    assert result['moves'] >= 6                                                # pointer parked before and after every click
    assert result['verifies'] == 1                                             # the end-of-question screenshot witness still ran once


def test_a_hover_glow_is_not_a_selection_and_a_dead_card_is_reported(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=visual_noop')
    w.evaluate(BOOT, tid)
    result = run_visual(w, tid, [A, C])
    assert result['status'] == 'needs_review'
    failed = next(e for e in result['events'] if e['detail'] == 'Screen readback did not confirm the click')
    assert failed['option'] == C and float(failed['pixels'].rstrip('%')) < 1
    assert any(e['failure_code'] in ('INPUT_NO_EFFECT', 'REPEATED_STATE') for e in result['events'])
    assert page.evaluate(SELECTED) == ['(Choice A)']                            # A confirmed; C never counted


def test_a_page_that_grades_early_stops_the_group_and_sends_no_screenshot(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=visual_grade')
    w.evaluate(BOOT, tid)
    result = run_visual(w, tid, [A, B, D])
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] == 'GUARD_REJECTED')
    assert 'graded before every planned choice' in stop['detail']
    assert page.evaluate('clicks') == ['(Choice A)', '(Choice B)']             # the third planned click never happened
    assert result['verifies'] == 0                                             # no whole-page screenshot after grading
