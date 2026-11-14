#!/usr/bin/env python3
"""One bounded ICICIBANK historical audit run (Spec 09). Sanitized stdout only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.brokers.upstox_market_data import _token_present
from nifty_lab.research.historical_audit import run_historical_data_audit
from nifty_lab.research.historical_audit.types import OverallStatus


def main() -> int:
    live = _token_present()
    if not live:
        print("LIVE_CHECK_UNVERIFIED: no UPSTOX_ACCESS_TOKEN — audit artifacts will omit live candles.")
    try:
        result = run_historical_data_audit(live_fetch=live)
    except FileExistsError:
        print("BLOCKED: audit run directory already exists (versioned run id collision — retry).")
        return 3
    except Exception as exc:
        print(f"BLOCKED: {type(exc).__name__}: sanitized failure (details in logs avoided).")
        return 1
    print(f"overall_status={result.overall_status.value}")
    print(f"historical_requests={result.budget.historical_attempted}/{result.budget.historical_limit}")
    print(f"master_requests={result.budget.master_attempted}/{result.budget.master_limit}")
    print(f"artifact_dir={result.output_dir}")
    print(f"manifest={result.manifest_path}")
    if result.overall_status == OverallStatus.BLOCKED:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
