"""Spec 09 — bounded ICICIBANK historical data audit."""
from __future__ import annotations

import gzip
import json
import socket
from datetime import date
from pathlib import Path

import pytest

from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_transport import API_HOST, ASSETS_HOST
from nifty_lab.research.historical_audit.types import WindowStatus
from nifty_lab.config import FAKE_SECRET_SENTINEL, PROJECT_ROOT
from nifty_lab.research.historical_audit.budget import AuditBudgetExceeded, AuditRequestBudget
from nifty_lab.research.historical_audit.client import fetch_historical_candles_raw
from nifty_lab.research.historical_audit.manifest import write_manifest
from nifty_lab.research.historical_audit.quality import accepted_to_frame, audit_raw_candles, canonical_data_hash
from nifty_lab.research.historical_audit.runner import run_historical_data_audit
from nifty_lab.research.historical_audit.types import (
    AuditRunResult,
    OverallStatus,
    RequestBudgetSnapshot,
    WindowAuditResult,
    WindowStatus,
)


class MockTransport:
    def __init__(self, routes: dict[str, tuple[int, bytes, dict]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        auth = (headers or {}).get("Authorization", "")
        if FAKE_SECRET_SENTINEL in auth:
            pytest.fail("sentinel leaked into Authorization header")
        for prefix, response in self.routes.items():
            if prefix in url:
                return response
        return 404, b"{}", {}


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def _master_records():
    return [
        {
            "exchange": "NSE",
            "segment": "NSE_EQ",
            "trading_symbol": "ICICIBANK",
            "instrument_key": "NSE_EQ|INE090A01021",
            "name": "ICICI BANK",
            "instrument_type": "EQ",
        }
    ]


def _candles(rows: list) -> bytes:
    return json.dumps({"status": "success", "data": {"candles": rows}}).encode()


def test_raw_audit_flags_broken_and_out_of_range():
    raw = [
        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0],
        ["2021-01-05T00:00:00+05:30", 100, 99, 101, 100.0, 500, 0],  # bad OHLC
        ["2020-12-31T00:00:00+05:30", 100, 101, 99, 100.0, 100, 0],  # out of range
        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0],  # dup identical
    ]
    stats, accepted = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert stats.same_date_conflicts == 1
    assert stats.invalid_ohlc >= 1
    assert stats.out_of_range == 1
    assert len(accepted) == 1


def test_canonical_hash_stable_for_same_data():
    raw = [
        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0],
        ["2021-01-05T00:00:00+05:30", 101, 102, 100, 101.0, 900, 0],
    ]
    _, accepted = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    df = accepted_to_frame(accepted)
    h1 = canonical_data_hash(df)
    h2 = canonical_data_hash(df.sort_index(ascending=False))
    assert h1 == h2


def test_budget_guard_no_extra_historical():
    budget = AuditRequestBudget()
    for i in range(3):
        budget.consume_historical(label=str(i))
    with pytest.raises(AuditBudgetExceeded):
        budget.consume_historical(label="fourth")


def test_mocked_three_window_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "audit-test-token-value")
    master_gz = gzip.compress(json.dumps(_master_records()).encode())
    cache_path = tmp_path / "master.json.gz"
    cache_path.write_bytes(master_gz)

    class WindowedTransport:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
            self.calls.append(url)
            if FAKE_SECRET_SENTINEL in (headers or {}).get("Authorization", ""):
                pytest.fail("sentinel leaked")
            if "2021-01-31/2021-01-01" in url:
                body = _candles([["2021-01-04T00:00:00+05:30", 900, 910, 890, 905, 1_000_000, 0]])
            elif "2023-01-31/2023-01-01" in url:
                body = _candles([["2023-01-05T00:00:00+05:30", 910, 915, 905, 912, 900_000, 0]])
            elif "2025-12-31/2025-12-01" in url:
                body = _candles([["2025-12-05T00:00:00+05:30", 1200, 1210, 1195, 1205, 800_000, 0]])
            else:
                return 404, b"{}", {}
            return 200, body, {}

    transport = WindowedTransport()
    out = tmp_path / "runs"
    result = run_historical_data_audit(
        transport,
        output_root=out,
        master_cache_path=cache_path,
        live_fetch=True,
    )
    assert result.budget.historical_attempted <= 3
    assert result.budget.master_attempted == 0
    assert Path(result.manifest_path).is_file()
    assert FAKE_SECRET_SENTINEL not in Path(result.manifest_path).read_text()
    assert result.trading_symbol == "ICICIBANK"


def test_auth_blocked_sanitized(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "audit-test-token-value")
    master_gz = gzip.compress(json.dumps(_master_records()).encode())
    cache_path = tmp_path / "master.json.gz"
    cache_path.write_bytes(master_gz)
    transport = MockTransport({f"https://{API_HOST}": (401, b'{"status":"error"}', {})})
    result = run_historical_data_audit(
        transport,
        output_root=tmp_path / "runs",
        master_cache_path=cache_path,
        live_fetch=True,
    )
    assert result.overall_status in (OverallStatus.BLOCKED, OverallStatus.LIMITED)
    assert result.budget.historical_attempted == 1
    assert len(result.windows) == 3
    assert FAKE_SECRET_SENTINEL not in Path(result.report_path).read_text()


def test_no_token_live_unverified(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    master_gz = gzip.compress(json.dumps(_master_records()).encode())
    cache_path = tmp_path / "master.json.gz"
    cache_path.write_bytes(master_gz)
    transport = MockTransport({})
    result = run_historical_data_audit(
        transport,
        output_root=tmp_path / "runs",
        master_cache_path=cache_path,
        live_fetch=False,
    )
    assert result.overall_status == OverallStatus.LIVE_CHECK_UNVERIFIED
    assert result.budget.historical_attempted == 0


def test_intraday_same_date_limited_not_feasible():
    raw = [
        ["2021-01-04T09:15:00+05:30", 100, 101, 99, 100.5, 1000, 0],
        ["2021-01-04T09:20:00+05:30", 100, 101, 99, 100.0, 900, 0],
    ]
    stats, accepted = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert stats.intraday_timestamp_rejected == 2
    assert len(accepted) == 0
    from nifty_lab.research.historical_audit.runner import _classify_window

    assert _classify_window(stats, 0, None) == WindowStatus.LIMITED


def test_daily_midnight_descending_input_order_feasible():
    raw = [
        ["2021-01-05T00:00:00+05:30", 101, 102, 100, 101.0, 900, 0],
        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0],
    ]
    stats, accepted = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert stats.input_order == "descending"
    assert len(accepted) == 2
    from nifty_lab.research.historical_audit.runner import _classify_window

    assert _classify_window(stats, 2, None) == WindowStatus.FEASIBLE_SAMPLE


def test_nat_timestamp_rejected():
    raw = [["not-a-date", 100, 101, 99, 100.0, 100, 0]]
    stats, accepted = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert stats.bad_timestamp == 1
    assert accepted == []


def test_weekday_gaps_recorded_without_verification():
    raw = [["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.0, 1000, 0]]
    stats, _ = audit_raw_candles(raw, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert stats.candidate_weekday_gap_count > 0
    assert any(f.code == "CANDIDATE_WEEKDAY_GAPS" for f in stats.findings)


def test_canonical_hash_changes_when_values_change():
    raw_a = [["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0]]
    raw_b = [["2021-01-04T00:00:00+05:30", 100, 101, 99, 101.0, 1000, 0]]
    _, acc_a = audit_raw_candles(raw_a, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    _, acc_b = audit_raw_candles(raw_b, window_from=date(2021, 1, 1), window_to=date(2021, 1, 31))
    assert canonical_data_hash(accepted_to_frame(acc_a)) != canonical_data_hash(accepted_to_frame(acc_b))


def test_raising_transport_auth_writes_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "audit-test-token-value")
    master_gz = gzip.compress(json.dumps(_master_records()).encode())
    cache_path = tmp_path / "master.json.gz"
    cache_path.write_bytes(master_gz)

    class RaisingTransport:
        def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
            if "historical-candle" in url:
                raise UpstoxAuthError("Authentication failed. Set a fresh token locally.")
            return 404, b"{}", {}

    result = run_historical_data_audit(
        RaisingTransport(),
        output_root=tmp_path / "runs",
        master_cache_path=cache_path,
        live_fetch=True,
    )
    assert Path(result.manifest_path).is_file()
    assert result.budget.historical_attempted == 1
    assert sum(1 for w in result.windows if w.status == WindowStatus.NOT_FETCHED) == 2
    assert "Authentication failed" not in Path(result.manifest_path).read_text()


def test_manifest_rejects_secret_sentinel():
    result = AuditRunResult(
        run_id="x",
        fetched_at_utc="t",
        overall_status=OverallStatus.LIVE_CHECK_UNVERIFIED,
        instrument_key="k",
        trading_symbol="ICICIBANK",
        windows=[],
        budget=RequestBudgetSnapshot(0, 3, 0, 1),
        output_dir="/tmp",
        manifest_path=str(PROJECT_ROOT / ".pytest_tmp" / "m.json"),
        report_path=str(PROJECT_ROOT / ".pytest_tmp" / "r.md"),
        limitations=[FAKE_SECRET_SENTINEL],
    )
    Path(result.manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        write_manifest(result)
