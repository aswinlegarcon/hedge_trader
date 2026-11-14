"""NSE instrument master resolution (official Upstox JSON asset)."""
from __future__ import annotations

import gzip
import io
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..config import PROVISIONAL_WATCHLIST
from .upstox_transport import ASSETS_HOST, HttpTransport

NSE_JSON_URL = f"https://{ASSETS_HOST}/market-quote/instruments/exchange/NSE.json.gz"
MASTER_TTL_SEC = 86_400

# Research labels → preferred trading_symbol (exact match); user resolves ambiguity in UI.
SYMBOL_HINTS: dict[str, str] = {
    "ICICI Bank": "ICICIBANK",
    "Gold BeES": "GOLDBEES",
    "Bharti Airtel": "BHARTIARTL",
    "L&T": "LT",
}


@dataclass(frozen=True)
class ResolvedInstrument:
    instrument_key: str
    trading_symbol: str
    name: str
    segment: str
    instrument_type: str

    @property
    def display_label(self) -> str:
        return f"{self.trading_symbol} · {self.name} ({self.segment})"


@dataclass
class InstrumentMasterCache:
    records: list[dict[str, Any]]
    loaded_at: datetime


_master: InstrumentMasterCache | None = None


def _parse_master_bytes(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except OSError:
        text = raw.decode("utf-8")
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "data" in data:
        inner = data["data"]
        if isinstance(inner, list):
            return inner
    raise ValueError("Unexpected instrument master shape")


def load_master(transport: HttpTransport, *, force: bool = False) -> InstrumentMasterCache:
    global _master
    now = datetime.now(timezone.utc)
    if not force and _master is not None and (now - _master.loaded_at).total_seconds() < MASTER_TTL_SEC:
        return _master
    status, body, _ = transport.get(NSE_JSON_URL, headers={"Accept": "application/json"}, allow_redirects=False)
    if status != 200:
        raise ValueError(f"Instrument master HTTP {status}")
    records = _parse_master_bytes(body)
    _master = InstrumentMasterCache(records=records, loaded_at=now)
    return _master


def _eq_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in records:
        seg = str(row.get("segment", "") or row.get("exchange", ""))
        exch = str(row.get("exchange", ""))
        if exch == "NSE" and seg in ("NSE_EQ", "NSE_INDEX", "NSE"):
            inst_type = str(row.get("instrument_type", "") or "")
            if inst_type in ("EQ", "ETF", "INDEX") or seg == "NSE_EQ":
                out.append(row)
    return out


def find_by_trading_symbol(records: list[dict[str, Any]], symbol: str) -> list[ResolvedInstrument]:
    sym = symbol.strip().upper()
    matches = []
    for row in _eq_candidates(records):
        ts = str(row.get("trading_symbol", "")).upper()
        if ts == sym:
            matches.append(_row_to_resolved(row))
    return matches


def find_by_label(records: list[dict[str, Any]], label: str) -> tuple[list[ResolvedInstrument], str]:
    hint = SYMBOL_HINTS.get(label, "")
    if hint:
        exact = find_by_trading_symbol(records, hint)
        if len(exact) == 1:
            return exact, ""
        if len(exact) > 1:
            return exact, "Multiple exact symbol matches — choose one."
    # Name contains (strict) for disambiguation only
    label_l = label.lower()
    name_hits = []
    for row in _eq_candidates(records):
        name = str(row.get("name", "")).lower()
        if label_l in name or name in label_l:
            name_hits.append(_row_to_resolved(row))
    if len(name_hits) == 1:
        return name_hits, ""
    if len(name_hits) > 1:
        return name_hits, f"Ambiguous name match for '{label}' — choose the exact security."
    return [], f"No NSE equity/ETF match for '{label}'."


def _row_to_resolved(row: dict[str, Any]) -> ResolvedInstrument:
    key = str(row.get("instrument_key", ""))
    if not key:
        key = f"NSE_EQ|{row.get('isin', row.get('trading_symbol', ''))}"
    return ResolvedInstrument(
        instrument_key=key,
        trading_symbol=str(row.get("trading_symbol", "")),
        name=str(row.get("name", "")),
        segment=str(row.get("segment", "NSE_EQ")),
        instrument_type=str(row.get("instrument_type", "")),
    )


def encode_instrument_key(instrument_key: str) -> str:
    return quote(instrument_key, safe="")


def research_labels() -> tuple[str, ...]:
    return PROVISIONAL_WATCHLIST
