#!/usr/bin/env python3
"""Verify a local sanitized TE calendar JSON import (Spec 07) — no secrets."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nifty_lab.calendar import import_calendar_json


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if path is None or not path.is_file():
        print("Usage: macro_calendar_import_check.py <path-to-sanitized.json>")
        return 2
    raw = path.read_bytes()
    try:
        snap = import_calendar_json(raw)
    except ValueError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(
        f"OK events={snap.event_count} origin={snap.origin.value} "
        f"captured={snap.capture_started_at.isoformat()} "
        f"coverage={snap.coverage_date_min}..{snap.coverage_date_max} "
        f"timezone={snap.timezone_status[:40]} importance={snap.importance_status[:30]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
