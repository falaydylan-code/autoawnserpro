import asyncio
import pytest
from playwright.async_api import async_playwright
from adapters import Adapter, Selectors
from runner import Run
import runner


def test_full_practice_loop_graph_and_submission():
    async def scenario():
        run=Run('alice','practice','',Selectors(),True,10)
        try:
            await run.open('')
            assert run.status=='ready', run.message
            await run.execute()
            assert run.status=='completed', run.message
            assert len(run.results)==4
            assert all(r['status']=='verified' for r in run.results)
            assert [r['answer'] for r in run.results]==['4','Price increases','6','10']
            assert all(r['cost']==0 for r in run.results)
            assert await run.browser.page.locator('[data-agent-complete]').is_visible()
        finally:
            await run.close()
    asyncio.run(scenario())


def test_review_then_resume_without_duplicate_answers():
    async def scenario():
        run=Run('alice','practice','',Selectors(),False,10)
        try:
            await run.open('')
            await run.execute()
            assert run.status=='review',run.message
            assert await run.browser.page.locator('[data-agent-submit]').is_visible()
            run.auto_submit=True
            await run.execute()
            assert run.status=='completed',run.message
            assert len(run.results)==4
        finally: await run.close()
    asyncio.run(scenario())


def test_graph_screenshot_and_bad_answer():
    async def scenario():
        run=Run('alice','practice','',Selectors(),False,10)
        try:
            await run.open('')
            adapter=Adapter(run.browser.page,Selectors())
            question,_,image=await adapter.read()
            assert image.startswith(b'\x89PNG')
            with pytest.raises(ValueError,match='uniquely'):
                await adapter.apply('a nonexistent answer')
            assert await run.browser.page.locator('input:checked').count()==0
            await adapter.apply('4')
            await run.browser.page.locator('[data-agent-next]').click()
            question,_,image=await adapter.read()
            assert 'supply and demand' in question['text']
            assert len(image)>10000
        finally: await run.close()
    asyncio.run(scenario())


def test_stop_cancels_model_before_click(monkeypatch):
    async def scenario():
        entered=asyncio.Event()
        async def slow(*args):
            entered.set()
            await asyncio.sleep(100)
        monkeypatch.setattr(runner,'solve',slow)
        run=Run('alice','practice_ai','fake',Selectors(),False,10)
        try:
            await run.open('')
            run.task=asyncio.create_task(run.execute())
            await asyncio.wait_for(entered.wait(),10)
            await run.stop()
            assert run.status=='paused'
            assert await run.browser.page.locator('input:checked').count()==0
        finally: await run.close()
    asyncio.run(scenario())


def test_check_then_next_flow_does_not_solve_a_question_twice(tmp_path):
    """Sites where one button both checks and advances.

    MathPapa's practice pages relabel a single button from "Try it!" to
    "Next Question". Without a check step the loop sees the feedback state as a
    fresh question and pays to solve the same one twice.
    """
    page = tmp_path / 'twoclick.html'
    page.write_text('''<!doctype html><meta charset="utf-8"><body>
<div id="train">
  <span id="q">Solve. 2x = <span id="n">8</span></span>
  <input id="ans">
  <button id="go">Try it!</button><span id="fb"></span>
</div>
<script>
let stage=0, values=[8,10,12], idx=0;
document.getElementById('go').onclick=()=>{
  if(stage===0){stage=1;document.getElementById('go').textContent='Next Question';
                document.getElementById('fb').textContent='Correct!';}
  else{stage=0;idx++;document.getElementById('go').textContent='Try it!';
       document.getElementById('fb').textContent='';
       document.getElementById('ans').value='';
       document.getElementById('n').textContent=values[idx%values.length];}
};
</script></body>''', encoding='utf-8')

    selectors = Selectors(question='#train', choices='', answer='#ans',
                          check='#go', next='#go', submit='', complete='#never')
    solved = []

    async def scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            pg = await browser.new_page()
            await pg.goto(page.as_uri())
            adapter = Adapter(pg, selectors)
            for _ in range(3):
                question, fingerprint, _ = await adapter.read()
                solved.append(question['text'].split('=')[-1].strip().split()[0])
                await adapter.apply('4')
                checker = await adapter.button(selectors.check)
                await checker.click()
                for _ in range(20):
                    await asyncio.sleep(.05)
                    _, settled, _ = await adapter.read()
                    if settled != fingerprint:
                        fingerprint = settled
                        break
                nxt = await adapter.button(selectors.next)
                await nxt.click()
                for _ in range(20):
                    await asyncio.sleep(.05)
                    _, cur, _ = await adapter.read()
                    if cur != fingerprint:
                        break
            await browser.close()

    asyncio.run(scenario())
    assert solved == ['8', '10', '12'], f'each question should be read once, got {solved}'
