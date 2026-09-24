"""A tab strip that declares no panels must not fork the question's identity (0.10.43).

McGraw Q12 (E4-15, 2026-09-21 12:38 PM, 0.10.42): the journal-entry worksheet's tabs 1 2 3 4 are bare
<input type=button role=tab> with no aria-controls and no tabpanel. The harness clicked tab 2 to reveal it,
looked once, and the question key had moved -- the transaction text tab 2 replaced was part of the identity --
so TARGET_STALE ended the run before any model call. Three things change here, all general:
  * planner_content.js infers the tab WIDGET when the page declares nothing: the single tab group's nearest box
    that holds a real answer control (never a tab or a button), below the question root, and only when an anchor
    survives outside it: 40+ characters of question text. Its contents leave the identity, as declared panels do;
    the tab count and VISIBLE labels join it. Model text is untouched.
    0.10.45: the anchor no longer requires a question-position element. The live McGraw frame has none
    (8:14 PM, 0.10.44: TARGET_MISSING "no question position outside the tab widget" on the same tab click), so
    0.10.43 never engaged on the page it was built for. The position still joins the key when a page has one.
    The tab signature reads the tab's value/text rather than its accessible name, because McGraw writes progress
    into aria-label ("Transaction Number 2 not yet entered ...") and an entry would otherwise move the key.
  * planner_runtime.js showPart settles on the requested part's OWN controls in its OWN frame (two agreeing
    polls of slots, key and the part's content; busy resets), asserts identity once on the settled view, and
    checks identity on the pre-click view. The aggregate key is hashed over frames with slots OR a tab strip,
    so an instant with zero slots no longer changes which frames make the key.
  * TARGET_STALE says what moved: the document, or which identity ingredient (stem, structure, position, tabs,
    frames).
Settling stays a bounded heuristic: a part whose text changes later, with no busy marker, is not caught.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate

TX = ['rent expired during the year, $1,190', 'supplies used during the year, $2,400', 'depreciation on equipment for the year, $3,100']
VALUES = {'General Journal row 1': '101', 'Debit row 1': '1190'}


def observe(w, tid):
    return w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      const f=o.frames.find(f=>f.parts?.length)||o.frames[0];
      return {question_key:o.question_key,identity:f.identity,frames:o.identity.frames,parts:o.parts.map(p=>({part_id:p.part_id,label:p.label,selected:p.selected})),
        slots:o.slots.map(s=>({slot_key:s.slot_key,label:s.label,part_id:s.part_id||null,part_scope:s.part_scope||null})),question:o.question}}''', tid)


def run(w, tid, values=VALUES, declared=3):
    """Scripted planner: enter_value on every slot; records what it was shown and every event with its data."""
    return w.evaluate('''async ({id,values,declared})=>{const h=__assignmentHarness;await AssignmentVisual.detach();await AssignmentVisual.attach(id);   // a fresh gesture per run: navigation cancels the old one
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      globalThis.planBodies=[];
      bridge.request=async(phase,body)=>{if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        globalThis.planBodies.push(body.observation);
        const tasks=body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'enter_value',desired:{value:values[s.label]??'1'},depends_on:[]}));
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,tasks,parts_declared:declared}};};
      globalThis.engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,failure_data:e.failure_data||null,slots:e.slots??null,purpose:e.click_details?.purpose||null})),
        bodies:globalThis.planBodies.map(o=>({question:o.question,slots:o.slots.length,parts:(o.parts||[]).map(p=>p.slots)}))}}''',
      {'id': tid, 'values': values, 'declared': declared})


def tab(page, n):
    page.locator('#worksheet [role=tab]').nth(n - 1).click()


def test_bare_input_tabs_without_panels_keep_the_question_identity_across_tabs(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html')
    first = observe(w, tid)
    assert [p['label'] for p in first['parts']] == ['1', '2', '3'] and first['parts'][0]['selected']
    assert first['identity']['inferred_widget'] is True and first['identity']['panels'] == 0 and first['identity']['tabs'] == '3:1/2/3'
    assert len(first['slots']) == 2 and all(s['part_scope'] == 'inferred' and s['part_id'] == first['parts'][0]['part_id'] for s in first['slots'])
    tab(page, 2)
    second = observe(w, tid)
    assert second['question_key'] == first['question_key'], 'switching tabs forked the question identity'
    assert second['parts'][1]['selected'] and all(s['part_id'] == first['parts'][1]['part_id'] for s in second['slots'])
    assert {s['slot_key'] for s in second['slots']}.isdisjoint({s['slot_key'] for s in first['slots']})     # same cell ids, own keys
    assert TX[1] in second['question'] and TX[0] not in second['question']                                    # the model reads the visible tab
    tab(page, 1)
    back = observe(w, tid)
    assert back['question_key'] == first['question_key'] and [s['slot_key'] for s in back['slots']] == [s['slot_key'] for s in first['slots']]


def test_tabs_beside_the_table_still_infer_the_box_not_the_strip(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?wrapper=1')
    first = observe(w, tid)
    assert first['identity']['inferred_widget'] is True and all(s['part_scope'] == 'inferred' for s in first['slots'])
    tab(page, 2)
    assert observe(w, tid)['question_key'] == first['question_key']


def test_a_run_reveals_every_tab_waits_for_each_rebuild_and_fills_all_of_them(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?delay=300')                                     # empty for longer than two polls
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert [b['parts'] for b in result['bodies']] == [[2, 2, 2]] and result['bodies'][0]['slots'] == 6      # no tab was recorded empty
    assert all(t in result['bodies'][0]['question'] for t in TX)                                             # every transaction reached the model
    assert page.evaluate('window.values') == [{'0_table0_cell_c1_r0': '101', '0_table0_cell_c2_r0': '1190'}] * 3
    assert page.evaluate('window.tabClicks')[:3] == [2, 3, 1]
    assert [e['slots'] for e in result['events'] if e['detail'].startswith('Revealed part')] == [2, 2]


def test_a_field_in_another_frame_does_not_make_an_empty_tab_look_settled(extension):
    page, w, tid = navigate(extension, 'worksheet_parent.html')
    result = run(w, tid, {**VALUES, 'Scratch notes': 'workings'})
    assert result['status'] == 'finished', result['events'][-3:]
    assert result['bodies'][0]['parts'] == [2, 2, 2] and result['bodies'][0]['slots'] == 7
    frame = page.frame_locator('iframe')
    assert frame.locator('[id="0_table0_cell_c1_r0"]').input_value() == '101'


def test_declared_panels_without_a_platform_id_are_unchanged(extension):
    page, w, tid = navigate(extension, 'tabs_parts.html')
    page.evaluate("()=>document.querySelector('main').removeAttribute('data-question-id')")
    first = observe(w, tid)
    assert first['identity']['inferred_widget'] is False and first['identity']['panels'] == 2 and first['identity']['tabs'] == ''
    assert all(s['part_scope'] == 'panel' for s in first['slots'])
    page.click('#tab-bs')
    assert observe(w, tid)['question_key'] == first['question_key']


def test_a_different_question_on_the_same_url_gets_a_different_key(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html')
    base = observe(w, tid)['question_key']
    page.evaluate("()=>{position.textContent='Question 13 of 21'}"); moved_position = observe(w, tid)['question_key']
    page.evaluate("()=>{position.textContent='Question 12 of 21';required.firstChild.textContent='Required (revised):'}"); moved_stem = observe(w, tid)['question_key']
    page.evaluate("()=>{required.firstChild.textContent='Required:';tabs.insertAdjacentHTML('beforeend','<input type=button role=tab value=4 aria-selected=false>')}"); moved_tabs = observe(w, tid)['question_key']
    assert len({base, moved_position, moved_stem, moved_tabs}) == 4


def test_a_document_replaced_by_the_tab_click_is_named(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?docswap=1')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    stop = next(e for e in result['events'] if e['failure_code'] == 'TARGET_STALE')
    assert 'Document was replaced' in stop['detail']                                                        # the frame guard or showPart, whichever looks first


def test_without_question_text_outside_the_box_nothing_is_inferred_and_the_switch_stops_honestly(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?shorttext=1')
    first = observe(w, tid)
    assert first['identity']['inferred_widget'] is False and 'fewer than 40 characters' in first['identity']['no_inference']
    assert all(s['part_scope'] == 'fallback' for s in first['slots'])
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    # 0.10.46: the stop is now the honest one. Ownership no longer depends on the scope label, so the tab IS
    # accepted -- but with no anchor the widget cannot leave the identity, so the switch moves the question's own
    # fingerprint and the run stops on that instead. Either way: one tab click, nothing entered, no guess.
    stop = next(e for e in result['events'] if e['failure_code'] == 'TARGET_STALE')
    assert 'Question identity changed' in stop['detail'] and 'stem' in stop['detail'], stop['detail']
    assert not any(e['detail'].startswith('Revealed part') for e in result['events'])                         # nothing recorded for the part
    assert [e['purpose'] for e in result['events'] if e['purpose']] == ['show_part']                         # one tab click, no answer input
    assert page.evaluate('window.values') == [{}, {}, {}]


def test_a_page_without_a_position_marker_is_still_anchored_by_its_question_text(extension):
    """The live McGraw frame: no aria-current, no .question-number, tabs 1 2 3 with no panels (8:14 PM log)."""
    for variant in ['noposition=1', 'inpos=1']:
        page, w, tid = navigate(extension, 'worksheet_tabs.html?' + variant)
        first = observe(w, tid)
        assert first['identity']['inferred_widget'] is True and first['identity']['position'] == '' and 'no_inference' not in first['identity'], variant
        assert first['identity']['tabs'] == '3:1/2/3' and all(s['part_scope'] == 'inferred' for s in first['slots']), variant
        tab(page, 2)
        assert observe(w, tid)['question_key'] == first['question_key'], variant
        tab(page, 1)
        result = run(w, tid)
        assert result['status'] == 'finished', (variant, result['events'][-3:])
        assert result['bodies'][0]['parts'] == [2, 2, 2] and all(t in result['bodies'][0]['question'] for t in TX), variant
        assert page.evaluate('window.values') == [{'0_table0_cell_c1_r0': '101', '0_table0_cell_c2_r0': '1190'}] * 3, variant


def test_progress_written_into_the_tab_label_does_not_move_the_key(extension):
    """McGraw's tabs are named "Transaction Number N not yet entered <text>"; the name flips once a value is in."""
    page, w, tid = navigate(extension, 'worksheet_tabs.html?status=1&noposition=1')
    first = observe(w, tid)
    assert all(p['label'].startswith('Transaction Number %d not yet entered' % (i + 1)) and t in p['label'] for i, (p, t) in enumerate(zip(first['parts'], TX)))   # the model reads the full name
    assert first['identity']['tabs'] == '3:1/2/3'                                                             # the key reads what the student sees
    page.fill('[id="0_table0_cell_c1_r0"]', '101')
    assert page.get_attribute('#worksheet [role=tab]', 'aria-label').startswith('Transaction Number 1 entered')
    after = observe(w, tid)
    assert after['question_key'] == first['question_key'] and after['identity']['tabs'] == first['identity']['tabs']
    assert after['parts'][0]['label'].startswith('Transaction Number 1 entered')
    page.fill('[id="0_table0_cell_c1_r0"]', '')
    result = run(w, tid)                                                                                      # every entry flips a label mid-run
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.evaluate('window.values') == [{'0_table0_cell_c1_r0': '101', '0_table0_cell_c2_r0': '1190'}] * 3


def test_two_tab_groups_prevent_inference(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?twostrips=1')
    first = observe(w, tid)
    assert first['identity']['inferred_widget'] is False and first['identity']['no_inference'] == 'more than one tab group'


def test_a_late_description_behind_a_busy_marker_is_waited_for(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html?latetext=1')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert all(t in result['bodies'][0]['question'] for t in TX)                                             # the final text, not the stale one


def test_the_stale_message_names_the_ingredient_that_moved(extension):
    page, w, tid = navigate(extension, 'worksheet_tabs.html')
    messages = w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});const o=await e.observe();
      e.current={key:o.question_key,document:o.document_id,identity:o.identity,recovery:new AssignmentPlanner.Recovery()};const out=[];
      const probe=async()=>{try{e.same(await e.observe());out.push('same')}catch(x){out.push(x.message)}};
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.getElementById('required').firstChild.textContent='Required (revised):'}});await probe();
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.getElementById('required').firstChild.textContent='Required:';document.getElementById('position').textContent='Question 13 of 21'}});await probe();
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.getElementById('position').textContent='Question 12 of 21';document.querySelector('main').insertAdjacentHTML('beforeend','<label>Extra <input id="extra"></label>')}});await probe();
      await chrome.scripting.executeScript({target:{tabId:id},func:()=>{document.getElementById('extra').parentElement.remove()}});await probe();return out}''', tid)
    assert messages[0].startswith('TARGET_STALE: Question identity changed (stem)')
    assert messages[1].startswith('TARGET_STALE: Question identity changed (') and 'position' in messages[1]   # the number is also text
    assert messages[2].startswith('TARGET_STALE: Question identity changed (') and 'structure' in messages[2]  # the label is also text
    assert messages[3] == 'same'
