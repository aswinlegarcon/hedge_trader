"""Spec 09 — resumable ICICIBANK full daily history."""
from __future__ import annotations

import gzip
import json
import socket
from datetime import date
from pathlib import Path

import pytest

from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_transport import API_HOST
from nifty_lab.config import FAKE_SECRET_SENTINEL, PROJECT_ROOT
from nifty_lab.research.full_daily_history.config import config_hash, default_dataset_id
from nifty_lab.research.full_daily_history.io_utils import DatasetLockError, dataset_lock
from nifty_lab.research.full_daily_history.manifest import write_manifest
from nifty_lab.research.full_daily_history.overlap import compare_overlaps
from nifty_lab.research.full_daily_history.runner import run_full_daily_history
from nifty_lab.research.full_daily_history.types import (
    AcquisitionStatus,
    BacktestEligibility,
    BudgetSnapshot,
    ChunkStatus,
    FullHistoryResult,
    QualityStatus,
)


class MockTransport:
    def __init__(self, routes: dict[str, tuple[int, bytes, dict]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        if FAKE_SECRET_SENTINEL in (headers or {}).get("Authorization", ""):
            pytest.fail("sentinel leaked")
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


def _year_candle(year: int, month: int = 1, day: int = 4):
    return [f"{year}-{month:02d}-{day:02d}T00:00:00+05:30", 900, 910, 890, 905, 1_000_000, 0]


def _setup_master(tmp_path: Path) -> Path:
    cache_path = tmp_path / "master.json.gz"
    cache_path.write_bytes(gzip.compress(json.dumps(_master_records()).encode()))
    return cache_path


class YearlyTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
        self.calls.append(url)
        for year in ("2021", "2022", "2023", "2024", "2025"):
            if f"{year}-12-31/{year}-01-01" in url:
                return 200, _candles([_year_candle(int(year))]), {}
        return 404, b"{}", {}


def test_five_chunks_merge_and_budget(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    transport = YearlyTransport()
    out = tmp_path / "history"
    result = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
    )
    assert len(transport.calls) == 5
    assert result.budget.invocation_historical_attempted == 5
    assert result.budget.dataset_historical_attempted == 5
    assert result.acquisition == AcquisitionStatus.COMPLETE
    assert result.merged_hash is not None
    assert Path(result.manifest_path).is_file()
    assert (out / default_dataset_id() / "merged_daily.json").is_file()
    assert FAKE_SECRET_SENTINEL not in Path(result.manifest_path).read_text()


def test_resume_skips_completed_no_http(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    transport = YearlyTransport()
    out = tmp_path / "history"
    ds = default_dataset_id()
    first = run_full_daily_history(transport, output_root=out, master_cache_path=cache, live_fetch=True)
    assert first.acquisition == AcquisitionStatus.COMPLETE
    transport.calls.clear()
    second = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    assert transport.calls == []
    assert second.budget.invocation_historical_attempted == 0
    assert second.merged_hash == first.merged_hash
    assert second.acquisition == AcquisitionStatus.COMPLETE


def test_raising_auth_stops_with_checkpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)

    class AuthThenOk:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
            self.calls.append(url)
            if "2021-12-31/2021-01-01" in url:
                return 200, _candles([_year_candle(2021)]), {}
            if "historical-candle" in url:
                raise UpstoxAuthError("Authentication failed.")
            return 404, b"{}", {}

    result = run_full_daily_history(
        AuthThenOk(),
        output_root=tmp_path / "h",
        master_cache_path=cache,
        live_fetch=True,
    )
    assert Path(result.manifest_path).is_file()
    assert result.budget.invocation_historical_attempted == 2
    assert any(c.status == ChunkStatus.NOT_FETCHED for c in result.chunks)
    assert "Authentication failed" not in Path(result.manifest_path).read_text()


def test_config_hash_conflict_on_resume(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    out = tmp_path / "h"
    ds = default_dataset_id()
    run_full_daily_history(YearlyTransport(), output_root=out, master_cache_path=cache, live_fetch=True)
    cp_path = out / ds / "checkpoint.json"
    cp_before = cp_path.read_bytes()
    manifest_before = (out / ds / "manifest.json").read_bytes()
    transport = YearlyTransport()
    monkeypatch.setattr(
        "nifty_lab.research.full_daily_history.checkpoint.config_hash",
        lambda: "deadbeef" * 8,
    )
    conflict = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    assert any("Config hash mismatch" in x for x in conflict.limitations)
    assert conflict.acquisition == AcquisitionStatus.BLOCKED
    assert conflict.backtest_eligibility == BacktestEligibility.BLOCKED
    assert transport.calls == []
    assert cp_path.read_bytes() == cp_before
    assert (out / ds / "manifest.json").read_bytes() == manifest_before
    assert conflict.budget.dataset_historical_attempted == 5
    assert transport.calls == []
    again = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    assert again.budget.dataset_historical_attempted == 5
    assert transport.calls == []
    assert again.backtest_eligibility == BacktestEligibility.BLOCKED


def test_corrupt_completed_hash_marks_conflict(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    out = tmp_path / "h"
    ds = default_dataset_id()
    run_full_daily_history(YearlyTransport(), output_root=out, master_cache_path=cache, live_fetch=True)
    cp_path = out / ds / "checkpoint.json"
    cp = json.loads(cp_path.read_text())
    cp["chunks"]["2021"]["data_hash"] = "0" * 64
    cp_path.write_text(json.dumps(cp))
    transport = YearlyTransport()
    result = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    y2021 = next(c for c in result.chunks if c.chunk_year == "2021")
    assert y2021.status == ChunkStatus.CONFLICT
    assert len([u for u in transport.calls if "2021" in u]) == 0
    cp = json.loads(cp_path.read_text())
    assert cp["chunks"]["2021"]["status"] == "CONFLICT"
    second = run_full_daily_history(
        transport,
        output_root=out,
        master_cache_path=cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    assert not any("2021" in u for u in transport.calls)
    assert next(c for c in second.chunks if c.chunk_year == "2021").status == ChunkStatus.CONFLICT


def test_conflict_persists_through_master_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    out = tmp_path / "h"
    ds = default_dataset_id()
    run_full_daily_history(YearlyTransport(), output_root=out, master_cache_path=cache, live_fetch=True)
    cp_path = out / ds / "checkpoint.json"
    cp = json.loads(cp_path.read_text())
    cp["chunks"]["2021"]["status"] = "CONFLICT"
    cp["chunks"]["2021"]["error_class"] = "HASH_MISMATCH"
    cp_path.write_text(json.dumps(cp))
    raw_before = (out / ds / "raw_2021.json").read_bytes()
    missing_cache = tmp_path / "no_master.json.gz"
    transport = YearlyTransport()

    class FailMaster:
        def get(self, url, *, headers=None, allow_redirects=False):
            transport.calls.append(url)
            if "historical-candle" in url:
                return 200, _candles([_year_candle(2022)]), {}
            raise OSError("master blocked")

    run_full_daily_history(
        FailMaster(),
        output_root=out,
        master_cache_path=missing_cache,
        live_fetch=True,
        resume=True,
        dataset_id=ds,
    )
    cp_mid = json.loads(cp_path.read_text())
    assert cp_mid["chunks"]["2021"]["status"] == "CONFLICT"
    assert (out / ds / "raw_2021.json").read_bytes() == raw_before
    n_before = len(transport.calls)
    run_full_daily_history(transport, output_root=out, master_cache_path=cache, live_fetch=True, resume=True, dataset_id=ds)
    assert not any("2021" in u for u in transport.calls[n_before:])
    assert json.loads(cp_path.read_text())["chunks"]["2021"]["status"] == "CONFLICT"


def test_dataset_lock_blocks_concurrent_writer(tmp_path: Path):
    d = tmp_path / "ds"
    with dataset_lock(d):
        with pytest.raises(DatasetLockError):
            with dataset_lock(d):
                pass


def test_per_chunk_attempt_cap(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)

    class Fail2022:
        def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
            if "2022-12-31/2022-01-01" in url:
                return 401, b"{}", {}
            for year in ("2021", "2023", "2024", "2025"):
                if f"{year}-12-31/{year}-01-01" in url:
                    return 200, _candles([_year_candle(int(year))]), {}
            return 404, b"{}", {}

    out = tmp_path / "h"
    ds = default_dataset_id()
    run_full_daily_history(Fail2022(), output_root=out, master_cache_path=cache, live_fetch=True)
    run_full_daily_history(Fail2022(), output_root=out, master_cache_path=cache, live_fetch=True, resume=True, dataset_id=ds)
    cp = json.loads((out / ds / "checkpoint.json").read_text())
    assert cp["per_chunk_attempts"]["2022"] == 2


def test_overlap_offline_uses_audit_baseline(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    out = tmp_path / "h"
    run_full_daily_history(YearlyTransport(), output_root=out, master_cache_path=cache, live_fetch=True)
    audit_base = PROJECT_ROOT / "research" / "audit_runs" / "38e457b0-5004-4731-bb68-f79118621d2a"
    if not audit_base.is_dir():
        pytest.skip("original audit run not present in workspace")
    overlap = compare_overlaps(out / default_dataset_id(), audit_root=audit_base.parent)
    assert overlap
    assert all("status" in row for row in overlap)


def test_full_gap_dates_not_truncated_to_twelve(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    result = run_full_daily_history(
        YearlyTransport(),
        output_root=tmp_path / "h",
        master_cache_path=cache,
        live_fetch=True,
    )
    y2021 = next(c for c in result.chunks if c.chunk_year == "2021")
    assert len(y2021.candidate_weekday_gap_dates) > 12


def test_normalized_tamper_persists_conflict_no_refetch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)
    out = tmp_path / "h"
    ds = default_dataset_id()
    run_full_daily_history(YearlyTransport(), output_root=out, master_cache_path=cache, live_fetch=True)
    norm = out / ds / "normalized_2021.json"
    norm.write_text("[not-valid", encoding="utf-8")
    t = YearlyTransport()
    r1 = run_full_daily_history(t, output_root=out, master_cache_path=cache, live_fetch=True, resume=True, dataset_id=ds)
    assert next(c for c in r1.chunks if c.chunk_year == "2021").status == ChunkStatus.CONFLICT
    assert not any("2021" in u for u in t.calls)
    t.calls.clear()
    r2 = run_full_daily_history(t, output_root=out, master_cache_path=cache, live_fetch=True, resume=True, dataset_id=ds)
    assert t.calls == []
    assert next(c for c in r2.chunks if c.chunk_year == "2021").status == ChunkStatus.CONFLICT


def test_raw_conflicts_block_eligibility(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "history-test-token")
    cache = _setup_master(tmp_path)

    class Conflict2021:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, *, headers: dict[str, str] | None = None, allow_redirects: bool = False):
            self.calls.append(url)
            if "2021-12-31/2021-01-01" in url:
                body = _candles(
                    [
                        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 100.5, 1000, 0],
                        ["2021-01-04T00:00:00+05:30", 100, 101, 99, 101.0, 900, 0],
                    ]
                )
                return 200, body, {}
            for year in ("2022", "2023", "2024", "2025"):
                if f"{year}-12-31/{year}-01-01" in url:
                    return 200, _candles([_year_candle(int(year))]), {}
            return 404, b"{}", {}

    result = run_full_daily_history(
        Conflict2021(),
        output_root=tmp_path / "h",
        master_cache_path=cache,
        live_fetch=True,
    )
    y2021 = next(c for c in result.chunks if c.chunk_year == "2021")
    assert y2021.status == ChunkStatus.CONFLICT
    assert result.quality == QualityStatus.INVALID
    assert result.backtest_eligibility == BacktestEligibility.BLOCKED
    assert result.acquisition == AcquisitionStatus.PARTIAL
    assert result.merged_hash is None


def test_manifest_rejects_sentinel():
    result = FullHistoryResult(
        dataset_id="x",
        invocation_id="i",
        fetched_at_utc="t",
        acquisition=AcquisitionStatus.UNVERIFIED,
        quality=QualityStatus.LIMITED,
        calendar_coverage="UNVERIFIED",
        adjustment_status="UNKNOWN",
        backtest_eligibility=BacktestEligibility.BLOCKED,
        instrument_key="k",
        trading_symbol="ICICIBANK",
        config_hash=config_hash(),
        merged_hash=None,
        chunks=[],
        budget=BudgetSnapshot(0, 5, 0, 10, 0, 1, 0, {}),
        split_coverage={},
        overlap_comparisons=[],
        output_dir="/tmp",
        manifest_path=str(tmp_path if False else PROJECT_ROOT / ".pytest_tmp" / "hm.json"),
        report_path=str(PROJECT_ROOT / ".pytest_tmp" / "hr.md"),
        limitations=[FAKE_SECRET_SENTINEL],
        proposed_next_step="",
    )
    Path(result.manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        write_manifest(result)
