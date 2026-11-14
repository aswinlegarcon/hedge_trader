"""Spec 09 — archived results loader integrity regressions."""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.research.results_review.config import (
    APPROVED_DEVELOPMENT_RUN_ID,
    APPROVED_VALIDATION_RUN_ID,
    BACKTEST_RUNS_ROOT,
    REVIEW_OUTPUT_ROOT,
)
from nifty_lab.research.results_review.loader import load_archived_book, load_approved_pair
from nifty_lab.research.results_review.trade_arithmetic import (
    recompute_trade_net,
    round_inr,
    validate_trade_record,
)
from nifty_lab.research.results_review.ui_data import build_results_review_view


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def _copy_validation(tmp_path: Path) -> Path:
    d = tmp_path / APPROVED_VALIDATION_RUN_ID
    shutil.copytree(BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID, d)
    return d


def test_reviewer_probe_exit_fill_tamper(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("validation run missing")
    d = _copy_validation(tmp_path)
    trades = json.loads((d / "trades.json").read_text())
    trades[0]["exit_fill"] = "9999.00"
    (d / "trades.json").write_text(json.dumps(trades), encoding="utf-8")
    book = load_archived_book(APPROVED_VALIDATION_RUN_ID, runs_root=tmp_path, book_id="validation", validation_split=True)
    assert book.load_status == "RESULT_INCONSISTENT"
    assert book.load_error in ("TRADE_EXIT_SLIP", "TRADE_NET_IDENTITY", "SUMMARY_TURNOVER")
    view = build_results_review_view(runs_root=tmp_path)
    assert view["validation"]["status"] == "RESULT_INCONSISTENT"
    assert view["cost_diagnostics"]["validation"] is None


def test_reviewer_probe_cash_delta_tamper(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("validation run missing")
    d = _copy_validation(tmp_path)
    summary = json.loads((d / "summary.json").read_text())
    equity = json.loads((d / "equity_daily.json").read_text())
    summary["cash_reconcile_delta_inr"] = "100.00"
    cash = Decimal(equity[-1]["cash_inr"]) + Decimal("100")
    equity[-1]["cash_inr"] = str(cash)
    summary["final_cash_inr"] = str(cash)
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (d / "equity_daily.json").write_text(json.dumps(equity), encoding="utf-8")
    manifest = json.loads((d / "manifest.json").read_text())
    manifest["summary"]["final_cash_inr"] = str(cash)
    manifest["summary"]["cash_reconcile_delta_inr"] = "100.00"
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    book = load_archived_book(APPROVED_VALIDATION_RUN_ID, runs_root=tmp_path, book_id="validation", validation_split=True)
    assert book.load_status == "RESULT_INCONSISTENT"
    assert book.load_error == "CASH_RECONCILE_NONZERO"


def test_hand_valid_trade_identity():
    t = {
        "qty": 10,
        "entry_raw_open": "100.00",
        "entry_fill": "100.10",
        "exit_raw_reference": "101.00",
        "exit_fill": "100.90",
        "entry_fee_inr": "1.00",
        "exit_fee_inr": "1.01",
        "entry_slippage_inr": "1.00",
        "exit_slippage_inr": "1.00",
        "net_pnl_inr": "6.99",
    }
    net = recompute_trade_net(10, Decimal("100.10"), Decimal("100.90"), Decimal("1.00"), Decimal("1.01"))
    t["net_pnl_inr"] = str(net)
    assert validate_trade_record(t, 0) is None


def test_fractional_qty_rejected():
    t = {
        "qty": 10.5,
        "entry_raw_open": "100",
        "entry_fill": "100.1",
        "exit_raw_reference": "101",
        "exit_fill": "100.9",
        "entry_fee_inr": "1",
        "exit_fee_inr": "1",
        "entry_slippage_inr": "1",
        "exit_slippage_inr": "1",
        "net_pnl_inr": "5",
    }
    assert validate_trade_record(t, 0) == "TRADE_QTY"


def test_approved_sources_and_inventory_unchanged_on_load(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("runs missing")

    def snap(root: Path) -> dict[str, str]:
        out = {}
        for run_id in (APPROVED_DEVELOPMENT_RUN_ID, APPROVED_VALIDATION_RUN_ID):
            for p in (root / "backtest_runs" / run_id).glob("*.json"):
                out[f"{run_id}/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()
        inv = root / "backtest_runs" / "trial_inventory.jsonl"
        if inv.is_file():
            out["trial_inventory.jsonl"] = hashlib.sha256(inv.read_bytes()).hexdigest()
        rev = REVIEW_OUTPUT_ROOT / "ee63ea6a-53e8-4b22-aa8a-edd5d4c68a76"
        if rev.is_dir():
            for p in rev.glob("*"):
                if p.is_file():
                    out[f"review/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    before = snap(PROJECT_ROOT)
    load_approved_pair()
    build_results_review_view()
    after = snap(PROJECT_ROOT)
    assert before == after


def test_streamlit_apptest_valid_page():
    pytest.importorskip("streamlit.testing.v1", exc_type=ImportError)
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PROJECT_ROOT / "pages" / "07_Backtesting_Lab.py"))
    at.run(timeout=60)
    assert not at.exception
    assert any("NOT EVALUATED" in (m.value or "") for m in at.warning)
    assert at.metric  # development + validation metrics present


def test_fail_closed_view_invalid_book_stress_hidden(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("validation run missing")
    shutil.copytree(BACKTEST_RUNS_ROOT / APPROVED_DEVELOPMENT_RUN_ID, tmp_path / APPROVED_DEVELOPMENT_RUN_ID)
    d = _copy_validation(tmp_path)
    trades = json.loads((d / "trades.json").read_text())
    trades[0]["exit_fill"] = "9999.00"
    (d / "trades.json").write_text(json.dumps(trades), encoding="utf-8")

    dev = load_archived_book(
        APPROVED_DEVELOPMENT_RUN_ID,
        runs_root=tmp_path,
        book_id="development_2021_2023",
        development_lineage=True,
    )
    val = load_archived_book(
        APPROVED_VALIDATION_RUN_ID,
        runs_root=tmp_path,
        book_id="validation_2024",
        validation_split=True,
    )
    assert dev.load_status == "OK"
    assert val.load_status == "RESULT_INCONSISTENT"
    view = build_results_review_view(runs_root=tmp_path)
    assert view["development"]["status"] == "OK"
    assert view["validation"]["status"] == "RESULT_INCONSISTENT"
    assert view["cost_diagnostics"]["validation"] is None
    assert view["cost_diagnostics"]["development"] is not None
