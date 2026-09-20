"""Pick-one vs pick-many for a candidate choice group: read it from the screen, or let the model fill the blank.

Khan Academy (2:06 PM, 0.10.38): the answer group was found -- four lettered aria-pressed buttons -- and stayed
unresolved with "Single or multiple selection is not established by the visible instructions", although the
page shows "Choose 1 answer:" right above the choices. The legend carries aria-hidden="true", and the text
walk honoured that mark even for text a person can see. The model then planned the group anyway (correctly)
and was refused because unresolved slots may never be planned.

Two changes, both bounded: (1) text that is genuinely on screen classifies the group even when aria-hidden;
(2) when the page says neither, the model may send classify_choices with selection_mode, applied only while
the page text is silent, and the executor still verifies exactly what is selected. The fixture is the live
Khan shape, chrome included.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate
from test_planner_executor import BOOT

MODE_REASON = 'Single or multiple selection is not established by the visible instructions.'
CHROME = ['Share link', 'Course: AP Macroeconomics', 'Unit 6', 'Draw on exercise', 'Start over', 'Skip', 'Check']


def resolve(w):
    return w.evaluate('''async()=>{const o=await engine.observe();engine.current={key:o.question_key,document:o.document_id,recovery:new AssignmentPlanner.Recovery()};
      const r=await engine.resolveInteractions(o);return {slots:r.slots.map(s=>({slot_key:s.slot_key,kind:s.kind,options:s.options,evidence:s.interaction?.evidence||null}))}}''')


def run_with(w, tid, assert_mode=None, label='(Choice A) — Net exports and employment will decrease.'):
    """Full run with a scripted model: optionally one classify_choices request carrying selection_mode, then a
    plan choosing `label`. Returns status, events and every call the scripted model received."""
    return w.evaluate('''async ({assert_mode,label})=>{let asked=false;
      engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};
        const o=body.observation,cand=o.slots.find(s=>s.interaction?.adapter==='candidate_choices'&&s.kind==='unresolved');
        if(assert_mode&&cand&&!asked){asked=true;return {cost:0,response:{kind:'request_inspection',question_key:o.question_key,observation_id:o.observation_id,
          inspection:{slot_key:cand.slot_key,question:'Is this a pick-one question?',requests:['classify_choices'],selection_mode:assert_mode}}}}
        const ready=o.slots.filter(s=>s.kind!=='unresolved');
        return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,
          tasks:ready.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:s.kind==='choice_set'?'set_choice_set':'choose_one',desired:s.kind==='choice_set'?{labels:[label]}:{label},depends_on:[]}))}}};
      const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,cardinality:e.cardinality||null,actual:e.actual||null,purpose:e.click_details?.purpose||null})),calls:calls.map(c=>c.phase)}}''',
      {'assert_mode': assert_mode, 'label': label})


def test_an_instruction_on_screen_counts_even_when_aria_hidden_and_chrome_is_not_offered(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=legend')
    w.evaluate(BOOT, tid)
    r = resolve(w)
    assert len(r['slots']) == 1, r                                              # header, breadcrumb and controls are not candidates
    slot = r['slots'][0]
    assert slot['kind'] == 'choice' and slot['evidence']['selection_mode_source'] == 'page_text'
    assert not any(c in o for o in slot['options'] for c in CHROME)
    result = run_with(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('clicks') == ['(Choice A)']
    assert page.locator('button[aria-label="(Choice A)"]').get_attribute('aria-pressed') == 'true'
    assert not any(e['cardinality'] for e in result['events'])                 # the page said pick-one; nothing to caveat


def test_with_no_instruction_the_model_may_say_pick_one_and_the_log_says_so(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=none')
    w.evaluate(BOOT, tid)
    r = resolve(w)
    assert r['slots'][0]['kind'] == 'unresolved' and r['slots'][0]['evidence']['reason'] == MODE_REASON
    result = run_with(w, tid, assert_mode='choice')
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['calls'][:2] == ['plan', 'plan']                             # one classify round, then the plan
    assert page.evaluate('clicks') == ['(Choice A)']
    verified = next(e for e in result['events'] if e['phase'] == 'VERIFY' and e['detail'].endswith('answers verified'))
    assert verified['cardinality'] == 'asserted by the model; verified by selected-state readback only'
    classified = next(e for e in result['events'] if e['phase'] == 'INSPECT' and e['detail'].startswith('Model read this group as pick one; accepted'))
    assert classified['actual']['selection_mode'] == 'choice' and classified['actual']['selection_mode_source'] == 'model_assertion'


def test_a_genuinely_hidden_instruction_still_does_not_count(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=hidden')
    w.evaluate(BOOT, tid)
    r = resolve(w)
    assert r['slots'][0]['kind'] == 'unresolved' and r['slots'][0]['evidence']['reason'] == MODE_REASON
    assert r['slots'][0]['evidence']['selection_mode'] is None


def test_page_text_beats_the_model_when_it_disagrees(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=all')
    w.evaluate(BOOT, tid)
    r = resolve(w)
    assert r['slots'][0]['kind'] == 'choice_set' and r['slots'][0]['evidence']['selection_mode_source'] == 'page_text'
    verdict = w.evaluate('''async()=>{const o=await engine.observe(),s=o.slots[0];return engine.inspect(s.frame,s.target,'classify_choices',{selection_mode:'choice'})}''')
    assert verdict['asserted_mode'] == 'choice' and verdict['accepted'] is False
    assert verdict['evidence']['selection_mode'] == 'choice_set' and verdict['evidence']['selection_mode_source'] == 'page_text'
    after = resolve(w)
    assert after['slots'][0]['kind'] == 'choice_set'                          # a refused claim leaves nothing behind
    assert page.evaluate('clicks') == []


# 0.10.40: the live Khan rerun on 0.10.39 showed the model never takes the optional classify round -- it plans the
# group directly, every time. So the planned operation IS the reading: choose_one = pick one, set_choice_set = pick
# many. The page still decides whether it stands, before anything is clicked.
def plan_directly(w, tid, operation='choose_one', label='(Choice A) — Net exports and employment will decrease.'):
    return w.evaluate('''async ({operation,label})=>{
      engine.b.request=async(phase,body)=>{calls.push({phase,body});if(phase==='verify')return {cost:0,response:{kind:'verified'}};
        const o=body.observation,group=o.slots.find(s=>s.interaction?.adapter==='candidate_choices'||s.kind==='choice'||s.kind==='choice_set');
        return {cost:0,response:{kind:'plan',question_key:o.question_key,observation_id:o.observation_id,
          tasks:[{task_id:'t0',slot_key:group.slot_key,operation,desired:operation==='choose_one'?{label}:{labels:[label]},depends_on:[]}]}}};
      const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,cardinality:e.cardinality||null,accepted:e.accepted??null})),plans:calls.filter(c=>c.phase==='plan').length}}''',
      {'operation': operation, 'label': label})


def test_the_planned_operation_is_the_reading_when_the_page_says_neither(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=none')
    w.evaluate(BOOT, tid)
    assert resolve(w)['slots'][0]['kind'] == 'unresolved'
    result = plan_directly(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['plans'] == 1                                                  # no detour round
    assert page.evaluate('clicks') == ['(Choice A)']
    assert next(e for e in result['events'] if e['detail'].startswith('Model read this group as pick one; accepted'))['accepted'] is True
    assert next(e for e in result['events'] if e['phase'] == 'VERIFY' and e['detail'].endswith('answers verified'))['cardinality']


def test_a_page_that_contradicts_itself_refuses_the_reading_before_any_click(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=conflict')
    w.evaluate(BOOT, tid)
    assert resolve(w)['slots'][0]['evidence']['reason'] == MODE_REASON
    result = plan_directly(w, tid)
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] == 'GUARD_REJECTED')
    assert 'does not support reading this group as pick one' in stop['detail']
    assert next(e for e in result['events'] if e['detail'].startswith('Model read this group as pick one; not accepted'))
    assert page.evaluate('clicks') == []


def test_a_group_with_no_readback_cannot_be_planned_at_all(extension):
    page, w, tid = navigate(extension, 'choice_mode.html?mode=noreadback')
    w.evaluate(BOOT, tid)
    slot = resolve(w)['slots'][0]
    assert slot['kind'] == 'unresolved' and slot['evidence']['reason'].startswith('No supported selected-state readback')
    result = plan_directly(w, tid)
    assert result['status'] == 'needs_review'
    assert any(e['failure_code'] == 'QUESTION_INCOMPLETE' for e in result['events'])
    assert page.evaluate('clicks') == []
