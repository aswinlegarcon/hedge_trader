"""Bounded public calendar refresh — honest availability (Spec 07)."""
from __future__ import annotations

from datetime import datetime, timezone

from .html_parse import parse_calendar_html
from .te_transport import PUBLIC_CALENDAR_URL, TEHttpTransport, TETransport
from .types import MacroCalendarSnapshot, SnapshotOrigin


def try_public_calendar_refresh(
    transport: TETransport,
    *,
    prior: MacroCalendarSnapshot | None = None,
) -> tuple[MacroCalendarSnapshot | None, str]:
    """
    Returns (new_snapshot_or_none, status_message).
    On failure, prior snapshot is not mutated; caller keeps reference copy.
    """
    if isinstance(transport, TEHttpTransport):
        transport.reset_call_budget()
    try:
        status, body, _ = transport.get(PUBLIC_CALENDAR_URL)
    except Exception as exc:
        return None, f"UNAVAILABLE: network error ({type(exc).__name__})"
    if status in (202, 204) or (status == 200 and not body.strip()):
        return None, f"UNAVAILABLE: HTTP {status} with empty body (no realtime calendar HTML)."
    if status in (401, 403, 429):
        return None, f"UNAVAILABLE: HTTP {status} access denied or rate limited."
    if 300 <= status < 400:
        return None, f"UNAVAILABLE: HTTP {status} redirect not followed."
    if status != 200:
        return None, f"UNAVAILABLE: HTTP {status}."
    if b"table" not in body.lower() and b"calendar" not in body.lower():
        return None, "UNAVAILABLE: response is not calendar HTML."
    snap = parse_calendar_html(
        body,
        origin=SnapshotOrigin.PUBLIC_HTML,
        capture_started_at=datetime.now(timezone.utc),
    )
    if not snap.events:
        snap.parser_diagnostics += " Parse-empty — coverage unknown, not 'no events'."
        snap.refresh_failed = True
        snap.refresh_failure = "HTTP 200 but zero valid event rows."
        return snap, "PARSE_EMPTY: validated HTML but no event rows."
    snap.retrieval_note = "Public GET succeeded — still a web snapshot, not guaranteed realtime feed."
    return snap, "SUCCESS"
