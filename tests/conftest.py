from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from health_agent.config import ROOT


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Path:
    test_root = Path(tempfile.mkdtemp(prefix="pytest-", dir=ROOT / "data/quarantine"))
    database = test_root / "health.sqlite3"
    monkeypatch.setenv("HEALTH_AGENT_DATABASE", str(database))
    try:
        yield database
    finally:
        shutil.rmtree(test_root)
