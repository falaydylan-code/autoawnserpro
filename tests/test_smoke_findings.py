"""What the first MiniMax smoke run on the dropdown fixture exposed.

The model planned all twenty cells correctly and opened the first menu, then the
harness fought it over form rather than substance: it said `select` on a menu
option instead of `click`, and it sharpened "Equity" to "Stockholders' Equity"
once it could see the real label. Both stopped the run. Neither should.
"""
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def plan_ap_type(w, tid, answer):
    return w.evaluate('''async ({id,answer})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'Accounts Payable Account Type',answer,ref:cell.ref}]},p);
      return h.coverage.ledger()[0];}''', {'id': tid, 'answer': answer})


def test_select_on_a_custom_menu_option_is_treated_as_the_click_it_is(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    plan_ap_type(w, tid, 'Liability')
    opened = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      return h.executeAction(id,{action:'click',ref:cell.ref,part_id:'a',purpose:'open'},p,{});}''', tid)
    assert opened['ok']
    # the model says `select` on the <li role=option>, and forgets part_id
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),option=p.elements.find(e=>e.role==='option'&&e.name==='Liability');
      const r=await h.executeAction(id,{action:'select',ref:option.ref,option:'Liability'},p,{});await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''', tid)
    assert out['ok'] and out.get('needsVerification'), out
    assert page.locator('#cell_0_0').inner_text() == 'Liability'
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_select_naming_the_cell_and_option_text_resolves_to_that_option(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    plan_ap_type(w, tid, 'Liability')
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      return h.executeAction(id,{action:'click',ref:cell.ref,part_id:'a',purpose:'open'},p,{});}''', tid)
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      const r=await h.executeAction(id,{action:'select',ref:cell.ref,option:'Liability',part_id:'a'},p,{});await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''', tid)
    assert out['ok'], out
    assert page.locator('#cell_0_0').inner_text() == 'Liability'
    # and a wrong option name against an OPEN menu is refused with the real
    # choices, rather than guessed
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_1_0'));
      h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'Accounts Payable Account Type',answer:'Liability',ref:p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref},{id:'b',what:'Common Stock Account Type',answer:'Equity',ref:cell.ref}]},p);
      await h.executeAction(id,{action:'click',ref:cell.ref,part_id:'b',purpose:'open'},p,{});}''', tid)
    assert page.locator('ul[role=listbox] li').count() == 5, 'the menu is open'
    refused = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_1_0'));
      return h.executeAction(id,{action:'select',ref:cell.ref,option:'Equity',part_id:'b'},p,{});}''', tid)
    assert not refused['ok'] and 'No option "Equity"' in refused['detail'] and "Stockholders' Equity" in refused['detail'], refused


def test_sharpening_an_unentered_answer_to_the_visible_label_is_a_refinement_not_a_change(extension):
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    plan_ap_type(w, tid, 'Equity')
    # re-read after seeing the menu: the label the page offers is longer
    refined = plan_ap_type(w, tid, "Stockholders' Equity")
    assert refined['answer'] == "Stockholders' Equity"
    assert w.evaluate('__assignmentHarness.coverage.questions.size') == 1
    # a not-yet-entered answer may change freely: the model is still deciding
    message = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const read=a=>h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'Accounts Payable Account Type',answer:a,ref:p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref}]},p);
      read('Asset');read('Revenue');read('Liability');
      return {revised:h.coverage.revised.length,answer:h.coverage.ledger()[0].answer};}''', tid)
    assert message['revised'] == 0 and message['answer'] == 'Liability', message


def test_a_change_after_entry_resets_the_part_and_a_second_change_is_refused(extension):
    """Before entry the answer may change freely. Once a value has been entered,
    changing it is taken once -- the part goes back to unentered -- and refused
    the second time. Changing back and forth is the oscillation guard."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    plan_ap_type(w, tid, 'Liability')
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      await h.executeAction(id,{action:'click',ref:cell.ref,part_id:'a',purpose:'open'},p,{});
      const q=await h.observeAllFrames(id),option=q.elements.find(e=>e.role==='option'&&e.name==='Liability');
      await h.executeAction(id,{action:'click',ref:option.ref,part_id:'a',purpose:'answer'},q,{});}''', tid)
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].entered')
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const read=a=>h.coverage.read({question:'Classify accounts',parts:[{id:'a',what:'Accounts Payable Account Type',answer:a,ref:p.elements.find(e=>e.key.endsWith('#cell_0_0')).ref}]},p);
      read('Asset');const after=h.coverage.ledger()[0];
      try{read('Liability');return {after,second:'accepted'};}catch(e){return {after,second:e.message};}}''', tid)
    assert result['after']['answer'] == 'Asset' and not result['after']['entered'] and not result['after']['verified'], 'taken once, and the part is reset'
    assert 'Plan changed again' in result['second']


def test_a_rephrased_re_read_pointing_at_the_same_cells_is_the_same_question(extension):
    """Fourth smoke run: the model re-read mid-table with a different stem, the
    text hash changed, and the harness opened a new seven-part question while
    the correct twenty-part plan sat orphaned. The controls are the identity."""
    page, w, tid = navigate(extension, 'custom_dropdowns.html')
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const cells=p.elements.filter(e=>e.dropdown);
      h.coverage.read({question:'Classify each account by type and statement',
        parts:cells.map((c,i)=>({id:'p'+i,what:c.row+' '+c.column,answer:c.column==='Statement'?'Balance Sheet':'Asset',ref:c.ref}))},p);}''', tid)
    assert w.evaluate('__assignmentHarness.coverage.current.parts.size') == 20
    # a rephrased stem, naming only the Statement column, pointing at cells the plan owns
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      const cells=p.elements.filter(e=>e.dropdown&&e.column==='Statement').slice(0,7);
      h.coverage.read({question:'Fill the Statement column for the remaining rows',
        parts:cells.map((c,i)=>({id:'s'+i,what:c.row+' Statement',answer:'Balance Sheet',ref:c.ref}))},p);}''', tid)
    assert w.evaluate('__assignmentHarness.coverage.questions.size') == 1, 'same controls, same question'
    assert w.evaluate('__assignmentHarness.coverage.current.parts.size') == 20, 'one cell, one part: new ids for owned cells refer to the existing parts'
    # a genuinely different question -- none of its controls are ours -- is still new
    page.evaluate('''()=>{const f=document.createElement('fieldset');f.innerHTML='<legend>Bonus</legend><label>Total <input id="total"></label>';document.body.append(f);}''')
    w.evaluate('''async id=>{const h=__assignmentHarness;h.coverage.current.parts.forEach(p=>p.verified=true);const p=await h.observeAllFrames(id);
      h.coverage.read({question:'Bonus: enter the total',parts:[{id:'t',what:'total',answer:'9',ref:p.elements.find(e=>e.key.endsWith('#total')).ref}]},p);}''', tid)
    assert w.evaluate('__assignmentHarness.coverage.questions.size') == 2
