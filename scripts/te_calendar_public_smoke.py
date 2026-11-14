#!/usr/bin/env python3
"""One ordinary credential-free GET to Trading Economics calendar (Spec 07)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nifty_lab.calendar.public_refresh import try_public_calendar_refresh
from nifty_lab.calendar.te_transport import TEHttpTransport


def main() -> int:
    transport = TEHttpTransport()
    snap, msg = try_public_calendar_refresh(transport, prior=None)
    if snap is None:
        print(f"LIVE: {msg}")
        return 0 if "202" in msg else 1
    print(
        f"LIVE: {msg} events={snap.event_count} "
        f"note={snap.retrieval_note or snap.parser_diagnostics[:80]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
