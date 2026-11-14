"""Import sanitized Trading Economics calendar JSON (Spec 07)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .types import IMPORTANCE_NOT_DECODED, MacroCalendarEvent, MacroCalendarSnapshot, SnapshotOrigin

MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _parse_capture_time(value: str | None) -> datetime:
    if not value:
        return datetime.now().astimezone()
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now().astimezone()


def _event_from_dict(row: dict[str, Any]) -> MacroCalendarEvent | None:
    eid = str(row.get("provider_event_id") or "").strip()
    if not eid:
        return None
    url = str(row.get("source_url") or "").strip()
    if not url.startswith("https://tradingeconomics.com/"):
        return None
    imp = row.get("importance")
    importance = str(imp).strip() if imp not in (None, "") else None
    return MacroCalendarEvent(
        provider_event_id=eid,
        country=str(row.get("country") or "").strip().lower(),
        category=str(row.get("category") or "").strip(),
        event=str(row.get("event") or "").strip(),
        reference=(str(row["reference"]).strip() if row.get("reference") not in (None, "") else None),
        display_date=(str(row["display_date"]).strip() if row.get("display_date") else None),
        display_time=(str(row["display_time"]).strip() if row.get("display_time") else None),
        scheduled_at_utc=None,
        importance=importance,
        actual=(str(row["actual"]).strip() if row.get("actual") not in (None, "") else None),
        previous=(str(row["previous"]).strip() if row.get("previous") not in (None, "") else None),
        revised_raw=(str(row["revised_raw"]).strip() if row.get("revised_raw") not in (None, "") else None),
        consensus=(str(row["consensus"]).strip() if row.get("consensus") not in (None, "") else None),
        provider_forecast=(
            str(row["provider_forecast"]).strip() if row.get("provider_forecast") not in (None, "") else None
        ),
        source_url=url,
        importance_source=IMPORTANCE_NOT_DECODED if importance is None else "IMPORTED",
    )


def _coverage_dates(events: list[MacroCalendarEvent]) -> tuple[str | None, str | None]:
    dates = sorted({e.display_date for e in events if e.display_date})
    if not dates:
        return None, None
    return dates[0], dates[-1]


def import_calendar_json(raw: bytes) -> MacroCalendarSnapshot:
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("Import exceeds 5 MB limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object at top level.")
    events_raw = payload.get("events")
    if not isinstance(events_raw, list):
        raise ValueError("Missing events array.")
    origin_raw = str(payload.get("origin") or "JSON_IMPORT").upper()
    try:
        origin = SnapshotOrigin(origin_raw)
    except ValueError:
        origin = SnapshotOrigin.JSON_IMPORT
    tz_status = str(payload.get("timezone_status") or "UNCONFIRMED — no UTC conversion applied")
    imp_status = str(payload.get("importance_status") or IMPORTANCE_NOT_DECODED)
    capture_at = _parse_capture_time(str(payload.get("capture_started_at") or ""))
    request_url = str(payload.get("request_url") or "https://tradingeconomics.com/calendar?partial=calendar")
    seen: dict[str, MacroCalendarEvent] = {}
    dupes = 0
    for item in events_raw:
        if not isinstance(item, dict):
            continue
        ev = _event_from_dict(item)
        if ev is None:
            continue
        if ev.provider_event_id in seen:
            dupes += 1
            continue
        seen[ev.provider_event_id] = ev
    events = list(seen.values())
    dmin, dmax = _coverage_dates(events)
    diag = f"Imported {len(events)} events."
    if dupes:
        diag += f" Skipped {dupes} duplicate provider_event_id rows."
    return MacroCalendarSnapshot(
        origin=origin,
        capture_started_at=capture_at,
        request_url=request_url,
        timezone_status=tz_status,
        importance_status=imp_status,
        events=events,
        parser_diagnostics=diag,
        coverage_date_min=dmin,
        coverage_date_max=dmax,
    )
