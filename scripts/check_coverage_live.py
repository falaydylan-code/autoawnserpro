"""Optional paid smoke check through the real extension, backend and provider.

Not collected by pytest. Uses a temporary browser profile and localhost servers.
Example: python scripts/check_coverage_live.py --env-file ../assignment-agent/.env
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--fixture',default='multipart_tabs.html',choices=['multipart_tabs.html','matching_html5.html','matching_pointer.html','blanks_prose.html','table_blanks.html','shadow_question.html'])
    parser.add_argument('--url',default='')
    parser.add_argument('--timeout',type=int,default=240)
    args=parser.parse_args()
    if args.env_file.exists():
        for line in args.env_file.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name,value=line.split('=',1)
                if name.strip() in ('OPENROUTER_API_KEY','OPENROUTER_MODEL'):os.environ[name.strip()]=value.strip().strip('"\'')
    if not os.environ.get('OPENROUTER_API_KEY'):raise SystemExit('Set OPENROUTER_API_KEY or pass --env-file. No call made.')
    os.environ.update(APP_ENV='development',PUBLIC_ACCESS='true',BROWSER_MODE='local',MAX_CALLS_PER_INVITE='24',MAX_COST_PER_INVITE='0.50')
    from playwright.sync_api import sync_playwright
    import uvicorn
    from app import app
    out=ROOT/'data'/'coverage-checks';out.mkdir(parents=True,exist_ok=True)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    fixtures=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT/'tests'/'fixtures')))
    threading.Thread(target=fixtures.serve_forever,daemon=True).start()
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    while not server.started and thread.is_alive():time.sleep(.05)
    status={};name='mathpapa' if args.url else args.fixture.removesuffix('.html')
    try:
        with tempfile.TemporaryDirectory(prefix='coverage-live-') as directory:
            # SQLite cleanup may outlive the browser on Windows. Keep metering
            # under ignored data/, outside the ephemeral profile.
            os.environ['DATA_DIR']=str(out/('meter-'+str(time.time_ns())))
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(directory,channel='chromium',headless=True,
                    args=[f'--disable-extensions-except={ROOT/"extension"}',f'--load-extension={ROOT/"extension"}'],viewport={'width':1500,'height':1100})
                worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                page=context.pages[0];page.goto(args.url or f'http://127.0.0.1:{fixtures.server_port}/{args.fixture}',wait_until='domcontentloaded')
                page.wait_for_timeout(1000)
                if args.url and 'mathpapa.com/practice' in args.url:
                    # Set up a public exercise by following an actual visible link.
                    links=page.get_by_role('link',name='Addition',exact=True)
                    if links.count():links.first.click();page.wait_for_timeout(1000)
                    starts=page.get_by_role('button',name='Start',exact=True)
                    if starts.count():starts.first.click()
                tab_id=worker.evaluate('(url)=>chrome.tabs.query({}).then(ts=>ts.find(t=>t.url===url).id)',page.url)
                await_config={'backend':f'http://127.0.0.1:{port}','model':os.environ.get('OPENROUTER_MODEL',''),'advance':False,'auto_submit':not bool(args.url),'badges':True,
                    'note':('Complete every part of this one practice question, then use Submit Assignment when every part is verified. Do not start another question.' if not args.url else 'Answer this one practice question, use Check if available, then stop. Do not start another question.')}
                worker.evaluate('(s)=>chrome.storage.local.set(s)',await_config)
                extension_id=worker.url.split('/')[2]
                panel=context.new_page();panel.goto(f'chrome-extension://{extension_id}/sidepanel.html')
                page.bring_to_front()
                panel.evaluate('(tabId)=>chrome.runtime.sendMessage({type:"start",tabId})',tab_id)
                deadline=time.time()+args.timeout;seen=0
                while time.time()<deadline:
                    status=worker.evaluate('({...__assignmentHarness.state})')
                    for row in status.get('log',[])[seen:]:
                        if row['kind'] in ('act','warn','error','stop','progress'):print(row['kind']+': '+row['message']+(' '+row.get('detail','')),flush=True)
                    seen=len(status.get('log',[]))
                    if not status.get('running'):break
                    page.wait_for_timeout(1000)
                if status.get('running'):
                    panel.evaluate('chrome.runtime.sendMessage({type:"stop"})');page.wait_for_timeout(1000)
                    status=worker.evaluate('({...__assignmentHarness.state})')
                status['page_text']=page.locator('body').inner_text()[:10000]
                status['parts']=worker.evaluate('__assignmentHarness.coverage.ledger()')
                page.screenshot(path=str(out/(name+'.png')),full_page=True)
                (out/(name+'.json')).write_text(json.dumps(status,indent=2),encoding='utf-8')
                print(json.dumps({'steps':status['steps'],'cost':status['cost'],'parts':status['parts'],'page':status['page_text'][:1800]}),flush=True)
                context.close()
    finally:
        server.should_exit=True;thread.join(timeout=5);fixtures.shutdown();fixtures.server_close()

if __name__=='__main__':main()
