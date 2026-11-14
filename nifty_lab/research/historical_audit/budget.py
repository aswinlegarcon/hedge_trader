"""Hard request budget for historical audit (Spec 09)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .types import MAX_HISTORICAL_REQUESTS, MAX_INSTRUMENT_MASTER_REQUESTS


class AuditBudgetExceeded(Exception):
    """Raised before any network call that would exceed the audit budget."""


@dataclass
class AuditRequestBudget:
    historical_limit: int = MAX_HISTORICAL_REQUESTS
    master_limit: int = MAX_INSTRUMENT_MASTER_REQUESTS
    historical_attempted: int = 0
    master_attempted: int = 0
    _attempt_log: list[str] = field(default_factory=list)

    def consume_master(self, *, label: str) -> None:
        if self.master_attempted >= self.master_limit:
            raise AuditBudgetExceeded("Instrument master request budget exceeded.")
        self.master_attempted += 1
        self._attempt_log.append(f"master:{label}")

    def consume_historical(self, *, label: str) -> None:
        if self.historical_attempted >= self.historical_limit:
            raise AuditBudgetExceeded("Historical candle request budget exceeded.")
        self.historical_attempted += 1
        self._attempt_log.append(f"historical:{label}")

    def snapshot(self) -> dict[str, int]:
        return {
            "historical_attempted": self.historical_attempted,
            "historical_limit": self.historical_limit,
            "master_attempted": self.master_attempted,
            "master_limit": self.master_limit,
        }
