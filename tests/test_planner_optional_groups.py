"""A discovered group the model leaves alone is a decision, and the runtime must honour it (0.10.47 integration).

The Formative bundle (claude/formative-bundle 407854b) taught the BACKEND that a group the harness discovered
(interaction.adapter candidate_choices) is its own guess and may be left out of a plan -- a per-option tool row is
not an answer. The runtime keeps its own copy of the coverage rule and did not learn it, so on the merged tree a
plan the backend accepted was refused twice over:
  * planner_runtime.js validate() still required every resolved slot: "Plan does not cover every answerable slot."
  * once that was mirrored, the round loop saw the skipped group as "an answer control that appeared after the
    planned answers", re-offered it alone, the model skipped it again, and the empty plan died "Cannot execute an
    incomplete plan."
The bundle's own engine test could not see either: its mirror rule removes the tool row before the model is shown
it. These use the fixture's non-mirror row (?tools=distinct&chrome=none), which stays a discovered answer group.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

PAGE = 'tool_rows.html?tools=distinct&chrome=none'


def run(w, tid, plan):
    """plan='marked': only slots the page marks up. 'all': those plus the discovered group. 'discovered': only it."""
    return w.evaluate('''async ({id,plan})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      const offered=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        const slots=body.observation.slots.filter(s=>s.kind==='choice'||s.kind==='choice_set');
        offered.push(body.observation.slots.map(s=>s.interaction?.adapter||'marked'));
        const found=s=>s.interaction?.adapter==='candidate_choices';
        const wanted=plan==='all'?slots:plan==='discovered'?slots.filter(found):slots.filter(s=>!found(s));
        const tasks=wanted.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:s.kind==='choice_set'?'set_choice_set':'choose_one',
          desired:s.kind==='choice_set'?{labels:[s.options[2]]}:{label:s.options[2]},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:1}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,offered,events:r.events.map(e=>({detail:e.detail,failure_code:e.failure_code||null}))}}''',
      {'id': tid, 'plan': plan})


def test_the_page_really_offers_a_marked_up_answer_and_a_discovered_group(extension):
    page, w, tid = navigate(extension, PAGE)
    result = run(w, tid, 'marked')
    assert sorted(result['offered'][0]) == ['candidate_choices', 'marked'], result['offered']


def test_leaving_the_discovered_group_alone_finishes_with_one_plan(extension):
    page, w, tid = navigate(extension, PAGE)
    result = run(w, tid, 'marked')
    assert result['status'] == 'finished', result['events'][-3:]
    assert len(result['offered']) == 1, 'the skipped group was re-offered as if it had just appeared'
    assert not any('appeared after the planned answers' in e['detail'] for e in result['events'])
    assert page.evaluate('window.struck') == []                          # the tool row was never touched


def test_planning_the_discovered_group_too_is_still_allowed(extension):
    """Optional means optional: a model that DOES plan the discovered group must not be refused for it."""
    page, w, tid = navigate(extension, PAGE)
    result = run(w, tid, 'all')
    assert result['status'] == 'finished', result['events'][-3:]


def test_skipping_the_answer_the_page_marks_up_is_still_refused(extension):
    """Only the harness's own guesses are optional. A marked-up answer left out stops the run, nothing clicked."""
    page, w, tid = navigate(extension, PAGE)
    result = run(w, tid, 'discovered')
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] == 'QUESTION_INCOMPLETE')
    assert 'Plan does not cover every answerable slot' in stop['detail'], stop['detail']
    assert page.evaluate('window.picked') == [] and page.evaluate('window.struck') == []
