"""Spec 09 — read-only results and fixed-fill cost diagnostics."""
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
)
from nifty_lab.research.results_review.diagnostics import (
    archived_net_pnl_inr,
    executed_turnover_inr,
    extra_cost_bps,
    fixed_fill_stress_table,
    round_inr,
)
from nifty_lab.research.results_review.loader import load_archived_book, load_approved_pair
from nifty_lab.research.results_review.runner import run_results_cost_review
from nifty_lab.research.results_review.ui_data import build_results_review_view


@pytest.fixture(autouse=True)
def block_socket(monkeypatch):
    class Guarded(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", Guarded)


def test_hand_fixture_turnover_and_1bp_stress():
    trades = [
        {"qty": 10, "entry_fill": "100.00", "exit_fill": "101.00", "net_pnl_inr": "5.00"},
        {"qty": 5, "entry_fill": "200.00", "exit_fill": "199.00", "net_pnl_inr": "-10.00"},
    ]
    turn = executed_turnover_inr(trades)
    assert turn == round_inr(Decimal("4005.00"))
    net = archived_net_pnl_inr(trades)
    assert net == Decimal("-5.00")
    extra = extra_cost_bps(turn, 1)
    assert extra == Decimal("0.40")
    table = fixed_fill_stress_table(trades, book_label="fixture")
    one_bp = next(s for s in table["scenarios"] if s["scenario_id"] == "EXTRA_1BP")
    assert one_bp["diagnostic_net_pnl_inr"] == "-5.40"


def test_validation_saved_expected_cost_diagnostics():
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("validation run missing")
    _, val = load_approved_pair()
    assert val.load_status == "OK"
    stress = fixed_fill_stress_table(val.trades, book_label="validation")
    assert stress["executed_turnover_inr"] == "430003.98"
    assert stress["archived_net_pnl_inr"] == "24.30"
    s1 = next(s for s in stress["scenarios"] if s["scenario_id"] == "EXTRA_1BP")
    assert s1["extra_cost_inr"] == "43.00"
    assert s1["diagnostic_net_pnl_inr"] == "-18.70"
    s5 = next(s for s in stress["scenarios"] if s["scenario_id"] == "EXTRA_5BP")
    assert s5["diagnostic_net_pnl_inr"] == "-190.70"
    s10 = next(s for s in stress["scenarios"] if s["scenario_id"] == "EXTRA_10BP")
    assert s10["diagnostic_net_pnl_inr"] == "-405.70"
    inr1 = next(s for s in stress["scenarios"] if s["scenario_id"] == "EXTRA_INR1_PER_EXECUTION")
    assert inr1["extra_cost_inr"] == "28.00"
    assert inr1["diagnostic_net_pnl_inr"] == "-3.70"
    assert abs(float(stress["break_even_extra_bps"]) - 0.565) < 0.01


def test_development_break_even_already_nonpositive():
    if not (BACKTEST_RUNS_ROOT / APPROVED_DEVELOPMENT_RUN_ID).is_dir():
        pytest.skip("development run missing")
    dev, _ = load_approved_pair()
    stress = fixed_fill_stress_table(dev.trades, book_label="development")
    assert stress["break_even_extra_bps"] == "ALREADY_NONPOSITIVE"


def test_malformed_trade_blocked(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("validation run missing")
    d = tmp_path / APPROVED_VALIDATION_RUN_ID
    shutil.copytree(BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID, d)
    trades = json.loads((d / "trades.json").read_text())
    trades[0]["qty"] = 0
    (d / "trades.json").write_text(json.dumps(trades), encoding="utf-8")
    book = load_archived_book(
        APPROVED_VALIDATION_RUN_ID,
        runs_root=tmp_path,
        book_id="validation",
        validation_split=True,
    )
    assert book.load_status == "RESULT_INCONSISTENT"


def test_source_bytes_unchanged_after_review(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("runs missing")
    before = {
        p.name: hashlib.sha256((BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID / p.name).read_bytes()).hexdigest()
        for p in (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).glob("*.json")
    }
    out = run_results_cost_review(output_root=tmp_path / "reviews", runs_root=BACKTEST_RUNS_ROOT)
    assert out["status"] == "REVIEW_COMPLETE"
    after = {
        p.name: hashlib.sha256((BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID / p.name).read_bytes()).hexdigest()
        for p in (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).glob("*.json")
    }
    assert before == after


def test_review_rejects_overwrite(tmp_path: Path):
    if not (BACKTEST_RUNS_ROOT / APPROVED_VALIDATION_RUN_ID).is_dir():
        pytest.skip("runs missing")
    rid = "fixed-review-id"
    run_results_cost_review(output_root=tmp_path / "reviews", review_id=rid, runs_root=BACKTEST_RUNS_ROOT)
    with pytest.raises(FileExistsError):
        run_results_cost_review(output_root=tmp_path / "reviews", review_id=rid, runs_root=BACKTEST_RUNS_ROOT)


def test_ui_helper_no_side_effects_import():
    view = build_results_review_view()
    assert "EXPLORATORY" in view["overall_status"]
    assert view["live_or_paper_qualification"] is False
    assert view["cost_diagnostics"]["validation"]["scenarios"]


def test_dashboard_smoke_view_model():
    view = build_results_review_view()
    assert view["development"]["status"] == "OK"
    assert view["validation"]["status"] == "OK"
    assert view["holdout_2025"] == "NOT EVALUATED"
