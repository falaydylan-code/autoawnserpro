"""The failure modes the visual/ordering plan named that had no test yet.

Each one is a way the browser-input path could look like it worked when it
did not: the debugger refusing to attach, Stop arriving mid-gesture, a page
that accepts a click and discards the value, and a menu being opened counting
as an answer. Every one is driven through the loaded extension.
"""
import pytest
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def test_debugger_attach_failure_is_a_clear_stop_not_a_silent_no_op(extension):
    """If Chrome refuses the attach (DevTools open, another debugger), the
    visual path must say so and execute nothing -- never a pretend click that
    reports ok."""
    page, w, tid = navigate(extension, 'closed_dropdown.html')
    rect = page.locator('answer-box').bounding_box()
    point = {'x': (rect['x'] + rect['width'] / 2) / 1500, 'y': (rect['y'] + rect['height'] / 2) / 1100}
    result = w.evaluate('''async ({id,point})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Type',answer:'Liability',ref:null}]},p);
      const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);
      await AssignmentVisual.detach();                 // the run attaches at start; model the attach itself failing
      const real=chrome.debugger.attach;chrome.debugger.attach=async()=>{throw new Error('Another debugger is already attached');};
      try{return await h.executeAction(id,{action:'visual_click',purpose:'open',part_id:'a',observation_id:snap.id,point},p,{});}
      catch(e){return {threw:e.message};}finally{chrome.debugger.attach=real;}}''', {'id': tid, 'point': point})
    assert 'threw' in result and 'Browser input unavailable' in result['threw'], result
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_stop_during_a_reorder_drag_releases_the_mouse_and_moves_nothing(extension):
    """Stop mid-gesture must not leave the page with a held button or a half
    move. The adapter releases and the list is unchanged."""
    page, w, tid = navigate(extension, 'ordering.html')
    before = page.locator('li').all_text_contents()
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Order',parts:[{id:'o',what:'Order',kind:'ordering',answer:'ordered',ref:ref('order'),order:['revenue','expense','net'].map(ref),sequence:['Revenues','Expenses','Net Income']}]},p);
      const real=chrome.debugger.sendCommand;let moves=0;
      chrome.debugger.sendCommand=async (t,m,params)=>{if(params?.type==='mouseMoved'&&++moves===4){h.state.stopRequested=true;}return real(t,m,params);};
      try{return await h.executeAction(id,{action:'reorder',ref:ref('net'),to:ref('expense'),placement:'after',part_id:'o'},p,{});}
      catch(e){return {threw:e.message};}finally{chrome.debugger.sendCommand=real;h.state.stopRequested=false;}}''', tid)
    assert 'threw' in result or not result.get('ok'), result
    assert page.locator('li').all_text_contents() == before, 'a stopped drag must not have moved anything'
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_a_dropdown_selection_that_does_not_persist_is_not_verified(extension):
    """The page accepted the click but threw the value away. Only what the cell
    actually shows counts, so the part stays unverified and outstanding."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    # make cell_0_0's menu discard whatever is chosen: once it opens, every
    # option just closes the menu without writing the value
    page.evaluate('''()=>{const cell=document.getElementById("cell_0_0");const arrow=document.getElementById("arrow_0_0");
      const sabotage=()=>{for(const o of document.querySelectorAll("li[role=option]"))o.onclick=()=>{document.querySelector("ul").remove();cell.setAttribute("aria-expanded","false");};};
      const origCell=cell.onclick,origArrow=arrow.onclick;cell.onclick=e=>{origCell(e);sabotage();};arrow.onclick=e=>{origArrow(e);sabotage();};}''')
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    target = next(e for e in observed['elements'] if e['key'].endswith('#cell_0_0'))
    w.evaluate('(p)=>__assignmentHarness.coverage.read(p.action,p.page)',
               {'page': observed, 'action': {'question': 'Classify accounts', 'parts': [
                   {'id': 'a', 'what': 'Accounts Payable Account Type', 'answer': 'Liability', 'ref': target['ref']}]}})
    opened = w.evaluate('async a=>{const h=__assignmentHarness;return h.executeAction(a.id,a.action,await h.observeAllFrames(a.id),{});}',
                        {'id': tid, 'action': {'action': 'click', 'ref': target['ref'], 'part_id': 'a', 'purpose': 'open'}})
    assert opened['ok']
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),option=p.elements.find(e=>e.role==='option'&&e.name==='Liability');
      const r=await h.executeAction(id,{action:'click',ref:option.ref,part_id:'a',purpose:'answer'},p,{});await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''', tid)
    assert out['ok'], 'the click itself executed'
    assert page.locator('#cell_0_0').inner_text() == '', 'the page discarded the value'
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified'), 'executed is not verified'
    assert 'Accounts Payable Account Type' in w.evaluate('__assignmentHarness.coverage.outstanding().join("|")')


def test_opening_a_menu_is_preparation_and_an_option_from_another_cell_is_refused(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    target = next(e for e in observed['elements'] if e['key'].endswith('#cell_3_1'))
    assert target['row'] == 'Accounts Receivable' and target['column'] == 'Statement'
    w.evaluate('(p)=>__assignmentHarness.coverage.read(p.action,p.page)',
               {'page': observed, 'action': {'question': 'Classify accounts', 'parts': [
                   {'id': 's', 'what': 'AR statement', 'answer': 'Balance Sheet', 'ref': target['ref']}]}})
    out = w.evaluate('async a=>{const h=__assignmentHarness;return h.executeAction(a.id,a.action,await h.observeAllFrames(a.id),{});}',
                     {'id': tid, 'action': {'action': 'click', 'ref': target['ref'], 'part_id': 's', 'purpose': 'open'}})
    assert out['ok'] and out.get('preparation') and not out.get('needsVerification')
    ledger = w.evaluate('__assignmentHarness.coverage.ledger()[0]')
    assert not ledger['entered'] and not ledger['verified']
    assert page.locator('ul[role=listbox] li').count() == 2, 'the menu is open with its two options'
    # swap the open menu to a different cell; its option must be refused for part s
    page.evaluate('document.getElementById("cell_0_0").click()')
    refused = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),option=p.elements.find(e=>e.role==='option'&&e.name==='Asset');
      return h.executeAction(id,{action:'click',ref:option.ref,part_id:'s',purpose:'answer'},p,{});}''', tid)
    assert not refused['ok'] and 'belongs to the cell' in refused['detail'], refused
