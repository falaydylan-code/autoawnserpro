import asyncio
import hashlib
import json
from pydantic import BaseModel, Field


class Selectors(BaseModel):
    question: str = Field(default='[data-agent-question]', min_length=1, max_length=500)
    choices: str = Field(default='input[type=radio]', max_length=500)
    answer: str = Field(default='[data-agent-answer]', max_length=500)
    check: str = Field(default='', max_length=500)
    next: str = Field(default='[data-agent-next]', max_length=500)
    submit: str = Field(default='[data-agent-submit]', max_length=500)
    complete: str = Field(default='[data-agent-complete]', max_length=500)


class Adapter:
    def __init__(self, page, selectors):
        self.page = page
        self.s = selectors
        self.frame = None

    async def locate(self):
        matches = []
        for frame in self.page.frames:
            roots = frame.locator(self.s.question)
            for index in range(await roots.count()):
                root = roots.nth(index)
                if await root.is_visible():
                    matches.append((frame, root))
        if len(matches) != 1:
            raise ValueError('Could not identify exactly one question. Open a single question and configure its question selector.')
        self.frame, root = matches[0]
        return root

    async def read(self):
        root = await self.locate()
        text = await root.inner_text()
        if len(text) > 24000:
            raise ValueError('Question region is too large. Select the question and graph rather than the whole page.')
        choices = root.locator(self.s.choices) if self.s.choices else root.locator('agent-no-choice')
        labels = []
        for i in range(await choices.count()):
            el = choices.nth(i)
            if not await el.is_visible():
                raise ValueError('An answer control is hidden. Adjust the choices selector to visible controls.')
            labels.append(await el.evaluate('(el) => (el.labels?.[0]?.innerText || el.getAttribute("aria-label") || el.innerText || el.value || "").trim()'))
        if not labels and (not self.s.answer or await root.locator(self.s.answer).count() != 1):
            raise ValueError('No supported answer controls found. Configure radio choices or one text/numeric answer field.')
        question = {'text': text, 'options': labels}
        fingerprint = hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest()
        rect = await root.bounding_box()
        if not rect or rect['height'] > 6000 or rect['width'] > 2500:
            raise ValueError('Question screenshot is too large or unavailable. Narrow the question selector.')
        await root.scroll_into_view_if_needed()
        for _ in range(30):
            images_ready = await root.locator('img').evaluate_all('(images) => images.every(img => img.complete && img.naturalWidth > 0)')
            if images_ready:
                break
            await asyncio.sleep(.25)
        else:
            raise ValueError('A question image did not load. Check page access and resource domains before starting.')
        screenshot = await root.screenshot(type='png', timeout=15000)
        return question, fingerprint, screenshot

    async def apply(self, answer):
        root = await self.locate()
        choices = root.locator(self.s.choices) if self.s.choices else root.locator('agent-no-choice')
        count = await choices.count()
        if count:
            labels = [await choices.nth(i).evaluate('(el) => (el.labels?.[0]?.innerText || el.getAttribute("aria-label") || el.innerText || el.value || "").trim()') for i in range(count)]
            matches = [i for i, label in enumerate(labels) if label.casefold().strip() == answer.casefold().strip()]
            if not matches:
                import re
                letter = re.fullmatch(r'\(?([A-Z])\)?\.?', answer.strip().upper())
                if letter and ord(letter[1]) - 65 < count:
                    matches = [ord(letter[1]) - 65]
            if len(matches) != 1:
                raise ValueError('Answer does not uniquely match an option. No option was selected; review the model answer.')
            el = choices.nth(matches[0])
            kind = await el.get_attribute('type')
            if kind == 'radio':
                await el.check(timeout=10000)
                if not await el.is_checked():
                    raise ValueError('Selection did not stick. Review this question.')
            elif await el.get_attribute('role') == 'radio':
                await el.click(timeout=10000)
                if await el.get_attribute('aria-checked') != 'true':
                    raise ValueError('Custom radio did not confirm selection. Review this question.')
            else:
                raise ValueError('Unsupported answer control. Use native radio buttons or role=radio controls.')
        else:
            el = root.locator(self.s.answer)
            await el.fill(answer, timeout=10000)
            await el.press('Tab')
            if await el.input_value() != answer:
                raise ValueError('Entered answer did not stick. Review this question.')

    async def button(self, selector):
        if not selector:
            return None
        frame = self.frame or self.page.main_frame
        loc = frame.locator(selector)
        visible = [loc.nth(i) for i in range(await loc.count()) if await loc.nth(i).is_visible()]
        if len(visible) > 1:
            raise ValueError('Multiple navigation buttons matched. Narrow the selector before continuing.')
        return visible[0] if visible else None

    async def complete(self):
        for frame in self.page.frames:
            if self.s.complete:
                items = frame.locator(self.s.complete)
                for i in range(await items.count()):
                    if await items.nth(i).is_visible():
                        return True
        return False
