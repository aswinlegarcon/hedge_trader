"""Sequential watchlist refresh via existing Upstox services (Spec 05)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import pandas as pd

from ..brokers.upstox_candles import INTERVAL_5M, INTERVAL_DAILY
from ..brokers.upstox_errors import UpstoxAuthError
from ..brokers.upstox_instruments import ResolvedInstrument, find_by_label, load_master, research_labels
from ..brokers.upstox_market_data import UpstoxMarketDataService
from ..data.base import MarketDataset
from .observations import WatchlistObservation, build_observation

NOT_FETCHED = "NOT FETCHED"


@dataclass
class InstrumentFrames:
    daily: pd.DataFrame
    m5: pd.DataFrame


@dataclass
class WatchlistRefreshBundle:
    observations: list[WatchlistObservation]
    frames: dict[str, InstrumentFrames]


class MarketDataPort(Protocol):
    transport: object

    def load_dataset(self, instrument: ResolvedInstrument, spec: object) -> MarketDataset: ...


@dataclass
class WatchlistRefreshService:
    market_data: MarketDataPort

    def refresh(
        self,
        *,
        labels: tuple[str, ...] | None = None,
        now: datetime | None = None,
    ) -> WatchlistRefreshBundle:
        labels = labels or research_labels()
        now = now or datetime.now(timezone.utc)
        master = load_master(self.market_data.transport)
        results: list[WatchlistObservation] = []
        frames: dict[str, InstrumentFrames] = {}
        auth_failed = False
        for label in labels:
            if auth_failed:
                results.append(
                    WatchlistObservation(
                        research_label=label,
                        trading_symbol="",
                        instrument_key="",
                        display_name="",
                        data_state=NOT_FETCHED,
                        daily_context_date="",
                        daily_trend=NOT_FETCHED,
                        daily_close=None,
                        m5_completed_at="",
                        m5_close=None,
                        ema_relation=NOT_FETCHED,
                        vwap_relation=NOT_FETCHED,
                        session_vwap=None,
                        rel_volume=NOT_FETCHED,
                        nearest_support=None,
                        nearest_resistance=None,
                        level_observation=NOT_FETCHED,
                        summary=NOT_FETCHED,
                        limitations=("Authentication required — remaining instruments not fetched.",),
                        diagnostic="AUTH REQUIRED",
                        retrieved_at_utc=now.strftime("%Y-%m-%d %H:%M UTC"),
                    )
                )
                continue
            matches, hint = find_by_label(master.records, label)
            if len(matches) != 1:
                results.append(
                    WatchlistObservation(
                        research_label=label,
                        trading_symbol="",
                        instrument_key="",
                        display_name="",
                        data_state="INSUFFICIENT DATA",
                        daily_context_date="",
                        daily_trend="INSUFFICIENT DATA",
                        daily_close=None,
                        m5_completed_at="",
                        m5_close=None,
                        ema_relation="unavailable",
                        vwap_relation="unavailable",
                        session_vwap=None,
                        rel_volume="unavailable",
                        nearest_support=None,
                        nearest_resistance=None,
                        level_observation="unavailable",
                        summary="instrument resolution failed",
                        limitations=(),
                        diagnostic=hint or "ambiguous or missing instrument",
                        retrieved_at_utc=now.strftime("%Y-%m-%d %H:%M UTC"),
                    )
                )
                continue
            inst = matches[0]
            try:
                ds_daily = self.market_data.load_dataset(inst, INTERVAL_DAILY)
                self.market_data.reset_call_budget()  # type: ignore[attr-defined]
                ds_m5 = self.market_data.load_dataset(inst, INTERVAL_5M)
            except UpstoxAuthError as exc:
                auth_failed = True
                results.append(
                    WatchlistObservation(
                        research_label=label,
                        trading_symbol=inst.trading_symbol,
                        instrument_key=inst.instrument_key,
                        display_name=inst.display_label,
                        data_state=NOT_FETCHED,
                        daily_context_date="",
                        daily_trend=NOT_FETCHED,
                        daily_close=None,
                        m5_completed_at="",
                        m5_close=None,
                        ema_relation=NOT_FETCHED,
                        vwap_relation=NOT_FETCHED,
                        session_vwap=None,
                        rel_volume=NOT_FETCHED,
                        nearest_support=None,
                        nearest_resistance=None,
                        level_observation=NOT_FETCHED,
                        summary=NOT_FETCHED,
                        limitations=("Authentication required.",),
                        diagnostic=str(exc),
                        retrieved_at_utc=now.strftime("%Y-%m-%d %H:%M UTC"),
                    )
                )
                continue
            except Exception as exc:
                results.append(
                    WatchlistObservation(
                        research_label=label,
                        trading_symbol=inst.trading_symbol,
                        instrument_key=inst.instrument_key,
                        display_name=inst.display_label,
                        data_state="PARTIAL DATA",
                        daily_context_date="",
                        daily_trend="unavailable",
                        daily_close=None,
                        m5_completed_at="",
                        m5_close=None,
                        ema_relation="unavailable",
                        vwap_relation="unavailable",
                        session_vwap=None,
                        rel_volume="unavailable",
                        nearest_support=None,
                        nearest_resistance=None,
                        level_observation="unavailable",
                        summary="fetch failed for this instrument",
                        limitations=(),
                        diagnostic=str(exc),
                        retrieved_at_utc=now.strftime("%Y-%m-%d %H:%M UTC"),
                    )
                )
                continue

            obs = build_observation(
                research_label=label,
                trading_symbol=inst.trading_symbol,
                instrument_key=inst.instrument_key,
                display_name=inst.display_label,
                daily=ds_daily.df,
                m5=ds_m5.df,
                now=now,
                retrieved_at=ds_m5.provenance.retrieved_at,
            )
            results.append(obs)
            frames[label] = InstrumentFrames(daily=ds_daily.df, m5=ds_m5.df)
        return WatchlistRefreshBundle(observations=results, frames=frames)


def refresh_watchlist(svc: UpstoxMarketDataService | None = None, **kwargs) -> WatchlistRefreshBundle:
    svc = svc or UpstoxMarketDataService()
    return WatchlistRefreshService(svc).refresh(**kwargs)
