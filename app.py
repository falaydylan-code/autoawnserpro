import asyncio
import csv
import hashlib
import hmac
import io
import ipaddress
import secrets
import socket
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from settings import ROOT, setting, missing
from adapters import Selectors
from runner import Run
import agent
import store

runs, tokens, attempts = {}, {}, {}
# host -> addresses it first resolved to, so a later swap is visible
_resolved_hosts: dict = {}
creation_lock = asyncio.Lock()


async def cleanup():
    while True:
        await asyncio.sleep(15)
        for rid, run in list(runs.items()):
            if time.time() > run.expires:
                async with run.lock:
                    await run.close(expired=True)
                    runs.pop(rid, None)
        for token, (_, expiry) in list(tokens.items()):
            if expiry < time.time():
                tokens.pop(token, None)


@asynccontextmanager
async def lifespan(app):
    store.recover()
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    for run in list(runs.values()):
        await run.close()
    runs.clear()


app = FastAPI(title='Assignment Lab', lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in setting('FRONTEND_ORIGIN', 'http://127.0.0.1:8010').split(',')],
                   # The Chrome extension calls from chrome-extension://<its id>, which is
                   # only known once it is loaded, so it is matched by scheme instead.
                   allow_origin_regex=r'^chrome-extension://[a-p]{32}$',
                   allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])


@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.exception_handler(Exception)
async def unexpected(request, exc):
    return JSONResponse(status_code=500, content={'detail': 'The server could not complete this action. Check setup and restart the session.'})


def owner(authorization: str = Header(default='')):
    value = tokens.get(authorization.removeprefix('Bearer '))
    if not value or value[1] < time.time():
        raise HTTPException(401, 'Sign in with your invite code to continue.')
    return value[0]


class Login(BaseModel):
    code: str = Field(min_length=1, max_length=200)


def throttle(request, kind, per_ip, per_global, window, message):
    """Per-IP and global rate limit. The dashboard is public, so every entry
    point that can spend money has to be bounded by something other than a
    secret. Caller-supplied forwarded headers are never trusted."""
    ip = request.client.host if request.client else 'unknown'
    now = time.time()
    for bucket, cap in ((kind + ':global', per_global), (kind + ':' + ip, per_ip)):
        attempts[bucket] = [t for t in attempts.get(bucket, []) if now - t < window]
        if len(attempts[bucket]) >= cap:
            raise HTTPException(429, message)
        attempts[bucket].append(now)
    return ip


def budget_key(who, request):
    """Guests share one spend allowance per network. A random guest identity
    keeps sessions private, but it must not hand out a fresh budget on demand."""
    if not str(who).startswith('guest:'):
        return who
    ip = request.client.host if request.client else 'unknown'
    return 'net:' + hashlib.sha256(ip.encode()).hexdigest()


def issue_token(identity):
    token = secrets.token_urlsafe(32)
    tokens[token] = (identity, time.time() + 8 * 3600)
    return token


@app.post('/api/guest')
async def guest(request: Request):
    """Public sign-in. Anyone loading the dashboard gets their own identity, so
    sessions and history stay separated per visitor even without a code."""
    if setting('PUBLIC_ACCESS', 'false').lower() != 'true':
        raise HTTPException(403, 'Public access is turned off. Use your private access link.')
    throttle(request, 'guest', per_ip=10, per_global=200, window=300,
             message='Too many new visitors from your network. Wait a few minutes.')
    return {'token': issue_token('guest:' + secrets.token_hex(8))}


@app.post('/api/login')
async def login(body: Login, request: Request):
    ip = throttle(request, 'login', per_ip=20, per_global=100, window=60,
                  message='Too many sign-in attempts. Wait one minute.')
    now = time.time()
    codes = [x.strip() for x in setting('INVITE_CODES').split(',') if x.strip()]
    if not codes and setting('APP_ENV', 'development') == 'development':
        codes = ['LOCAL-DEMO']
    if not any(hmac.compare_digest(body.code, code) for code in codes):
        raise HTTPException(401, 'Invite code not recognized. Ask the operator for your code.')
    return {'token': issue_token(hashlib.sha256(body.code.encode()).hexdigest())}


@app.get('/api/health')
async def health():
    return {'ok': True, 'service': 'Assignment Lab'}


@app.get('/api/setup')
async def setup(who=Depends(owner)):
    return {'missing': missing(), 'browser_mode': setting('BROWSER_MODE', 'local'),
            'model': setting('OPENROUTER_MODEL'), 'max_sessions': int(setting('MAX_ACTIVE_SESSIONS', '3')),
            'session_minutes': int(setting('SESSION_MINUTES', '20')),
            'allowed_hosts': setting('ALLOWED_ASSIGNMENT_HOSTS'),
            'message': 'Practice simulation uses fixture answers and makes no model calls.'}


@app.get('/api/models')
async def models(who=Depends(owner)):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            result = await client.get('https://openrouter.ai/api/v1/models')
            result.raise_for_status()
            models = result.json()['data']
        return [{'id': m['id'], 'vision': 'image' in m.get('architecture', {}).get('input_modalities', []),
                 'pricing': m.get('pricing', {})} for m in models if 'minimax' in m['id'].lower()]
    except Exception:
        raise HTTPException(502, 'Could not load the live OpenRouter model list. Check internet access and retry.') from None


async def safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use an HTTPS assignment URL without embedded credentials or a custom port.')
    host = parsed.hostname.lower()
    allowed = [h.strip().lower() for h in setting('ALLOWED_ASSIGNMENT_HOSTS').split(',') if h.strip()]
    # '*' opens every public website. The private-address check below still
    # applies, so this can never be pointed at the host's internal network.
    if '*' not in allowed:
        if not any(host == h or host.endswith('.' + h) for h in allowed):
            raise ValueError('This website is not enabled. Add its domain to ALLOWED_ASSIGNMENT_HOSTS on the backend.')
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        resolved = {a[4][0] for a in addresses}
        if not resolved or any(not ipaddress.ip_address(ip).is_global for ip in resolved):
            raise ValueError('Private network addresses are not supported.')
    except socket.gaierror:
        raise ValueError('Assignment domain could not be resolved. Check the URL.') from None

    # A host that answers with a public address now can answer with an internal
    # one a moment later, before the browser connects. The browser cannot be
    # pinned to the address checked here, so instead the first answer is
    # remembered and every later check for the same host must still overlap it.
    # A host that starts pointing somewhere new is refused rather than followed.
    known = _resolved_hosts.get(host)
    if known is None:
        _resolved_hosts[host] = resolved
    elif not (known & resolved):
        raise ValueError(
            'This domain changed which server it points to during the session. '
            'Refused, because that is how a public address is swapped for an internal one.'
        )
    return url


class Create(BaseModel):
    mode: str = Field(default='practice', pattern='^(practice|practice_ai|live)$')
    url: str = Field(default='', max_length=2000)
    model: str = Field(default='', max_length=200)
    selectors: Selectors = Field(default_factory=Selectors)
    auto_submit: bool = False
    question_limit: int = Field(default=40, ge=1, le=100)


async def initialize(run, url):
    # Guard every navigation, including redirects and login popups, for local browser safety.
    await run.open('about:blank' if run.mode == 'live' else url)
    if run.mode == 'live' and run.status != 'error':
        async def guard(route):
            try:
                await safe_url(route.request.url)
                await route.continue_()
            except Exception:
                await route.abort()
        await run.browser.context.route('**/*', guard)
        try:
            await run.browser.page.goto(url, wait_until='domcontentloaded', timeout=45000)
        except Exception:
            run.event('Page did not load completely. Check the URL and allowlisted login/asset domains. Inspect the browser before continuing.', 'error')


@app.post('/api/sessions')
async def create(body: Create, request: Request, who=Depends(owner)):
    # Opening a session spends Browserbase minutes and, outside practice mode,
    # model credit. Bound it per network as well as by the seat limit below.
    throttle(request, 'session', per_ip=6, per_global=60, window=600,
             message='Too many sessions started from your network. Wait a few minutes and try again.')
    if body.mode != 'practice':
        if not setting('OPENROUTER_API_KEY'):
            raise HTTPException(400, 'Set OPENROUTER_API_KEY on the backend and restart.')
        registry = await models(who)
        selected = body.model or setting('OPENROUTER_MODEL')
        if not any(m['id'] == selected and m['vision'] for m in registry):
            raise HTTPException(400, 'Select a MiniMax model with image input from the live model list.')
        body.model = selected
    if body.mode == 'live':
        try:
            await safe_url(body.url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    async with creation_lock:
        if any(r.owner == who and r.status not in ('closed', 'expired') for r in runs.values()):
            raise HTTPException(409, 'Close your current session before opening another.')
        if len(runs) >= int(setting('MAX_ACTIVE_SESSIONS', '3')):
            raise HTTPException(429, 'All browser slots are busy. Try again after someone closes their session.')
        selectors = Selectors() if body.mode != 'live' else body.selectors
        run = Run(who, body.mode, body.model, selectors, body.auto_submit, body.question_limit,
                  budget=budget_key(who, request))
        runs[run.id] = run
        store.save(run)
        run.task = asyncio.create_task(initialize(run, body.url))
        return run.public()


def owned(rid, who):
    run = runs.get(rid)
    if not run or run.owner != who:
        raise HTTPException(404, 'Session not found. Open a new session or view your history.')
    return run


@app.get('/api/sessions/{rid}')
async def status(rid: str, who=Depends(owner)):
    return owned(rid, who).public()


class Start(BaseModel):
    auto_submit: bool = False
    page_index: int = Field(default=0, ge=0, le=50)


@app.get('/api/sessions/{rid}/pages')
async def pages(rid: str, who=Depends(owner)):
    run = owned(rid, who)
    if not run.browser.context:
        return []
    return [{'index': i, 'title': await p.title()} for i, p in enumerate(run.browser.context.pages)]


class Inspect(BaseModel):
    selectors: Selectors = Field(default_factory=Selectors)
    page_index: int = Field(default=0, ge=0, le=50)


@app.post('/api/sessions/{rid}/inspect')
async def inspect(rid: str, body: Inspect, who=Depends(owner)):
    import base64
    from adapters import Adapter
    run = owned(rid, who)
    async with run.lock:
        if run.task and not run.task.done():
            raise HTTPException(409, 'Stop the agent before inspecting or changing controls.')
        if not run.browser.context or body.page_index >= len(run.browser.context.pages):
            raise HTTPException(400, 'Open a browser and choose the assignment tab first.')
        page = run.browser.context.pages[body.page_index]
        selectors = Selectors() if run.mode != 'live' else body.selectors
        try:
            question, _, screenshot = await Adapter(page, selectors).read()
        except Exception as exc:
            raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else 'Could not read those controls. Check selectors and the selected browser tab.') from None
        run.selectors = selectors
        run.browser.page = page
        run.event('Question preview checked. Verify that its screenshot includes the complete graph and labels.')
        return {'question': question, 'image': 'data:image/png;base64,' + base64.b64encode(screenshot).decode()}


@app.post('/api/sessions/{rid}/start')
async def start(rid: str, body: Start, who=Depends(owner)):
    run = owned(rid, who)
    async with run.lock:
        if run.task and not run.task.done():
            raise HTTPException(409, 'This session is already working. Wait or click Stop.')
        if run.status in ('closed', 'expired', 'completed'):
            raise HTTPException(409, 'This session has finished. Open a new session.')
        if not run.browser.context or body.page_index >= len(run.browser.context.pages):
            raise HTTPException(400, 'Browser page unavailable. Close this session and open another.')
        run.browser.page = run.browser.context.pages[body.page_index]
        run.auto_submit = body.auto_submit
        run.event('Starting…', 'running')
        run.task = asyncio.create_task(run.execute())
    return run.public()


@app.post('/api/sessions/{rid}/stop')
async def stop(rid: str, who=Depends(owner)):
    run = owned(rid, who)
    async with run.lock:
        await run.stop()
    return run.public()


@app.post('/api/sessions/{rid}/close')
async def close(rid: str, who=Depends(owner)):
    run = owned(rid, who)
    async with run.lock:
        await run.close()
        runs.pop(rid, None)
    return run.public()


class ObservedPart(agent.Part):
    entered: bool = False
    verified: bool = False
    retired: bool = False
    target_key: str = Field(default='', max_length=600)
    source_key: str = Field(default='', max_length=600)
    source_label: str = Field(default='', max_length=400)


class ObservedElement(BaseModel):
    ref: int = Field(ge=1, le=10000, strict=True)
    key: str = Field(default='', max_length=600)
    group: int | None = Field(default=None, ge=1, le=10000)
    depth: int = Field(default=0, ge=0, le=20)
    role: str = Field(default='', max_length=60)
    name: str = Field(default='', max_length=400)
    context: str = Field(default='', max_length=1200)
    row: str = Field(default='', max_length=300)
    column: str = Field(default='', max_length=300)
    blank: str = Field(default='', max_length=80)
    drag: str | None = Field(default=None, max_length=20)
    control: str = Field(default='', max_length=30)
    value: str = Field(default='', max_length=1000)
    checked: bool = False
    disabled: bool = False
    new: bool = False
    choice: bool = False
    external: bool = False
    dropdown: bool = False
    trigger: bool = False
    expanded: bool = False
    opaque: bool = False
    qid: str = Field(default='', max_length=200)
    owner_ref: int | None = None
    list_ref: int | None = None
    order_index: int | None = None
    box: dict[str, Annotated[float, Field(allow_inf_nan=False, ge=-10_000_000, le=10_000_000)]] | None = None


class VerificationTarget(BaseModel):
    part_id: str = Field(min_length=1, max_length=80)
    what: str = Field(max_length=300)
    kind: Literal['value', 'ordering'] = 'value'


class Observation(BaseModel):
    screenshot: str = Field(default='', max_length=12_000_000)
    elements: list[ObservedElement] = Field(default_factory=list, max_length=400)
    text: str = Field(default='', max_length=200_000)
    host: str = Field(default='', max_length=300)
    step: int = Field(default=1, ge=1, le=10000)
    step_budget: int = Field(default=8, ge=1, le=1000)
    page_changed: bool = True
    last_action: dict = Field(default_factory=dict)
    task_note: str = Field(default='', max_length=2000)
    phase: Literal['', 'read_check', 'act', 'must_act', 'navigate', 'verify'] = ''
    observation_id: str = Field(default='', max_length=80)
    page_state: Literal['', 'answering', 'editable_feedback', 'locked', 'loading', 'complete'] = ''
    feedback: str = Field(default='', max_length=400)
    attempts_left: int | None = Field(default=None, ge=0, le=1000)
    verification: VerificationTarget | None = None
    plan: str = Field(default='', max_length=2000)
    progress: str = Field(default='', max_length=4000)
    ledger: list[ObservedPart] = Field(default_factory=list, max_length=60)
    warnings: list[Annotated[str, Field(max_length=1000)]] = Field(default_factory=list, max_length=30)
    auto_submit: bool = False
    advance: bool = False
    model: str = Field(default='', max_length=200)


@app.get('/api/capabilities')
async def capabilities():
    # The extension refuses to start against a backend that does not report the
    # protocol it needs, so a stale deploy is an actionable message, not a loop.
    return {'protocol': 3, 'extension': '0.8.0',
            'features': ['parts', 'ordering', 'visual_input', 'visual_verification', 'browser_input', 'page_states', 'no_step_ceiling']}


@app.post('/api/agent/step')
async def agent_step(body: Observation, request: Request, who=Depends(owner)):
    """One turn of the observe / decide / act loop.

    The extension observes and acts; this returns a single validated action.
    Cost is metered against the caller the same way a solve is.
    """
    throttle(request, 'agentstep', per_ip=1500, per_global=9000, window=600,
             message='Too many agent steps from your network. Wait a few minutes.')
    if not setting('OPENROUTER_API_KEY'):
        raise HTTPException(400, 'Set OPENROUTER_API_KEY on the backend and restart.')
    if len(body.elements) > 400:
        raise HTTPException(400, 'That page reported too many interactive elements to review safely.')
    selected = body.model or setting('OPENROUTER_MODEL')
    registry = await models(who)
    if not any(m['id'] == selected and m['vision'] for m in registry):
        raise HTTPException(400, 'Select a model with image input from the live model list.')

    record = {}
    try:
        require = ''
        if body.phase == 'read_check':
            require = 'read_check'
        elif body.phase == 'must_act':
            require = 'act'
        elif body.phase == 'verify':
            require = 'verify'
        action = await agent.decide(budget_key(who, request), body.model_dump(), selected, record,
                                    require=require)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={'detail':str(exc), 'cost':record.get('cost'),
            'input_tokens':record.get('input_tokens'), 'output_tokens':record.get('output_tokens')})
    return {
        'action': action.model_dump(),
        'cost': record.get('cost'),
        'input_tokens': record.get('input_tokens'),
        'output_tokens': record.get('output_tokens'),
        'raw': (record.get('raw_reply') or '')[:4000],
        'working': action.working[:4000],
        'plan': action.plan[:2000],
        'sent': {
            'elements': len(body.elements),
            'text_chars': len(body.text or ''),
            'screenshot': bool(body.screenshot),
            'phase': body.phase or 'act',
            'advance': body.advance,
            'model': selected,
        },
    }


@app.get('/api/history')
async def history(who=Depends(owner)):
    return store.history(who)


@app.get('/api/history/{rid}/csv')
async def export(rid: str, who=Depends(owner)):
    item = next((r for r in store.history(who) if r['id'] == rid), None)
    if not item:
        raise HTTPException(404, 'Result not found.')
    output = io.StringIO(newline='')
    fields = ['question', 'answer', 'status', 'confidence', 'reasoning', 'cost', 'input_tokens', 'output_tokens', 'latency', 'verification', 'raw_reply']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in item['results']:
        safe = dict(row)
        for key, value in safe.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                safe[key] = "'" + value
        writer.writerow(safe)
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="assignment-{rid}.csv"'})


@app.get('/')
async def index():
    return FileResponse(ROOT / 'frontend' / 'index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')


if __name__ == '__main__':
    import uvicorn
    production = setting('APP_ENV', 'development') == 'production'
    if production and (not setting('INVITE_CODES') or setting('BROWSER_MODE') != 'cloud' or not setting('BROWSERBASE_API_KEY')):
        print('Hosted setup incomplete. Set INVITE_CODES, BROWSER_MODE=cloud, and Browserbase credentials before starting.')
        raise SystemExit(1)
    port = int(setting('PORT', '8010'))
    print('Assignment Lab: ' + ('hosting port ' + str(port) if production else f'http://127.0.0.1:{port}'))
    if missing():
        print('Practice mode is available. For AI runs configure: ' + ', '.join(missing()))
    uvicorn.run(app, host='0.0.0.0' if production else '127.0.0.1', port=port, access_log=False)
