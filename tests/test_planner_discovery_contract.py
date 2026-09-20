import json
import pytest
import planner
import store
from test_planner_contract import obs, raw


def test_candidate_classification_can_only_name_an_offered_candidate():
    o=obs('unresolved')
    r=planner.parse_plan(raw(kind='request_inspection',tasks=[],inspection={'slot_key':'q/a','question':'Read grouping and state evidence','requests':['classify_choices']}))
    with pytest.raises(planner.InspectionTargetError):planner.validate_context(r,o)
    o['slots'][0]['interaction']={'adapter':'candidate_choices','evidence':{'state_attribute':'aria-pressed'}}
    assert planner.validate_context(r,o).kind=='request_inspection'
    with pytest.raises(ValueError,match='resolved offered slot'):planner.validate_context(planner.parse_plan(raw()),o)


def test_exact_broken_quizlet_prefix_is_strictly_rejected():
    text='":"request_inspection","question_key":"q","inspection":{"script":"document.body.click()"}}'
    with pytest.raises(planner.InvalidJsonError,match='invalid JSON at line 1, column 4'):
        planner.parse_plan(text,'stop')
    # Semantically invalid valid-JSON replies do not receive the format retry marker.
    with pytest.raises(ValueError) as err:planner.parse_plan(raw(extra='bad'))
    assert not isinstance(err.value,planner.InvalidJsonError)


def test_format_correction_is_metered_and_server_bounded(monkeypatch):
    import app,agent,httpx
    from fastapi.testclient import TestClient
    monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
    async def models(who):return [{'id':'test','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},'supported_parameters':['structured_outputs']}]
    monkeypatch.setattr(app,'models',models)
    original=httpx.AsyncClient;sent=[]
    def handler(request):
        sent.append(json.loads(request.content))
        content='":"request_inspection"}' if len(sent)==1 else raw()
        return httpx.Response(200,json={'usage':{'cost':.001},'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with TestClient(app.app) as client:
        headers={'Authorization':'Bearer '+app.issue_token('format-test')}
        body={'run_id':'format-run','request_id':'first','model':'test','observation':obs()}
        first=client.post('/api/agent/plan',json=body,headers=headers)
        assert first.status_code==400 and first.json()['cost']==.001
        assert first.json()['format_correction']=={'kind':'invalid_json'}
        body.update(request_id='correction',format_correction=True)
        assert client.post('/api/agent/plan',json=body,headers=headers).status_code==200
        body['request_id']='repeat'
        repeat=client.post('/api/agent/plan',json=body,headers=headers)
        assert 'BUDGET_EXHAUSTED' in repeat.text and len(sent)==2
        assert store.plan_status('format-test','format-run')['cost']==pytest.approx(.002)


def test_extension_requires_matching_discovery_backend():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    worker=(root/'extension/background.js').read_text(encoding='utf-8')
    assert 'choice_discovery' in worker and 'bounded_format_correction' in worker
    import app
    from fastapi.testclient import TestClient
    with TestClient(app.app) as client:
        caps=client.get('/api/capabilities?protocol=4').json()
        assert caps['extension']==json.loads((root/'extension/manifest.json').read_text())['version']
        assert {'choice_discovery','bounded_format_correction'}<=set(caps['features'])
