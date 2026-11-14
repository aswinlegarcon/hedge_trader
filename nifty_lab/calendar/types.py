"""Macro calendar snapshot types (Spec 07)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SnapshotOrigin(str, Enum):
    HAR_SNAPSHOT = "HAR_SNAPSHOT"
    JSON_IMPORT = "JSON_IMPORT"
    PUBLIC_HTML = "PUBLIC_HTML"


TIMEZONE_UNCONFIRMED = "UNCONFIRMED"
TIMEZONE_USER_CONFIRMED = "USER_CONFIRMED"
IMPORTANCE_NOT_DECODED = "NOT DECODED"

STALE_IMMINENT_MINUTES = 30


@dataclass(frozen=True)
class MacroCalendarEvent:
    provider_event_id: str
    country: str
    category: str
    event: str
    reference: str | None
    display_date: str | None
    display_time: str | None
    scheduled_at_utc: datetime | None
    importance: str | None
    actual: str | None
    previous: str | None
    revised_raw: str | None
    consensus: str | None
    provider_forecast: str | None
    source_url: str
    importance_source: str = IMPORTANCE_NOT_DECODED

    def display_datetime_label(self) -> str:
        parts = [p for p in (self.display_date, self.display_time) if p]
        if not parts:
            return "—"
        return " ".join(parts) + " (timezone unconfirmed)"


@dataclass
class MacroCalendarSnapshot:
    origin: SnapshotOrigin
    capture_started_at: datetime
    request_url: str
    timezone_status: str
    importance_status: str
    events: list[MacroCalendarEvent] = field(default_factory=list)
    parser_diagnostics: str = ""
    retrieval_note: str = ""
    user_timezone: str | None = None
    refresh_failed: bool = False
    refresh_failure: str = ""
    coverage_date_min: str | None = None
    coverage_date_max: str | None = None

    @property
    def event_count(self) -> int:
        return len(self.events)

    def is_stale_for_imminent(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        cap = self.capture_started_at
        if cap.tzinfo is None:
            cap = cap.replace(tzinfo=timezone.utc)
        age = (now - cap.astimezone(timezone.utc)).total_seconds()
        return age > STALE_IMMINENT_MINUTES * 60
