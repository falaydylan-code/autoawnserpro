"""Owner utility: get a private dashboard link using existing Railway sign-in."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import webbrowser
import httpx

BACKEND = 'https://positive-tranquility-production-9fdc.up.railway.app'
FRONTEND = 'https://frontend-topaz-iota-25.vercel.app'

def client():
    cli = shutil.which('railway.exe') or shutil.which('railway')
    if not cli:
        raise ValueError('Railway CLI was not found. Install it and run railway login first.')
    result = subprocess.run([cli, 'variable', 'list', '--project', '6195f77e-b5c7-4a03-b554-8b1e4e848474', '--environment', 'production', '--service', '50fe1453-47fb-46c0-b0bd-c007c5201f98', '--json'], capture_output=True, text=True,
        env=dict(os.environ, RAILWAY_CALLER='skill:use-railway@1.4.0', RAILWAY_AGENT_SESSION='assignment-lab-owner-access'))
    if result.returncode:
        raise ValueError('Railway account access failed. Run railway login and try again.')
    code = json.loads(result.stdout).get('INVITE_CODES', '').split(',')[0]
    if not code:
        raise ValueError('Backend access is not configured.')
    c = httpx.Client(base_url=BACKEND, timeout=45)
    response = c.post('/api/login', json={'code':code})
    if response.status_code != 200:
        c.close()
        raise ValueError('Backend access failed. Check Railway service health and retry.')
    token = response.json()['token']
    c.headers['Authorization'] = 'Bearer ' + token
    return c, FRONTEND + '/#access=' + token

def save_link(link):
    path = Path(__file__).resolve().parent / 'data' / 'hosted-access.html'
    path.parent.mkdir(exist_ok=True)
    path.write_text('<!doctype html><meta charset="utf-8"><title>Assignment Lab</title><style>body{font:20px system-ui;padding:60px;max-width:750px;margin:auto;background:#f3f5ef;color:#183a3b}a{display:inline-block;padding:18px;background:#225f4e;color:white;border-radius:8px}</style><h1>Your hosted app is ready.</h1><p>This private access link expires after eight hours or a backend restart. Run open-hosted.bat for a fresh link.</p><a href="'+link+'">Open Assignment Lab</a><p>Keep this owner link private. Separate tester access should be issued before sharing browser sessions.</p>', encoding='utf-8')
    return path

if __name__ == '__main__':
    try:
        c, link = client()
        save_link(link)
        c.close()
        webbrowser.open(link)
        print('Opened your private hosted dashboard. No provider keys or access tokens were printed.')
    except (ValueError, httpx.HTTPError, OSError):
        print('Could not open hosted access. Check Railway login and backend health, then try again.')
        raise SystemExit(1)
