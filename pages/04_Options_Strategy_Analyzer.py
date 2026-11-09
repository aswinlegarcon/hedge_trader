"""Options Strategy Analyzer — defined-risk payoff calculator with risk-budget gate."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nifty_lab.contracts import CONTRACTS, get_contract, next_monthly_expiries, round_to_strike, strike_ladder
from nifty_lab.journal import JournalEntry
from nifty_lab.options import (
    DEFAULT_COSTS,
    DEFAULT_DIV_YIELD,
    DEFAULT_RISK_FREE,
    Quote,
    bear_call_spread,
    bull_put_spread,
    covered_call,
    iron_condor,
    protective_put,
    theoretical_quote_book,
    years_to_expiry,
)
from nifty_lab.risk import check_position_eligibility, max_lots_for_budget
from nifty_lab.ui.common import footer, get_journal, inr, provenance_banner, setup_page, sidebar_data_source

cfg = setup_page("Options Strategy Analyzer")
ds = sidebar_data_source()
provenance_banner(ds)
journal = get_journal(cfg)

st.sidebar.header("Contract")
symbol = st.sidebar.selectbox("Underlying", list(CONTRACTS), index=0)
spec = get_contract(symbol)
st.sidebar.caption(f"Lot size **{spec.lot_size}** · strike step **{spec.strike_interval:g}** · verified {spec.verified_on} · {spec.source}")
lot_size = st.sidebar.number_input("Lot size (override if exchange changed it)", 1, 10_000, spec.lot_size)
expiries = next_monthly_expiries(symbol, date.today(), 3)
expiry = st.sidebar.selectbox("Monthly expiry (nominal, holiday-unadjusted)", expiries, format_func=lambda d: d.strftime("%d %b %Y (%a)"))
dte = (expiry - date.today()).days
st.sidebar.caption(f"{dte} calendar days to expiry")

default_spot = float(ds.last_close) if ds is not None else 24_000.0
spot = st.sidebar.number_input("Underlying spot", 100.0, 200_000.0, round(default_spot, 2), step=spec.strike_interval)
if ds is not None and ds.provenance.is_synthetic:
    st.sidebar.caption("Spot pre-filled from SYNTHETIC data — override with the real level.")

# --- Quote source -----------------------------------------------------------------
st.subheader("1 · Option quotes")
qsrc = st.radio("Quote source", ["Manual bid/ask entry (recommended)", "Theoretical Black-Scholes chain (SYNTHETIC — research only)"], horizontal=True)
r_rate = st.number_input("Risk-free rate (annual)", 0.0, 0.2, DEFAULT_RISK_FREE, 0.005, format="%.3f")
q_rate = st.number_input("Dividend yield (annual)", 0.0, 0.1, DEFAULT_DIV_YIELD, 0.001, format="%.3f")
T = years_to_expiry(dte)

book: dict = {}
ivs: dict | None = None
if qsrc.startswith("Theoretical"):
    st.warning("These are MODEL prices with a flat IV and a synthetic ±2% bid-ask. They are NOT market quotes. Any result below is a research approximation, not an opportunity.", icon="⚠️")
    iv_in = st.slider("Flat implied volatility (annual)", 0.05, 0.60, 0.14, 0.005, format="%.3f")
    ladder = strike_ladder(spot, symbol, 12)
    if T > 0:
        book, ivs = theoretical_quote_book(spot, ladder, T, iv_in, r_rate, q_rate)
    chain = pd.DataFrame([{"strike": k, "CE bid": book[("CE", k)].bid, "CE ask": book[("CE", k)].ask, "PE bid": book[("PE", k)].bid, "PE ask": book[("PE", k)].ask} for k in ladder]) if book else pd.DataFrame()
    with st.expander("Theoretical chain"):
        st.dataframe(chain, width='stretch', hide_index=True)
else:
    st.caption("Enter executable quotes from your broker's option chain (bid = what you receive when selling, ask = what you pay when buying). Leave 0/0 for strikes you did not look up — those strikes will report INSUFFICIENT DATA.")
    atm = round_to_strike(spot, symbol)
    default_rows = [{"type": t, "strike": atm + i * spec.strike_interval, "bid": 0.0, "ask": 0.0, "iv": 0.0} for t in ("PE", "CE") for i in range(-6, 7)]
    edited = st.data_editor(pd.DataFrame(default_rows), num_rows="dynamic", width='stretch', height=300, key="manual_quotes")
    ivs = {}
    for _, row in edited.iterrows():
        try:
            if float(row["bid"]) > 0 or float(row["ask"]) > 0:
                book[(str(row["type"]).upper(), float(row["strike"]))] = Quote(float(row["bid"]), float(row["ask"]))
                if float(row.get("iv", 0)) > 0:
                    ivs[(str(row["type"]).upper(), float(row["strike"]))] = float(row["iv"]) / (100.0 if float(row["iv"]) > 1.5 else 1.0)
        except ValueError as exc:
            st.error(f"Bad quote for {row['type']} {row['strike']}: {exc}")

# --- Strategy ------------------------------------------------------------------------
st.subheader("2 · Strategy")
strategy = st.selectbox("Strategy", ["Bull put credit spread", "Bear call credit spread", "Iron condor (research)", "Protective put", "Covered call"])
lots = st.number_input("Lots", 1, 50, 1)
step = spec.strike_interval
atm = round_to_strike(spot, symbol)
c = st.columns(4)
position = None
err: str | None = None
try:
    if strategy.startswith("Bull put"):
        ss = c[0].number_input("Short put strike", value=atm - 4 * step, step=step)
        ls = c[1].number_input("Long put strike", value=atm - 5 * step, step=step)
        position = bull_put_spread(symbol, expiry.isoformat(), ss, ls, book, int(lots), int(lot_size), ivs)
    elif strategy.startswith("Bear call"):
        ss = c[0].number_input("Short call strike", value=atm + 4 * step, step=step)
        ls = c[1].number_input("Long call strike", value=atm + 5 * step, step=step)
        position = bear_call_spread(symbol, expiry.isoformat(), ss, ls, book, int(lots), int(lot_size), ivs)
    elif strategy.startswith("Iron"):
        pl = c[0].number_input("Long put", value=atm - 6 * step, step=step)
        ps = c[1].number_input("Short put", value=atm - 5 * step, step=step)
        cs = c[2].number_input("Short call", value=atm + 5 * step, step=step)
        cl = c[3].number_input("Long call", value=atm + 6 * step, step=step)
        position = iron_condor(symbol, expiry.isoformat(), ps, pl, cs, cl, book, int(lots), int(lot_size), ivs)
    elif strategy.startswith("Protective"):
        k = c[0].number_input("Put strike", value=atm - 2 * step, step=step)
        uq = c[1].number_input("Underlying units held", 1, 100_000, int(lots) * int(lot_size))
        up = c[2].number_input("Underlying entry price", value=float(spot))
        position = protective_put(symbol, expiry.isoformat(), up, int(uq), k, book, int(lots), int(lot_size), ivs)
    else:
        k = c[0].number_input("Call strike", value=atm + 2 * step, step=step)
        uq = c[1].number_input("Underlying units held", 1, 100_000, int(lots) * int(lot_size))
        up = c[2].number_input("Underlying entry price", value=float(spot))
        position = covered_call(symbol, expiry.isoformat(), up, int(uq), k, book, int(lots), int(lot_size), ivs)
except KeyError as exc:
    err = str(exc)
except ValueError as exc:
    err = str(exc)

st.subheader("3 · Analysis")
if err or position is None:
    st.error(f"INSUFFICIENT DATA — {err or 'no position'}")
    st.stop()

elig = check_position_eligibility(position, cfg.risk, open_risk_inr=journal.open_risk_inr())
mp, ml = position.max_profit(), position.max_loss()
rr = position.reward_to_risk()
bes = position.breakevens()
costs = position.estimated_total_costs()

if elig.eligible:
    st.success(f"ELIGIBLE under risk budget — max loss incl. costs {inr(ml)} is within {inr(cfg.risk.risk_per_trade_min)}–{inr(cfg.risk.risk_per_trade_max)}.")
else:
    st.error("REJECTED by risk budget:\n\n- " + "\n- ".join(elig.reasons))
for w in elig.warnings:
    st.warning(w)

k = st.columns(6)
k[0].metric("Net premium", f"{'credit' if position.is_credit else 'debit'} {inr(abs(position.net_premium))}")
k[1].metric("Max profit (after costs)", inr(mp))
k[2].metric("Max loss (after costs)", inr(ml))
k[3].metric("Reward : risk", f"{rr:.2f}" if rr is not None else "n/a")
k[4].metric("Breakeven(s)", ", ".join(f"{b:,.0f}" for b in bes) or "none")
k[5].metric("Est. costs (open+close)", inr(costs))
st.caption(f"Costs use {DEFAULT_COSTS.source} (verified {DEFAULT_COSTS.verified_on}). Margin requirement: **INSUFFICIENT DATA** — SPAN/exposure margin needs a broker margin API (Phase 2). For defined-risk spreads the margin is typically close to the max loss, but verify with your broker.")

legs_df = pd.DataFrame(
    [
        {"Leg": f"{leg.side.value} {leg.option_type.value}", "Strike": leg.strike, "Bid": leg.quote.bid, "Ask": leg.quote.ask, "Fill (executable)": leg.fill_price, "Qty": leg.quantity, "IV": f"{leg.iv:.1%}" if leg.iv else "n/a", "Expiry": position.expiry}
        for leg in position.legs
    ]
)
st.dataframe(legs_df, width='stretch', hide_index=True)

greeks = position.net_greeks(spot, T, r_rate, q_rate) if T > 0 else None
if greeks:
    g = st.columns(4)
    g[0].metric("Net delta", f"{greeks['delta']:+.1f}")
    g[1].metric("Net gamma", f"{greeks['gamma']:+.4f}")
    g[2].metric("Net theta / day", inr(greeks["theta_per_day"]))
    g[3].metric("Net vega / 1% IV", inr(greeks["vega_per_pct"]))
    st.caption("Greeks from Black-Scholes using each leg's IV. Theta is the expected daily P&L from time decay alone if nothing else moves.")
else:
    st.info("Greeks: INSUFFICIENT DATA — provide an IV for every leg (or use the theoretical chain).")

xs, ys = position.payoff_curve(spot)
fig = go.Figure()
fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="P&L at expiry (after costs)", line=dict(color="#1f77b4", width=2)))
fig.add_trace(go.Scatter(x=xs, y=np.where(ys >= 0, ys, 0), fill="tozeroy", mode="none", fillcolor="rgba(26,152,80,0.25)", showlegend=False))
fig.add_trace(go.Scatter(x=xs, y=np.where(ys < 0, ys, 0), fill="tozeroy", mode="none", fillcolor="rgba(215,48,39,0.25)", showlegend=False))
fig.add_vline(x=spot, line=dict(dash="dash", color="gray"), annotation_text=f"spot {spot:,.0f}")
for b in bes:
    fig.add_vline(x=b, line=dict(dash="dot", color="#555"), annotation_text=f"BE {b:,.0f}", annotation_position="bottom")
fig.update_layout(title=f"{position.name} — expiry payoff ({position.underlying} {position.expiry})", xaxis_title="Underlying at expiry", yaxis_title="P&L (₹)", height=420, margin=dict(l=40, r=40, t=50, b=40))
st.plotly_chart(fig, width='stretch')

per_lot_loss = position.max_loss() / lots
st.caption(f"Position sizing: max loss per lot {inr(per_lot_loss)} → up to **{max_lots_for_budget(per_lot_loss, cfg.risk)} lot(s)** fit the ₹{cfg.risk.risk_per_trade_max:,.0f} budget.")
for n in position.notes:
    st.write("• " + n)

with st.expander("Save to paper-trading journal"):
    thesis = st.text_area("Entry thesis (why this trade, in your own words)")
    target_pct = st.slider("Profit target (% of max profit)", 25, 100, 50)
    planned_exit = st.text_input("Planned exit rule", "Close at target or if index closes beyond short strike; exit 5 days before expiry.")
    if st.button("Record paper position", disabled=not elig.eligible):
        entry = JournalEntry(
            trade_date=date.today().isoformat(),
            instrument=f"{symbol} {position.expiry}",
            strategy=position.name,
            entry_thesis=thesis,
            legs=[{"side": leg.side.value, "type": leg.option_type.value, "strike": leg.strike, "fill": leg.fill_price, "qty": leg.quantity} for leg in position.legs],
            fill_prices={f"{leg.option_type.value}{leg.strike:g}": leg.fill_price for leg in position.legs},
            lots=int(lots),
            quantity=int(lots) * int(lot_size),
            net_premium_inr=position.net_premium,
            max_risk_inr=ml,
            max_profit_inr=mp,
            profit_target_inr=mp * target_pct / 100.0,
            planned_exit=planned_exit,
            data_source=("THEORETICAL quotes" if qsrc.startswith("Theoretical") else "manual quotes") + (f" / {ds.provenance.kind.value}" if ds else ""),
        )
        new_id = journal.add_entry(entry)
        st.success(f"Saved paper position #{new_id}. This is a simulation — no order was placed.")
    if not elig.eligible:
        st.caption("Saving is disabled because the position fails the risk budget.")

footer()
