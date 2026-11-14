"""Resolve public instrument keys for watchlist news (no holdings/positions)."""
from __future__ import annotations

from dataclasses import dataclass

from ..brokers.upstox_instruments import find_by_label, load_master, research_labels
from ..brokers.upstox_transport import HttpTransport
from ..research.watchlist_board import WatchlistRefreshBundle


@dataclass(frozen=True)
class WatchlistKeyRow:
    label: str
    instrument_key: str
    trading_symbol: str
    display_name: str


def resolve_watchlist_instrument_keys(
    transport: HttpTransport,
    *,
    bundle: WatchlistRefreshBundle | None = None,
) -> tuple[list[WatchlistKeyRow], str]:
    if bundle is not None:
        rows: list[WatchlistKeyRow] = []
        for o in bundle.observations:
            if o.instrument_key:
                rows.append(
                    WatchlistKeyRow(
                        label=o.research_label,
                        instrument_key=o.instrument_key,
                        trading_symbol=o.trading_symbol,
                        display_name=o.display_name or o.trading_symbol,
                    )
                )
        if rows:
            return rows, ""
    master = load_master(transport)
    rows = []
    for label in research_labels():
        matches, hint = find_by_label(master.records, label)
        if len(matches) == 1:
            m = matches[0]
            rows.append(WatchlistKeyRow(label, m.instrument_key, m.trading_symbol, m.display_label))
    if not rows:
        return [], "Could not resolve watchlist keys from public master — refresh Watchlist Research first."
    return rows, ""
