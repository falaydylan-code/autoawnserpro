"""Reaching a question's parts when the page does not spell them out (0.10.46).

Two live McGraw failures, one rule each:

  * Ch.3 Q1 (2026-09-23 21:32): the tabs are `<li role=tab>` with no `aria-controls`, and the page separately
    renders a `role=tabpanel` that no tab claims. Panels existed, so the box was never inferred; no tab owned a
    panel, so every cell was scoped `fallback`; and `showPart` only accepted `panel` or `inferred`. A tab that was
    plainly selected, with its cells on screen, could never be worked on -> TARGET_MISSING after 5 s, no model call.
    Ownership is now judged by what is there: the tab is lit, the frame holds answer controls, no other part claims
    them. The scope labels keep their own job in the identity key.

  * A question whose parts are plain numbered buttons is not multi-part to the harness at all, because parts are
    only ever `role=tab`. The model already reports how many parts the WORDING names (`parts_declared`), and the
    harness already stops rather than finish short. It now looks once, before stopping, for a switcher the page
    built out of ordinary controls -- and only then. The model supplies the count and nothing else: which controls
    exist, whether they are a group, which one is current, and whether the page actually changed are the page's
    answers. A group with no current-marker is never a candidate; a group that does not promote is dropped.

Nothing here costs an extra model call on a simple question: the count rides on the plan reply that already
happens, and the search only runs when that count exceeds the parts found.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate
from test_planner_worksheet_tabs import observe


def run(w, tid, values, declared=1):
    """Scripted planner: fills the answerable value cells it is shown and leaves everything else alone.

    Unlike the worksheet-tabs helper it does not plan every slot blindly -- a row of numbered buttons is offered as
    an unresolved candidate choice group until it is asserted as the part switcher, and a real model would not name
    an unresolved slot either.
    """
    return w.evaluate('''async ({id,values,declared})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const answerable=body.observation.slots.filter(s=>s.kind==='value');
        const tasks=answerable.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label]??'1'},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:declared}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,slots:e.slots??null,purpose:e.click_details?.purpose||null})),
        bodies:globalThis.planBodies.map(o=>({question:o.question,slots:o.slots.length,parts:(o.parts||[]).map(p=>p.slots)}))}}''',
      {'id': tid, 'values': values, 'declared': declared})


def events(result, phrase):
    return [e for e in result['events'] if phrase in e['detail']]


def test_tabs_that_declare_an_unclaimed_panel_are_owned_by_the_selected_tab(extension):
    """Ch.3 Q1: panels exist, no tab claims one, so every cell is fallback-scoped."""
    page, w, tid = navigate(extension, 'half_declared_tabs.html')
    first = observe(w, tid)
    assert [p['label'] for p in first['parts']] == ['Cash Basis', 'Accrual Basis'] and first['parts'][0]['selected']
    assert first['identity']['panels'] == 1 and first['identity']['inferred_widget'] is False   # the orphan panel blocks inference
    assert all(s['part_scope'] == 'fallback' for s in first['slots'])                           # and nothing can be scoped
    page.click('#tab-2')
    second = observe(w, tid)
    assert second['parts'][1]['selected'] and second['question_key'] == first['question_key']
    assert {s['slot_key'] for s in second['slots']}.isdisjoint({s['slot_key'] for s in first['slots']})


def test_a_run_fills_both_halves_of_a_half_declared_tab_widget(extension):
    page, w, tid = navigate(extension, 'half_declared_tabs.html?slow=300')
    result = run(w, tid, {'Cash Sales': '4100', 'Customer Deposits': '250'}, declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['bodies'][0]['parts'] == [2, 2] and result['bodies'][0]['slots'] == 4
    assert page.evaluate('window.values') == [{'0_table0_cell_c1_r4': '4100', '0_table0_cell_c1_r5': '250'}] * 2
    assert page.evaluate('window.tabClicks')[:2] == [2, 1]


def test_an_unmarked_tab_strip_stops_instead_of_mixing_the_parts_up(extension):
    """No tab says which one is showing. Every part then keys its slots the same way, so one part's answer would be
    written under another's name -- the old code reached 'Logical answer slot is not unique' after entering one."""
    page, w, tid = navigate(extension, 'half_declared_tabs.html?noselect=1')
    result = run(w, tid, {'Cash Sales': '4100', 'Customer Deposits': '250'}, declared=2)
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] == 'TARGET_MISSING')
    assert 'does not say which one is showing' in stop['detail'], stop['detail']
    assert page.evaluate('window.values') == [{}, {}]                                           # nothing entered anywhere


def test_numbered_buttons_become_parts_only_because_the_wording_names_two(extension):
    page, w, tid = navigate(extension, 'numbered_parts.html')
    first = observe(w, tid)
    # Not multi-part on sight: no parts at all, and the numbered row is offered only as an unresolved
    # candidate choice group -- never as a part, until the wording's count says otherwise.
    assert first['parts'] == [] and [s['label'] for s in first['slots']] == ['Debit amount', 'Answer choices']
    result = run(w, tid, {'Debit amount': '780'}, declared=2)
    assert result['status'] == 'finished', result['events'][-3:]
    assert events(result, "Treating 2 page controls as this question's parts"), result['events'][-4:]
    assert page.evaluate('window.values') == [{'0_table0_cell_c1_r0': '780'}] * 2
    assert page.evaluate('window.switchClicks'), 'the switcher was never used'


def test_a_single_part_question_never_touches_the_switcher(extension):
    """The search runs only when the count exceeds what was found: a simple question pays nothing and is not clicked."""
    page, w, tid = navigate(extension, 'numbered_parts.html')
    result = run(w, tid, {'Debit amount': '780'}, declared=1)
    assert page.evaluate('window.switchClicks') == []                                           # never clicked
    assert not events(result, 'part switcher') and not events(result, 'Treating')               # never even looked
    assert page.evaluate('window.values') == [{'0_table0_cell_c1_r0': '780'}, {}]               # the visible part is answered
    # The run still ends needs_review, on the PRE-EXISTING leftovers rule: the numbered row is offered as an
    # unresolved candidate choice group and an unresolved group left on the page blocks a clean finish. That is the
    # open "unresolved leftovers" item, not this change; asserted here so it is visible when it is fixed.
    assert result['status'] == 'needs_review'
    assert events(result, 'Answer group needs more interaction evidence')


def test_a_switcher_that_never_says_which_one_is_current_is_not_a_candidate(extension):
    page, w, tid = navigate(extension, 'numbered_parts.html?nomarker=1')
    result = run(w, tid, {'Debit amount': '780'}, declared=2)
    assert result['status'] == 'needs_review'
    assert events(result, 'shows no part switcher the harness can read back'), result['events'][-4:]
    stop = next(e for e in result['events'] if e['failure_code'] == 'QUESTION_INCOMPLETE')
    assert 'PART_UNREACHABLE' in stop['detail']
    assert page.evaluate('window.switchClicks') == []


def test_previous_next_chrome_is_never_read_as_a_part_switcher(extension):
    page, w, tid = navigate(extension, 'numbered_parts.html?chrome=1')
    result = run(w, tid, {'Debit amount': '780'}, declared=2)
    assert result['status'] == 'needs_review'
    assert events(result, 'shows no part switcher the harness can read back'), result['events'][-4:]
    assert page.evaluate('window.switchClicks') == []


def test_a_switcher_that_changes_nothing_is_refused_and_the_question_stops(extension):
    """Marked current, looks like a switcher, does nothing when clicked: the page's own report is the last word."""
    page, w, tid = navigate(extension, 'numbered_parts.html?inert=1')
    result = run(w, tid, {'Debit amount': '780'}, declared=2)
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] in ('QUESTION_INCOMPLETE', 'TARGET_MISSING'))
    assert 'PART_UNREACHABLE' in stop['detail'] or 'did not become selected' in stop['detail'], stop['detail']
    assert page.evaluate('window.values')[1] == {}                                              # nothing written to a part that never appeared
