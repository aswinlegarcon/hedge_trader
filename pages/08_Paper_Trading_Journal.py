"""Paper Trading Journal — SQLite-backed research & simulated-trade log with reports."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from nifty_lab.journal import JournalEntry
from nifty_lab.ui.common import footer, get_journal, inr, setup_page

cfg = setup_page("Paper Trading Journal")
journal = get_journal(cfg)
st.caption(f"Database: `{cfg.db_path}` · every row is a SIMULATION (is_paper = 1). Real account results are never stored here.")

tab_open, tab_new, tab_closed, tab_notes, tab_reports = st.tabs(["Open paper positions", "New entry", "Closed & lessons", "Research notes", "Reports"])

with tab_open:
    df = journal.entries(status="OPEN")
    if df.empty:
        st.info("No open paper positions. Create one here or from the Options Strategy Analyzer.")
    else:
        show = df[["id", "trade_date", "instrument", "strategy", "market_regime", "signal", "lots", "quantity", "net_premium_inr", "max_risk_inr", "max_profit_inr", "profit_target_inr", "planned_exit", "data_source"]]
        st.dataframe(show, width='stretch', hide_index=True)
        st.markdown("##### Close a position (record simulated outcome)")
        with st.form("close_form"):
            pid = st.selectbox("Position id", df["id"].tolist())
            pnl = st.number_input("Realised P&L (₹, after costs; negative for loss)", value=0.0, step=100.0)
            outcome = st.text_area("What happened")
            mistakes = st.text_area("Mistakes")
            lessons = st.text_area("Lessons learned")
            if st.form_submit_button("Close position"):
                try:
                    journal.close_entry(int(pid), float(pnl), outcome, mistakes, lessons)
                    st.success(f"Closed #{pid}.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

with tab_new:
    with st.form("new_entry"):
        c1, c2, c3 = st.columns(3)
        td = c1.date_input("Trade date", value=date.today())
        instrument = c2.text_input("Instrument", "NIFTY")
        strategy = c3.text_input("Strategy", "Bull Put Spread")
        c4, c5, c6 = st.columns(3)
        regime = c4.selectbox("Market regime", ["BULLISH", "BEARISH", "NEUTRAL", "UNCERTAIN"])
        signal = c5.selectbox("Signal", ["BULLISH SETUP", "BEARISH SETUP", "NEUTRAL SETUP", "WAIT", "INSUFFICIENT DATA"])
        lots = c6.number_input("Lots", 1, 100, 1)
        thesis = st.text_area("Entry thesis")
        c7, c8, c9, c10 = st.columns(4)
        prem = c7.number_input("Net premium ₹ (+credit / -debit)", value=0.0, step=50.0)
        max_risk = c8.number_input("Max risk ₹ (incl. costs)", value=0.0, step=100.0, min_value=0.0)
        max_profit = c9.number_input("Max profit ₹", value=0.0, step=100.0)
        target = c10.number_input("Profit target ₹", value=0.0, step=100.0)
        fills = st.text_input("Hypothetical fill prices (free text, e.g. 'sold 23500PE @ 85 bid, bought 23450PE @ 62 ask')")
        planned_exit = st.text_input("Planned exit")
        if st.form_submit_button("Save paper entry"):
            if max_risk > cfg.risk.risk_per_trade_max:
                st.error(f"Max risk ₹{max_risk:,.0f} exceeds the configured per-trade budget ₹{cfg.risk.risk_per_trade_max:,.0f}. Entry not saved.")
            else:
                eid = journal.add_entry(JournalEntry(trade_date=td.isoformat(), instrument=instrument, strategy=strategy, market_regime=regime, signal=signal, entry_thesis=thesis, fill_prices={"text": fills}, lots=int(lots), net_premium_inr=prem, max_risk_inr=max_risk, max_profit_inr=max_profit, profit_target_inr=target, planned_exit=planned_exit, data_source="manual"))
                st.success(f"Saved paper entry #{eid}.")

with tab_closed:
    df = journal.entries(status="CLOSED")
    if df.empty:
        st.info("No closed paper positions yet.")
    else:
        st.dataframe(df[["id", "trade_date", "closed_at", "instrument", "strategy", "max_risk_inr", "realised_pnl_inr", "outcome_notes", "mistakes", "lessons"]], width='stretch', hide_index=True)
        perf = journal.performance_summary()
        m = st.columns(6)
        m[0].metric("Trades", perf["trades"])
        m[1].metric("Net P&L", inr(perf["net_pnl_inr"]))
        m[2].metric("Win rate", f"{perf['win_rate']:.0%}")
        m[3].metric("Profit factor", "∞" if perf["profit_factor"] == float("inf") else f"{perf['profit_factor']:.2f}")
        m[4].metric("Expectancy / trade", inr(perf["expectancy_inr"]))
        m[5].metric("Largest loss", inr(perf["largest_loss_inr"]))
        st.caption("Simulated results. Paper fills ignore partial fills, queue position and real slippage; expect live results to be worse.")

with tab_notes:
    with st.form("note"):
        title = st.text_input("Title")
        body = st.text_area("Note")
        tags = st.text_input("Tags (comma separated)")
        if st.form_submit_button("Add note") and title.strip():
            journal.add_note(title.strip(), body, tags)
            st.success("Saved.")
    notes = journal.notes()
    if not notes.empty:
        st.dataframe(notes, width='stretch', hide_index=True)
    sig = journal.signal_history()
    if not sig.empty:
        st.markdown("##### Logged signal evaluations")
        st.dataframe(sig, width='stretch', hide_index=True)

with tab_reports:
    all_df = journal.entries()
    now = datetime.now(timezone.utc)
    st.markdown(f"### Daily research report — {date.today().isoformat()}")
    today = all_df[all_df["trade_date"] == date.today().isoformat()] if not all_df.empty else all_df
    open_df = journal.entries(status="OPEN")
    st.write(f"- Paper entries created today: **{len(today)}**")
    st.write(f"- Open paper positions: **{len(open_df)}** · total max risk {inr(journal.open_risk_inr())} (cap {inr(cfg.risk.max_portfolio_risk_pct * cfg.risk.capital)})")
    st.write(f"- Realised paper P&L to date: **{inr(journal.realised_pnl_inr())}**")
    if not open_df.empty:
        st.write("- Positions expiring soonest: " + ", ".join(open_df["instrument"].head(3).tolist()))
    st.markdown("### Weekly performance review (last 7 days)")
    week_ago = (now - timedelta(days=7)).isoformat()
    closed = journal.entries(status="CLOSED")
    wk = closed[closed["closed_at"] >= week_ago] if not closed.empty else closed
    if wk.empty:
        st.write("- No paper positions closed in the last 7 days.")
    else:
        pnl = wk["realised_pnl_inr"].astype(float)
        st.write(f"- Closed: **{len(wk)}** · net **{inr(pnl.sum())}** · wins {int((pnl > 0).sum())} / losses {int((pnl <= 0).sum())}")
        st.write("- Lessons logged: " + "; ".join([x for x in wk["lessons"].fillna("").tolist() if x][:5]) if wk["lessons"].fillna("").str.len().sum() else "- No lessons recorded — write them down!")
    st.download_button("Download full journal CSV", all_df.to_csv(index=False).encode() if not all_df.empty else b"", file_name="paper_journal.csv", mime="text/csv", disabled=all_df.empty)

footer()
