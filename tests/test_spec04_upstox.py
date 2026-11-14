"""Spec 04 — mocked Upstox HTTP and candle normalization."""
from __future__ import annotations

import json
import socket
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from nifty_lab.brokers.upstox_candles import (
    INTERVAL_5M,
    INTERVAL_DAILY,
    candles_to_frame,
    drop_incomplete_bars,
    merge_hist_intraday,
    parse_candle_response,
)
from nifty_lab.brokers.upstox_instruments import encode_instrument_key, find_by_trading_symbol
from nifty_lab.brokers.upstox_market_data import UpstoxMarketDataService
from nifty_lab.brokers.upstox_transport import API_HOST, ASSETS_HOST
from nifty_lab.config import FAKE_SECRET_SENTINEL
from nifty_lab.data.base import DataKind
from nifty_lab.ui.common import supports_nifty_signal_voting
from nifty_lab.data.sample import generate_synthetic_nifty


class MockTransport:
    def __init__(self, routes: dict[str, tuple[int, bytes, dict]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        if FAKE_SECRET_SENTINEL in (headers or {}).get("Authorization", ""):
            pytest.fail("sentinel leaked into Authorization header")
        for prefix, response in self.routes.items():
            if prefix in url:
                return response
        return 404, b"{}", {}


def _candle_payload(rows: list) -> bytes:
    return json.dumps({"status": "success", "data": {"candles": rows}}).encode()


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def test_encode_instrument_key():
    key = "NSE_EQ|INE123"
    enc = encode_instrument_key(key)
    assert "|" not in enc.replace("%7C", "")


def test_normalize_and_drop_forming_5m():
    now = datetime(2024, 6, 3, 9, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    rows = _candle_payload(
        [
            ["2024-06-03T09:15:00+05:30", 100, 101, 99, 100.5, 1000, 0],
            ["2024-06-03T09:55:00+05:30", 101, 102, 100, 101.5, 900, 0],
        ]
    )
    df = candles_to_frame(parse_candle_response(rows), spec=INTERVAL_5M)
    completed, dropped = drop_incomplete_bars(df, INTERVAL_5M, now=now)
    assert dropped == 1
    assert len(completed) == 1


def test_reject_conflicting_duplicate():
    rows = _candle_payload(
        [
            ["2024-06-03T09:15:00+05:30", 100, 101, 99, 100.5, 1000, 0],
            ["2024-06-03T09:20:00+05:30", 100, 101, 99, 99.0, 500, 0],
            ["2024-06-03T09:15:00+05:30", 100, 101, 99, 99.0, 500, 0],
        ]
    )
    with pytest.raises(Exception):
        candles_to_frame(parse_candle_response(rows), spec=INTERVAL_5M)


def test_load_dataset_mocked(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "live-test-token-value-not-sentinel")
    inst = type("I", (), {"instrument_key": "NSE_EQ|TEST", "trading_symbol": "TEST", "name": "Test", "segment": "NSE_EQ", "instrument_type": "EQ"})()
    from nifty_lab.brokers import upstox_instruments as ui

    master = [{"exchange": "NSE", "segment": "NSE_EQ", "trading_symbol": "TEST", "instrument_key": "NSE_EQ|TEST", "name": "Test", "instrument_type": "EQ"}]
    day = _candle_payload([["2024-06-01T00:00:00+05:30", 10, 11, 9, 10.5, 100, 0]])
    routes = {
        f"https://{ASSETS_HOST}": (200, json.dumps(master).encode(), {}),
        f"https://{API_HOST}/v3/historical-candle": (200, day, {}),
    }
    transport = MockTransport(routes)
    svc = UpstoxMarketDataService(transport=transport)
    ds = svc.load_dataset(inst, INTERVAL_DAILY)  # type: ignore[arg-type]
    assert ds.provenance.kind == DataKind.BROKER_LIVE
    assert ds.provenance.symbol == "TEST"
    assert "live-test-token" not in " ".join(transport.calls)


def test_auth_failure_clears_verified(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "tok")
    transport = MockTransport({f"https://{API_HOST}": (401, b'{"status":"error"}', {})})
    svc = UpstoxMarketDataService(transport=transport)
    inst = type("I", (), {"instrument_key": "NSE_EQ|X", "trading_symbol": "X", "name": "X", "segment": "NSE_EQ", "instrument_type": "EQ"})()
    with pytest.raises(Exception):
        svc.fetch_candles_historical(inst, INTERVAL_DAILY, pd.Timestamp("2024-01-01").date(), pd.Timestamp("2024-01-02").date())  # type: ignore[arg-type]
    assert svc.state.verified is False
    assert FAKE_SECRET_SENTINEL not in (svc.state.last_error or "")


def test_supports_nifty_signal_voting():
    syn = generate_synthetic_nifty()
    assert supports_nifty_signal_voting(syn)


def test_find_by_trading_symbol():
    recs = [
        {"exchange": "NSE", "segment": "NSE_EQ", "trading_symbol": "ICICIBANK", "instrument_key": "k1", "name": "ICICI", "instrument_type": "EQ"}
    ]
    hits = find_by_trading_symbol(recs, "ICICIBANK")
    assert len(hits) == 1


def test_merge_hist_intraday():
    idx = pd.date_range("2024-06-03 09:15", periods=2, freq="5min", tz="Asia/Kolkata")
    h = pd.DataFrame({"open": [1, 1], "high": [2, 2], "low": [0.5, 0.5], "close": [1.5, 1.5], "volume": [10, 10]}, index=idx)
    idx2 = pd.date_range("2024-06-03 09:25", periods=1, freq="5min", tz="Asia/Kolkata")
    i = pd.DataFrame({"open": [1.5], "high": [2], "low": [1], "close": [1.8], "volume": [5]}, index=idx2)
    m = merge_hist_intraday(h, i)
    assert len(m) == 3
