"""SmartBook's drag-and-drop matching question (2026-09-24 9:17 PM log): the harness found ZERO answer slots.

SmartBook renders the OLD react-beautiful-dnd (data-react-beautiful-dnd-droppable / -draggable / -drag-handle); the
content script only knew v12's data-rbd-droppable-id. Now each drop zone beside its own prompt is offered as an
ordinary pick-one (label = prompt, options = every card's text, current = the card in the zone), the runtime enters
it by dragging the card onto the zone, and it counts only when the zone reads back with that card in it. Found by
structure (droppables, cards that carry a drag handle, repeated prompt rows), not by SmartBook's class names.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

RIGHT = {'Accounts receivable': 'Current asset', 'Bonds payable': 'Long-term liability', 'Common stock': 'Owner equity'}


def run(w, tid, answers):
    """Scripted planner: set_selection on every slot, the card named by answers[slot label]."""
    return w.evaluate('''async ({id,answers})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,check_work:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const tasks=body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label:answers[s.label]??''},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:1}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null})),bodies:globalThis.planBodies}}''',
      {'id': tid, 'answers': answers})


def test_every_drop_zone_is_offered_as_a_pick_one_with_its_prompt_and_every_card(extension):
    page, w, tid = navigate(extension, 'smartbook_matching.html')
    result = run(w, tid, RIGHT)
    obs = result['bodies'][0]
    slots = obs['slots']
    assert [s['label'] for s in slots] == ['Accounts receivable', 'Bonds payable', 'Common stock'], slots
    for s in slots:
        assert s['kind'] == 'selection' and s['current'] == '' and s['interaction']['adapter'] == 'drag_match'
        # the visible card text; not the aria-label number, not the 1px "Choice 1 of 3", not a placeholder twice
        assert s['options'] == ['Current asset', 'Long-term liability', 'Owner equity'], s['options']
        assert 'cards' not in s                                                     # element tokens never reach the model
    assert 'Match each account' in obs['question'] and 'Each choice is used once' in obs['question']
    assert 'Current asset' not in obs['question']                                   # cards are options, not question text


def test_the_cards_are_dragged_into_their_zones_and_read_back(extension):
    page, w, tid = navigate(extension, 'smartbook_matching.html')
    result = run(w, tid, RIGHT)
    assert result['status'] == 'finished', result['events'][-4:]
    assert page.evaluate('window.placed') == [0, 1, 2]
    assert page.evaluate('window.drags') == 3                                       # one drag per zone, none repeated
    assert not page.evaluate('window.submitted || false')                           # entering answers never hands in
    # The widget redrew itself on every drop, yet each zone is still found under the key it was planned with (the key
    # is the zone's place among the zones), and now reads back the card it holds. Nothing is dragged a second time.
    again = run(w, tid, RIGHT)
    before, after = result['bodies'][0]['slots'], again['bodies'][0]['slots']
    assert [s['slot_key'] for s in after] == [s['slot_key'] for s in before]
    assert [s['current'] for s in after] == ['Current asset', 'Long-term liability', 'Owner equity']
    assert page.evaluate('window.drags') == 3


def test_one_card_planned_for_two_zones_is_refused_before_any_drag(extension):
    page, w, tid = navigate(extension, 'smartbook_matching.html')
    result = run(w, tid, {**RIGHT, 'Bonds payable': 'Current asset'})
    assert result['status'] != 'finished'
    assert any('One matching card was planned for two drop zones' in e['detail'] for e in result['events']), result['events'][-4:]
    assert page.evaluate('window.drags') == 0


def test_a_drag_the_page_ignores_stops_the_run_and_says_so(extension):
    page, w, tid = navigate(extension, 'smartbook_matching.html?drop=never')
    result = run(w, tid, RIGHT)
    assert result['status'] != 'finished'
    assert any(e['failure_code'] == 'INPUT_NO_EFFECT' and 'did not land in its drop zone' in e['detail'] for e in result['events']), result['events'][-4:]


def test_two_zones_with_one_prompt_are_not_claimed(extension):
    """Structure the harness cannot name unambiguously is left alone -- the page reports no answer slots, as before."""
    page, w, tid = navigate(extension, 'smartbook_matching.html?extra=zone')
    result = run(w, tid, RIGHT)
    assert not any(s.get('interaction', {}).get('adapter') == 'drag_match' for b in result['bodies'] for s in b['slots'])
    assert page.evaluate('window.drags') == 0
