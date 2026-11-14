"""Paper ledger path (same convention as Trade Ticket; no ExecutionLedger)."""
from __future__ import annotations

from pathlib import Path

from nifty_lab.config import PROJECT_ROOT

PAPER_DB_FILENAME = "paper_execution.db"


def paper_db_path() -> Path:
    return PROJECT_ROOT / "data" / PAPER_DB_FILENAME
