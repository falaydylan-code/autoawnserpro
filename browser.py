import httpx
from playwright.async_api import async_playwright
from settings import setting


async def bb(method, path, payload=None):
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.request(method, 'https://api.browserbase.com/v1/sessions' + path,
            headers={'X-BB-API-Key': setting('BROWSERBASE_API_KEY')}, json=payload)
    if response.status_code not in (200, 201):
        raise ValueError(f'Browserbase HTTP {response.status_code}. Check credentials, credits, and concurrent-session allowance.')
    return response.json()


class Browser:
    def __init__(self):
        self.pw = self.browser = self.context = self.page = None
        self.remote_id = None
        self.live_url = ''
        self.engine = ''

    async def open(self):
        self.pw = await async_playwright().start()
        if setting('BROWSER_MODE', 'local') == 'cloud':
            if not setting('BROWSERBASE_API_KEY') or not setting('BROWSERBASE_PROJECT_ID'):
                raise ValueError('Set BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID on the backend, then restart.')
            result = await bb('POST', '', {
                'projectId': setting('BROWSERBASE_PROJECT_ID'),
                'timeout': max(60, min(21600, int(setting('SESSION_MINUTES', '20')) * 60)),
                'browserSettings': {'viewport': {'width': 1280, 'height': 900},
                                    'recordSession': False, 'logSession': False}
            })
            self.remote_id = result['id']
            self.browser = await self.pw.chromium.connect_over_cdp(result['connectUrl'])
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            debug = await bb('GET', '/' + self.remote_id + '/debug')
            self.live_url = debug['debuggerFullscreenUrl']
        else:
            headless = setting('HEADLESS', 'false').lower() == 'true'
            try:
                self.browser = await self.pw.chromium.launch(headless=headless)
                self.engine = 'Chromium'
            except Exception:
                try:
                    self.browser = await self.pw.chromium.launch(channel='chrome', headless=headless)
                    self.engine = 'Installed Chrome (Chromium fallback)'
                except Exception:
                    raise ValueError('No usable browser found. Install Google Chrome or run setup.bat to install Chromium, then restart.') from None
            self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 900})
            self.page = await self.context.new_page()
        self.page.set_default_timeout(10000)

    async def close(self):
        errors = []
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                errors.append('Browser connection could not close.')
        if self.remote_id:
            try:
                await bb('POST', '/' + self.remote_id, {'projectId': setting('BROWSERBASE_PROJECT_ID'), 'status': 'REQUEST_RELEASE'})
            except Exception:
                errors.append('Browserbase release was not confirmed. End the session in Browserbase; its time limit remains active.')
        if self.pw:
            try:
                await self.pw.stop()
            except Exception:
                pass
        self.live_url = ''
        return ' '.join(errors)
