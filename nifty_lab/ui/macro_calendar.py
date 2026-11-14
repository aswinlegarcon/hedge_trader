"""Macro calendar UI helpers — shared session (Spec 07)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from ..calendar import MacroCalendarSnapshot, filter_events, import_calendar_json, try_public_calendar_refresh
from ..calendar.filters import DEFAULT_COUNTRIES
from ..calendar.te_transport import TEHttpTransport
from ..calendar.types import TIMEZONE_USER_CONFIRMED, MacroCalendarEvent
from ..config import PROVISIONAL_WATCHLIST

SESSION_MACRO = "macro_calendar_snapshot"
SESSION_MACRO_FAIL = "macro_calendar_refresh_failure"

WATCHLIST_COUNTRY: dict[str, str] = {
    "ICICI Bank": "india",
    "Gold BeES": "india",
    "Bharti Airtel": "india",
    "L&T": "india",
}


def get_macro_snapshot() -> MacroCalendarSnapshot | None:
    return st.session_state.get(SESSION_MACRO)


def import_uploaded_json(raw: bytes) -> None:
    snap = import_calendar_json(raw)
    st.session_state[SESSION_MACRO] = snap
    st.session_state.pop(SESSION_MACRO_FAIL, None)


def run_public_refresh() -> None:
    prior = get_macro_snapshot()
    transport = TEHttpTransport()
    snap, msg = try_public_calendar_refresh(transport, prior=prior)
    st.session_state[SESSION_MACRO_FAIL] = msg
    if snap is not None and snap.events and not snap.refresh_failed:
        st.session_state[SESSION_MACRO] = snap
        st.success("Public refresh returned new HTML snapshot (not realtime-certified).")
    else:
        if prior is not None:
            st.warning(
                f"Public refresh: {msg} — keeping prior imported snapshot "
                f"(captured {prior.capture_started_at.strftime('%Y-%m-%d %H:%M UTC')})."
            )
        else:
            st.error(f"Public refresh: {msg}")


def _countries_in_snapshot(snap: MacroCalendarSnapshot) -> list[str]:
    return sorted({e.country for e in snap.events if e.country})


def render_macro_calendar_section() -> None:
    st.subheader("Macro calendar (Trading Economics import)")
    st.caption(
        "Import a sanitized JSON snapshot from your capture. **Public refresh is not guaranteed** "
        "(ordinary GET may return HTTP 202 empty). Timezone and CSS importance stay explicit/unknown unless confirmed."
    )
    c1, c2 = st.columns(2)
    with c1:
        uploaded = st.file_uploader("Import calendar JSON", type=["json"], help="Max 5 MB; sanitized fields only.")
        if st.button("Load import", disabled=uploaded is None):
            if uploaded is not None:
                import_uploaded_json(uploaded.getvalue())
                st.rerun()
    with c2:
        if st.button("Try public calendar refresh"):
            run_public_refresh()
            st.rerun()

    fail = st.session_state.get(SESSION_MACRO_FAIL)
    if fail:
        st.caption(f"Last public refresh status: {fail}")

    snap = get_macro_snapshot()
    if snap is None:
        st.info("No macro calendar loaded — import the sanitized JSON or use public refresh (may be UNAVAILABLE).")
        return

    stale = snap.is_stale_for_imminent()
    st.caption(
        f"**Origin:** {snap.origin.value} · **Captured:** {snap.capture_started_at.strftime('%Y-%m-%d %H:%M UTC')} · "
        f"**Events:** {snap.event_count} · **Coverage dates:** {snap.coverage_date_min or '—'} → {snap.coverage_date_max or '—'}"
    )
    st.caption(f"**Timezone:** {snap.timezone_status}")
    st.caption(f"**Importance:** {snap.importance_status}")
    if snap.parser_diagnostics:
        st.caption(snap.parser_diagnostics)
    if stale:
        st.caption("Cached snapshot — imminent-event claims disabled (>30m since capture).")
    if snap.retrieval_note:
        st.caption(snap.retrieval_note)

    with st.expander("Optional: confirm display timezone (USER_CONFIRMED)"):
        zone = st.selectbox(
            "IANA timezone for website display times",
            ["", "UTC", "America/New_York", "Asia/Kolkata", "Europe/London"],
            key="macro_tz_pick",
        )
        if st.button("Apply timezone label", key="macro_tz_apply") and zone:
            snap.user_timezone = zone
            snap.timezone_status = f"{TIMEZONE_USER_CONFIRMED}: display times interpreted in {zone} (heuristic, not provider-certified)"
            st.session_state[SESSION_MACRO] = snap

    countries_avail = _countries_in_snapshot(snap)
    default_sel = [c for c in DEFAULT_COUNTRIES if c in countries_avail] or countries_avail[:2]
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        range_mode = st.selectbox("Date filter", ["All dates in snapshot", "Today", "Tomorrow", "This Week", "Custom"])
    with fc2:
        country_pick = st.multiselect("Countries", countries_avail, default=default_sel)
    with fc3:
        importance = st.selectbox("Importance", ["All", "High", "Medium", "Low", "Unknown"])
    if importance == "High":
        st.caption("High filter excludes events with unknown importance (not decoded from CSS).")
    custom_start = custom_end = None
    if range_mode == "Custom":
        cc1, cc2 = st.columns(2)
        custom_start = cc1.date_input("From", value=date.today())
        custom_end = cc2.date_input("To", value=date.today())
    filtered = filter_events(
        snap.events,
        countries=country_pick or None,
        importance=importance,
        range_mode="All dates in snapshot" if range_mode == "All dates in snapshot" else range_mode,
        range_start=custom_start,
        range_end=custom_end,
        today=date.today(),
    )
    if not filtered:
        st.warning("No matching rows in this snapshot — not the same as all-clear event risk.")

    rows = []
    for e in filtered[:500]:
        rows.append(
            {
                "Date/time (as captured)": e.display_datetime_label(),
                "Country": e.country,
                "Event": e.event,
                "Reference": e.reference or "—",
                "Importance": e.importance or "Unknown",
                "Actual": e.actual or "—",
                "Consensus": e.consensus or "—",
                "Previous": e.previous or "—",
                "TE forecast": e.provider_forecast or "—",
                "Source": e.source_url,
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if len(filtered) > 500:
        st.caption(f"Showing first 500 of {len(filtered)} matching rows.")


def render_watchlist_macro_panel(research_label: str) -> None:
    snap = get_macro_snapshot()
    st.markdown("#### Macro context (imported calendar)")
    country = WATCHLIST_COUNTRY.get(research_label, "india")
    if snap is None:
        st.caption("Macro calendar not imported — use Global News & Events → Macro calendar section.")
        return
    if snap.is_stale_for_imminent():
        st.caption(
            f"Snapshot captured {snap.capture_started_at.strftime('%Y-%m-%d %H:%M UTC')} — "
            "**STALE/reference** for imminent-event claims."
        )
    scoped = [e for e in snap.events if e.country == country]
    if not scoped:
        st.info(f"No {country} events in imported snapshot for this filter.")
        return
    if "UNCONFIRMED" in snap.timezone_status.upper() and not snap.user_timezone:
        upcoming = scoped[:5]
        st.caption("Calendar imported; **timing unconfirmed** — see Macro calendar on Global News for full table.")
        for e in upcoming:
            st.write(f"• {e.display_datetime_label()} — {e.event} ({e.category})")
            st.link_button("TE source", e.source_url, use_container_width=False)
        return
    st.caption(f"Country scope: {country} · timezone status: {snap.timezone_status}")
    for e in scoped[:5]:
        st.write(f"• {e.display_datetime_label()} — {e.event}")
        st.link_button("TE source", e.source_url, use_container_width=False)
