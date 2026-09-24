"""A per-option tool row is not an answer group, and a discovered group is never mandatory.

Formative macroeconomics quiz (2026-09-24 1:00 AM, 0.10.46): the question was answered correctly by the model
and the plan was thrown away. Beside every option Formative puts a second button, "Strikethrough this option —
<that option>". Those four are repeated siblings with unique labels in a scope whose text settles pick-one, so
`discoverChoices` typed them a resolved 'choice' slot (`planner_content.js` kind = g.mode), and `planner.py`
then required every resolved slot to be planned -- i.e. required the model to plan crossing out its own correct
answer. It planned only the real answer, which was right, and the run died QUESTION_INCOMPLETE. Four changes:

  * planner.py: a group the harness DISCOVERED is its own guess and is OPTIONAL in the plan. Answer controls the
    page marks up (value, selection, native choice/choice_set) stay required, and a plan may never be empty.
  * planner_content.js MIRROR rule: strip the phrase a group's labels share; if what is left maps one for one onto
    another group's labels as that group writes them, this is a tool row for that group, not an answer group.
    Structural, no vocabulary. Prefix and suffix are tried separately -- the live options share the tail
    "unemployment", so stripping both at once would mirror nothing.
  * planner_content.js whole-group chrome rule: a group whose every label is workflow (the vocabulary
    navigationInfo and navigationKind already own, plus the auxiliary words) is chrome. Formative's Previous/Next
    and hint/Feedback pairs each arrived as a candidate group because the pool filter judges one control at a
    time. Markup outranks labels: a member the page marks up as an answer control keeps its group.
  * planner_content.js: ARIA role outranks `e.type`, so `<button type="button" role="radio">` is pick-ONE. The
    live group was typed choice_set, which would have let the harness enter several answers on a pick-one
    question, and its key carried an empty trailing segment (`button:node:45:`).

Suppressed groups stay candidates -- their text is still kept out of the question stem -- and each one is
reported on the observation as `suppressed_groups` with the reason.
"""
import json
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

OPTIONS = ['Seasonal unemployment', 'Cyclical unemployment', 'Frictional unemployment', 'Structural unemployment']
ANSWER = 'Frictional unemployment'


def observe(w, tid):
    return w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      return {question:o.question,suppressed:o.frames.flatMap(f=>f.suppressed_groups||[]),
        slots:o.slots.map(s=>({key:s.slot_key,kind:s.kind,label:s.label,options:s.options,adapter:s.interaction?.adapter||null}))}}''', tid)


def run(w, tid, plan='answer'):
    """Scripted planner. plan='answer' plans only the marked-up answer group, which is what the live model did;
    plan='none' sends an empty task list; plan='all' plans every offered slot, including any discovered group."""
    return w.evaluate('''async ({id,plan})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.bodies=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        const slots=body.observation.slots;globalThis.bodies.push(slots);
        const wanted=plan==='none'?[]:plan==='all'?slots:slots.filter(s=>s.kind==='choice'||s.kind==='choice_set');
        const tasks=wanted.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,
          operation:s.kind==='choice_set'?'set_choice_set':'choose_one',
          desired:s.kind==='choice_set'?{labels:[s.options[2]]}:{label:s.options[2]},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:1}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null})),
        offered:globalThis.bodies.map(s=>s.map(x=>({kind:x.kind,label:x.label})))}}''',
      {'id': tid, 'plan': plan})


MIRROR = 'mirrors another group one option for one'
CHROME = 'every label is a workflow or auxiliary control'


def why(seen, reason):
    return [g for g in seen['suppressed'] if g['reason'] == reason]


def kinds(result):
    return sorted((s['kind'], s['label'][:40]) for s in result['slots'])


# --- the mirror rule -------------------------------------------------------------------------------------

def test_the_strikethrough_row_is_not_offered_as_an_answer_group(extension):
    page, w, tid = navigate(extension, 'tool_rows.html')
    seen = observe(w, tid)
    answers = [s for s in seen['slots'] if s['kind'] == 'choice']
    assert len(answers) == 1, kinds(seen)
    assert answers[0]['options'] == OPTIONS
    assert not any('Strikethrough' in o for s in seen['slots'] for o in (s['options'] or []))
    assert len(why(seen, MIRROR)) == 1, seen['suppressed']
    assert why(seen, MIRROR)[0]['labels'][0].startswith('Strikethrough this option')


def test_the_suppressed_tool_text_still_stays_out_of_the_question(extension):
    page, w, tid = navigate(extension, 'tool_rows.html')
    assert 'Strikethrough' not in observe(w, tid)['question']


def test_a_tool_row_that_mirrors_nothing_stays_an_answer_group(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=distinct&chrome=none')
    seen = observe(w, tid)
    assert not seen['suppressed'], seen['suppressed']
    assert any(s['options'] and s['options'][0].startswith('Cross out A') for s in seen['slots']), kinds(seen)


def test_a_partial_row_is_not_a_mirror(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=partial&chrome=none')
    seen = observe(w, tid)
    assert not seen['suppressed'], seen['suppressed']


def test_the_only_choice_like_group_is_never_suppressed(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=only&chrome=none')
    seen = observe(w, tid)
    assert not seen['suppressed'], 'a mirror needs a target; with the answers as plain text there is none'
    assert any(s['options'] and s['options'][0].startswith('Strikethrough') for s in seen['slots'])


def test_two_tool_rows_cannot_cancel_each_other_out(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?mirror=both&chrome=none')
    seen = observe(w, tid)
    assert len(why(seen, MIRROR)) == 2, seen['suppressed']
    assert len([s for s in seen['slots'] if s['kind'] == 'choice']) == 1, kinds(seen)


def test_options_with_no_shared_tail_mirror_through_the_prefix_too(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?plain=1&chrome=none')
    seen = observe(w, tid)
    assert len(why(seen, MIRROR)) == 1, seen['suppressed']


# --- the whole-group chrome rule -------------------------------------------------------------------------

def test_pager_and_aid_pairs_are_not_offered_as_answer_groups(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=none')
    seen = observe(w, tid)
    labels = [o for s in seen['slots'] for o in (s['options'] or [])]
    assert 'Previous' not in labels and 'Next' not in labels, kinds(seen)
    assert 'Feedback' not in labels and not any('hint' in o.lower() for o in labels), kinds(seen)
    assert len(why(seen, CHROME)) >= 1, seen['suppressed']


def test_markup_outranks_a_workflow_label(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=none&chrome=answer')
    seen = observe(w, tid)
    kept = [s for s in seen['slots'] if s['options'] and 'Previous' in s['options']]
    assert kept, 'a group the page marks up with role=radio must survive its labels: ' + json.dumps(kinds(seen))


def test_no_chrome_no_suppression(extension):
    page, w, tid = navigate(extension, 'tool_rows.html?tools=none&chrome=none')
    assert not observe(w, tid)['suppressed']


# --- role before e.type ----------------------------------------------------------------------------------

def test_a_button_with_role_radio_is_pick_one_and_its_key_has_no_empty_segment(extension):
    page, w, tid = navigate(extension, 'tool_rows.html')
    answers = [s for s in observe(w, tid)['slots'] if s['options'] == OPTIONS]
    assert len(answers) == 1
    assert answers[0]['kind'] == 'choice', 'role=radio is pick-one; e.type "button" must not win'
    assert not answers[0]['key'].endswith(':'), answers[0]['key']
    assert '/radio:' in answers[0]['key'], answers[0]['key']


# --- end to end ------------------------------------------------------------------------------------------

def test_the_live_plan_is_accepted_and_the_answer_is_entered(extension):
    page, w, tid = navigate(extension, 'tool_rows.html')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('window.picked') == [ANSWER]
    assert page.evaluate('window.struck') == [], 'the harness must never cross out an option'
    assert all(len(offered) == 1 for offered in result['offered']), result['offered']


def test_an_empty_plan_is_still_refused(extension):
    page, w, tid = navigate(extension, 'tool_rows.html')
    result = run(w, tid, plan='none')
    assert result['status'] == 'needs_review'
    assert result['events'][-1]['failure_code'] == 'QUESTION_INCOMPLETE'
    assert page.evaluate('window.picked') == [] and page.evaluate('window.struck') == []


def test_the_backend_refuses_an_empty_plan_even_when_every_slot_is_optional():
    """Making every slot optional would open a hole if nothing else required a task. Nothing else had to be added:
    the schema check already refuses a plan with no tasks server-side, and planner_runtime.js refuses it again
    before execution. Pinned here so neither guard can be dropped quietly."""
    import planner
    only_discovered = {'question_key': 'q', 'observation_id': 'o', 'document_id': 'd', 'question': 'Which?',
                       'completeness': {'complete': True},
                       'slots': [{'slot_key': 'q/a', 'kind': 'choice', 'label': 'Answer', 'options': ['A', 'B'],
                                  'interaction': {'adapter': 'candidate_choices', 'evidence': {'ready': True}}}]}
    empty = json.dumps({'kind': 'plan', 'question_key': 'q', 'observation_id': 'o', 'tasks': []})
    with pytest.raises(ValueError, match='a plan needs tasks'):
        planner.validate_context(planner.parse_plan(empty), only_discovered)


def test_the_backend_still_requires_every_marked_up_slot():
    """Discovered groups became optional; a dropdown, a field or a native group did not."""
    import planner
    both = {'question_key': 'q', 'observation_id': 'o', 'document_id': 'd', 'question': 'Which?',
            'completeness': {'complete': True},
            'slots': [{'slot_key': 'q/real', 'kind': 'choice', 'label': 'Answer', 'options': ['A', 'B']},
                      {'slot_key': 'q/tool', 'kind': 'choice', 'label': 'Tools', 'options': ['A', 'B'],
                       'interaction': {'adapter': 'candidate_choices', 'evidence': {'ready': True}}}]}
    def plan_for(*keys):
        return json.dumps({'kind': 'plan', 'question_key': 'q', 'observation_id': 'o',
                           'tasks': [{'task_id': 't%d' % i, 'slot_key': k, 'operation': 'choose_one',
                                      'desired': {'label': 'B'}} for i, k in enumerate(keys)]})
    assert planner.validate_context(planner.parse_plan(plan_for('q/real')), both).tasks[0].slot_key == 'q/real'
    with pytest.raises(ValueError, match='resolved offered slot the page itself marks up'):
        planner.validate_context(planner.parse_plan(plan_for('q/tool')), both)
