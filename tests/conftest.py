import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HEADLESS', 'true')
    monkeypatch.setenv('BROWSER_MODE', 'local')
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('INVITE_CODES', 'alice-secret,bob-secret')
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    monkeypatch.setenv('OPENROUTER_MODEL', '')
    monkeypatch.setenv('MAX_CALLS_PER_INVITE', '100')
    monkeypatch.setenv('MAX_COST_PER_INVITE', '2')
