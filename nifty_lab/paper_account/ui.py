"""Streamlit UI for Paper Account results (read-only)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from nifty_lab.brokers.upstox_transport import RequestsTransport

from .accounting import PaperAccountView, load_paper_account_view
from .broker_overlay import (
    account_fingerprint,
    materialize_overlay,
    refresh_broker_overlay,
    utc_now,
)
from .paths import paper_db_path

_OVERLAY_SESSION_KEY = "paper_broker_overlay_cache"
_OVERLAY_ERROR_KEY = "paper_broker_overlay_error"


def _sync_overlay_session(view: PaperAccountView) -> None:
    fp = account_fingerprint(view)
    cache = st.session_state.get(_OVERLAY_SESSION_KEY)
    if cache is None:
        return
    if fp is None or cache.fingerprint != fp:
        st.session_state.pop(_OVERLAY_SESSION_KEY, None)
        st.session_state.pop(_OVERLAY_ERROR_KEY, None)


def render_paper_account_results(
    *,
    db_path: Path | None = None,
    transport: RequestsTransport | None = None,
    overlay_now=utc_now,
) -> PaperAccountView:
    db_path = db_path or paper_db_path()
    if "paper_results_refresh" not in st.session_state:
        st.session_state["paper_results_refresh"] = 0
    view = load_paper_account_view(db_path)
    st.caption(
        f"Snapshot (read-only): **{view.snapshot_at_utc}** · "
        f"LOCAL PAPER · query_only={'yes' if view.read_only_verified else 'unknown'}"
    )
    st.caption("No trade, mark, funding, or API actions on this page.")

    if st.button("Refresh local snapshot", help="Re-reads the existing Paper database only."):
        st.session_state["paper_results_refresh"] += 1
        st.rerun()

    if view.status == "NOT_INITIALIZED":
        st.warning("**NOT INITIALIZED** — No local Paper execution database found. Nothing was created.")
        for line in view.limitations:
            st.markdown(f"- {line}")
        return view

    if view.status != "OK":
        st.session_state.pop(_OVERLAY_SESSION_KEY, None)
        st.session_state.pop(_OVERLAY_ERROR_KEY, None)
        st.error(f"**{view.status}** — {view.error or 'unavailable'}")
        st.caption("Derived cash, P&L, and equity totals suppressed until reconciliation succeeds.")
        for line in view.limitations:
            st.markdown(f"- {line}")
        return view

    _sync_overlay_session(view)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cash (net of fees)", view.cash_inr)
    c2.metric("Reserved cash", view.reserved_cash_inr)
    c3.metric("Cash available", view.cash_available_inr)
    c4.metric("Realized net", view.realized_net_inr)

    st.markdown(
        f"Reserved risk: **{view.reserved_risk_inr}** INR · "
        f"Fees paid (fills): **{view.fees_paid_total_inr}** · "
        f"Reconciliation: **{view.reconciliation_status}**"
    )

    st.subheader("Portfolio valuation (indicative)")
    if view.portfolio_valuation_status == "UNAVAILABLE_MISSING_MARK":
        st.warning("Portfolio market equity and total P&L **unavailable** — at least one open position lacks a valid stored mark.")
    elif view.stored_mark_equity_inr:
        st.metric("Stored-mark equity (indicative)", view.stored_mark_equity_inr, help="Cash + positions at stored ledger marks only.")
        st.metric("Total P&L after paid entry fees (excl. future exit costs)", view.total_pnl_after_paid_fees_inr)
    st.caption(
        f"Gross unrealized: {view.gross_unrealized_total_inr or 'n/a'} · "
        f"After remaining entry fees: {view.unrealized_after_fees_total_inr or 'n/a'} · "
        f"Remaining entry fees on open books: {view.remaining_entry_fees_inr}"
    )

    if view.positions:
        rows = []
        for p in view.positions:
            rows.append(
                {
                    "Symbol": p.symbol,
                    "Owned qty": p.quantity,
                    "Reserved sell": p.reserved_sell_qty,
                    "Sellable qty": p.sellable_qty,
                    "Avg (INR)": p.avg_price_inr,
                    "Stored mark (INR)": p.mark_price_inr or "—",
                    "Mark provenance": p.mark_provenance,
                    "Gross unrealized (INR)": p.gross_unrealized_inr or "—",
                    "Unrealized after entry fees (INR)": p.unrealized_after_paid_entry_fees_inr or "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        for p in view.positions:
            if p.mark_age_note:
                st.caption(f"{p.symbol}: {p.mark_age_note}")

    if view.recent_orders:
        st.subheader("Recent paper orders (snapshot)")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Order": o.local_id,
                        "Side": o.side,
                        "Status": o.status,
                        "Symbol": o.symbol,
                        "Qty": o.quantity,
                        "Filled": o.filled_qty,
                        "Reserved cash (INR)": o.reserved_cash_inr,
                        "Reserved risk (INR)": o.reserved_risk_inr,
                    }
                    for o in view.recent_orders
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    if view.recent_fills:
        st.subheader("Recent paper fills (snapshot)")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Fill event": f.fill_event_id,
                        "Order": f.local_order_id,
                        "Qty": f.qty,
                        "Price (INR)": f.price_inr,
                        "Fees (INR)": f.fees_inr,
                    }
                    for f in view.recent_fills
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Broker snapshot overlay (indicative)")
    st.caption(
        "Separate from stored ledger marks. Session-only quotes; not execution, risk, or mark-writer input. "
        "Excludes future exit costs — **not net liquidation**. Never labeled BROKER LIVE."
    )
    if st.button(
        "Refresh broker prices",
        help="One batched Upstox quote request for open paper positions (max 10 instruments).",
    ):
        tr = transport or RequestsTransport()
        result = refresh_broker_overlay(view, tr)
        st.session_state.pop(_OVERLAY_ERROR_KEY, None)
        if result.ok and result.cache is not None:
            st.session_state[_OVERLAY_SESSION_KEY] = result.cache
        else:
            st.session_state.pop(_OVERLAY_SESSION_KEY, None)
            st.session_state[_OVERLAY_ERROR_KEY] = result.error or "FETCH_FAILED"
        st.rerun()

    overlay_error = st.session_state.get(_OVERLAY_ERROR_KEY)
    if overlay_error:
        st.error(f"Broker refresh failed: **{overlay_error}**")

    cache = st.session_state.get(_OVERLAY_SESSION_KEY)
    if cache is None:
        st.info("No broker snapshot in this session. Click **Refresh broker prices** to fetch once.")
    else:
        overlay = materialize_overlay(view, cache, now=overlay_now())
        if overlay.positions:
            bro_rows = []
            for b in overlay.positions:
                bro_rows.append(
                    {
                        "Instrument key": b.instrument_key,
                        "Instrument token": b.instrument_token,
                        "Broker price (INR)": b.last_price_inr,
                        "Freshness": b.freshness,
                        "Trade age (s)": "—" if b.trade_age_seconds < 0 else f"{b.trade_age_seconds:.1f}",
                        "Retrieval age (s)": f"{b.retrieval_age_seconds:.1f}",
                        "Position value (INR)": b.position_value_inr,
                        "Gross unrealized (INR)": b.gross_unrealized_inr,
                        "Unrealized after entry fees (INR)": b.unrealized_after_entry_fees_inr,
                    }
                )
            st.dataframe(pd.DataFrame(bro_rows), width="stretch", hide_index=True)
            for b in overlay.positions:
                if b.age_note:
                    st.caption(f"{b.instrument_key}: {b.age_note}")
            if overlay.coverage_note:
                st.warning(overlay.coverage_note)
            elif overlay.portfolio_value_inr:
                st.metric(
                    "Broker-snapshot portfolio value (cash + fresh quotes)",
                    overlay.portfolio_value_inr,
                    help="Requires fresh trade time for every open position at display time.",
                )
                st.caption(
                    f"Broker gross unrealized: {overlay.gross_unrealized_total_inr} · "
                    f"After remaining entry fees: {overlay.unrealized_after_fees_total_inr} · "
                    f"Retrieved: {overlay.fetched_at_utc}"
                )

    st.subheader("Limitations")
    for line in view.limitations:
        st.markdown(f"- {line}")
    return view
