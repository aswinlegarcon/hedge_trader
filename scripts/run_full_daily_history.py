#!/usr/bin/env python3
"""Bounded ICICIBANK 2021–2025 daily history acquisition (Spec 09). Sanitized stdout only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.brokers.upstox_market_data import _token_present
from nifty_lab.research.full_daily_history import run_full_daily_history
from nifty_lab.research.full_daily_history.config import default_dataset_id
from nifty_lab.research.full_daily_history.io_utils import DatasetLockError
from nifty_lab.research.full_daily_history.types import AcquisitionStatus


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec 09 full daily history (bounded)")
    parser.add_argument("--resume", action="store_true", help="Resume existing dataset (explicit only)")
    parser.add_argument("--dataset-id", default=None, help="Override dataset id (default: config-derived)")
    args = parser.parse_args()

    live = _token_present()
    if not live:
        print("LIVE_CHECK_UNVERIFIED: no UPSTOX_ACCESS_TOKEN — artifacts will omit live candles.")
    try:
        result = run_full_daily_history(
            live_fetch=live,
            resume=args.resume,
            dataset_id=args.dataset_id or default_dataset_id(),
        )
    except (FileExistsError, DatasetLockError):
        print("BLOCKED: dataset exists or lock held — use --resume or wait for other writer.")
        return 3
    except Exception as exc:
        print(f"BLOCKED: {type(exc).__name__}: sanitized failure.")
        return 1
    print(f"acquisition={result.acquisition.value}")
    print(f"quality={result.quality.value}")
    print(f"backtest_eligibility={result.backtest_eligibility.value}")
    print(
        f"historical_requests_invocation="
        f"{result.budget.invocation_historical_attempted}/{result.budget.invocation_historical_limit}"
    )
    print(
        f"historical_requests_dataset="
        f"{result.budget.dataset_historical_attempted}/{result.budget.dataset_historical_limit}"
    )
    print(f"artifact_dir={result.output_dir}")
    print(f"manifest={result.manifest_path}")
    if result.acquisition == AcquisitionStatus.BLOCKED:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
