import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


load_env()


def setting(name, default=''):
    return os.environ.get(name, default)


def missing():
    names = ['OPENROUTER_API_KEY', 'OPENROUTER_MODEL']
    if setting('BROWSER_MODE', 'local') == 'cloud':
        names += ['BROWSERBASE_API_KEY', 'BROWSERBASE_PROJECT_ID']
    return [name for name in names if not setting(name)]
