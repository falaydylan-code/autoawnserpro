import json
import asyncio
import pytest
from pydantic import ValidationError
import planner


def body(**changes):
    payload = dict(run_id='run-navigation', request_id='nav-request', spend_limit=2,
        observation=dict(question_key='q1', document_id='doc1', observation_id='obs1',
            question='Navigation only', slots=[], completeness=dict(complete=True, note='')),
        candidates=[dict(candidate_id='0:high',label='High',context='Rate confidence to submit your answer',
                         group='0:footer',kind='answer_submit',allowed_actions=['answer_submit'],confidence=True)],
        requested_actions=['check','answer_submit'], permissions=dict(check=True,advance=True,submit=False),
        answer_reason='The answer follows directly from the provided definitions.')
    payload.update(changes)
    return planner.NavigationRequest.model_validate(payload)


def response(**changes):
    result=dict(kind='action',question_key='q1',observation_id='obs1',candidate_id='0:high',
                action='answer_submit',reason='The local instruction submits this answer; reasoning supports this rating.')
    result.update(changes)
    return result


def call(request, result, finish='stop', seen=None):
    async def transport(messages, max_tokens):
        if seen is not None: seen.extend(messages)
        return json.dumps(result), finish
    return asyncio.run(planner.request_navigation(request, transport))


def test_valid_confidence_submission_is_a_separate_action():
    assert call(body(), response()).action == 'answer_submit'


@pytest.mark.parametrize('changes', [
    {'candidate_id':'invented'}, {'action':'advance'}, {'action':'submit'},
    {'question_key':'q2'}, {'observation_id':'old'},
    {'kind':'none'}, {'kind':'needs_review'}, {'reason':''},
    {'script':'document.body.click()'},
])
def test_invalid_or_widened_decisions_never_validate(changes):
    with pytest.raises(ValueError):
        call(body(), response(**changes))


def test_setting_and_disabled_state_are_enforced():
    request=body(permissions=dict(check=False,advance=True,submit=False))
    with pytest.raises(ValueError, match='GUARD_REJECTED'):call(request,response())
    request=body()
    request.candidates[0].disabled=True
    with pytest.raises(ValueError, match='GUARD_REJECTED'):call(request,response())


def test_duplicate_candidates_and_truncation_refuse():
    request=body()
    request.candidates.append(request.candidates[0])
    with pytest.raises(ValueError,match='TARGET_AMBIGUOUS'):call(request,response())
    with pytest.raises(ValueError,match='truncated'):call(body(),response(),finish='length')


def test_none_requires_no_target_and_navigation_does_not_forward_feedback_or_screenshot():
    request=body()
    request.observation.question='REVEALED ANSWER KEY'
    request.observation.screenshot='secret page pixels'
    request.observation.evidence=[{'feedback':'REVEALED ANSWER KEY'}]
    seen=[]
    result=call(request,response(kind='none',candidate_id='',action=None,reason='No eligible action.'),seen=seen)
    assert result.kind=='none'
    serialized=json.dumps(seen)
    assert 'REVEALED ANSWER KEY' not in serialized and 'secret page pixels' not in serialized
    assert request.answer_reason in serialized


def test_unknown_check_variant_allowed_but_not_final_submission():
    request=body(requested_actions=['check'])
    request.candidates[0].kind='unknown'
    request.candidates[0].confidence=False
    request.candidates[0].allowed_actions=['check','answer_submit','advance']
    assert call(request,response(action='check')).action=='check'
    with pytest.raises(ValueError):call(request,response(action='submit'))


def test_navigation_endpoint_is_metered_and_limited_to_two_calls(monkeypatch):
    import app, agent, httpx, store
    from fastapi.testclient import TestClient
    monkeypatch.setenv('OPENROUTER_API_KEY','navigation-test-key')
    async def models(who):
        return [{'id':'test','vision':False,'pricing':{'prompt':'0.0000003','completion':'0.000001'},
                 'supported_parameters':['structured_outputs']}]
    monkeypatch.setattr(app,'models',models)
    original=httpx.AsyncClient
    sent=[]
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200,json={'usage':{'cost':.001},
            'choices':[{'message':{'content':json.dumps(response())},'finish_reason':'stop'}]})
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with TestClient(app.app) as client:
        headers={'Authorization':'Bearer '+app.issue_token('navigation-test')}
        payload=body().model_dump()
        payload['model']='test'
        for i in range(2):
            payload['request_id']='nav-'+str(i)
            reply=client.post('/api/agent/navigation',json=payload,headers=headers)
            assert reply.status_code==200,reply.text
            assert reply.json()['phase']=='navigation'
        payload['request_id']='nav-third'
        refused=client.post('/api/agent/navigation',json=payload,headers=headers)
        assert 'BUDGET_EXHAUSTED' in refused.text and len(sent)==2
        assert store.plan_status('navigation-test','run-navigation')['cost']==pytest.approx(.002)
        assert all('navigation-test-key' not in json.dumps(m['messages']) for m in sent)
        caps=client.get('/api/capabilities?protocol=4').json()
        assert 'contextual_navigation' in caps['features']
        from pathlib import Path
        manifest=json.loads((Path(__file__).resolve().parents[1]/'extension/manifest.json').read_text())
        assert caps['extension']==manifest['version']
