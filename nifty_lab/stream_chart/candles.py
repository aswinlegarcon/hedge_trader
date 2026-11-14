"""5-minute candle aggregation from trade ticks (source time, not receipt)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .constants import CANDLE_MINUTES, IST, MAX_DEDUPE_KEYS, MAX_RETAINED_BARS


@dataclass(frozen=True)
class CandleBar:
    time_epoch: int  # UTC epoch seconds (bar open), for Lightweight Charts
    open: float
    high: float
    low: float
    close: float
    complete: bool
    source: Literal["bootstrap", "stream"]
    incomplete_coverage: bool = False
    gap_after: bool = False


@dataclass(frozen=True)
class CoverageNote:
    kind: str
    detail: str


@dataclass
class CandleBook:
    bootstrap_completed: list[CandleBar] = field(default_factory=list)
    stream_completed: list[CandleBar] = field(default_factory=list)
    forming: CandleBar | None = None
    late_ticks_ignored: int = 0
    duplicate_ticks_ignored: int = 0
    coverage_notes: list[CoverageNote] = field(default_factory=list)
    _high_water_trade_ms: int = 0
    _seen_keys: set[tuple[int, float]] = field(default_factory=set)

    def copy(self) -> CandleBook:
        other = CandleBook(
            bootstrap_completed=list(self.bootstrap_completed),
            stream_completed=list(self.stream_completed),
            forming=self.forming,
            late_ticks_ignored=self.late_ticks_ignored,
            duplicate_ticks_ignored=self.duplicate_ticks_ignored,
            coverage_notes=list(self.coverage_notes),
            _high_water_trade_ms=self._high_water_trade_ms,
            _seen_keys=set(self._seen_keys),
        )
        return other

    def bar_open_epoch(self, trade_ms: int) -> int:
        dt = datetime.fromtimestamp(trade_ms / 1000.0, tz=timezone.utc).astimezone(IST)
        minute = (dt.minute // CANDLE_MINUTES) * CANDLE_MINUTES
        floored = dt.replace(minute=minute, second=0, microsecond=0)
        return int(floored.astimezone(timezone.utc).timestamp())

    def merge_bootstrap(self, bars: list[CandleBar]) -> None:
        have = {b.time_epoch for b in self.bootstrap_completed}
        for b in sorted(bars, key=lambda x: x.time_epoch):
            if not b.complete or b.time_epoch in have:
                continue
            if any(s.time_epoch == b.time_epoch for s in self.stream_completed):
                continue
            self.bootstrap_completed.append(b)
            have.add(b.time_epoch)
        self.bootstrap_completed.sort(key=lambda x: x.time_epoch)
        self._trim()

    def load_replay_bootstrap(self, bars: list[CandleBar]) -> None:
        self.merge_bootstrap(bars)

    def _trim(self) -> None:
        if len(self.bootstrap_completed) > MAX_RETAINED_BARS:
            self.bootstrap_completed = self.bootstrap_completed[-MAX_RETAINED_BARS:]
        if len(self.stream_completed) > MAX_RETAINED_BARS:
            self.stream_completed = self.stream_completed[-MAX_RETAINED_BARS:]
        if len(self._seen_keys) > MAX_DEDUPE_KEYS:
            self._seen_keys = set(list(self._seen_keys)[-MAX_DEDUPE_KEYS:])

    def _stream_epoch_taken(self, epoch: int) -> bool:
        return any(b.time_epoch == epoch for b in self.stream_completed)

    def _finalize_forming(self, *, gap_after: bool = False) -> None:
        if self.forming is None:
            return
        done = CandleBar(
            time_epoch=self.forming.time_epoch,
            open=self.forming.open,
            high=self.forming.high,
            low=self.forming.low,
            close=self.forming.close,
            complete=True,
            source="stream",
            incomplete_coverage=self.forming.incomplete_coverage,
            gap_after=gap_after,
        )
        if not self._stream_epoch_taken(done.time_epoch):
            self.stream_completed.append(done)
            self.stream_completed.sort(key=lambda x: x.time_epoch)
        self.forming = None
        self._trim()

    def apply_trade(self, *, price: float, trade_ms: int) -> bool:
        if not math.isfinite(price) or price <= 0:
            return False
        key = (trade_ms, round(price, 4))
        if key in self._seen_keys:
            self.duplicate_ticks_ignored += 1
            return False
        open_epoch = self.bar_open_epoch(trade_ms)

        # Conservative late policy: never move backward across buckets after forward progress.
        if self._high_water_trade_ms and trade_ms < self._high_water_trade_ms:
            if self.forming is None or open_epoch != self.forming.time_epoch:
                self.late_ticks_ignored += 1
                return False
            bar_open_ms = self.forming.time_epoch * 1000
            if trade_ms < bar_open_ms:
                self.late_ticks_ignored += 1
                return False

        # Do not mutate a completed stream bar or re-open a bootstrapped bucket via late data.
        if open_epoch != (self.forming.time_epoch if self.forming else None):
            if self._stream_epoch_taken(open_epoch):
                self.late_ticks_ignored += 1
                return False
            if any(b.time_epoch == open_epoch for b in self.bootstrap_completed) and self.forming is None:
                # First stream observation in a bootstrapped bucket — forming only; drop bootstrap view for that epoch.
                self.bootstrap_completed = [b for b in self.bootstrap_completed if b.time_epoch != open_epoch]
                self.coverage_notes.append(
                    CoverageNote("overlap", f"Stream forming supersedes bootstrap bar at {open_epoch}.")
                )

        self._seen_keys.add(key)
        older = bool(self._high_water_trade_ms) and trade_ms < self._high_water_trade_ms
        self._high_water_trade_ms = max(self._high_water_trade_ms, trade_ms)

        if self.forming and self.forming.time_epoch != open_epoch:
            self._finalize_forming()

        if self.forming is None:
            self.forming = CandleBar(
                time_epoch=open_epoch,
                open=price,
                high=price,
                low=price,
                close=price,
                complete=False,
                source="stream",
                incomplete_coverage=True,
            )
        else:
            f = self.forming
            # Older-than-latest trade in the same bucket extends high/low but cannot overwrite the newer close.
            # Equal timestamps keep the Spec 14 arrival-order policy (later arrival sets close).
            self.forming = CandleBar(
                time_epoch=f.time_epoch,
                open=f.open,
                high=max(f.high, price),
                low=min(f.low, price),
                close=f.close if older else price,
                complete=False,
                source="stream",
                incomplete_coverage=f.incomplete_coverage,
            )
        self._trim()
        return True

    def chart_rows(self) -> list[dict]:
        """Unique strictly ascending bar times for Lightweight Charts."""
        by_epoch: dict[int, CandleBar] = {}
        for b in self.bootstrap_completed:
            by_epoch[b.time_epoch] = b
        for b in self.stream_completed:
            by_epoch[b.time_epoch] = b
        if self.forming is not None:
            by_epoch[self.forming.time_epoch] = self.forming
        ordered = sorted(by_epoch.values(), key=lambda x: x.time_epoch)
        rows: list[dict] = []
        prev_t: int | None = None
        for b in ordered:
            if prev_t is not None and b.time_epoch <= prev_t:
                continue
            prev_t = b.time_epoch
            rows.append(
                {
                    "time": b.time_epoch,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "complete": b.complete,
                    "source": b.source,
                    "incomplete_coverage": b.incomplete_coverage,
                    "gap_after": b.gap_after,
                }
            )
        return rows

    def chart_series(self) -> list[dict]:
        return [{"time": r["time"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]} for r in self.chart_rows()]

    def assert_chart_invariants(self) -> None:
        times = [r["time"] for r in self.chart_series()]
        if times != sorted(set(times)):
            raise AssertionError(f"Non-monotonic chart times: {times}")