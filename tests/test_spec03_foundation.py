"""Spec 03 scenario coverage — fake inputs and temporary databases only."""
from __future__ import annotations

import socket
import tempfile
from pathlib import Path

import pytest

from nifty_lab.brokers import ALL_BROKERS, UpstoxReadOnly
from nifty_lab.config import (
    DEFAULT_CAPITAL_INR,
    DEFAULT_LOSS_CEILING_INR,
    FAKE_SECRET_SENTINEL,
    RESEARCH_PROFILE_ID,
    RiskConfig,
    credential_status,
    load_config,
)
from nifty_lab.journal import Journal, JournalEntry
from nifty_lab.journal.db import FUNDED_PAPER_QUALIFIED, UNQUALIFIED_MANUAL
from nifty_lab.options import Quote, bull_put_spread
from nifty_lab.risk import (
    EligibilityStatus,
    OpenRiskLeg,
    check_position_eligibility,
    independent_test_context,
    production_context_blocked,
)
from nifty_lab.risk.recording import context_for_production_save, try_record_funded_paper

def _spread(long=23750):
    b = {("PE", 23800.0): Quote(90, 92), ("PE", float(long)): Quote(60, 62)}
    return bull_put_spread("NIFTY", "x", 23800, long, b, 1, 65)


@pytest.fixture(autouse=True)
def block_socket_connect(monkeypatch):
    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, *args, **kwargs):
            raise OSError("network connect blocked in tests")

        def connect_ex(self, *args, **kwargs):
            return 1

    monkeypatch.setattr(socket, "socket", GuardedSocket)


def test_profile_defaults():
    cfg = load_config()
    assert cfg.profile_id == RESEARCH_PROFILE_ID
    assert cfg.risk.capital == DEFAULT_CAPITAL_INR
    assert cfg.risk.max_drawdown == DEFAULT_LOSS_CEILING_INR
    assert cfg.risk.risk_per_trade_max == 400.0


def test_upstox_only_registry():
    assert len(ALL_BROKERS) == 1
    assert isinstance(ALL_BROKERS[0], UpstoxReadOnly)


def test_offline_status_never_connected(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", FAKE_SECRET_SENTINEL)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", FAKE_SECRET_SENTINEL)
    status = UpstoxReadOnly().status()
    assert status.state.value != "CONNECTED"
    blob = f"{status.detail} {status.name} {status.pricing_note}"
    assert FAKE_SECRET_SENTINEL not in blob


def test_credential_status_hides_sentinel(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_SECRET", FAKE_SECRET_SENTINEL)
    st = credential_status()
    assert st["Upstox API"]["UPSTOX_API_SECRET"] is False


def test_drawdown_boundary_rejects(monkeypatch):
    monkeypatch.delenv("NSL_CAPITAL_INR", raising=False)
    ctx = independent_test_context(
        equity_inr=18_000,
        peak_equity_inr=20_000,
        per_position_risk_max=1_500,
        candidate_margin_required_inr=0.0,
    )
    res = check_position_eligibility(_spread(), RiskConfig(risk_per_trade_max=1_500), context=ctx)
    assert res.status == EligibilityStatus.REJECTED


def test_peak_drawdown_after_gains_rejects():
    ctx = independent_test_context(
        equity_inr=19_000,
        peak_equity_inr=21_000,
        per_position_risk_max=2_000,
        candidate_margin_required_inr=0.0,
    )
    res = check_position_eligibility(_spread(), RiskConfig(risk_per_trade_max=2_000), context=ctx)
    assert res.status == EligibilityStatus.REJECTED
    assert any("drawdown" in r.lower() for r in res.reasons)


def test_unconfirmed_per_position_insufficient():
    ctx = independent_test_context(per_position_risk_max=None)
    risk = RiskConfig()
    res = check_position_eligibility(_spread(), risk, context=ctx)
    assert res.status == EligibilityStatus.INSUFFICIENT_DATA
    assert any("unconfirmed" in r.lower() for r in res.reasons)


def test_no_minimum_risk_encouragement():
    ctx = independent_test_context(per_position_risk_max=1_500, candidate_margin_required_inr=0.0)
    risk = RiskConfig(risk_per_trade_max=1_500)
    pos = _spread(long=23790)
    res = check_position_eligibility(pos, risk, context=ctx)
    assert not any("minimum research size" in w.lower() for w in res.warnings)


def test_production_context_blocks_save():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "t.db"
        journal = Journal(jpath)
        cfg = load_config()
        ctx = context_for_production_save(cfg, journal)
        entry = JournalEntry(trade_date="2026-01-01", instrument="NIFTY", strategy="test", max_risk_inr=500)
        eid, res = try_record_funded_paper(journal, entry, _spread(), cfg.risk, ctx)
        assert eid is None
        assert res.status == EligibilityStatus.INSUFFICIENT_DATA


def test_save_recheck_with_valid_fixture():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "t.db"
        journal = Journal(jpath)
        risk = RiskConfig(risk_per_trade_max=1_600)
        ctx = independent_test_context(
            per_position_risk_max=1_600,
            candidate_margin_required_inr=0.0,
            max_portfolio_risk_pct=0.10,
            max_single_underlying_pct=0.10,
        )
        entry = JournalEntry(trade_date="2026-01-01", instrument="NIFTY x", strategy="bps", max_risk_inr=1_600)
        pos = _spread(long=23750)
        eid, res = try_record_funded_paper(journal, entry, pos, risk, ctx)
        assert eid is not None, res.reasons
        assert res.status == EligibilityStatus.ELIGIBLE
        df = journal.entries(status="OPEN")
        assert FUNDED_PAPER_QUALIFIED in str(df.iloc[0]["data_source"])


def test_legacy_journal_blocks_qualification():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "t.db"
        journal = Journal(jpath)
        journal.add_entry(
            JournalEntry(
                trade_date="2026-01-01",
                instrument="NIFTY",
                strategy="manual",
                max_risk_inr=400,
                data_source=journal.manual_data_source(),
            )
        )
        cfg = load_config()
        ctx = context_for_production_save(cfg, journal)
        assert ctx.has_unreconciled_legacy
        res = check_position_eligibility(_spread(), cfg.risk, context=ctx)
        assert res.status == EligibilityStatus.INSUFFICIENT_DATA


def test_manual_journal_preserved_and_close():
    with tempfile.TemporaryDirectory() as td:
        jpath = Path(td) / "t.db"
        journal = Journal(jpath)
        eid = journal.add_entry(
            JournalEntry(
                trade_date="2026-01-01",
                instrument="NIFTY",
                strategy="legacy",
                max_risk_inr=1_200,
                data_source=journal.manual_data_source("fixture"),
            )
        )
        journal.close_entry(eid, -150.0, outcome_notes="closed in test")
        closed = journal.entries(status="CLOSED")
        assert float(closed.iloc[0]["realised_pnl_inr"]) == pytest.approx(-150.0)
        assert UNQUALIFIED_MANUAL in str(closed.iloc[0]["data_source"])


def test_production_context_blocked_factory():
    ctx = production_context_blocked(
        initial_capital=20_000,
        loss_ceiling=2_000,
        profile_authorized=False,
    )
    assert not ctx.valuation_trusted
    assert ctx.equity_inr is None
