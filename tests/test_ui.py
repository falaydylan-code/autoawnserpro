"""Exercise the real HTTP server and dashboard with no API credits."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from playwright.async_api import async_playwright


def test_dashboard_end_to_end(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env=dict(os.environ,PORT=str(port),HEADLESS='true',INVITE_CODES='ui-test-invite',DATA_DIR=str(tmp_path))
    root=Path(__file__).resolve().parents[1]
    process=subprocess.Popen([sys.executable,'app.py'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                if httpx.get(base+'/api/health',timeout=.3).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        else:raise AssertionError('Test web server did not start')
        async def scenario():
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True)
                page=await browser.new_page()
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(base)
                assert await page.locator('#invite').count()==0
                assert await page.locator('#open').is_disabled()
                # ETH starts red: browser control is off until it is armed.
                assert await page.locator('#eth').get_attribute('aria-pressed')=='false'
                assert 'off' in (await page.locator('#eth').get_attribute('class'))
                auth = httpx.post(base+'/api/login',json={'code':'ui-test-invite'}).json()['token']
                await page.goto(base+'/#access='+auth)
                await page.reload()
                await page.wait_for_function("!location.hash")
                # Still disabled while red, even with a valid token present.
                assert await page.locator('#open').is_disabled()
                await page.locator('#eth').click()
                await page.wait_for_function("document.querySelector('#eth').getAttribute('aria-pressed')==='true'")
                assert 'on' in (await page.locator('#eth').get_attribute('class'))
                await page.wait_for_function("!document.querySelector('#open').disabled")
                await page.locator('#workspace').wait_for(state='visible')
                await page.locator('#auto').check()
                await page.locator('#open').click()
                await page.wait_for_function("document.querySelector('#state').textContent==='READY'")
                await page.locator('#inspect').click()
                await page.locator('#previewImage').wait_for(state='visible')
                await page.locator('#preview').evaluate('(el)=>el.open=false')
                await page.locator('#start').click()
                await page.wait_for_function("document.querySelector('#state').textContent==='COMPLETED'",timeout=30000)
                assert await page.locator('#verified').inner_text()=='4'
                await page.locator('.record').first.click()
                await page.wait_for_timeout(2100)
                assert await page.locator('.detail').first.is_visible()
                async with page.expect_download() as event:await page.locator('#export').click()
                download=await event.value
                target=tmp_path/'results.csv'
                await download.save_as(target)
                assert 'Price increases' in target.read_text(encoding='utf-8')
                await page.locator('#close').click()
                await page.wait_for_function("document.querySelector('#state').textContent==='CLOSED'")
                # Turning ETH red again disarms the controls.
                await page.locator('#eth').click()
                await page.wait_for_function("document.querySelector('#open').disabled")
                assert 'off' in (await page.locator('#eth').get_attribute('class'))
                assert not errors
                await page.set_viewport_size({'width':390,'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                await browser.close()
        asyncio.run(scenario())
    finally:
        process.terminate()
        process.wait(timeout=15)
