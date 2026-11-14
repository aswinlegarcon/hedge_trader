"""Pre-registered run artifacts written before simulation."""
from __future__ import annotations

import json
from pathlib import Path

from nifty_lab.research.full_daily_history.io_utils import atomic_write_json


def write_preregistered_artifacts(run_dir: Path, registration: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "registration.json", registration)
