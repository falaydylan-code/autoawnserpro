"""Opening a custom dropdown: the standard ways are tried in order, each proven by a visible menu that belongs to
the cell, and no rung ever chooses an option.

The live M3-2 run (9:19 PM): the statement's title-row date dropdown has no label, so the only accepted opener
evidence (button label == cell label, plus geometry) could never match; the harness reported no menu twice and
stopped. The fixture `dropdown_openers.html` builds the same unlabelled cell four ways.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def run(w, tid, label='For the Month Ended March 31'):
    return w.evaluate('''async ({id,label})=>{const h=__assignmentHarness;await AssignmentVisual.attach(id);
      const bridge=h.plannerBridge();bridge.config=async()=>({advance:false,auto_submit:false,spend_limit:2,model:'test'});
      bridge.request=async(phase,body)=>{
        if(phase==='verify')return {cost:.001,response:{kind:'verified'}};
        return {cost:.001,response:{kind:'plan',question_key:body.observation.question_key,observation_id:body.observation.observation_id,
          tasks:body.observation.slots.map((s,i)=>({task_id:'t'+i,slot_key:s.slot_key,operation:'set_selection',desired:{label},depends_on:[]}))}};};
      const engine=new AssignmentPlanner.Engine(bridge,id,await bridge.config());const r=await engine.run();
      return {status:r.status,events:r.events.map(e=>({phase:e.phase,detail:e.detail,failure_code:e.failure_code||null,purpose:e.click_details?.purpose||null,evidence:e.click_details?.evidence||null,timing:e.click_details?.timing||null,slow_input:e.slow_input||null}))};}''',
      {'id': tid, 'label': label})


@pytest.mark.parametrize('mode,rung', [('overlay', 'open_menu_by_geometry'), ('click', 'open_combobox'), ('keyboard', None)])
def test_unlabelled_dropdown_opens_by_the_first_rung_that_works(extension, mode, rung):
    page, w, tid = navigate(extension, f'dropdown_openers.html?mode={mode}')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#date_line .dropdownValue').inner_text() == 'For the Month Ended March 31'
    purposes = [e['purpose'] for e in result['events'] if e['purpose']]
    assert 'activate_cell' in purposes                                   # rung 1 always runs first
    if rung: assert rung in purposes, purposes
    else: assert 'open_menu_by_geometry' not in purposes and 'open_combobox' in purposes   # keyboard: click rung tried first, then keys
    assert purposes[-1] == 'choose_option'                               # an option is chosen only after a menu was proven open
    if mode == 'overlay':
        assert next(e for e in result['events'] if e['purpose'] == 'open_menu_by_geometry')['evidence'] == 'overlay_geometry'


def test_a_stray_button_outside_the_cell_is_never_clicked_and_the_stop_names_what_was_tried(extension):
    page, w, tid = navigate(extension, 'dropdown_openers.html?mode=stray')
    result = run(w, tid)
    assert result['status'] == 'needs_review'
    assert page.evaluate('clicks') == []                                 # the stray arrow was left alone
    assert page.locator('#date_line .dropdownValue').inner_text() == ''
    stop = next(e for e in result['events'] if e['failure_code'] == 'WRONG_MENU_OWNER')
    for tried in ('activate_cell', 'open_combobox', 'key:ArrowDown', 'key:Alt+ArrowDown'):
        assert tried in stop['detail'], stop['detail']


def test_labelled_dropdowns_still_use_their_labelled_trigger_first(extension):
    """The labelled path (this morning's M2-1 shape) is untouched: explicit evidence outranks geometry."""
    page, w, tid = navigate(extension, 'spreadsheet_text.html')
    obs = w.evaluate('''async id=>{const e=new AssignmentPlanner.Engine(__assignmentHarness.plannerBridge(),id,{});await AssignmentVisual.attach(id);
      const o=await e.observe();const s=o.slots.find(s=>s.kind==='selection');return {status:s.opening_control.status,geometry_only:!!s.opening_control.geometry_only}}''', tid)
    assert obs['geometry_only'] is False


def test_a_slow_click_does_not_starve_dropdown_discovery(extension):
    """The discovery loop's 5 s window also used to start before the activation click; a 5 s click left no time to
    find the arrow, so every dropdown ended OPTION_MISSING (12 of 12 at 5:11 PM). The window now starts after the click."""
    page, w, tid = navigate(extension, 'dropdown_openers.html?mode=overlay&slow=5200')
    result = run(w, tid)
    assert result['status'] == 'finished', result['events'][-3:]
    assert page.locator('#date_line .dropdownValue').inner_text() == 'For the Month Ended March 31'
    assert not any(e['failure_code'] == 'OPTION_MISSING' for e in result['events']), [e['detail'] for e in result['events'] if e['failure_code']]
    assert 'Read dropdown choices without clicking' in [e['detail'] for e in result['events']]       # choices were read BEFORE planning
    first = next(e for e in result['events'] if e['purpose'] == 'discover_activate_cell')
    assert first['timing']['input_ms'] >= 5000, first['timing']
    assert len([e for e in result['events'] if e['slow_input']]) == 1


def test_a_planned_blank_clears_a_filled_dropdown_and_leaves_an_empty_one_untouched(extension):
 """The executor treats "" like any other label: a cell showing a wrong choice is opened and its blank entry chosen;
 a cell already blank matches the plan and is skipped -- no menu opened, nothing clicked."""
 page,w,tid=navigate(extension,'dropdown_openers.html?mode=overlay&prefill=At+March+31')
 assert page.locator('#date_line .dropdownValue').inner_text()=='At March 31'
 result=run(w,tid,label='')
 assert result['status']=='finished',result['events'][-3:]
 assert page.locator('#date_line .dropdownValue').inner_text()==''                              # the wrong choice was blanked
 purposes=[e['purpose'] for e in result['events'] if e['purpose']]
 assert 'choose_option' in purposes and page.evaluate('opens')>=1                              # through the menu, like any option


def test_a_planned_blank_on_an_already_blank_dropdown_touches_nothing(extension):
 page,w,tid=navigate(extension,'dropdown_openers.html?mode=overlay')
 result=run(w,tid,label='')
 assert result['status']=='finished',result['events'][-3:]
 purposes=[e['purpose'] for e in result['events'] if e['purpose']]
 assert not any(p in purposes for p in ('activate_cell','open_menu_by_geometry','open_combobox','choose_option')), purposes   # already blank: execution skipped it
 assert page.evaluate('opens')==1 and page.locator('#date_line .dropdownValue').inner_text()==''            # the one open was discovery reading the choices
