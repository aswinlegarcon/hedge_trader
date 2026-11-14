#!/usr/bin/env python3
"""Optional one-instrument watchlist observation smoke (Spec 05) — sanitized output."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.brokers.upstox_candles import INTERVAL_5M, INTERVAL_DAILY
from nifty_lab.brokers.upstox_instruments import find_by_trading_symbol, load_master
from nifty_lab.brokers.upstox_market_data import UpstoxAuthError, UpstoxMarketDataService, read_access_token
from nifty_lab.research import build_observation


def main() -> int:
    try:
        read_access_token()
    except UpstoxAuthError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    svc = UpstoxMarketDataService()
    master = load_master(svc.transport)
    matches = find_by_trading_symbol(master.records, "ICICIBANK")
    if not matches:
        print("BLOCKED: ICICIBANK not resolved")
        return 3
    inst = matches[0]
    try:
        ds_d = svc.load_dataset(inst, INTERVAL_DAILY)
        svc.reset_call_budget()
        ds_m = svc.load_dataset(inst, INTERVAL_5M)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1
    obs = build_observation(
        research_label="ICICI Bank",
        trading_symbol=inst.trading_symbol,
        instrument_key=inst.instrument_key,
        display_name=inst.display_label,
        daily=ds_d.df,
        m5=ds_m.df,
        retrieved_at=ds_m.provenance.retrieved_at,
    )
    print(
        f"OK symbol={obs.trading_symbol} state={obs.data_state} daily={obs.daily_trend} "
        f"5m_close={obs.m5_close} summary={obs.summary[:80]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
