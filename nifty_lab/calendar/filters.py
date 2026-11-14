"""Filter macro calendar events in-memory (Spec 07)."""
from __future__ import annotations

from datetime import date, timedelta

from .types import MacroCalendarEvent

DEFAULT_COUNTRIES = ("india", "united states")


def _parse_display_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def filter_events(
    events: list[MacroCalendarEvent],
    *,
    countries: list[str] | None,
    importance: str,
    range_mode: str,
    range_start: date | None,
    range_end: date | None,
    today: date,
) -> list[MacroCalendarEvent]:
    out = events
    if countries:
        want = {c.lower() for c in countries}
        out = [e for e in out if e.country in want]
    if importance and importance != "All":
        if importance == "Unknown":
            out = [e for e in out if e.importance is None]
        else:
            out = [e for e in out if (e.importance or "").lower() == importance.lower()]
            if importance == "High":
                pass  # unknown excluded by design
    if range_mode == "Today":
        out = [e for e in out if _parse_display_date(e.display_date) == today]
    elif range_mode == "Tomorrow":
        tom = today + timedelta(days=1)
        out = [e for e in out if _parse_display_date(e.display_date) == tom]
    elif range_mode == "This Week":
        end = today + timedelta(days=6)
        out = [
            e
            for e in out
            if (d := _parse_display_date(e.display_date)) is not None and today <= d <= end
        ]
    elif range_mode == "Custom" and range_start and range_end:
        out = [
            e
            for e in out
            if (d := _parse_display_date(e.display_date)) is not None and range_start <= d <= range_end
        ]
    return out
