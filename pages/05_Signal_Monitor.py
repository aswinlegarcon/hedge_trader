"""Signal Monitor — every rule, its outcome, and reasons to avoid."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from nifty_lab.signals import evaluate
from nifty_lab.ui.common import footer, get_journal, indicator_frame, provenance_banner, setup_page, sidebar_data_source

cfg = setup_page("Signal Monitor")
ds = sidebar_data_source()
provenance_banner(ds)
if ds is None:
    st.stop()
journal = get_journal(cfg)
ind = indicator_frame(ds.df)

st.sidebar.header("Context inputs")
vix_in = st.sidebar.number_input("India VIX (manual, 0 = unknown)", 0.0, 100.0, 0.0, 0.5, help="Live VIX arrives in Phase 2. Enter today's value from NSE if you know it.")
vix = vix_in if vix_in > 0 else None
events = [f"{e['date']}: {e['event']} ({e['impact']})" for e in st.session_state.get("manual_events", []) if e.get("impact") == "High"]
as_of_options = ind.index[-250:]
as_of = st.sidebar.select_slider("Evaluate as of", options=list(as_of_options), value=as_of_options[-1], format_func=lambda t: t.strftime("%Y-%m-%d"))

report = evaluate(ind, as_of=as_of, india_vix=vix, event_risk_notes=events)

color = {"BULLISH SETUP": "green", "BEARISH SETUP": "red", "NEUTRAL SETUP": "blue", "WAIT": "orange", "INSUFFICIENT DATA": "gray"}[report.signal.value]
st.markdown(f"## :{color}[{report.signal.value}] &nbsp; <span style='font-size:1rem'>regime **{report.regime.value}** · as of **{report.as_of.date() if report.as_of is not None else 'n/a'}** · source {ds.provenance.kind.value}</span>", unsafe_allow_html=True)
st.caption("A signal is a description of current conditions under fixed rules. It is NOT a prediction and NOT a profitable trade.")

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### ✅ Conditions that passed")
    for cnd in report.passed:
        st.write(f"- **{cnd.name}** — {cnd.detail}  `{cnd.direction}`")
with c2:
    st.markdown("#### ❌ Conditions that failed")
    for cnd in report.failed:
        st.write(f"- **{cnd.name}** — {cnd.detail}  `{cnd.direction}`")

direction = {"BULLISH SETUP": "bull", "BEARISH SETUP": "bear"}.get(report.signal.value)
if direction:
    s1, s2 = st.columns(2)
    s1.markdown("#### Supporting indicators")
    for cnd in report.supporting(direction):
        s1.write(f"- {cnd.name}")
    s2.markdown("#### Contradicting indicators")
    contra = report.contradicting(direction)
    for cnd in contra:
        s2.write(f"- {cnd.name}")
    if not contra:
        s2.write("- none at this bar")

st.markdown("#### ⚠️ Reasons to avoid trading")
if report.reasons_to_avoid:
    for r in report.reasons_to_avoid:
        st.write("- " + r)
else:
    st.write("- No rule-based objections at this bar (that is not an endorsement).")

st.markdown("#### Strategy under evaluation & hypothetical plan")
for s in report.strategy_candidates:
    st.write("- " + s)
if report.hypothetical_plan:
    plan = report.hypothetical_plan
    st.write(f"**Entry:** {plan.get('entry')}")
    st.write(f"**Profit exit:** {plan.get('exit_profit')}")
    st.write(f"**Loss exit:** {plan.get('exit_loss')}")
    st.write(f"**1 ATR:** {plan.get('atr')}")
    st.write(f"**Maximum possible loss:** defined by the spread width you choose in the Options Strategy Analyzer, capped by the ₹{cfg.risk.risk_per_trade_max:,.0f} budget. Any position with a larger max loss is rejected there.")
st.markdown("#### Signal becomes invalid when")
for inv in report.invalidation:
    st.write("- " + inv)

st.markdown("#### Indicator values")
vals = {k: (f"{v:,.4f}" if isinstance(v, float) and abs(v) < 10 else (f"{v:,.2f}" if isinstance(v, float) else v)) for k, v in report.indicator_values.items()}
st.dataframe(pd.DataFrame(vals.items(), columns=["indicator", "value"]), hide_index=True, width='stretch')
if report.levels:
    st.write(f"Support: {', '.join(f'{x:,.0f}' for x in report.levels.get('support', [])) or 'none'} · Resistance: {', '.join(f'{x:,.0f}' for x in report.levels.get('resistance', [])) or 'none'}")

if st.button("Log this signal evaluation to the journal"):
    payload = {"values": report.indicator_values, "passed": [c.name for c in report.passed], "failed": [c.name for c in report.failed], "avoid": report.reasons_to_avoid}
    journal.log_signal(str(report.as_of), ds.provenance.symbol, report.signal.value, report.regime.value, payload, ds.provenance.kind.value)
    st.success("Logged.")

with st.expander("Signal history (this bar range, from the selected data)"):
    rows = []
    for ts in ind.index[-60:]:
        rep = evaluate(ind, as_of=ts, india_vix=vix)
        rows.append({"date": ts.date(), "signal": rep.signal.value, "regime": rep.regime.value, "rsi14": round(rep.indicator_values.get("rsi14", float("nan")), 1) if rep.indicator_values.get("rsi14") is not None else None})
    st.dataframe(pd.DataFrame(rows).iloc[::-1], hide_index=True, width='stretch', height=300)

footer()
