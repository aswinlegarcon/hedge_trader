"""Spec 09 — offline development backtest (mechanics correction)."""
from __future__ import annotations

import json
import shutil
import socket
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.research.development_backtest.config import (
    EXPECTED_MERGED_HASH,
    INITIAL_CASH,
    REGISTERED_DATASET_ID,
    REGISTERED_DATASET_DIR,
    ORIGINAL_RULES_CONFIG_HASH,
    rules_config_hash,
)
from nifty_lab.research.development_backtest.engine import _max_shares, simulate_development
from nifty_lab.research.development_backtest.indicators import ema_series, rolling_median_excluding_current
from nifty_lab.research.development_backtest.metrics import _max_buy_hold_shares, buy_hold_baseline
from nifty_lab.research.development_backtest.money import adverse_buy_fill, modeled_fee
from nifty_lab.research.development_backtest.preflight import verify_registered_dataset
from nifty_lab.research.development_backtest.runner import run_development_backtest


IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def _frame(rows: list[tuple]) -> pd.DataFrame:
    out = []
    for r in rows:
        ts = pd.Timestamp(r[0], tz=IST)
        out.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    return df.sort_index()


def _rising_with_pullback_signal(n: int = 122) -> pd.DataFrame:
    """Trend up then bar n-2 is pullback signal, n-1 entry, n-1 may exit."""
    rows = []
    p = 100.0
    for i in range(n):
        day = (i % 27) + 1
        month = 1 + (i // 27)
        ts = f"2021-{month:02d}-{day:02d}"
        if i < n - 3:
            rows.append((ts, p, p + 1, p - 0.2, p + 0.3, 1500.0))
            p += 0.15
        elif i == n - 3:
            rows.append((ts, p, p + 1, p - 0.5, p + 0.2, 2500.0))
        elif i == n - 2:
            rows.append((ts, p + 0.1, p + 0.6, p - 0.1, p + 0.4, 2500.0))
        else:
            rows.append((ts, p, p + 0.5, p - 2.0, p - 1.0, 2000.0))
    return _frame(rows)


def test_max_shares_respects_20k_allocation_ceiling():
    fill = Decimal("100.00")
    stop = Decimal("99.50")
    q = _max_shares(Decimal("30000"), fill, stop)
    cost = Decimal(q) * fill + modeled_fee(Decimal(q) * fill)
    assert cost <= Decimal("20000")
    assert q <= 199


def test_raw_open_below_stop_skips_entry():
    assert adverse_buy_fill(Decimal("99.95")) > Decimal("100")
    rows = []
    p = 100.0
    day = 4
    month = 1
    for i in range(101):
        rows.append((f"2021-{month:02d}-{day:02d}", p, p + 1, p, p + 0.2, 2000))
        day += 1
        if day > 28:
            day = 1
            month += 1
        p += 0.05
    rows.append((f"2021-{month:02d}-{day:02d}", 105, 106, 104.5, 105.5, 3000))
    day += 1
    rows.append((f"2021-{month:02d}-{day:02d}", 99.95, 100.5, 99.5, 100, 2500))
    sim = simulate_development(_frame(rows))
    assert sim.opportunity_count >= 1
    assert sim.admission_skips >= 1
    assert len(sim.trades) == 0


def test_buy_hold_baseline_non_negative_cash():
    rows = []
    for i in range(120):
        rows.append((f"2021-01-{min(4+i,28):02d}", 99.9, 100, 99.5, 99.95, 1000))
    df = _frame(rows)
    bh = buy_hold_baseline(df)
    assert bh["status"] == "OK"
    assert Decimal(bh["remaining_cash_after_buy"]) >= 0
    assert _max_buy_hold_shares(adverse_buy_fill(Decimal("99.9"))) == bh["shares"]
    assert bh["shares"] == 199


def test_median_excludes_current_bar():
    assert rolling_median_excluding_current([1, 3, 5, 7]) == 4.0


def test_ema_seed_first_close():
    assert ema_series([10.0, 20.0], 20)[0] == 10.0


def test_malformed_merged_meta_writes_blocked_manifest(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    d = tmp_path / REGISTERED_DATASET_ID
    shutil.copytree(REGISTERED_DATASET_DIR, d)
    (d / "merged_meta.json").write_text("{not json", encoding="utf-8")
    pf = verify_registered_dataset(d)
    assert not pf.ok
    assert pf.error_class == "MERGED_META_PARSE"
    out = tmp_path / "runs"
    inv = tmp_path / "inv.jsonl"
    r = run_development_backtest(dataset_dir=d, output_root=out, trial_inventory_path=inv)
    assert r["status"] == "BLOCKED"
    assert (out / r["run_id"] / "manifest.json").is_file()


def test_checkpoint_config_tamper_blocks(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    d = tmp_path / REGISTERED_DATASET_ID
    shutil.copytree(REGISTERED_DATASET_DIR, d)
    cp = json.loads((d / "checkpoint.json").read_text())
    cp["config_hash"] = "0" * 64
    (d / "checkpoint.json").write_text(json.dumps(cp))
    pf = verify_registered_dataset(d)
    assert not pf.ok
    assert pf.error_class == "CONFIG_HASH_MISMATCH"


def test_rules_hash_changes_with_mechanics_correction():
    h = rules_config_hash()
    assert h != ORIGINAL_RULES_CONFIG_HASH


def test_cash_reconciles_with_trades_sum():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    from nifty_lab.research.development_backtest.preflight import development_frame_from_verified

    dev = development_frame_from_verified(REGISTERED_DATASET_DIR)
    sim = simulate_development(dev)
    from nifty_lab.research.development_backtest.metrics import summarize_trades

    s = summarize_trades(sim.trades, sim)
    assert Decimal(s["cash_reconcile_delta_inr"]) == Decimal("0.00")


def test_prefix_invariance_development_hash(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    from nifty_lab.research.development_backtest.preflight import development_frame_from_verified
    from nifty_lab.research.development_backtest.splits import SplitConfig, simulate_split

    dev = development_frame_from_verified(REGISTERED_DATASET_DIR)
    sim_a = simulate_development(dev)
    merged = json.loads((REGISTERED_DATASET_DIR / "merged_daily.json").read_text())
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    future_rows = []
    for row in merged:
        if pd.Timestamp(row["ts"]).year in (2024, 2025):
            for k in ("open", "high", "low", "close"):
                row = dict(row)
                row[k] = float(row[k]) * 4.2
            ts = pd.Timestamp(row["ts"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(IST)
            future_rows.append(
                (ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"]))
            )
    future = pd.DataFrame(future_rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    extended = pd.concat([dev, future]).sort_index()
    sim_b = simulate_split(extended, SplitConfig.development())
    assert len(sim_a.trades) == len(sim_b.trades)
    for ta, tb in zip(sim_a.trades, sim_b.trades):
        assert ta.net_pnl_inr == tb.net_pnl_inr


def test_preregistered_and_lineage(tmp_path: Path):
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    out = tmp_path / "runs"
    inv = tmp_path / "inv.jsonl"
    r = run_development_backtest(
        dataset_dir=REGISTERED_DATASET_DIR,
        output_root=out,
        trial_inventory_path=inv,
    )
    assert r["status"] == "EXPLORATORY_COMPLETE"
    reg = json.loads((out / r["run_id"] / "registration.json").read_text())
    assert reg["parent_run_id"] == "cffbcdd3-e725-4ca6-bd01-97d424dbc6a2"
    assert reg["correction_reason"] == "MECHANICS_CORRECTION"


def test_registered_preflight_readonly():
    if not REGISTERED_DATASET_DIR.is_dir():
        pytest.skip("dataset missing")
    pf = verify_registered_dataset(REGISTERED_DATASET_DIR)
    assert pf.ok
    assert pf.merged_hash == EXPECTED_MERGED_HASH
