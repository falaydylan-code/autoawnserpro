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
 assert planner.call_limits(obs())==600
@pytest.mark.parametrize('text',['prefix '+raw(),'```json\n'+raw()+'\n```',raw()+raw(),raw(extra='injected')])
def test_only_one_strict_envelope(text):
 with pytest.raises(ValueError):planner.parse_plan(text)
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

def test_plan_endpoint_meters_once_and_preserves_key(monkeypatch,tmp_path):
 import app,agent,httpx
 from fastapi.testclient import TestClient
 secret='planner-secret-do-not-expose';monkeypatch.setenv('OPENROUTER_API_KEY',secret)
 async def models(who):return [{'id':'model-test','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'context_length':100000}]
 monkeypatch.setattr(app,'models',models)
 sent=[];original=httpx.AsyncClient
 def handler(request):
  sent.append(json.loads(request.content))
  return httpx.Response(200,json={'usage':{'cost':.001,'prompt_tokens':200,'completion_tokens':90},'choices':[{'message':{'content':raw()},'finish_reason':'stop'}]})
 monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
 with TestClient(app.app) as client:
  token=client.post('/api/login',json={'code':'alice-secret'}).json()['token'];headers={'Authorization':'Bearer '+token}
  body={'run_id':'run','request_id':'call','spend_limit':1,'model':'model-test','observation':obs()}
  r=client.post('/api/agent/plan',json=body,headers=headers)
  assert r.status_code==200,r.text
  assert r.json()['cost']==.001 and len(sent)==1
  assert sent[0]['usage']=={'include':True} and sent[0]['max_tokens']==600
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
