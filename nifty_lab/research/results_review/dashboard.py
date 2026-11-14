"""Streamlit rendering for archived results review (read-only)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .config import BROKERAGE_REFERENCE_URL, REVIEW_OUTPUT_ROOT
from .ui_data import build_results_review_view, equity_series_for_chart


def render_archived_results_review(
    *,
    runs_root: Path | None = None,
    review_root: Path | None = None,
) -> dict:
    """Single validated snapshot drives cards, charts and cost tables."""
    view = build_results_review_view(runs_root=runs_root, review_root=review_root)
    books = view.get("books", {})
    diag = view["cost_diagnostics"]

    st.subheader("Archived results review (read-only)")
    st.caption(
        "Sources: corrected development 2021–2023 and independent validation 2024. "
        "No simulation, API refresh, or holdout unlock on this page."
    )

    for label, key in (("Development (2021–2023)", "development"), ("Validation (2024)", "validation")):
        card = view[key]
        with st.expander(f"{label} — run `{card.get('run_id', 'n/a')}`", expanded=key == "validation"):
            if card.get("status") != "OK":
                st.error(f"**{card.get('status')}** — {card.get('error', 'unavailable')}")
                continue
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Net P&L (INR)", card.get("net_pnl_inr"))
            c2.metric("Trades", card.get("closed_trades"))
            c3.metric("Final cash", card.get("final_cash_inr"))
            wr = card.get("win_rate")
            c4.metric(
                "Observed win rate",
                f"{100 * wr:.1f}%" if isinstance(wr, (int, float)) else "n/a",
                help=card.get("win_rate_note"),
            )
            st.markdown(
                f"Profit factor: **{card.get('profit_factor')}** · "
                f"Max DD: **{card.get('max_drawdown_inr')} INR** "
                f"({(card.get('max_drawdown_pct') or 0) * 100:.2f}% of {card.get('drawdown_denominator', 'peak')}) · "
                f"Modeled fees (entry+exit): **{card.get('modeled_fees_entry_inr')}** + **{card.get('modeled_fees_exit_inr')}** · "
                f"Turnover: **{card.get('turnover_notional_inr')}** INR"
            )
            if card.get("baselines"):
                st.json({"baselines": card["baselines"]})
            book = books.get(key)
            series = equity_series_for_chart(book) if book else None
            if series:
                df = pd.DataFrame(series)
                df["net_liquidation_inr"] = pd.to_numeric(df["net_liquidation_inr"])
                st.line_chart(df.set_index("ts")["net_liquidation_inr"], height=220)
            st.caption(f"Reconcile delta: {card.get('reconcile', {}).get('cash_reconcile_delta_inr', 'n/a')} INR")

    st.subheader("Fixed-fill cost sensitivity (diagnostic)")
    st.info(diag["disclaimer"])
    st.caption(f"Diagnostics source: **{diag.get('source')}**")
    if diag.get("artifact_warning"):
        st.warning(diag["artifact_warning"])
    if diag.get("artifact_stale"):
        st.warning("Saved review artifact fingerprints no longer match source runs — economic checks still apply.")

    for book_key, title in (("development", "Development"), ("validation", "Validation 2024")):
        stress = diag.get(book_key)
        if not stress or stress.get("status") != "OK":
            st.caption(f"{title}: cost diagnostics unavailable ({view[book_key].get('error', 'not verified')}).")
            continue
        st.markdown(
            f"**{title}** — turnover `{stress.get('executed_turnover_inr')}` · "
            f"archived net `{stress.get('archived_net_pnl_inr')}` · "
            f"break-even extra ~ **{stress.get('break_even_extra_bps')}** bps"
        )
        rows = [
            {
                "Scenario": sc.get("scenario_id"),
                "Extra cost (INR)": sc.get("extra_cost_inr"),
                "Diagnostic net (INR)": sc.get("diagnostic_net_pnl_inr"),
            }
            for sc in stress.get("scenarios", [])
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader("Data limitations")
    for line in view.get("limitations", []):
        st.markdown(f"- {line}")

    with st.expander("Brokerage reference (not applied to fills)"):
        st.markdown(
            f"Reviewer note only ([Upstox brokerage charges]({BROKERAGE_REFERENCE_URL}), checked 2026-11-13): "
            "brokerage, statutory, exchange and DP components vary by plan and date. "
            "Actual historical tariffs for this account were **not** confirmed in this slice."
        )

    if diag.get("artifact_path") and not diag.get("artifact_warning"):
        st.caption(f"Latest review artifact: `{diag['artifact_path']}` (read-only reference).")
    elif not diag.get("artifact_path"):
        st.caption(
            "No persisted review artifact — table uses in-memory diagnostics validated against sources. "
            f"Optional CLI: `scripts/run_results_cost_review.py` → `{REVIEW_OUTPUT_ROOT}/<review_id>/`."
        )

    return view
