import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone
from adapters import Adapter, Selectors
from browser import Browser
from solver import solve, Answer
from settings import ROOT, setting
import store

# Used only by the explicitly labeled, no-model practice simulation.
PRACTICE_ANSWERS = ['4', 'Price increases', '6', '10']


class Run:
    def __init__(self, owner, mode, model, selectors, auto_submit, limit, budget=None):
        self.id = uuid.uuid4().hex
        self.owner, self.mode, self.model = owner, mode, model
        # Who pays. For invite holders this is the same as owner. For public
        # guests it is tied to the network instead, so a visitor cannot reset
        # their spend limit just by clearing storage and taking a new token.
        self.budget = budget or owner
        self.selectors, self.auto_submit, self.limit = selectors, auto_submit, limit
        self.created = datetime.now(timezone.utc).isoformat()
        self.expires = time.time() + int(setting('SESSION_MINUTES', '20')) * 60
        self.status, self.message = 'opening', 'Opening an isolated browser…'
        self.logs, self.results = [], []
        self.browser = Browser()
        self.task = None
        self.seen = set()
        self.submit_attempted = False
        self.lock = asyncio.Lock()

    def public(self, include_live=True):
        return dict(id=self.id, mode=self.mode, model=self.model, created=self.created,
                    expires=self.expires, status=self.status, message=self.message,
                    logs=self.logs[-100:], results=self.results, auto_submit=self.auto_submit,
                    live_url=self.browser.live_url if include_live else '', browser_engine=self.browser.engine,
                    cost=sum(row.get('cost') or 0 for row in self.results),
                    unknown_costs=sum(1 for row in self.results if row.get('cost') is None and row.get('attempted')))

    def event(self, message, status=None):
        if status:
            self.status = status
        self.message = message
        self.logs.append({'time': datetime.now(timezone.utc).strftime('%H:%M:%S'), 'message': message})
        store.save(self)

    async def open(self, url):
        try:
            await self.browser.open()
            if self.mode in ('practice', 'practice_ai'):
                await self.browser.page.set_content((ROOT / 'frontend' / 'practice.html').read_text(encoding='utf-8'))
            else:
                await self.browser.page.goto(url, wait_until='domcontentloaded', timeout=45000)
            self.event('Browser ready. Log in and open one question, then click Start.' if self.mode == 'live'
                       else 'Practice ready. Click Start to test the loop.', 'ready')
        except asyncio.CancelledError:
            await self.browser.close()
            self.event('Browser opening was stopped. Close this session and open another.', 'error')
            raise
        except Exception as exc:
            self.event(str(exc) if isinstance(exc, ValueError) else 'Browser could not open. Check browser installation or Browserbase settings, then start a new session.', 'error')
            await self.browser.close()

    async def execute(self):
        adapter = Adapter(self.browser.page, self.selectors)
        self.event('Reading the question…', 'running')
        try:
            for _ in range(self.limit):
                if time.time() >= self.expires:
                    raise ValueError('Session time limit reached. Close this session and start another.')
                if await adapter.complete():
                    self.event('Submission confirmed by the page.', 'completed')
                    return
                question, fingerprint, screenshot = await adapter.read()
                if fingerprint not in self.seen:
                    row = {'question': question['text'], 'options': question['options'], 'fingerprint': fingerprint,
                           'answer': '', 'confidence': None, 'reasoning': '', 'raw_reply': '',
                           'status': 'solving', 'cost': 0 if self.mode == 'practice' else None,
                           'attempted': self.mode != 'practice', 'input_tokens': None, 'output_tokens': None,
                           'latency': None, 'verification': 'Not yet verified'}
                    self.results.append(row)
                    self.event('Solving question ' + str(len(self.seen) + 1) + (' with fixture answers (no AI)…' if self.mode == 'practice' else ' with MiniMax…'))
                    started = time.monotonic()
                    try:
                        if self.mode == 'practice':
                            # Bind fixtures to the known practice document, never a navigated page.
                            marker = await self.browser.page.locator('body').get_attribute('data-practice')
                            if marker != 'assignment-agent-v1' or self.browser.page.url != 'about:blank':
                                raise ValueError('Practice simulation only operates on the built-in practice page.')
                            answer = Answer(answer=PRACTICE_ANSWERS[len(self.seen)], confidence=100, reasoning='Fixture answer; this is not an AI accuracy measurement.')
                        else:
                            answer = await solve(self.budget, question, screenshot, self.model, row)
                        row.update(answer=answer.answer, confidence=answer.confidence, reasoning=answer.reasoning)
                        row['latency'] = round(time.monotonic() - started, 3)
                        # A user or page may have navigated while the model was thinking.
                        _, current, _ = await adapter.read()
                        if current != fingerprint:
                            raise ValueError('Question changed while solving. No answer was entered. Return to the intended question and resume.')
                        self.event('Entering the answer and checking the page…')
                        await adapter.apply(answer.answer)
                        row.update(status='verified', verification='Field value or selected radio read back successfully; correctness is not verified.')
                        self.seen.add(fingerprint)
                        self.event('Answer entered and verified.')
                    except BaseException:
                        row['status'] = 'interrupted' if isinstance(__import__('sys').exc_info()[1], asyncio.CancelledError) else 'error'
                        store.save(self)
                        raise
                # Some sites verify an answer and advance with two separate clicks
                # of the same control ("Try it!" then "Next Question"). Without
                # this step the loop mistakes the feedback state for a new
                # question and solves the same one twice.
                if getattr(self.selectors, 'check', ''):
                    checker = await adapter.button(self.selectors.check)
                    if checker and await checker.is_enabled():
                        self.event('Checking the answer on the page…')
                        await checker.click()
                        for _ in range(20):
                            await asyncio.sleep(.3)
                            try:
                                _, settled, _ = await adapter.read()
                            except Exception:
                                continue
                            if settled != fingerprint:
                                fingerprint = settled
                                self.seen.add(settled)
                                break

                button = await adapter.button(self.selectors.next)
                if button:
                    if not await button.is_enabled():
                        raise ValueError('Next is disabled. Check required fields or page validation before resuming.')
                    self.event('Clicking Next and waiting for a new question…')
                    await button.click()
                    changed = False
                    for _ in range(30):
                        await asyncio.sleep(.3)
                        if await adapter.complete():
                            self.event('Completion confirmed by the page.', 'completed')
                            return
                        try:
                            _, current, _ = await adapter.read()
                            if current != fingerprint:
                                changed = True
                                break
                        except Exception:
                            pass
                    if not changed:
                        raise ValueError('Next did not load a different question. Check the page and resume; the recorded answer will not be re-solved.')
                    continue
                submit = await adapter.button(self.selectors.submit)
                if submit:
                    if not self.auto_submit:
                        self.event('Reached the final question. Review and submit manually, or enable auto-submit and resume.', 'review')
                        return
                    if self.submit_attempted:
                        raise ValueError('Submission was already attempted. Verify or finish manually; automatic resubmission is blocked.')
                    self.submit_attempted = True
                    self.event('Submitting because auto-submit is enabled...')
                    await submit.click()
                    for _ in range(30):
                        await asyncio.sleep(.3)
                        if await adapter.complete():
                            self.event('Submission confirmed by the page.', 'completed')
                            return
                    raise ValueError('Submit was clicked but confirmation was not found. Inspect the page; do not blindly submit again.')
                raise ValueError('Neither Next nor Submit was found. Configure the navigation selectors or finish manually.')
            self.event('Question limit reached. Review progress before resuming.', 'paused')
        except asyncio.CancelledError:
            self.event('Stopped. No further browser actions will be issued. An API request already sent may still be billed.', 'paused')
        except Exception as exc:
            self.event(str(exc) if isinstance(exc, ValueError) else 'Browser action failed or timed out. Check the page and selectors, then resume.', 'error')

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def close(self, expired=False):
        await self.stop()
        warning = await self.browser.close()
        self.event(('Session expired.' if expired else 'Browser session closed.') + (' ' + warning if warning else ''), 'expired' if expired else 'closed')
