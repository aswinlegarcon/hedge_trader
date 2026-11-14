"""Spec 07 — macro calendar import, parse, public refresh (offline)."""
from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone

import pytest

from nifty_lab.brokers.upstox_errors import UpstoxDataError
from nifty_lab.brokers.upstox_transport import RequestsTransport
from nifty_lab.calendar import import_calendar_json, try_public_calendar_refresh
from nifty_lab.calendar.html_parse import parse_calendar_html
from nifty_lab.calendar.te_transport import PUBLIC_CALENDAR_URL, TEHttpTransport
from nifty_lab.calendar.types import STALE_IMMINENT_MINUTES, MacroCalendarSnapshot, SnapshotOrigin


@pytest.fixture(autouse=True)
def block_net(monkeypatch):
    class G(socket.socket):
        def connect(self, *a, **k):
            raise OSError("blocked")

    monkeypatch.setattr(socket, "socket", G)


MINI_HTML = """
<table id="calendar">
<thead><tr><th>Date</th><th>Country</th><th>Event</th><th>Actual</th><th>Previous</th><th>Consensus</th><th>TE Forecast</th></tr></thead>
<tbody>
<tr data-id="100" data-country="india" data-category="gdp" data-event="gdp-growth" data-url="/india/gdp-growth">
  <td>2026-11-14</td><td>india</td>
  <td><span class="calendar-event">GDP Growth</span></td>
  <td><span id="actual">6.1%</span></td>
  <td><span id="previous">6.0%</span></td>
  <td><span id="consensus">6.2%</span></td>
  <td>6.15%</td>
  <td><span class="calendar-reference">Q3</span></td>
</tr>
<tr data-id="100" data-country="india" data-category="gdp" data-event="dup" data-url="/india/gdp-growth">
  <td>dup</td>
</tr>
<tr data-id="200" data-country="united states" data-category="cpi" data-event="cpi" data-url="https://tradingeconomics.com/united-states/cpi">
  <td>2026-11-15</td>
  <td><span class="calendar-event">US CPI</span></td>
  <td><span id="consensus">0.3%</span></td>
</tr>
</tbody>
</table>
"""


def test_parse_outer_rows_and_forecast_column():
    snap = parse_calendar_html(MINI_HTML, capture_started_at=datetime(2026, 11, 13, tzinfo=timezone.utc))
    assert len(snap.events) == 2
    gdp = next(e for e in snap.events if e.provider_event_id == "100")
    assert gdp.provider_forecast == "6.15%"
    assert gdp.consensus == "6.2%"
    assert gdp.actual == "6.1%"
    assert gdp.source_url.startswith("https://tradingeconomics.com/")


def test_import_synthetic_json():
    payload = {
        "origin": "HAR_SNAPSHOT",
        "capture_started_at": "2026-11-13T04:53:50.319Z",
        "timezone_status": "UNCONFIRMED",
        "importance_status": "NOT DECODED",
        "events": [
            {
                "provider_event_id": "1",
                "country": "india",
                "category": "rates",
                "event": "RBI",
                "reference": None,
                "display_date": "2026-11-13",
                "display_time": "10:00 AM",
                "actual": None,
                "previous": None,
                "consensus": None,
                "provider_forecast": None,
                "source_url": "https://tradingeconomics.com/india/rates",
            }
        ],
    }
    snap = import_calendar_json(json.dumps(payload).encode())
    assert snap.event_count == 1
    assert snap.coverage_date_min == "2026-11-13"
    assert "UNCONFIRMED" in snap.timezone_status or snap.timezone_status == "UNCONFIRMED"


def test_public_refresh_202_unavailable():
    class MockTE:
        def get(self, url: str):
            assert url == PUBLIC_CALENDAR_URL
            return 202, b"", {}

        def reset_call_budget(self):
            pass

    prior = import_calendar_json(
        json.dumps(
            {
                "capture_started_at": "2026-11-13T00:00:00Z",
                "events": [
                    {
                        "provider_event_id": "1",
                        "country": "india",
                        "category": "x",
                        "event": "E",
                        "source_url": "https://tradingeconomics.com/india/x",
                    }
                ],
            }
        ).encode()
    )
    new, msg = try_public_calendar_refresh(MockTE(), prior=prior)
    assert new is None
    assert "202" in msg
    assert prior.event_count == 1


def test_public_refresh_200_parsed():
    class MockTE:
        def __init__(self):
            self.n = 0

        def reset_call_budget(self):
            self.n = 0

        def get(self, url: str):
            self.n += 1
            assert self.n == 1
            return 200, MINI_HTML.encode(), {}

    snap, msg = try_public_calendar_refresh(MockTE(), prior=None)
    assert msg == "SUCCESS"
    assert snap is not None and snap.event_count == 2


def test_te_one_get_budget():
    tr = TEHttpTransport()
    tr.reset_call_budget()
    tr._calls = 1
    with pytest.raises(RuntimeError):
        tr.get(PUBLIC_CALENDAR_URL)


def test_upstox_blocks_te_host():
    tr = RequestsTransport()
    with pytest.raises(UpstoxDataError):
        tr.get(PUBLIC_CALENDAR_URL)


def test_stale_imminent():
    snap = MacroCalendarSnapshot(
        origin=SnapshotOrigin.JSON_IMPORT,
        capture_started_at=datetime.now(timezone.utc) - timedelta(minutes=STALE_IMMINENT_MINUTES + 5),
        request_url=PUBLIC_CALENDAR_URL,
        timezone_status="UNCONFIRMED",
        importance_status="NOT DECODED",
        events=[],
    )
    assert snap.is_stale_for_imminent()
