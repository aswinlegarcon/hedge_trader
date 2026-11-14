#!/usr/bin/env python3
"""Bounded one-instrument Upstox news smoke (Spec 06) — sanitized output only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.brokers.upstox_market_data import UpstoxAuthError, read_access_token
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.news.upstox_news import UpstoxNewsClient, refresh_watchlist_news
from nifty_lab.news.watchlist_keys import resolve_watchlist_instrument_keys


def main() -> int:
    try:
        read_access_token()
    except UpstoxAuthError as exc:
        print(f"BLOCKED: auth ({type(exc).__name__})")
        return 2
    except Exception:
        print("BLOCKED: token unavailable")
        return 2

    transport = RequestsTransport()
    client = UpstoxNewsClient(transport)
    rows, hint = resolve_watchlist_instrument_keys(transport)
    if not rows:
        print(f"BLOCKED: {hint}")
        return 3
    key = rows[0].instrument_key
    symbol = rows[0].trading_symbol
    snap = refresh_watchlist_news(client, [key])
    if snap.refresh_failed:
        print(f"FAILED: symbol={symbol} message=sanitized-failure state=UNAVAILABLE")
        return 1
    newest = snap.articles[0].published_at if snap.articles else None
    state = snap.per_key_state.get(key, "COVERAGE UNKNOWN")
    if state == "NO RECENT ARTICLES":
        outcome = "VALID_EMPTY"
    elif snap.articles:
        outcome = "SUCCESS"
    elif state == "COVERAGE UNKNOWN":
        outcome = "COVERAGE_UNKNOWN"
    elif state == "OK" and not snap.articles:
        outcome = "VALID_EMPTY"
    else:
        outcome = state
    print(
        f"OK outcome={outcome} symbol={symbol} articles={len(snap.articles)} "
        f"newest_utc={newest.isoformat() if newest else 'none'} "
        f"retrieved_utc={snap.retrieved_at.isoformat()} per_key={state} "
        f"page={snap.page_number} has_more={snap.has_more_pages}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
