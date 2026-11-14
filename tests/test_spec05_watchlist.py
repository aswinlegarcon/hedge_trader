"""Spec 05 — watchlist observations and selection identity."""
from __future__ import annotations

import socket
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from nifty_lab.brokers.upstox_candles import INTERVAL_DAILY
from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.config import FAKE_SECRET_SENTINEL
from nifty_lab.research import WatchlistRefreshService, build_observation
from nifty_lab.research.watchlist_board import NOT_FETCHED
from nifty_lab.ui.common import upstox_selection_identity

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(autouse=True)
def block_net(monkeypatch):
    class G(socket.socket):
        def connect(self, *a, **k):
            raise OSError("blocked")

    monkeypatch.setattr(socket, "socket", G)


def _daily(n: int = 220) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz=IST)
    close = np.linspace(100, 150, n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1_000_000},
        index=idx,
    )


def _m5_session(bars: int = 30, base: float = 100.0) -> pd.DataFrame:
    start = datetime(2026, 11, 13, 9, 15, tzinfo=IST)
    idx = pd.date_range(start, periods=bars, freq="5min", tz=IST)
    close = base + np.arange(bars) * 0.1
    vol = np.ones(bars) * 1000
    vol[-1] = 2500
    return pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": vol},
        index=idx,
    )


def test_daily_trend_above_both():
    obs = build_observation(
        research_label="X",
        trading_symbol="TST",
        instrument_key="k",
        display_name="T",
        daily=_daily(),
        m5=_m5_session(),
        now=datetime(2026, 11, 13, 15, 0, tzinfo=IST),
    )
    assert "ABOVE" in obs.daily_trend or obs.daily_trend == "MIXED"


def test_rel_volume_excludes_latest_from_mean():
    m5 = _m5_session(25)
    obs = build_observation(
        research_label="X",
        trading_symbol="TST",
        instrument_key="k",
        display_name="T",
        daily=_daily(),
        m5=m5,
        now=datetime(2026, 11, 13, 12, 0, tzinfo=IST),
    )
    assert "preceding 20" in obs.rel_volume


def test_vwap_zero_volume_unknown():
    m5 = _m5_session(5)
    m5.loc[m5.index, "volume"] = 0
    obs = build_observation(
        research_label="X",
        trading_symbol="TST",
        instrument_key="k",
        display_name="T",
        daily=None,
        m5=m5,
        now=datetime(2026, 11, 13, 12, 0, tzinfo=IST),
    )
    assert obs.session_vwap is None


def test_frozen_level_cross_detection():
    idx = pd.date_range("2026-11-13 09:15", periods=40, freq="5min", tz=IST)
    close = np.ones(40) * 100.0
    close[-2] = 99.0
    close[-1] = 101.5
    high = close + 1
    low = close - 1
    m5 = pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1000}, index=idx)
    obs = build_observation(
        research_label="X",
        trading_symbol="TST",
        instrument_key="k",
        display_name="T",
        daily=_daily(100),
        m5=m5,
        now=datetime(2026, 11, 13, 15, 0, tzinfo=IST),
    )
    assert "resistance" in obs.level_observation.lower() or "support" in obs.level_observation.lower() or "no frozen" in obs.level_observation.lower()


def test_selection_identity_changes():
    a = upstox_selection_identity("ICICI Bank", "", "5 minute")
    b = upstox_selection_identity("L&T", "", "5 minute")
    c = upstox_selection_identity("ICICI Bank", "ICICIBANK", "Daily")
    assert a != b
    assert a != c


class _FakeMD:
    def __init__(self, fail_second: bool = False):
        self.transport = object()
        self.fail_second = fail_second
        self.calls = 0

    def reset_call_budget(self) -> None:
        pass

    def load_dataset(self, inst, spec):
        self.calls += 1
        if self.fail_second and self.calls > 1:
            raise RuntimeError("fetch fail")
        idx = pd.date_range("2024-01-01", periods=60, freq="D", tz=IST) if spec.label == "daily" else pd.date_range(
            "2026-11-13 09:15", periods=30, freq="5min", tz=IST
        )
        close = np.linspace(100, 110, len(idx))
        df = pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000},
            index=idx,
        )
        from nifty_lab.data.base import DataKind, DataProvenance, MarketDataset

        prov = DataProvenance(
            kind=DataKind.BROKER_LIVE,
            source="mock",
            symbol=inst.trading_symbol,
            retrieved_at=datetime.now(ZoneInfo("UTC")),
            last_bar_time=idx[-1].to_pydatetime(),
        )
        return MarketDataset(df=df, provenance=prov)


def test_auth_abort_remaining_not_fetched(monkeypatch):
    from nifty_lab.brokers import upstox_instruments as inst_mod
    from nifty_lab.brokers.upstox_instruments import ResolvedInstrument
    from nifty_lab.research import watchlist_board as wb

    fake_master = type("M", (), {"records": [{"exchange": "NSE", "segment": "NSE_EQ", "trading_symbol": "A", "instrument_key": "k", "name": "A", "instrument_type": "EQ"}]})()
    monkeypatch.setattr(wb, "load_master", lambda t, force=False: fake_master)
    monkeypatch.setattr(
        inst_mod,
        "load_master",
        lambda t, force=False: fake_master,
    )
    monkeypatch.setattr(
        wb,
        "find_by_label",
        lambda recs, label: ([ResolvedInstrument("k", "A", "A", "NSE_EQ", "EQ")], ""),
    )
    monkeypatch.setattr(inst_mod, "research_labels", lambda: ("One", "Two"))

    class FailAuth(_FakeMD):
        def load_dataset(self, inst, spec):
            raise UpstoxAuthError("auth")

    bundle = WatchlistRefreshService(FailAuth()).refresh(labels=("One", "Two"))
    assert bundle.observations[0].data_state == NOT_FETCHED
    assert bundle.observations[1].data_state == NOT_FETCHED


def test_no_sentinel_in_diagnostic():
    obs = build_observation(
        research_label="X",
        trading_symbol="TST",
        instrument_key="k",
        display_name="T",
        daily=_daily(50),
        m5=_m5_session(25),
    )
    blob = f"{obs.summary} {obs.diagnostic}"
    assert FAKE_SECRET_SENTINEL not in blob
