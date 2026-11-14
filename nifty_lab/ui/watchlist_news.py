"""Streamlit helpers for watchlist news panel (Spec 06)."""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from ..brokers.upstox_transport import RequestsTransport
from ..news import UpstoxNewsClient, refresh_watchlist_news, resolve_watchlist_instrument_keys
from ..news.snapshot import NewsArticle, NewsSnapshot, news_selection_id
from ..research.watchlist_board import WatchlistRefreshBundle

SESSION_SNAPSHOT = "watchlist_news_snapshot"
SESSION_FAILED_AT = "watchlist_news_failed_at"
SESSION_CACHED_REFERENCE = "watchlist_news_cached_reference"


def invalidate_news_if_keys_changed(keys: list[str]) -> None:
    snap: NewsSnapshot | None = st.session_state.get(SESSION_SNAPSHOT)
    if snap is None:
        return
    if news_selection_id(keys) != snap.selection_id:
        st.session_state.pop(SESSION_SNAPSHOT, None)


def _store_failure_prior(snap: NewsSnapshot | None) -> None:
    if snap is not None and snap.articles:
        st.session_state[SESSION_CACHED_REFERENCE] = snap


def run_refresh_news(bundle: WatchlistRefreshBundle | None, *, page_number: int = 1) -> NewsSnapshot | None:
    client = UpstoxNewsClient(transport=RequestsTransport())
    rows, err = resolve_watchlist_instrument_keys(client.transport, bundle=bundle)
    keys = [r.instrument_key for r in rows]
    invalidate_news_if_keys_changed(keys)
    existing = st.session_state.get(SESSION_SNAPSHOT) if page_number > 1 else None
    prior = st.session_state.get(SESSION_SNAPSHOT)
    snap = refresh_watchlist_news(client, keys, page_number=page_number, existing=existing)
    if err and not keys:
        st.error(err)
        return None
    if snap.refresh_failed:
        _store_failure_prior(prior)
        st.session_state[SESSION_FAILED_AT] = datetime.now(timezone.utc).isoformat()
        st.error(f"News refresh failed: {snap.failure_message}")
        st.session_state.pop(SESSION_SNAPSHOT, None)
        return snap
    st.session_state[SESSION_SNAPSHOT] = snap
    st.session_state.pop(SESSION_FAILED_AT, None)
    return snap


def get_snapshot() -> NewsSnapshot | None:
    return st.session_state.get(SESSION_SNAPSHOT)


def articles_for_key(snap: NewsSnapshot, instrument_key: str, *, limit: int = 5) -> list[NewsArticle]:
    if instrument_key and instrument_key not in snap.requested_keys:
        return []
    out = [a for a in snap.articles if instrument_key in a.instrument_keys]
    return out[:limit]


def render_news_panel(snap: NewsSnapshot | None, instrument_key: str | None = None) -> None:
    cached = st.session_state.get(SESSION_CACHED_REFERENCE)
    if snap is None:
        if cached:
            st.warning(
                "Previous cached news reference only — not freshly checked. "
                f"Original retrieval {cached.retrieved_at.strftime('%Y-%m-%d %H:%M UTC')}."
            )
        else:
            st.caption("Company news: NOT CHECKED (Upstox instrument_keys). Macro/scheduled events NOT CHECKED.")
        return
    stale_lbl = " · cached news snapshot — refresh to check for updates" if snap.is_stale() else ""
    st.caption(
        f"Upstox company news checked at {snap.retrieved_at.strftime('%Y-%m-%d %H:%M UTC')}; "
        f"provider recent-history window (7d heuristic); macro/events NOT CHECKED{stale_lbl}"
    )
    if snap.has_more_pages and snap.page_number < 2:
        st.caption("More results may exist — use Load next page (one additional request).")
    if instrument_key:
        state = snap.per_key_state.get(instrument_key, "COVERAGE UNKNOWN")
        arts = articles_for_key(snap, instrument_key)
        st.write(f"**Coverage:** {state}")
        if not arts:
            if state == "NO RECENT ARTICLES":
                st.info("No recent articles in provider response — not the same as no event risk.")
            elif state == "COVERAGE UNKNOWN":
                st.info("Coverage unknown for this key in the last response.")
            else:
                st.info("No displayable articles for this instrument after validation.")
            return
        for a in arts:
            pub_ist = a.published_at.astimezone()
            st.markdown(f"**{a.heading}**")
            st.caption(f"Published {pub_ist.strftime('%Y-%m-%d %H:%M %Z')} · host `{a.host}` · {a.source_label}")
            if a.summary_excerpt:
                st.write(f"_Provider summary (excerpt):_ {a.summary_excerpt}")
            st.link_button("Open source article", a.url, use_container_width=False)
    else:
        st.dataframe(
            [
                {
                    "Heading": a.heading,
                    "Published (UTC)": a.published_at.strftime("%Y-%m-%d %H:%M"),
                    "Host": a.host,
                    "Keys": ", ".join(a.instrument_keys),
                }
                for a in snap.articles[:50]
            ],
            width="stretch",
            hide_index=True,
        )


def render_watchlist_news_section(bundle: WatchlistRefreshBundle | None = None) -> NewsSnapshot | None:
    st.subheader("Watchlist company news (Upstox)")
    st.caption("Manual refresh only · category fixed to instrument_keys · max 4 keys · no holdings/positions.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Refresh news", type="primary"):
            run_refresh_news(bundle, page_number=1)
    with c2:
        snap = get_snapshot()
        if snap and snap.has_more_pages and snap.page_number < 2:
            if st.button("Load next page"):
                run_refresh_news(bundle, page_number=2)
    snap = get_snapshot()
    render_news_panel(snap)
    return snap
