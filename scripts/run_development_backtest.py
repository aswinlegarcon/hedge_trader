#!/usr/bin/env python3
"""Offline development or validation-2024 backtest (Spec 09). Sanitized stdout only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.research.development_backtest.runner import run_development_backtest
from nifty_lab.research.development_backtest.validation_runner import run_validation_2024_backtest


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec 09 offline backtest")
    parser.add_argument(
        "--split",
        choices=("development", "validation-2024"),
        default="development",
        help="development (2021-2023) or one bounded validation-2024 replay",
    )
    args = parser.parse_args()
    try:
        if args.split == "validation-2024":
            out = run_validation_2024_backtest()
        else:
            out = run_development_backtest()
    except FileExistsError:
        print("BLOCKED: run directory already exists.")
        return 3
    except Exception:
        print("BLOCKED: sanitized failure")
        return 1
    print(f"status={out['status']}")
    print(f"run_dir={out['run_dir']}")
    if out["status"] in ("BLOCKED", "ERROR"):
        print(f"error_class={out.get('error_class')}")
        return 2
    if "summary" in out:
        s = out["summary"]
        print(f"closed_trades={s.get('closed_trades')}")
        print(f"net_pnl_inr={s.get('net_pnl_inr')}")
    if args.split == "validation-2024" and "evaluation_config_hash" in out:
        print(f"evaluation_config_hash={out['evaluation_config_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
