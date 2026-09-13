import json
import pytest
import agent
from test_extension_coverage import extension


def navigate(extension, fixture):
    page,worker,tid,_,origin=extension
    page.goto(origin+'/'+fixture)
    worker.evaluate('(id)=>__assignmentHarness.injectAll(id)',tid)
    return page,worker,tid


def test_custom_table_discovers_twenty_cells_and_verifies_original_cell(extension):
    page,w,tid=navigate(extension,'custom_dropdowns.html')
    observed=w.evaluate('(id)=>__assignmentHarness.observeAllFrames(id)',tid)
    cells=[e for e in observed['elements'] if e.get('dropdown')]
    assert len(cells)==20
    target=next(e for e in cells if e['key'].endswith('#cell_0_0'))
    assert target['row']=='Accounts Payable' and target['column']=='Account Type'
    w.evaluate('(p)=>__assignmentHarness.coverage.read(p.action,p.page)',{'page':observed,'action':{'question':'Classify accounts','parts':[{'id':'a','what':'Accounts Payable Account Type','answer':'Liability','ref':target['ref']}]}})
    out=w.evaluate('async a=>{const h=__assignmentHarness;return h.executeAction(a.id,a.action,await h.observeAllFrames(a.id),{});}',{'id':tid,'action':{'action':'click','ref':target['ref'],'part_id':'a','purpose':'open'}})
    assert out['ok'] and out['preparation']
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].verified') is False
    out=w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),option=p.elements.find(e=>e.role==='option'&&e.name==='Liability');
      const r=await h.executeAction(id,{action:'click',ref:option.ref,part_id:'a',purpose:'answer'},p,{});await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''',tid)
    assert out['ok']
    assert page.locator('#cell_0_0').inner_text()=='Liability'
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_ordering_checks_sequence_not_membership_and_moves_real_pointer(extension):
    page,w,tid=navigate(extension,'ordering.html')
    w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      h.coverage.read({question:'Order statement',parts:[{id:'o',what:'Statement order',kind:'ordering',answer:'ordered list',ref:ref('order'),order:['revenue','expense','net'].map(ref),sequence:['Revenues','Expenses','Net Income']}]},p);
      await h.refreshEvidence(id,p);}''',tid)
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')
    out=w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
      const r=await h.executeAction(id,{action:'reorder',ref:ref('net'),to:ref('expense'),placement:'after',part_id:'o'},p,{});
      await h.refreshEvidence(id,await h.observeAllFrames(id));return r;}''',tid)
    assert out['ok']
    assert page.locator('li').all_text_contents()==['Revenues','Expenses','Net Income']
    assert w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_visual_snapshot_rejects_changed_viewport(extension):
    page,w,tid=navigate(extension,'custom_dropdowns.html')
    w.evaluate('async id=>{const h=__assignmentHarness;globalThis.snap=await h.makeSnapshot(id,await h.observeAllFrames(id));}',tid)
    page.set_viewport_size({'width':1300,'height':900})
    message=w.evaluate('async id=>{try{await __assignmentHarness.currentSnapshot(id,snap,await __assignmentHarness.observeAllFrames(id));return "bad";}catch(e){return e.message;}}',tid)
    assert 'Stale' in message


@pytest.mark.parametrize('action',[
    {'action':'reorder','ref':1,'to':1,'placement':'after','part_id':'a'},
    {'action':'visual_click','point':{'x':2,'y':0.5},'part_id':'a','observation_id':'x','purpose':'answer'},
    {'action':'verify','part_id':'a'},
])
def test_invalid_new_actions_are_rejected(action):
    with pytest.raises(ValueError):agent.parse_action(json.dumps(action))


def test_backend_preserves_new_fields():
    from app import Observation
    o=Observation(phase='verify',observation_id='shot',verification={'part_id':'a','what':'Cell'},elements=[{'ref':1,'dropdown':True,'list_ref':4,'order_index':2}])
    assert o.model_dump()['elements'][0]['dropdown']
    a=agent.parse_action(json.dumps({'action':'read_check','parts':[{'id':'order','what':'List','answer':'ordered','kind':'ordering','order':[3,2],'sequence':['A','B']}]}))
    assert a.parts[0].order==[3,2]


def test_visual_input_operates_closed_shadow_without_a_ref(extension):
    page,w,tid=navigate(extension,'closed_dropdown.html')
    rect=page.locator('answer-box').bounding_box()
    point={'x':(rect['x']+rect['width']/2)/1500,'y':(rect['y']+rect['height']/2)/1100}
    out=w.evaluate('''async ({id,point})=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);h.coverage.read({question:'Classify',parts:[{id:'a',what:'Accounts Payable Type',answer:'Liability',ref:null}]},p);
      const snap=await h.makeSnapshot(id,p);h.setSnapshot(snap);return h.executeAction(id,{action:'visual_click',purpose:'open',part_id:'a',observation_id:snap.id,point},p,{});}''',{'id':tid,'point':point})
    assert out['ok']
    # Closed shadow contents remain absent from the DOM index, but pixels changed.
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')
    assert page.locator('answer-box').inner_text()==''


def test_visual_verification_does_not_trust_claimed_success(extension):
    page,w,tid=navigate(extension,'closed_dropdown.html')
    result=w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id);h.coverage.read({question:'Classify',parts:[{id:'a',what:'Accounts Payable Type',answer:'Liability'}]},p);
      const original=fetch;globalThis.fetch=async (url,options)=>{if(String(url).endsWith('/api/agent/step')){const b=JSON.parse(options.body);return new Response(JSON.stringify({action:{action:'verify',part_id:'a',observation_id:b.observation_id,status:'confirmed',observed:'Asset'},cost:0.001}),{status:200});}return original(url,options);};
      try{return await h.verifyVisual(id,p,h.coverage.current.parts.get('a'),{backend:'http://fixture',token:'test',model:'test'});}finally{globalThis.fetch=original;}}''',tid)
    assert not result
    assert not w.evaluate('__assignmentHarness.coverage.ledger()[0].verified')


def test_compatibility_check_stops_old_backend_without_model_call(extension):
    _,w,_,_,_=extension
    result=w.evaluate('''async()=>{const original=fetch;let calls=[];globalThis.fetch=async url=>{calls.push(url);return new Response('{}',{status:404});};try{await __assignmentHarness.compatible({backend:'http://old'});}catch(e){return {message:e.message,calls};}finally{globalThis.fetch=original;}}''')
    assert 'Backend update required' in result['message']
    assert result['calls']==['http://old/api/capabilities']


def test_same_labels_do_not_hide_wrong_item_identity(extension):
    page,w,tid=navigate(extension,'ordering.html')
    page.locator('#revenue').evaluate("e=>e.textContent='Item'")
    page.locator('#expense').evaluate("e=>e.textContent='Item'")
    result=w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),ref=s=>p.elements.find(e=>e.key.endsWith('#'+s)).ref;
    h.coverage.read({question:'Duplicate labels',parts:[{id:'o',kind:'ordering',what:'Order',answer:'ordered',ref:ref('order'),order:['net','expense','revenue'].map(ref),sequence:['Net Income','Item','Item']}]},p);await h.refreshEvidence(id,p);return h.coverage.ledger()[0].verified;}''',tid)
    assert not result


def test_unrelated_submit_label_does_not_block_dropdown_input(extension):
    page,w,tid=navigate(extension,'custom_dropdowns.html')
    page.evaluate("() => { const b=document.createElement('button'); b.textContent='Submit Assignment'; document.body.prepend(b); }")
    result=w.evaluate('''async id=>{const h=__assignmentHarness,p=await h.observeAllFrames(id),cell=p.elements.find(e=>e.key.endsWith('#cell_0_0'));
      h.coverage.read({question:'Classify',parts:[{id:'a',what:'Accounts Payable Type',answer:'Liability',ref:cell.ref}]},p);
      try{return await h.executeAction(id,{action:'click',purpose:'open',part_id:'a',ref:cell.ref},p,{});}catch(e){return {ok:false,detail:e.message};}}''',tid)
    assert result['ok'],result
    assert page.get_by_role('option',name='Liability',exact=True).is_visible()
    page.keyboard.press('Escape')
    blocked=page.evaluate('''() => {
      const button=document.querySelector('button');button.innerHTML='<span>Submit Assignment</span>';
      const r=button.querySelector('span').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};
    }''')
    refusal=w.evaluate('(a)=>chrome.tabs.sendMessage(a.id,{type:"visual_guard",point:a.point},{frameId:0})',{'id':tid,'point':blocked})
    assert not refusal['ok']
