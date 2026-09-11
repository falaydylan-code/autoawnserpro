import asyncio
import httpx
from browser import Browser, bb
import browser as browser_module


def test_browserbase_credentials_and_release(monkeypatch):
    monkeypatch.setenv('BROWSERBASE_API_KEY', 'fake-browserbase-key')
    original = httpx.AsyncClient
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'id':'fake-session'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    async def scenario():
        await bb('POST','',{'projectId':'test'})
        b=Browser()
        b.remote_id='fake-session'
        await b.close()
    asyncio.run(scenario())
    assert calls[0].headers['X-BB-API-Key']=='fake-browserbase-key'
    assert calls[1].url.path.endswith('/fake-session')
    assert b'REQUEST_RELEASE' in calls[1].content


def test_browserbase_error_does_not_expose_response(monkeypatch):
    import pytest
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(401,text='secret-provider-data')),**kw))
    with pytest.raises(ValueError) as exc:
        asyncio.run(bb('POST','',{}))
    assert 'secret-provider-data' not in str(exc.value)
    assert '401' in str(exc.value)


def test_release_failure_visible(monkeypatch):
    async def fail(*args): raise ValueError('provider failed')
    monkeypatch.setattr(browser_module,'bb',fail)
    b=Browser();b.remote_id='fake';b.live_url='private-live-url'
    message=asyncio.run(b.close())
    assert 'not confirmed' in message
    assert not b.live_url
