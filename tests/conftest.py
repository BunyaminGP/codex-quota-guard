import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('CODEX_QUOTA_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-home'))


@pytest.fixture
def fake_cli():
    return [sys.executable, str(ROOT / 'tests' / 'fake_cli.py')]
