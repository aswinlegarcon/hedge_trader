#!/usr/bin/env python3
"""Bounded read-only Upstox smoke — prints sanitized status only (Spec 04)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.brokers.upstox_candles import INTERVAL_DAILY
from nifty_lab.brokers.upstox_instruments import find_by_trading_symbol, load_master
from nifty_lab.brokers.upstox_market_data import UpstoxAuthError, UpstoxMarketDataService, read_access_token


def main() -> int:
    try:
        read_access_token()
    except UpstoxAuthError as exc:
        print(f"BLOCKED: {exc}")
        print("Setup: copy .env.example → .env, complete Upstox OAuth, set UPSTOX_ACCESS_TOKEN, restart.")
        return 2
    svc = UpstoxMarketDataService()
    try:
        master = load_master(svc.transport)
        matches = find_by_trading_symbol(master.records, "ICICIBANK")
        if not matches:
            print("BLOCKED: could not resolve ICICIBANK in instrument master.")
            return 3
        instrument = matches[0]
        ds = svc.load_dataset(instrument, INTERVAL_DAILY)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1
    last = ds.provenance.last_bar_time
    print(
        f"OK symbol={instrument.trading_symbol} interval=daily rows={len(ds.df)} "
        f"last_completed={last.isoformat() if last else 'n/a'} status=verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
