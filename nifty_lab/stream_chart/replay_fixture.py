"""Offline REPLAY timeline — bootstrap + feed share one coherent clock."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .candles import CandleBar
from .constants import INSTRUMENT_KEY
from .fixtures import ltpc_frame, market_info_frame


def _utc(*, y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).timestamp())


def _ms(epoch_sec: int) -> int:
    return epoch_sec * 1000


# Shared demo day: 2026-11-14 UTC. Bootstrap completes 04:40 & 04:45 bars; stream continues 04:45→04:50.
REPLAY_DAY = (2026, 11, 14)
BAR_0440 = _utc(y=2026, m=11, d=14, hh=4, mm=40)
BAR_0445 = _utc(y=2026, m=11, d=14, hh=4, mm=45)
BAR_0450 = _utc(y=2026, m=11, d=14, hh=4, mm=50)

REPLAY_BOOTSTRAP_BARS: list[CandleBar] = [
    CandleBar(BAR_0440, 1278.0, 1279.5, 1277.5, 1279.0, complete=True, source="bootstrap", incomplete_coverage=False),
    CandleBar(BAR_0445, 1279.0, 1281.0, 1278.5, 1280.5, complete=True, source="bootstrap", incomplete_coverage=False),
]

# Trades: 04:49:59 & 04:49:58 (04:45 bar), rollover 04:50:01, late 04:49:58 after rollover must be ignored.
T_045859 = _ms(_utc(y=2026, m=11, d=14, hh=4, mm=49, ss=59))
T_045858 = _ms(_utc(y=2026, m=11, d=14, hh=4, mm=49, ss=58))
T_045001 = _ms(_utc(y=2026, m=11, d=14, hh=4, mm=50, ss=1))
T_045005 = _ms(_utc(y=2026, m=11, d=14, hh=4, mm=50, ss=5))


@dataclass(frozen=True)
class ReplayScenario:
    bootstrap: list[CandleBar]
    frames: list[bytes]
    label: str


def acceptance_late_tick_scenario() -> ReplayScenario:
    frames = [
        ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1280.6, trade_ms=T_045859),
        ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1281.1, trade_ms=T_045001),
        ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1280.55, trade_ms=T_045858),
        ltpc_frame(instrument_key=INSTRUMENT_KEY, ltp=1281.4, trade_ms=T_045005),
        market_info_frame(receipt_ms=T_045005 + 500),
    ]
    return ReplayScenario(REPLAY_BOOTSTRAP_BARS, frames, "acceptance-late-tick")


def ui_demo_scenario() -> ReplayScenario:
    """Paced UI demo: extends acceptance path with visible delays between ticks."""
    base = acceptance_late_tick_scenario()
    return ReplayScenario(base.bootstrap, base.frames, "ui-replay-demo")


def paced_replay_frames(frames: list[bytes], *, step_sec: float = 0.35) -> ReplayScenario:
    return ReplayScenario(REPLAY_BOOTSTRAP_BARS, frames, f"paced-{step_sec}")