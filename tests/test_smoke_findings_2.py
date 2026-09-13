"""What the MiniMax smoke runs on the ordering and closed-shadow fixtures exposed.

The ordering plan was right in every field but forgot kind:"ordering", and the
harness refused every correct move without saying why. On the closed-shadow
page the model had to guess coordinates, missed by sixty pixels, and the guard's
refusal was thrown as a fatal error at step two.
"""
import json
import agent
from test_extension_coverage import extension  # noqa: F401  (fixture)
from test_ordering_visual import navigate


def test_a_plan_with_order_is_an_ordering_plan_even_without_the_kind_field():
    a = agent.parse_action(json.dumps({'action': 'read_check', 'has_question': True, 'question': 'Order these',
        'parts': [{'id': 'o', 'what': 'list', 'answer': 'Revenues, Expenses, Net Income', 'ref': 1,
                   'order': [3, 4, 2], 'sequence': ['Revenues', 'Expenses', 'Net Income']}]}))
    assert a.parts[0].kind == 'ordering'


def test_reorder_works_when_the_plan_omitted_kind_and_refusals_say_why(extension):
    page, w, tid = navigate(extension, 'ordering.html')
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Order statement',parts:[{id:'order',what:'Statement order',answer:'Revenues, Expenses, Net Income',ref:ref('order'),
        order:['revenue','expense','net'].map(ref),sequence:['Revenues','Expenses','Net Income']}]},p);}''', tid)
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].kind') == 'ordering'
    out = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      const r=await h.executeAction(id,{action:'reorder',ref:ref('net'),to:ref('expense'),placement:'after',part_id:'order'},p,{});
      await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''', tid)
    assert out['ok'], out
    assert page.locator('li').all_text_contents() == ['Revenues', 'Expenses', 'Net Income']
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')
    # a reorder against a value part is refused with an explanation, not a riddle
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      h.coverage.read({question:'Something else',parts:[{id:'v',what:'a value',answer:'x',ref:p.elements.find(e=>e.key.endsWith('#order')).ref}]},p);}''', tid)
    refused = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      return h.executeAction(id,{action:'reorder',ref:ref('net'),to:ref('expense'),placement:'after',part_id:'v'},p,{});}''', tid)
    assert not refused['ok'] and 'not an ordering plan' in refused['detail'] and 'order:[' in refused['detail']


def test_a_closed_shadow_host_is_listed_as_a_widget_and_clickable_by_ref(extension):
    page, w, tid = navigate(extension, 'closed_dropdown.html')
    observed = w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)', tid)
    widget = next((e for e in observed['elements'] if e['role'] == 'widget'), None)
    assert widget and widget['opaque'] and widget['box'], 'the host is visible and has a position even though its inside is not'
    out = w.evaluate('''async ({id,ref})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Accounts Payable Type',answer:'Liability',ref}]},p);
      return h.executeAction(id,{action:'click',ref,part_id:'a',purpose:'open'},p,{});}''', {'id': tid, 'ref': widget['ref']})
    assert out['ok'] and out.get('preparation'), out
    # the real mouse click reached the button inside the closed root: it changed
    assert page.locator('answer-box').evaluate('e=>e.getBoundingClientRect().width') > 0
    out2 = w.evaluate('''async ({id})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),wd=p.elements.find(e=>e.role==='widget');
      return h.executeAction(id,{action:'click',ref:wd.ref,part_id:'a',purpose:'answer'},p,{});}''', {'id': tid})
    assert out2['ok'] and out2.get('needsVerification'), out2
    ledger = w.evaluate('__assignmentHarness.coverage.ledger()[0]')
    assert ledger['entered'] and not ledger['verified'], 'entered by the click; verified only by a screenshot check'


def test_a_missed_visual_click_is_a_correctable_refusal_not_a_fatal_error(extension):
    page, w, tid = navigate(extension, 'closed_dropdown.html')
    result = w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Type',answer:'Liability',ref:null}]},p);
      const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);
      return h.executeAction(id,{action:'visual_click',purpose:'open',part_id:'a',observation_id:snap.id,point:{x:0.9,y:0.9}},p,{});}''', tid)
    assert result['ok'] is False and 'aim' in result['detail'], result
