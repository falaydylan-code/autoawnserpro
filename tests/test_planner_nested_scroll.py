"""A target inside a scrolling list, inside an iframe, inside a scrolling pane: move the list, not the page.

The live M3-9 run (12:20 PM): 'Service Revenue' is item 22 of 25 in an account list. The outer page (frame 0,
`node:3`) was scrolled 472 px to chase the option's rendered position, which put the open list under the fixed
header (page y=-33); the wheel meant for the list then landed on the header at (383,43) and nothing moved --
`moved:false` beside `wheel_hit:true`, then the identical retry, then REPEATED_STATE.

The reveal step must ask outer layers to show the scroll area that has to move, never the target itself, and
must refuse a wheel point that an outer layer covers. The page below is the live page's shape: a fixed 97 px
header, a scrolling pane at (205,97) 1214x686, the question iframe 21 px inside it, and the fixture's dropdown
extended to 27 options so the wanted one renders 728 px below the list top.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate
from test_planner_executor import BOOT

HEADER = 97
PANE = {'top': 97, 'left': 205, 'width': 1214, 'height': 686}
FRAME_TOP = PANE['top'] + 21          # page y of the iframe's top edge
WANTED = 'Extra 19'                    # option index 26 -> 26 * 28 px = 728 px below the list top


def framed_pane(extension, list_top, prescroll=0, overlay=None, custom_scrollbar=False):
    """scroll_dropdown.html inside an iframe inside a scrolling pane under a fixed header, its list opened at
    in-frame y=list_top (page y = FRAME_TOP + list_top). Returns page, worker, tab id, frame locator."""
    page, w, tid = navigate(extension, 'planner_standard.html')
    page.evaluate('''p=>{document.body.style.margin='0';document.body.innerHTML=`
      <div id="hdr" style="position:fixed;top:0;left:0;right:0;height:${p.HEADER}px;background:#dde;z-index:5">Study Mode: Homework</div>
      <div id="pane" style="position:absolute;top:${p.PANE.top}px;left:${p.PANE.left}px;width:${p.PANE.width}px;height:${p.PANE.height}px;overflow:auto">
        <div style="height:21px"></div><iframe src="scroll_dropdown.html" style="display:block;width:1100px;height:1700px;border:0"></iframe></div>`}''',
      {'HEADER': HEADER, 'PANE': PANE})
    frame = page.frame_locator('iframe')
    frame.locator('#row1').wait_for()
    frame.locator('body').evaluate('''(body,{list_top,custom})=>{const d=body.ownerDocument;
      for(let i=0;i<20;i++)choices.push('Extra '+i);                           // 27 options, 4 visible at a time
      const row=d.getElementById('row1');
      const spacer=d.createElement('div');d.querySelector('main').before(spacer);
      activate(row);openMenu();                                                // rebuild the menu with 27 options
      const menu=d.getElementById('menu');
      for(let pass=0;pass<3;pass++){                                             // margins collapse differently once the spacer exists
        spacer.style.height=Math.max(0,parseFloat(spacer.style.height||'0')+list_top-menu.getBoundingClientRect().top)+'px';
        activate(row);openMenu();}                                               // reposition below the spacer
      if(custom){const wrapper=d.createElement('div');menu.before(wrapper);wrapper.append(menu);menu.style.overflowY='hidden';
        const rail=d.createElement('div');rail.className='nicescroll-rails-vr';rail.style.cssText='position:absolute;right:0;top:0;width:8px;height:112px';wrapper.append(rail);
        menu.addEventListener('wheel',e=>{e.preventDefault();menu.scrollTop+=e.deltaY},{passive:false});}
    }''', {'list_top': list_top, 'custom': custom_scrollbar})
    assert abs(frame.locator('#menu').evaluate('e=>e.getBoundingClientRect().top') - list_top) < 2
    if prescroll:
        page.evaluate('n=>{document.getElementById("pane").scrollTop=n}', prescroll)
    if overlay:
        page.evaluate('''r=>{const x=document.createElement('div');x.id='cover';x.style.cssText=`position:fixed;left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px;background:rgba(255,255,255,.95);z-index:9`;
          x.textContent='cookie banner';document.body.append(x)}''', overlay)
    return page, w, tid, frame


def execute_wanted(w, tid):
    """Run one set_selection for row1 with the wanted label; record every wheel the engine sends."""
    w.evaluate(BOOT, tid)
    return w.evaluate('''async label=>{const obs=await engine.observe(),s=obs.slots[1];
      engine.current={key:obs.question_key,document:obs.document_id,recovery:new AssignmentPlanner.Recovery()};
      globalThis.wheels=[];const wheel=AssignmentVisual.wheel;AssignmentVisual.wheel=async(tab,point,dx,dy,cancel)=>{wheels.push({point,dx,dy});return wheel(tab,point,dx,dy,cancel)};
      try{await engine.execute({task_id:'nested',slot_key:s.slot_key,operation:'set_selection',desired:{label}});return {ok:true,wheels,events:engine.ledger.events}}
      catch(e){return {code:e.code,detail:e.message,wheels,events:engine.ledger.events}}
      finally{AssignmentVisual.wheel=wheel}}''', WANTED)


def scrolls(result):
    return [e['scroll_details'] for e in result['events'] if e.get('scroll_details')]


@pytest.mark.parametrize('custom_scrollbar', [False, True])
def test_a_list_in_view_scrolls_itself_and_the_pane_stays_put(extension, custom_scrollbar):
    # List at page 418..530, inside the pane; the wanted option renders at page 1146, below the pane's bottom (783).
    page, w, tid, frame = framed_pane(extension, list_top=300, custom_scrollbar=custom_scrollbar)
    result = execute_wanted(w, tid)
    assert result.get('ok'), result
    assert frame.locator('#row1 span').inner_text() == WANTED
    assert page.evaluate('document.getElementById("pane").scrollTop') == 0          # the page never moved
    assert scrolls(result) and all(s['moved'] for s in scrolls(result))
    assert {s['adapter'] for s in scrolls(result)} == {'nicescroll_wheel' if custom_scrollbar else 'native_wheel'}
    assert all(s['container'] != 'id:pane' and s['after']['role'] == 'listbox' for s in scrolls(result))
    assert result['wheels'] and all(HEADER <= x['point']['y'] < PANE['top'] + PANE['height'] for x in result['wheels'])


@pytest.mark.parametrize('custom_scrollbar', [False, True])
def test_a_list_left_under_the_header_is_brought_back_before_it_is_scrolled(extension, custom_scrollbar):
    # The exact live state: pane already scrolled so the open list sits at page -33..79, under the 97 px header.
    page, w, tid, frame = framed_pane(extension, list_top=300, prescroll=451, custom_scrollbar=custom_scrollbar)
    result = execute_wanted(w, tid)
    assert result.get('ok'), result
    assert frame.locator('#row1 span').inner_text() == WANTED
    first = scrolls(result)[0]
    assert first['adapter'] == 'native_wheel' and first['delta']['y'] < 0 and first['moved']   # the pane scrolls UP
    assert first['after']['role'] is None and first['before']['top'] == 451
    assert any(s['after']['role'] == 'listbox' and s['moved'] for s in scrolls(result))
    assert all(HEADER <= x['point']['y'] for x in result['wheels'])                         # nothing sent to the header


def test_a_list_below_the_pane_is_revealed_by_the_pane_then_scrolled_itself(extension):
    # List at page 918..1030, below the pane's bottom (783): the pane must move first, toward the LIST.
    page, w, tid, frame = framed_pane(extension, list_top=800)
    result = execute_wanted(w, tid)
    assert result.get('ok'), result
    assert frame.locator('#row1 span').inner_text() == WANTED
    first = scrolls(result)[0]
    assert first['after']['role'] is None and first['moved'] and first['delta']['y'] > 0
    # Toward the list's centre (page 974 -> pane centre 440 = 534), not toward the option (1646 -> clamped 600).
    assert abs(first['after']['top'] - 534) < 40, first
    assert any(s['after']['role'] == 'listbox' and s['moved'] for s in scrolls(result))


def test_a_wheel_point_covered_by_an_outer_layer_is_refused_before_anything_is_sent(extension):
    # The list (page 418..530) is inside the pane, but a fixed banner in the top page covers its middle (440..560):
    # no wheel, no click, a named stop.
    page, w, tid, frame = framed_pane(extension, list_top=300, overlay={'x': 205, 'y': 440, 'w': 1214, 'h': 120})
    result = execute_wanted(w, tid)
    assert result.get('code') == 'GUARD_REJECTED', result
    assert 'outer layer covers' in result['detail']
    assert result['wheels'] == []
    assert not any(e.get('click_details', {}).get('purpose') == 'choose_option' for e in result['events'])
    assert frame.locator('#row1 span').inner_text() == ''
    assert page.evaluate('document.getElementById("pane").scrollTop') == 0
