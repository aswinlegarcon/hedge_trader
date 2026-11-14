import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture(autouse=True)
def _isolated_upstox_token_store(monkeypatch, tmp_path):
    """Every test gets its own empty managed-token store; no test can read or write the real one (Spec 16)."""
    monkeypatch.setenv("NSL_TOKEN_STORE", str(tmp_path / "secrets" / "upstox_token.json"))
