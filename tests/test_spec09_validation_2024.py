"""Spec 09 — validation-2024 prerequisites and fixtures."""
from __future__ import annotations

import json
import shutil
import socket
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.research.development_backtest.config import (
    EXPECTED_VALIDATION_2024_ROWS,
    FROZEN_CORRECTED_RULES_HASH,
    REGISTERED_DATASET_ID,
    REGISTERED_DATASET_DIR,
    rules_config_hash,
)
from nifty_lab.research.development_backtest.engine import _max_shares, simulate_development
from nifty_lab.research.development_backtest.metrics import summarize_trades
from nifty_lab.research.development_backtest.money import adverse_buy_fill, adverse_sell_fill, modeled_fee
from nifty_lab.research.development_backtest.evaluation_config import evaluation_config_hash
from nifty_lab.research.development_backtest.preflight import (
    development_frame_from_verified,
    validation_frame_from_verified,
    verify_registered_dataset,
)
from nifty_lab.research.development_backtest.splits import SplitConfig, simulate_split


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def _frame(rows: list[tuple]) -> pd.DataFrame:
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    out = []
    for r in rows:
        ts = r[0] if isinstance(r[0], pd.Timestamp) else pd.Timestamp(r[0], tz=IST)
        out.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    return df.sort_index()


def test_frozen_rules_hash_stable():
    assert rules_config_hash() == FROZEN_CORRECTED_RULES_HASH


def test_evaluation_hash_separate_from_rules():
    assert evaluation_config_hash() != rules_config_hash()


def test_development_parity_saved_corrected_run():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    ref_dir = PROJECT_ROOT / "research" / "backtest_runs" / "22f4e81b-e66a-4ea1-b77d-325323f61db7"
    if not ref_dir.is_dir():
        pytest.skip("reference run missing")
    dev = development_frame_from_verified(REGISTERED_DATASET_DIR)
    sim = simulate_development(dev)
    ref_trades = json.loads((ref_dir / "trades.json").read_text())
    ref_eq = json.loads((ref_dir / "equity_daily.json").read_text())
    assert len(sim.trades) == len(ref_trades) == 16
    for t, r in zip(sim.trades, ref_trades):
        assert asdict(t) == r
    for e, r in zip(sim.equity_curve, ref_eq):
        assert asdict(e) == r


def test_prefix_invariance_uses_tampered_future_tail():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    dev = development_frame_from_verified(REGISTERED_DATASET_DIR)
    sim_a = simulate_development(dev)
    merged = json.loads((REGISTERED_DATASET_DIR / "merged_daily.json").read_text())
    tampered = []
    for row in merged:
        yr = pd.Timestamp(row["ts"]).year
        if yr in (2024, 2025):
            row = dict(row)
            row["close"] = float(row["close"]) * 3.7
            row["high"] = float(row["high"]) * 3.7
        tampered.append(row)
    tail = []
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    for rec in tampered:
        if pd.Timestamp(rec["ts"]).year in (2024, 2025):
            ts = pd.Timestamp(rec["ts"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(IST)
            tail.append(
                (
                    ts,
                    float(rec["open"]),
                    float(rec["high"]),
                    float(rec["low"]),
                    float(rec["close"]),
                    float(rec["volume"]),
                )
            )
    future = pd.DataFrame(tail, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    extended = pd.concat([dev, future]).sort_index()
    sim_b = simulate_split(extended, SplitConfig.development())
    assert len(sim_b.trades) == len(sim_a.trades)
    for ta, tb in zip(sim_a.trades, sim_b.trades):
        assert ta.net_pnl_inr == tb.net_pnl_inr
        assert ta.qty == tb.qty


def test_manifest_missing_blocked(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    d = tmp_path / REGISTERED_DATASET_DIR.name
    shutil.copytree(REGISTERED_DATASET_DIR, d)
    (d / "manifest.json").unlink()
    pf = verify_registered_dataset(d)
    assert not pf.ok
    assert pf.error_class == "MANIFEST_MISSING"


def test_merged_meta_nonint_row_count_blocked(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    d = tmp_path / REGISTERED_DATASET_DIR.name
    shutil.copytree(REGISTERED_DATASET_DIR, d)
    meta = json.loads((d / "merged_meta.json").read_text())
    meta["row_count"] = "1240"
    (d / "merged_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    pf = verify_registered_dataset(d)
    assert not pf.ok
    assert pf.error_class == "MERGED_META_ROW_COUNT_TYPE"


def _reviewer_rising_core():
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    rows = []
    base = pd.Timestamp("2021-01-04", tz=IST)
    for i in range(100):
        c = 100.0 + 0.2 * i
        ts = base + pd.Timedelta(days=i)
        low = 117.0 if i == 99 else c - 0.3
        rows.append((ts, c, c + 0.5, low, c + 0.1, 5000.0))
    return rows, base


def test_reviewer_115_share_stop_pnl():
    rows, base = _reviewer_rising_core()
    rows.append((base + pd.Timedelta(days=100), 120.0, 120.5, 119.5, 119.8, 7000.0))
    rows.append((base + pd.Timedelta(days=101), 119.0, 119.5, 116.0, 116.5, 6000.0))
    sim = simulate_development(_frame(rows))
    assert len(sim.trades) == 1
    t = sim.trades[0]
    assert t.qty == 115
    assert Decimal(t.net_pnl_inr) == Decimal("-399.85")


def test_reviewer_gap_stop_latch():
    rows, base = _reviewer_rising_core()
    rows.append((base + pd.Timedelta(days=100), 120.0, 120.5, 119.5, 119.8, 7000.0))
    rows.append((base + pd.Timedelta(days=101), 100.0, 101.0, 99.5, 100.2, 7000.0))
    sim = simulate_development(_frame(rows))
    assert len(sim.trades) == 1
    assert Decimal(sim.trades[0].net_pnl_inr) == Decimal("-2350.60")
    assert sim.halted_new_entries is True


def test_validation_frame_row_counts():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    vf = validation_frame_from_verified(REGISTERED_DATASET_DIR)
    n2024 = sum(1 for t in vf.index if pd.Timestamp(t).year == 2024)
    assert n2024 == EXPECTED_VALIDATION_2024_ROWS


def test_validation_2025_tamper_invariant():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    vf = validation_frame_from_verified(REGISTERED_DATASET_DIR)
    a = simulate_split(vf, SplitConfig.validation_2024())
    merged = json.loads((REGISTERED_DATASET_DIR / "merged_daily.json").read_text())
    hold = []
    for row in merged:
        if pd.Timestamp(row["ts"]).year == 2025:
            row = dict(row)
            for k in ("open", "high", "low", "close"):
                row[k] = float(row[k]) * 2.0
            hold.append(row)
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    extra = []
    for rec in hold:
        ts = pd.Timestamp(rec["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        extra.append((ts, float(rec["open"]), float(rec["high"]), float(rec["low"]), float(rec["close"]), float(rec["volume"])))
    fut = pd.DataFrame(extra, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    extended = pd.concat([vf, fut]).sort_index()
    b = simulate_split(extended, SplitConfig.validation_2024())
    assert len(a.trades) == len(b.trades)
    for ta, tb in zip(a.trades, b.trades):
        assert ta.net_pnl_inr == tb.net_pnl_inr
