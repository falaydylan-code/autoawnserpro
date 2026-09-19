import json
import pytest
import planner
import store

def obs(kind='choice'):
 return {'question_key':'q','observation_id':'o','document_id':'d','question':'Which?', 'completeness':{'complete':True},'slots':[{'slot_key':'q/a','kind':kind,'label':'Answer','options':['A','B']}]}
def raw(**changes):
 d={'kind':'plan','question_key':'q','observation_id':'o','tasks':[{'task_id':'a','slot_key':'q/a','operation':'choose_one','desired':{'label':'B'}}]};d.update(changes);return json.dumps(d)
def test_clean_plan_contract():
 p=planner.validate_context(planner.parse_plan(raw()),obs());assert p.tasks[0].verify.expected=='B'
 assert planner.call_limits(obs())==3000

def test_unresolved_slot_requires_evidence_before_answer_task():
 data=obs('unresolved');data['slots'][0]['interaction']={'adapter':'unknown','evidence':['answer_location_without_interaction_evidence']}
 assert planner.PlanObservation.model_validate(data).slots[0].kind=='unresolved'
 with pytest.raises(ValueError,match='resolved offered slot'):
  planner.validate_context(planner.parse_plan(raw()),data)
 request=planner.parse_plan(raw(kind='request_inspection',tasks=[],inspection={'slot_key':'q/a','question':'Identify the control','requests':['inspect_slot']}))
 assert planner.validate_context(request,data).kind=='request_inspection'

def test_slot_mapping_metadata_is_accepted_without_changing_logical_identity():
 data=obs();data['slots'][0].update(frame_id=1013,dom_id='0_table0_cell_c1_r1')
 parsed=planner.PlanObservation.model_validate(data)
 assert parsed.slots[0].slot_key=='q/a' and parsed.slots[0].frame_id==1013
 assert planner.validate_context(planner.parse_plan(raw()),data).tasks[0].slot_key=='q/a'

def test_dropdown_prompt_describes_bounded_discovery_and_slot_mapping():
 assert 'without selecting any answer' in planner.PLANNER_PROMPT
 assert 'NOT an HTML ID or CSS selector' in planner.PLANNER_PROMPT
 assert 'resolveSlot(' in planner.PLANNER_PROMPT
 assert 'read-only script or inspect_options' in planner.PLANNER_PROMPT
 assert 'return needs_review' in planner.PLANNER_PROMPT
 assert 'harness opens each menu' not in planner.PLANNER_PROMPT

def test_prompt_names_computed_answers_as_inputs_to_dependent_formulas():
 """M1-14 on Grok (0.10.21): Total Assets = L + CS + RE End was stated correctly,
 but RE End -- an answer cell the model had just computed as 43/25/260 -- was
 taken from the blank on the page, so the entries came out as L + CS. The prompt
 must say the input is the value computed in this plan, not the blank cell, and
 the repair prompt inherits it."""
 assert 'use the value you computed for it in this plan' in planner.PLANNER_PROMPT
 assert 'the blank cell on the page is not an input' in planner.PLANNER_PROMPT
 assert 'the blank cell on the page is not an input' in planner.REPAIR_PROMPT

def test_plan_may_drop_only_an_inert_inspection_block():
 diagnostics=[]
 inert={'slot_key':'','question':'All options supplied by harness.','requests':[],'script':''}
 plan=planner.parse_plan(raw(inspection=inert),diagnostics=diagnostics)
 assert plan.inspection is None and diagnostics==['removed_inert_inspection']
 planner.validate_context(plan,obs())
 for change in [{'script':'return document.title'},{'requests':['inspect_question']},{'slot_key':'q/a'}]:
  with pytest.raises(ValueError,match='no inspection'):
   planner.parse_plan(raw(inspection={**inert,**change}))

def test_inspection_forms_and_observed_id_schema():
 def request(key,requests,script=''):
  return planner.parse_plan(raw(kind='request_inspection',tasks=[],inspection={'slot_key':key,'question':'Read options','requests':requests,'script':script}))
 for key,requests in [('q/a',['inspect_options']),('', ['inspect_question'])]:
  assert planner.validate_context(request(key,requests),obs('selection')).kind=='request_inspection'
 assert planner.validate_context(request('',[],'return document.title'),obs()).inspection.slot_key==''
 for key,requests in [('q/options',['inspect_options']),('', ['inspect_options']),('q/a',['inspect_question'])]:
  with pytest.raises(planner.InspectionTargetError):planner.validate_context(request(key,requests),obs('selection'))
 schema=planner.response_format(['structured_outputs'],observation=obs('selection'))['json_schema']['schema']
 forms=schema['$defs']['Inspection']['anyOf']
 assert forms[0]['properties']['slot_key']['enum']==['']
 assert forms[0]['properties']['requests']['items']['enum']==['inspect_question']
 assert forms[1]['properties']['slot_key']['enum']==['q/a']
 assert 'inspect_question' not in forms[1]['properties']['requests']['items']['enum']
 assert all(t['properties']['slot_key']['enum']==['q/a'] for t in schema['$defs']['PlanTask']['anyOf'])
 assert len(planner.response_format(['structured_outputs'],observation=dict(obs(),slots=[]))['json_schema']['schema']['$defs']['Inspection']['anyOf'])==1

def test_inspection_correction_is_charged_and_server_bounded(monkeypatch):
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
 async def models(who):return [{'id':'test','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs']}]
 monkeypatch.setattr(app,'models',models)
 original=httpx.AsyncClient;sent=[]
 def handler(request):
  sent.append(json.loads(request.content))
  content=raw(kind='request_inspection',tasks=[],inspection={'slot_key':'q/options','question':'Read dropdown options','requests':['inspect_options'],'script':'return document.title'})
  return httpx.Response(200,json={'usage':{'cost':.001},'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app) as client:
  headers={'Authorization':'Bearer '+app.issue_token('inspection-test')}
  body={'run_id':'inspection-run','request_id':'first','model':'test','observation':obs('selection')}
  first=client.post('/api/agent/plan',json=body,headers=headers)
  assert first.status_code==400 and first.json()['cost']==.001
  assert first.json()['inspection_correction']=={'kind':'inspection_target','rejected_slot_key':'q/options'}
  body.update(request_id='correction',inspection_target_correction=True)
  assert client.post('/api/agent/plan',json=body,headers=headers).status_code==400
  body['request_id']='repeated-correction'
  response=client.post('/api/agent/plan',json=body,headers=headers)
  assert 'BUDGET_EXHAUSTED' in response.text and len(sent)==2
  assert store.plan_status('inspection-test','inspection-run')['cost']==pytest.approx(.002)
  assert sent[0]['response_format']['json_schema']['schema']['$defs']['Inspection']['anyOf'][1]['properties']['slot_key']['enum']==['q/a']
@pytest.mark.parametrize('text',['prefix '+raw(),'```json\n'+raw()+'\n```\nNote: done.','```json\n'+raw()+'\n``` ```json\n'+raw()+'\n```',raw()+raw(),raw(extra='injected')])
def test_only_one_strict_envelope(text):
 with pytest.raises(ValueError):planner.parse_plan(text)

def test_one_whole_reply_fence_is_absorbed_as_a_form_slip():
 """A thinking model asked for JSON in the prompt (no schema) sometimes wraps the whole reply in a ```json fence.
 That is still exactly one envelope, so it is unwrapped; a fence with anything beside it is rejected above."""
 assert planner.parse_plan('```json\n'+raw()+'\n```').kind=='plan'
 assert planner.parse_plan('```\n'+raw()+'\n```\n').kind=='plan'
 assert planner.unwrap_fence(raw())==raw()
def test_truncated_and_incomplete_rejected():
 with pytest.raises(ValueError):planner.parse_plan(raw(),'length')
 o=obs();o['completeness']['complete']=False
 with pytest.raises(ValueError):planner.validate_context(planner.parse_plan(raw()),o)
def test_verifier_cannot_disagree_with_desired():
 d=json.loads(raw());d['tasks'][0]['verify']={'kind':'selection_equals','expected':'A'}
 with pytest.raises(ValueError):planner.parse_plan(json.dumps(d))
def test_context_and_coverage():
 for o in [dict(obs(),observation_id='new'),dict(obs(),slots=[])]:
  with pytest.raises(ValueError):planner.validate_context(planner.parse_plan(raw()),o)
def test_math_points_are_math_units_not_screen_fractions():
 d=json.loads(raw());t=d['tasks'][0];t.update(operation='place_points',desired={'points':[{'id':'p','x':-2,'y':-4}]})
 assert planner.parse_plan(json.dumps(d)).tasks[0].desired.points[0].x==-2
@pytest.mark.parametrize('change',[{'operation':'click'},{'depends_on':['a']},{'desired':{'label':'B','value':'other'}}])
def test_closed_task_schema(change):
 d=json.loads(raw());d['tasks'][0].update(change)
 with pytest.raises(ValueError):planner.parse_plan(json.dumps(d))
def test_empty_checkbox_set_valid():
 d=json.loads(raw());d['tasks'][0].update(operation='set_choice_set',desired={'labels':[]})
 planner.parse_plan(json.dumps(d))
def test_reserved_amount_and_uncertain_charge(monkeypatch,tmp_path):
 monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('MAX_COST_PER_INVITE','2')
 args=dict(owner='alice',run_id='run',request_id='req',question='q',phase='plan',cap=.1,amount=.11,model='test')
 with pytest.raises(ValueError,match='BUDGET'):store.reserve_plan(**args)
 args['amount']=.06;store.reserve_plan(**args)
 with pytest.raises(ValueError,match='unconfirmed'):store.reserve_plan(**dict(args,request_id='r2'))
 store.settle_plan('alice','req',.05,{})
 with pytest.raises(ValueError,match='BUDGET'):store.reserve_plan(**dict(args,request_id='r3'))
 with pytest.raises(ValueError,match='REPEATED'):store.reserve_plan(**args)
def test_observation_not_silently_truncated():
 o=obs();o['question']='x'*10000
 assert 'x'*10000 in planner.build_plan_text(o)

@pytest.mark.parametrize('rejected',[False,True])
def test_plan_endpoint_meters_once_and_preserves_key(monkeypatch,tmp_path,rejected):
 import app,agent,httpx
 from fastapi.testclient import TestClient
 secret='planner-secret-do-not-expose';monkeypatch.setenv('OPENROUTER_API_KEY',secret)
 async def models(who):return [{'id':'model-test','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'context_length':100000,'supported_parameters':['structured_outputs']}]
 monkeypatch.setattr(app,'models',models)
 sent=[];original=httpx.AsyncClient
 def handler(request):
  sent.append(json.loads(request.content))
  content='not JSON '+secret if rejected else raw()
  return httpx.Response(200,json={'usage':{'cost':.001,'prompt_tokens':200,'completion_tokens':90},'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
 with TestClient(app.app) as client:
  token=client.post('/api/login',json={'code':'alice-secret'}).json()['token'];headers={'Authorization':'Bearer '+token}
  body={'run_id':'run','request_id':'call','spend_limit':1,'model':'model-test','observation':obs()}
  r=client.post('/api/agent/plan',json=body,headers=headers)
  assert r.status_code==(400 if rejected else 200),r.text
  assert r.json()['finish_reason']=='stop'
  assert r.json()['raw_reply']==('not JSON [redacted]' if rejected else raw())
  if rejected:assert 'invalid JSON at line 1, column 1' in r.json()['detail']
  assert r.json()['cost']==.001 and len(sent)==1
  assert sent[0]['usage']=={'include':True} and sent[0]['max_tokens']==3000
  assert sent[0]['response_format']['type']=='json_schema'
  assert sent[0]['response_format']['json_schema']['strict'] is True
  assert not any(p['type']=='image_url' for p in sent[0]['messages'][1]['content'])
  again=client.post('/api/agent/plan',json=body,headers=headers);assert again.status_code==400 and len(sent)==1
  assert secret not in r.text+again.text
  assert secret.encode() not in (tmp_path/'agent.db').read_bytes()

def test_inspection_accepts_a_read_script_and_rejects_an_empty_request():
 ok=planner.parse_plan(json.dumps({'kind':'request_inspection','question_key':'q','observation_id':'o','inspection':{'question':'?','script':'return document.title'}}))
 assert ok.kind=='request_inspection' and ok.inspection.script=='return document.title'
 packaged=planner.parse_plan(json.dumps({'kind':'request_inspection','question_key':'q','observation_id':'o','inspection':{'question':'?','slot_key':'q/a','requests':['inspect_options']}}))
 assert packaged.inspection.requests==['inspect_options']
 with pytest.raises(ValueError):  # neither requests nor script -> nothing to inspect
  planner.parse_plan(json.dumps({'kind':'request_inspection','question_key':'q','observation_id':'o','inspection':{'question':'?'}}))

def test_verify_contract_confirms_or_flags_known_slots_only():
 import asyncio,pytest
 o=obs('selection');o['screenshot']='data:image/png;base64,AAAA'
 body=planner.VerifyRequest(run_id='r',request_id='c',model='m',observation=o,expected=[{'slot_key':'q/a','label':'Answer','value':'A'}])
 async def good(m,mt):return ('{"kind":"verified"}','stop')
 async def flag(m,mt):return ('{"kind":"mismatch","mismatches":["q/a"],"reason":"blank"}','stop')
 async def bogus(m,mt):return ('{"kind":"mismatch","mismatches":["q/not-a-slot"],"reason":"x"}','stop')
 async def contra(m,mt):return ('{"kind":"verified","mismatches":["q/a"]}','stop')
 assert asyncio.run(planner.request_verify(body,good)).kind=='verified'
 assert asyncio.run(planner.request_verify(body,flag)).mismatches==['q/a']
 with pytest.raises(ValueError):asyncio.run(planner.request_verify(body,bogus))   # can't flag a slot it wasn't given
 with pytest.raises(ValueError):asyncio.run(planner.request_verify(body,contra))  # verified + mismatches is contradictory

def test_verify_phase_has_a_nonzero_budget(monkeypatch,tmp_path):
 # Regression for the meter that rejected every /api/agent/verify call because
 # 'verify' was missing from the phase-limit map (limit 0). The metering path is
 # exercised directly, not bypassed.
 import store,pytest
 monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('MAX_COST_PER_INVITE','5')
 args=dict(owner='v',run_id='vr',question='q',phase='verify',cap=2,amount=.01,model='test')
 for i in range(4):store.reserve_plan(request_id='vf%d'%i,**args);store.settle_plan('v','vf%d'%i,.001,{})
 with pytest.raises(ValueError,match='BUDGET'):store.reserve_plan(request_id='vf4',**args)   # 5th exceeds the budget of 4

def test_capabilities_negotiates_protocol_without_422():
 # The planner startup fetches /api/capabilities?protocol=4; the query int must
 # coerce and echo 4 (not 422), while the default stays 3 for loaded 0.8 builds.
 import app
 from fastapi.testclient import TestClient
 with TestClient(app.app) as client:
  assert client.get('/api/capabilities').json()['protocol']==3
  up=client.get('/api/capabilities?protocol=4').json()
  assert up['protocol']==4 and up['supported_protocols']==[3,4] and up['planner_release']=='preview'
  assert 'task_plans' in up['features']
  assert client.get('/api/capabilities?protocol=9').json()['protocol']==3   # unknown falls back, no 422


def test_schema_diagnostics_identify_field_without_rejected_value():
 with pytest.raises(ValueError,match='question_key: missing'):
  planner.parse_plan('{"kind":"needs_review","observation_id":"o","reason":"unclear"}')
 with pytest.raises(ValueError,match='invalid JSON at line 1, column'):
  planner.parse_plan('not json')
 with pytest.raises(ValueError) as error:
  planner.parse_plan('{"kind":"private-secret-value"}')
 assert 'private-secret-value' not in str(error.value)

def test_reported_prefix_is_not_guessed_and_choice_alias_is_context_checked():
 broken='":"plan","question_key":"q","observation_id":"o","tasks":[]}'
 with pytest.raises(ValueError,match='invalid JSON'):planner.parse_plan(broken)
 data=json.loads(raw());data['tasks'][0].update(operation='choice_set',desired={'labels':['B']})
 notes=[];response=planner.parse_plan(json.dumps(data),diagnostics=notes)
 assert response.tasks[0].operation=='set_choice_set' and len(notes)==1
 planner.validate_context(response,obs('choice_set'))
 with pytest.raises(ValueError):planner.validate_context(response,obs('choice'))

def test_formats_follow_live_capabilities():
 assert planner.response_format([]) is None
 assert planner.response_format(['response_format'])=={'type':'json_object'}
 schema=planner.response_format(['structured_outputs'])['json_schema']['schema']
 assert schema['additionalProperties'] is False
 assert set(schema['required'])==set(schema['properties'])
 variants=schema['$defs']['PlanTask']['anyOf']
 operations=[v['properties']['operation']['enum'][0] for v in variants]
 assert 'set_choice_set' in operations and 'choice_set' not in operations
 checkbox=variants[operations.index('set_choice_set')]
 assert set(checkbox['properties']['desired']['properties'])=={'labels'}
 assert 'verify' not in checkbox['properties']

def test_run_identity_survives_network_change_but_rejects_other_guest(tmp_path):
 args=dict(owner='guest:stable',run_id='stable-run',request_id='first',question='q',phase='plan',cap=1,amount=.01,model='m',budget_owner='network:first')
 store.reserve_plan(**args);store.settle_plan('guest:stable','first',.001,{})
 store.reserve_plan(**dict(args,request_id='second',phase='verify',budget_owner='network:changed'))
 store.settle_plan('guest:stable','second',.002,{})
 assert store.plan_status('guest:stable','stable-run')['cost']==pytest.approx(.003)
 with pytest.raises(ValueError,match='different user'):
  store.reserve_plan(**dict(args,owner='guest:other',request_id='third'))
 assert store.plan_status('guest:other','stable-run') is None
 with store.connect() as con:
  assert con.execute('SELECT calls,cost FROM usage WHERE owner=?',('network:first',)).fetchone()==(2,.003)
  assert con.execute('SELECT owner FROM usage WHERE owner=?',('network:changed',)).fetchone() is None

def test_guest_identity_persists_restart_and_renewal(monkeypatch):
 import app,time
 from fastapi.testclient import TestClient
 monkeypatch.setenv('PUBLIC_ACCESS','true')
 with TestClient(app.app) as client:
  token=client.post('/api/guest').json()['token'];identity=app.owner('Bearer '+token)
  app.tokens.clear()
  assert app.owner('Bearer '+token)==identity
  with store.connect() as con:con.execute('UPDATE access_sessions SET expires=?',(time.time()-10,))
  renewed=client.post('/api/guest',headers={'Authorization':'Bearer '+token}).json()['token']
  assert app.owner('Bearer '+renewed)==identity
  stranger=client.post('/api/guest',headers={'Authorization':'Bearer forged'}).json()['token']
  assert app.owner('Bearer '+stranger)!=identity


def test_plan_then_screenshot_verify_across_network_and_session_renewal(monkeypatch):
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('PUBLIC_ACCESS','true')
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
 async def models(who):return [{'id':'test','vision':True,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'context_length':100000}]
 monkeypatch.setattr(app,'models',models)
 sent=[];original=httpx.AsyncClient
 def handler(request):
  sent.append(request)
  content=raw() if len(sent)==1 else '{"kind":"verified"}'
  return httpx.Response(200,json={'usage':{'cost':.001},'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app,client=('network-one',50000)) as client:
  token=client.post('/api/guest').json()['token'];headers={'Authorization':'Bearer '+token}
  body={'run_id':'ownership-run','request_id':'plan-call','spend_limit':1,'model':'test','observation':obs()}
  response=client.post('/api/agent/plan',json=body,headers=headers)
  assert response.status_code==200,response.text
 app.tokens.clear() # persistent identity must survive a server restart
 with TestClient(app.app,client=('network-two',50000)) as client:
  token=client.post('/api/guest',headers=headers).json()['token'];headers={'Authorization':'Bearer '+token}
  body.update(request_id='verify-call',expected=[{'slot_key':'q/a','label':'Answer','value':'A'}])
  body['observation']['screenshot']='data:image/png;base64,AAAA'
  response=client.post('/api/agent/verify',json=body,headers=headers)
  assert response.status_code==200,response.text
  assert response.json()['response']['kind']=='verified'
  status=client.get('/api/agent/runs/ownership-run',headers=headers)
  assert status.status_code==200 and status.json()['cost']==pytest.approx(.002)
  stranger=client.post('/api/guest').json()['token']
  assert client.get('/api/agent/runs/ownership-run',headers={'Authorization':'Bearer '+stranger}).status_code==404
  body['request_id']='stranger-call'
  rejected=client.post('/api/agent/verify',json=body,headers={'Authorization':'Bearer '+stranger})
  assert rejected.status_code==400 and 'different user' in rejected.text
 assert len(sent)==2 # unauthorized verification never reaches the provider

def test_reasoning_policy_by_model_metadata():
 """Optional reasoning gets an explicit thinking budget; mandatory reasoning keeps the provider's default effort and
 only hides the thoughts; a model without the parameter, or the setting off, gets nothing."""
 optional={'supported_parameters':['reasoning','structured_outputs'],'reasoning':{'mandatory':False}}
 mandatory={'supported_parameters':['reasoning'],'reasoning':{'mandatory':True,'default_enabled':True,'supported_efforts':['xhigh','high','medium','low'],'default_effort':'high'}}
 efforts={'supported_parameters':['reasoning'],'reasoning':{'mandatory':False,'supported_efforts':['high','low'],'default_effort':'high'}}
 assert planner.reasoning_request(optional)=={'max_tokens':planner.REASONING_TOKENS,'exclude':True}
 assert planner.reasoning_request(mandatory)=={'exclude':True}
 assert planner.reasoning_request(efforts,'medium')=={'effort':'high','exclude':True}   # unsupported level -> model default
 assert planner.reasoning_request(efforts,'low')=={'effort':'low','exclude':True}
 assert planner.reasoning_request({'supported_parameters':['structured_outputs']}) is None
 assert planner.reasoning_request(optional,'off') is None and planner.reasoning_request(None) is None

def test_reasoning_is_requested_with_headroom_reserved_and_tokens_reported(monkeypatch):
 """Through the real endpoint: a reasoning-capable model gets the `reasoning` object AND max_tokens raised by the
 thinking budget (OpenRouter counts thinking against max_tokens); the reservation covers the extra output; the
 provider's reasoning_tokens come back in the response. A model without the parameter is untouched."""
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
 async def models(who):return [
  {'id':'thinker','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs','reasoning'],'reasoning':{'mandatory':False}},
  {'id':'plain','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs'],'reasoning':{}}]
 monkeypatch.setattr(app,'models',models)
 original=httpx.AsyncClient;sent=[]
 def handler(request):
  sent.append(json.loads(request.content))
  return httpx.Response(200,json={'usage':{'cost':.002,'prompt_tokens':300,'completion_tokens':1700,'completion_tokens_details':{'reasoning_tokens':1234}},
   'choices':[{'message':{'content':raw()},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app) as client:
  headers={'Authorization':'Bearer '+app.issue_token('reasoning-test')}
  r=client.post('/api/agent/plan',json={'run_id':'r1','request_id':'a','model':'thinker','observation':obs()},headers=headers)
  assert r.status_code==200, r.text
  assert sent[0]['reasoning']=={'max_tokens':planner.REASONING_TOKENS,'exclude':True}
  assert sent[0]['max_tokens']==planner.call_limits(obs())+planner.REASONING_TOKENS
  assert r.json()['reasoning_tokens']==1234 and r.json()['output_tokens']==1700 and r.json()['reasoning']=={'max_tokens':planner.REASONING_TOKENS,'exclude':True}
  assert r.json()['reservation']>=(planner.call_limits(obs())+planner.REASONING_TOKENS)*0.000001   # the thinking budget is paid for up front
  r=client.post('/api/agent/plan',json={'run_id':'r2','request_id':'b','model':'plain','observation':obs()},headers=headers)
  assert r.status_code==200 and 'reasoning' not in sent[1] and sent[1]['max_tokens']==planner.call_limits(obs())
  assert r.json()['reasoning_tokens']==1234 and r.json()['reasoning'] is None

def test_thinking_drops_the_schema_only_for_optional_reasoning_models(monkeypatch):
 """Measured: any response_format switches MiniMax M3's thinking off; Grok keeps thinking under json_schema. So the
 request for an optional-reasoning model carries `reasoning` and NO response_format (prompt JSON, logged as such),
 while a mandatory-reasoning model keeps the schema and only hides its thoughts."""
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
 async def models(who):return [
  {'id':'optional','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs','reasoning'],'reasoning':{'mandatory':False}},
  {'id':'mandatory','vision':False,'pricing':{'prompt':'0.000002','completion':'0.000006'},'supported_parameters':['structured_outputs','reasoning'],'reasoning':{'mandatory':True,'default_enabled':True,'supported_efforts':['high','medium'],'default_effort':'high'}}]
 monkeypatch.setattr(app,'models',models)
 original=httpx.AsyncClient;sent=[]
 def handler(request):
  sent.append(json.loads(request.content))
  return httpx.Response(200,json={'usage':{'cost':.001,'prompt_tokens':300,'completion_tokens':600,'completion_tokens_details':{'reasoning_tokens':90}},
   'choices':[{'message':{'content':'```json\n'+raw()+'\n```'},'finish_reason':'stop'}]})   # fenced, as MiniMax did live
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app) as client:
  headers={'Authorization':'Bearer '+app.issue_token('schema-policy')}
  r=client.post('/api/agent/plan',json={'run_id':'p1','request_id':'a','model':'optional','observation':obs()},headers=headers)
  assert r.status_code==200, r.text
  assert 'response_format' not in sent[0] and sent[0]['reasoning']=={'max_tokens':planner.REASONING_TOKENS,'exclude':True}
  assert r.json()['output_format']=='prompt_json' and r.json()['reasoning_tokens']==90 and r.json()['response']['kind']=='plan'
  r=client.post('/api/agent/plan',json={'run_id':'p2','request_id':'b','model':'mandatory','observation':obs()},headers=headers)
  assert r.status_code==200, r.text
  assert sent[1]['response_format']['type']=='json_schema' and sent[1]['reasoning']=={'exclude':True}
  assert sent[1]['max_tokens']==planner.call_limits(obs())+planner.REASONING_TOKENS and r.json()['output_format']=='json_schema'
 assert 'No code fences' in planner.PLANNER_PROMPT


def test_parts_travel_in_the_observation_and_the_plan_declares_them():
 """Multi-part questions: the observation carries the parts the harness revealed and each slot's part_id; the plan
 carries how many parts the wording names (default 1). The schema sent to structured-output providers includes it."""
 data=obs();data['parts']=[{'part_id':'part:id:tab-is','label':'Income Statement','selected':True,'slots':1},{'part_id':'part:id:tab-bs','label':'Balance Sheet','selected':False,'slots':0}]
 data['slots'][0]['part_id']='part:id:tab-is'
 parsed=planner.PlanObservation.model_validate(data)
 assert [p.label for p in parsed.parts]==['Income Statement','Balance Sheet'] and parsed.slots[0].part_id=='part:id:tab-is'
 assert planner.parse_plan(raw()).parts_declared==1
 assert planner.parse_plan(raw(parts_declared=2)).parts_declared==2
 with pytest.raises(ValueError):planner.parse_plan(raw(parts_declared=0))
 assert 'parts_declared' in json.dumps(planner.response_format(['structured_outputs']))
 assert 'parts_declared' in planner.PLANNER_PROMPT and 'every part' in planner.PLANNER_PROMPT

def test_reservation_understands_openrouter_pricing_shapes(monkeypatch):
 """Grok 4.6's live pricing dict (2026-09-17) has `web_search` (a plugin charge this backend never triggers) and
 `overrides` (a long-prompt tier). Both used to trip the unknown-charge guard -> BUDGET_EXHAUSTED 'pricing cannot be
 safely reserved' before any call. Now: the tier applies when the reserved bound crosses it, web_search is known, and
 a genuinely unknown positive charge is still refused -- by name."""
 grok={'prompt':'0.000002','completion':'0.000006','web_search':'0.005','input_cache_read':'0.0000005','overrides':[{'min_prompt_tokens':200000,'prompt':'0.000004','completion':'0.000012','input_cache_read':'0.000001'}]}
 assert planner.reservation_prices(grok,500000)==(4e-6,1.2e-5,0.0)        # image bound (full context) crosses the tier
 assert planner.reservation_prices(grok,8000)==(2e-6,6e-6,0.0)            # a text-only bound does not
 assert planner.unknown_charges(grok)==[] and planner.unknown_charges({'prompt':'1e-6','completion':'1e-6','audio':'0.01'})==['audio']
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key');monkeypatch.setenv('MAX_COST_PER_INVITE','5')   # as on Railway
 async def models(who):return [
  {'id':'grok','vision':True,'pricing':grok,'context_length':500000,'supported_parameters':['structured_outputs','reasoning'],'reasoning':{'mandatory':True,'default_enabled':True}},
  {'id':'odd','vision':False,'pricing':{'prompt':'1e-6','completion':'1e-6','audio':'0.01'},'supported_parameters':['structured_outputs']}]
 monkeypatch.setattr(app,'models',models)
 original=httpx.AsyncClient
 def handler(request):return httpx.Response(200,json={'usage':{'cost':.01,'prompt_tokens':6000,'completion_tokens':500},'choices':[{'message':{'content':raw()},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app) as client:
  headers={'Authorization':'Bearer '+app.issue_token('pricing-shapes')}
  r=client.post('/api/agent/plan',json={'run_id':'g1','request_id':'a','model':'grok','spend_limit':5,'observation':obs()},headers=headers)   # text only: fits
  assert r.status_code==200, r.text
  shot=dict(obs(),screenshot='data:image/png;base64,'+'A'*80)
  r=client.post('/api/agent/plan',json={'run_id':'g2','request_id':'b','model':'grok','spend_limit':2,'observation':shot},headers=headers)
  assert r.status_code==400 and 'Raise the spend limit' in r.text and '$2.11' in r.text, r.text   # 500k x $4/M + 9000 x $12/M at the tier
  r=client.post('/api/agent/plan',json={'run_id':'g3','request_id':'c','model':'odd','observation':obs()},headers=headers)
  assert r.status_code==400 and 'cannot reserve (audio)' in r.text, r.text

def test_a_reply_that_was_all_thinking_is_named_a_truncation_and_the_retry_hints_reach_the_provider(monkeypatch):
 """M3-9 (2:19 PM): 9,000 of 9,000 output tokens went to thinking on a provider that ignored the thinking cap; the
 reply had no content and was reported as SCHEMA_INVALID. Now: TRUNCATED_BY_THINKING with the numbers and the provider,
 and the coordinator's retry hints (avoid that provider; then thinking off) are honoured in the request."""
 import app,agent,httpx
 from fastapi.testclient import TestClient
 monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
 async def models(who):return [{'id':'thinker','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs','reasoning'],'reasoning':{'mandatory':False}}]
 monkeypatch.setattr(app,'models',models)
 original=httpx.AsyncClient;sent=[]
 def handler(request):
  sent.append(json.loads(request.content))
  if len(sent)==1:return httpx.Response(200,json={'provider':'Venice','usage':{'cost':.012,'prompt_tokens':6522,'completion_tokens':9000,'completion_tokens_details':{'reasoning_tokens':9000}},'choices':[{'message':{'content':None},'finish_reason':'length'}]})
  return httpx.Response(200,json={'provider':'Together','usage':{'cost':.004,'prompt_tokens':6522,'completion_tokens':900,'completion_tokens_details':{'reasoning_tokens':400}},'choices':[{'message':{'content':raw()},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 with TestClient(app.app) as client:
  headers={'Authorization':'Bearer '+app.issue_token('truncation')}
  r=client.post('/api/agent/plan',json={'run_id':'t1','request_id':'a','model':'thinker','observation':obs()},headers=headers)
  assert r.status_code==400 and r.json()['detail'].startswith('TRUNCATED_BY_THINKING') and '9000 of 9000' in r.json()['detail'] and 'Venice' in r.json()['detail'], r.text
  assert r.json()['reasoning_tokens']==9000 and r.json()['provider']=='Venice' and r.json()['finish_reason']=='length' and r.json()['cost']==.012
  r=client.post('/api/agent/plan',json={'run_id':'t1','request_id':'b','model':'thinker','observation':obs(),'avoid_providers':['Venice']},headers=headers)
  assert r.status_code==200, r.text
  assert sent[1]['provider']['ignore']==['Venice'] and 'reasoning' in sent[1]
  r=client.post('/api/agent/plan',json={'run_id':'t1','request_id':'c','model':'thinker','observation':obs(),'avoid_providers':['Venice'],'reasoning_mode':'off'},headers=headers)
  assert r.status_code==200 and 'reasoning' not in sent[2] and sent[2]['max_tokens']==planner.call_limits(obs()) and sent[2]['response_format']['type']=='json_schema'
 assert planner.reasoning_budget({'slots':[1]*20})==10500 and planner.reasoning_budget({'slots':[1]*3})==planner.REASONING_TOKENS

def test_an_unresolved_slot_is_not_required_in_the_plan_but_still_cannot_be_planned():
 """A cell the harness tried to identify and could not (locked or computed) is left out of the plan's required
 coverage; a task on it is still refused. M3-9 rows 5 and 11."""
 data=obs();data['slots'].append({'slot_key':'q/locked','kind':'unresolved','label':'locked amount','options':[],'current':'','interaction':{'adapter':'unknown','evidence':['answer_location_without_interaction_evidence']}})
 assert planner.validate_context(planner.parse_plan(raw()),data).tasks[0].slot_key=='q/a'          # covers the one resolved slot only
 with pytest.raises(ValueError,match='resolved offered slot'):
  planner.validate_context(planner.parse_plan(raw(tasks=[{'task_id':'a','slot_key':'q/a','operation':'choose_one','desired':{'label':'B'}},{'task_id':'b','slot_key':'q/locked','operation':'enter_value','desired':{'value':'1'}}])),data)
 assert 'leave it OUT of the plan' in planner.PLANNER_PROMPT


def test_request_deadline_scales_with_the_token_allowance_and_is_advertised():
 """M3-9 9:13 PM: a 13,500-token allowance (3,000 answer + 10,500 thinking) was cut off by two fixed 60 s timeouts
 (extension and backend) while the model was still answering. The deadline now comes from the allowance, is capped,
 and the backend advertises its maximum so the extension can wait at least as long."""
 import asyncio,app
 assert planner.request_deadline(3000)==90
 assert planner.request_deadline(9000)==210
 assert planner.request_deadline(13500)==planner.REQUEST_DEADLINE_MAX==300     # capped
 assert planner.request_deadline(200)<planner.request_deadline(2000)<planner.request_deadline(20000)
 assert store.STALE_RESERVATION_SECONDS>planner.REQUEST_DEADLINE_MAX             # a pending row older than any call can be is stale
 caps=asyncio.run(app.capabilities(4))
 assert caps['request_wait_seconds']==planner.REQUEST_DEADLINE_MAX


def test_timed_out_call_is_charged_at_worst_case_and_does_not_freeze_the_identity(monkeypatch,tmp_path):
 """Before: a provider timeout left the reservation 'pending', usage.unknown stayed 1, and every later plan request for
 that identity was refused with 'prior provider cost is unconfirmed' -- with no code path that could ever clear it.
 Now the call is charged at its reserved worst case (never less), named as a timeout, and the next call proceeds."""
 import asyncio,agent,httpx
 monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('OPENROUTER_API_KEY','test-key');monkeypatch.setenv('MAX_COST_PER_INVITE','2')
 original=httpx.AsyncClient;made=[]
 def handler(request):raise httpx.ReadTimeout('provider still generating',request=request)
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:(made.append(kw),original(transport=httpx.MockTransport(handler),**kw))[1])
 reservation=dict(run_id='run',request_id='req-1',question='q',phase='plan',cap=1,amount=.07,budget_owner='alice');record={}
 with pytest.raises(ValueError) as failure:
  asyncio.run(agent.planner_complete('alice',[{'role':'user','content':'x'}],'test',record,13500,reservation,deadline=planner.request_deadline(13500)))
 assert 'PROVIDER_TIMEOUT' in str(failure.value) and 'within 300 s' in str(failure.value) and '$0.07' in str(failure.value)
 assert made[0]['timeout']==300                                                   # the deadline reached the HTTP client
 status=store.plan_status('alice','run');call=status['calls'][0]
 assert call['status']=='charged_worst_case' and call['cost']==.07 and status['cost']==.07
 assert record['cost_confirmed'] is False
 store.reserve_plan('alice',model='test',**dict(reservation,request_id='req-2',phase='repair'))      # not refused as 'unconfirmed'


def test_unconfirmed_outcomes_all_charge_the_worst_case(monkeypatch,tmp_path):
 """A 5xx, a malformed body and a reply without a cost are the same class as a timeout: cost unconfirmed -> charge the
 reservation. Plain rejections (4xx) stay free, as before."""
 import asyncio,agent,httpx
 monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('OPENROUTER_API_KEY','test-key');monkeypatch.setenv('MAX_COST_PER_INVITE','5')
 original=httpx.AsyncClient;responses=[]
 def handler(request):return responses.pop(0)
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 def call(n,response,amount=.05):
  responses.append(response)
  with pytest.raises(ValueError) as failure:
   asyncio.run(agent.planner_complete('bob',[{'role':'user','content':'x'}],'test',{},100,dict(run_id='run',request_id=f'r{n}',question='q',phase='verify',cap=2,amount=amount,budget_owner='bob')))
  return str(failure.value),store.plan_status('bob','run')['calls'][-1]
 msg,row=call(1,httpx.Response(502,text='bad gateway'));assert row['status']=='charged_worst_case' and row['cost']==.05 and 'worst case' in msg
 msg,row=call(2,httpx.Response(200,text='not json'));assert row['status']=='charged_worst_case' and row['cost']==.05
 msg,row=call(3,httpx.Response(200,json={'usage':{},'choices':[{'message':{'content':'{}'}}]}));assert row['status']=='charged_worst_case' and 'no cost' in msg
 msg,row=call(4,httpx.Response(402,text='credits'));assert row['status']=='settled' and row['cost']==0 and 'HTTP 402' in msg
 assert store.plan_status('bob','run')['cost']==pytest.approx(.15)


def test_stale_pending_reservations_are_reconciled_at_startup_and_on_the_next_reservation(monkeypatch,tmp_path):
 """The 9:13 PM row: pending, created before the `created` column existed (NULL) or longer ago than any call could
 still run. Fresh pending rows (a call in flight) keep blocking, exactly as test_reserved_amount_and_uncertain_charge
 requires."""
 monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('MAX_COST_PER_INVITE','5')
 store.reserve_plan('carol',run_id='old',request_id='stuck',question='q',phase='plan',cap=1,amount=.12,model='m',budget_owner='carol')
 with pytest.raises(ValueError,match='unconfirmed'):store.reserve_plan('carol',run_id='old',request_id='next',question='q',phase='plan',cap=1,amount=.01,model='m')
 with store.connect() as con:con.execute('UPDATE planner_calls SET created=NULL WHERE id=?',('stuck',))          # pre-0.10.34 row
 assert store.reconcile_stale_plans()==1
 row=store.plan_status('carol','old')['calls'][0];assert row['status']=='charged_worst_case' and row['cost']==.12
 store.reserve_plan('carol',run_id='old',request_id='next',question='q',phase='plan',cap=1,amount=.01,model='m')   # unfrozen
 with store.connect() as con:con.execute('UPDATE planner_calls SET created=created-? WHERE id=?',(store.STALE_RESERVATION_SECONDS+1,'next'))   # aged out
 store.reserve_plan('carol',run_id='old',request_id='after',question='q',phase='plan',cap=1,amount=.01,model='m')  # the sweep runs inside reserve_plan
 rows={r['request_id']:r for r in store.plan_status('carol','old')['calls']}
 assert rows['next']['status']=='charged_worst_case' and rows['after']['status']=='pending'
 assert store.reconcile_stale_plans()==0                                                                           # nothing stale is left


def test_blank_is_a_legal_answer_exactly_when_the_page_offers_a_blank_choice():
 """Grok, 10:00 PM: a 13-row income statement with 3 spare rows; the model planned set_selection label "" for the
 spare rows (the page's menus start with a blank entry) and was refused 'empty option label' -- while the contract also
 demands one task per slot. No model could have produced an acceptable plan. Blank is now accepted when offered."""
 o=obs();o['slots']=[dict(slot_key='q/a',frame_id=0,dom_id='a',kind='selection',label='row 5',options=['','Rent Expense','Sales Revenue'],current='Rent Expense',interaction={'adapter':'selection','evidence':[]}),
                     dict(slot_key='q/b',frame_id=0,dom_id='b',kind='selection',label='row 6',options=['Rent Expense','Sales Revenue'],current='',interaction={'adapter':'selection','evidence':[]}),
                     dict(slot_key='q/c',frame_id=0,dom_id='c',kind='value',label='amount',options=[],current='12',interaction={'adapter':'text','evidence':[]})]
 def plan(label_b):
  return planner.parse_plan(json.dumps({'kind':'plan','question_key':o['question_key'],'observation_id':o['observation_id'],'tasks':[
   {'task_id':'t1','operation':'set_selection','slot_key':'q/a','desired':{'label':''},'depends_on':[]},
   {'task_id':'t2','operation':'set_selection','slot_key':'q/b','desired':{'label':label_b},'depends_on':[]},
   {'task_id':'t3','operation':'enter_value','slot_key':'q/c','desired':{'value':''},'depends_on':[]}]}))
 accepted=planner.validate_context(plan('Sales Revenue'),o)
 assert [t.desired.label for t in accepted.tasks[:2]]==['','Sales Revenue'] and accepted.tasks[2].desired.value==''
 assert accepted.tasks[0].verify.model_dump()=={'kind':'selection_equals','expected':''}       # verified as blank, not skipped
 with pytest.raises(ValueError,match='blank is not an offered choice'):planner.validate_context(plan(''),o)   # row 6 has no blank entry
 with pytest.raises(ValueError,match='blank is not an offered choice'):planner.validate_context(plan('   '),o)
 assert 'label "" when "" is among its offered choices' in planner.PLANNER_PROMPT
