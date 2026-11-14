"""Parse Trading Economics calendar HTML (undocumented layout adapter)."""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from .types import IMPORTANCE_NOT_DECODED, MacroCalendarEvent, MacroCalendarSnapshot, SnapshotOrigin

TE_BASE = "https://tradingeconomics.com"
CALENDAR_TABLE_ID = "calendar"

_FORECAST_HEADER = re.compile(r"forecast", re.I)
_TR_OPEN = re.compile(r"<tr\b", re.I)
_ROW_START = re.compile(
    r'<tr\b([^>]*\bdata-id\s*=\s*["\'](?P<id>\d+)["\'][^>]*)>',
    re.I | re.DOTALL,
)
_ATTR = re.compile(r'data-(?P<key>id|country|category|event|url)\s*=\s*["\'](?P<val>[^"\']*)["\']', re.I)
_TAG_TEXT = re.compile(
    r'<(?:span|a|div)[^>]*\bclass\s*=\s*["\'][^"\']*calendar-event[^"\']*["\'][^>]*>(?P<t>.*?)</(?:span|a|div)>',
    re.I | re.S,
)
_REF_TEXT = re.compile(
    r'<[^>]*class\s*=\s*["\'][^"\']*calendar-reference[^"\']*["\'][^>]*>(?P<t>.*?)</',
    re.I | re.S,
)
_ID_SPAN = re.compile(r'<[^>]*\bid\s*=\s*["\'](?P<which>actual|previous|consensus)["\'][^>]*>(?P<t>.*?)</', re.I | re.S)


def _extract_tr_block(body: str, start: int) -> tuple[str, int]:
    """Slice one outer <tr>...</tr> beginning at start (handles nested rows)."""
    if not _TR_OPEN.match(body, start):
        return "", start
    gt = body.find(">", start)
    if gt < 0:
        return body[start:], len(body)
    pos = gt + 1
    depth = 1
    while pos < len(body):
        open_m = _TR_OPEN.match(body, pos)
        if open_m:
            depth += 1
            pos = open_m.end()
            continue
        if body.startswith("</tr>", pos):
            depth -= 1
            pos += 5
            if depth == 0:
                return body[start:pos], pos
            continue
        pos += 1
    return body[start:], len(body)


def _strip_tags(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _safe_te_url(path: str) -> str | None:
    path = (path or "").strip()
    if path.startswith("https://tradingeconomics.com/"):
        return path.split()[0]
    if path.startswith("/"):
        return urljoin(TE_BASE + "/", path.lstrip("/"))
    return None


def _forecast_column_index(header_html: str) -> int | None:
    headers = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", header_html, re.I | re.S)
    for i, cell in enumerate(headers):
        if _FORECAST_HEADER.search(_strip_tags(cell)):
            return i
    return None


def _cell_values(row_html: str, forecast_idx: int | None) -> tuple[str | None, str | None, str | None, str | None]:
    actual = previous = consensus = provider_forecast = None
    for m in _ID_SPAN.finditer(row_html):
        val = _strip_tags(m.group("t")) or None
        which = m.group("which").lower()
        if which == "actual":
            actual = val
        elif which == "previous":
            previous = val
        elif which == "consensus":
            consensus = val
    if forecast_idx is not None:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
        if forecast_idx < len(cells):
            text = _strip_tags(cells[forecast_idx])
            if text:
                provider_forecast = text
    return actual, previous, consensus, provider_forecast


def parse_calendar_html(
    html: bytes | str,
    *,
    origin: SnapshotOrigin = SnapshotOrigin.PUBLIC_HTML,
    capture_started_at: datetime | None = None,
) -> MacroCalendarSnapshot:
    if isinstance(html, bytes):
        text = html.decode("utf-8", errors="replace")
    else:
        text = html
    if "id=\"calendar\"" not in text and "id='calendar'" not in text:
        return MacroCalendarSnapshot(
            origin=origin,
            capture_started_at=capture_started_at or datetime.now(timezone.utc),
            request_url=f"{TE_BASE}/calendar?partial=calendar",
            timezone_status="UNCONFIRMED",
            importance_status=IMPORTANCE_NOT_DECODED,
            events=[],
            parser_diagnostics="No table#calendar in HTML.",
        )
    table_match = re.search(
        r"<table[^>]*\bid\s*=\s*['\"]calendar['\"][^>]*>(?P<body>.*?)</table>",
        text,
        re.I | re.S,
    )
    if not table_match:
        return MacroCalendarSnapshot(
            origin=origin,
            capture_started_at=capture_started_at or datetime.now(timezone.utc),
            request_url=f"{TE_BASE}/calendar?partial=calendar",
            timezone_status="UNCONFIRMED",
            importance_status=IMPORTANCE_NOT_DECODED,
            events=[],
            parser_diagnostics="Could not isolate calendar table.",
        )
    body = table_match.group("body")
    forecast_idx = _forecast_column_index(body)
    events: dict[str, MacroCalendarEvent] = {}
    dupes = 0
    pos = 0
    while True:
        m = _ROW_START.search(body, pos)
        if not m:
            break
        attrs = {a.group("key"): unescape(a.group("val")) for a in _ATTR.finditer(m.group(0) + m.group(1))}
        eid = attrs.get("id") or m.group("id")
        row_html, end = _extract_tr_block(body, m.start())
        if end <= m.start():
            break
        if "<table" in row_html[10:] and not _TAG_TEXT.search(row_html):
            pos = end
            continue
        title_m = _TAG_TEXT.search(row_html)
        title = _strip_tags(title_m.group("t")) if title_m else attrs.get("event", "")
        ref_m = _REF_TEXT.search(row_html)
        reference = _strip_tags(ref_m.group("t")) if ref_m else None
        url = _safe_te_url(attrs.get("url", ""))
        if not eid or not title or not url:
            pos = end
            continue
        date_m = re.search(r'data-date\s*=\s*["\']([^"\']+)["\']', row_html, re.I)
        time_m = re.search(r'data-time\s*=\s*["\']([^"\']+)["\']', row_html, re.I)
        display_date = date_m.group(1) if date_m else None
        display_time = time_m.group(1) if time_m else None
        if not display_date:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
            for cell in cells[:3]:
                plain = _strip_tags(cell)
                if re.match(r"\d{4}-\d{2}-\d{2}", plain):
                    display_date = plain
                    break
        actual, previous, consensus, provider_forecast = _cell_values(row_html, forecast_idx)
        ev = MacroCalendarEvent(
            provider_event_id=eid,
            country=(attrs.get("country") or "").lower(),
            category=(attrs.get("category") or "").lower(),
            event=title,
            reference=reference or None,
            display_date=display_date,
            display_time=display_time,
            scheduled_at_utc=None,
            importance=None,
            actual=actual,
            previous=previous,
            revised_raw=None,
            consensus=consensus,
            provider_forecast=provider_forecast,
            source_url=url,
        )
        if eid in events:
            dupes += 1
        else:
            events[eid] = ev
        pos = end
    now = capture_started_at or datetime.now(timezone.utc)
    ev_list = list(events.values())
    dates = sorted({e.display_date for e in ev_list if e.display_date})
    return MacroCalendarSnapshot(
        origin=origin,
        capture_started_at=now,
        request_url=f"{TE_BASE}/calendar?partial=calendar",
        timezone_status="UNCONFIRMED — website display timezone not established",
        importance_status=IMPORTANCE_NOT_DECODED,
        events=ev_list,
        parser_diagnostics=f"Parsed {len(ev_list)} outer event rows." + (f" Skipped {dupes} duplicate IDs." if dupes else ""),
        coverage_date_min=dates[0] if dates else None,
        coverage_date_max=dates[-1] if dates else None,
    )


def decode_har_response_content(entry: dict) -> bytes | None:
    """Decode a HAR response body if base64-encoded (local extraction helper)."""
    content = entry.get("response", {}).get("content", {})
    text = content.get("text")
    if not text:
        return None
    if content.get("encoding") == "base64":
        return base64.b64decode(text)
    return text.encode("utf-8")
