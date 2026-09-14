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
      bridge.request=async(phase,body)=>{globalThis.calls.push(phase);return {cost:.001,response:{kind:'plan',
        question_key:body.observation.question_key,observation_id:body.observation.observation_id,
        tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());await engine.observe();return true;}''',
      {'id': tid, 'label': label})


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
