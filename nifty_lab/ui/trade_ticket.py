"""Trade Ticket UI — Paper / Sandbox / Live (Spec 08)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from ..config import PROJECT_ROOT
from ..brokers.upstox_errors import UpstoxError
from ..brokers.upstox_transport import RequestsTransport
from ..execution.broker_close_quote import BrokerCloseQuoteCapture, fetch_broker_close_quote
from ..execution.guard import live_mutations_forbidden
from ..execution.modes import ExecutionMode
from ..execution.paper import submit_paper_entry
from ..execution.paper_cancel import cancel_paper_remainder, confirm_cancel_label, list_paper_order_rows
from ..execution.paper_close import (
    quote_observation_id,
    re_evaluate_paper_close,
    submit_paper_close,
)
from ..execution.preview import build_close_preview, build_preview, confirm_close_preview, confirm_preview
from ..execution.policy import EXECUTION_V1
from ..execution.readiness import check_readiness
from ..execution.types import (
    InstrumentKind,
    OrderSide,
    ProductType,
    QuoteSnapshot,
    TradeCandidate,
)
from ..execution.ledger.store import ExecutionLedger
SESSION_MODE = "execution_mode"
SESSION_PREVIEW = "execution_preview"
SESSION_LEDGER = "execution_ledger"
SESSION_BROKER_CLOSE = "broker_close_quote_v1"
SESSION_CLOSE_SOURCE = "paper_close_quote_source"
CLOSE_SOURCE_BROKER = "broker"
CLOSE_SOURCE_MANUAL = "manual"


def _age_seconds(ts: datetime, *, now: datetime) -> float:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts.astimezone(timezone.utc)).total_seconds()


def _ledger_path(mode: ExecutionMode) -> Path:
    return PROJECT_ROOT / "data" / f"{mode.value.lower()}_execution.db"


def get_ledger(mode: ExecutionMode) -> ExecutionLedger:
    key = f"{SESSION_LEDGER}_{mode.value}"
    if key not in st.session_state:
        st.session_state[key] = ExecutionLedger(_ledger_path(mode), mode=mode)
    return st.session_state[key]


def render_trade_ticket() -> None:
    st.caption(
        f"Policy **{EXECUTION_V1.profile_id}**: ₹{EXECUTION_V1.initial_allocation_inr:,.0f} allocation · "
        f"₹{EXECUTION_V1.per_position_budget_inr:,.0f} per position · "
        f"₹{EXECUTION_V1.stop_new_risk_drawdown_inr:,.0f} stop-new-risk."
    )
    default_mode = st.session_state.get(SESSION_MODE, ExecutionMode.PAPER)
    mode = ExecutionMode(
        st.radio(
            "Execution mode",
            [ExecutionMode.PAPER.value, ExecutionMode.SANDBOX.value, ExecutionMode.LIVE.value],
            index=[ExecutionMode.PAPER, ExecutionMode.SANDBOX, ExecutionMode.LIVE].index(default_mode),
            horizontal=True,
        )
    )
    if mode != st.session_state.get(SESSION_MODE):
        st.session_state.pop(SESSION_PREVIEW, None)
    st.session_state[SESSION_MODE] = mode

    ready = check_readiness(mode)
    if mode == ExecutionMode.LIVE:
        st.warning("**LIVE MONEY** — each order needs your explicit confirm below. Agent did not place live test orders.")
    elif mode == ExecutionMode.PAPER:
        st.info("Paper mode uses the local execution ledger only (no broker order HTTP).")
    if ready.blockers:
        for b in ready.blockers:
            st.caption(f"Readiness: {b}")

    kind = InstrumentKind(
        st.selectbox("Instrument", [InstrumentKind.CASH_STOCK.value, InstrumentKind.CASH_ETF.value, InstrumentKind.NIFTY_OPTION.value])
    )
    c1, c2, c3 = st.columns(3)
    symbol = c1.text_input("Trading symbol / label", "ICICIBANK")
    ikey = c2.text_input("Instrument key", "NSE_EQ|INE090A01021")
    underlying = c3.text_input("Underlying", "ICICI" if "ICICI" in symbol else "NIFTY")
    c4, c5, c6, c7 = st.columns(4)
    qty = int(c5.number_input("Quantity", 1, 10_000, 1))
    limit_px = float(c4.number_input("Limit price ₹", 0.01, 1_000_000.0, 100.0, 0.05))
    stop_ref = float(c6.number_input("Stop reference ₹ (stocks)", 0.0, 1_000_000.0, max(0.01, limit_px * 0.97), 0.05))
    lot = int(c7.number_input("Lot size (options)", 1, 500, 1))
    product = ProductType(st.selectbox("Product", [ProductType.DELIVERY.value, ProductType.INTRADAY.value]))

    bid = float(st.number_input("Quote bid ₹ (manual simulation)", 0.01, 1_000_000.0, max(0.01, limit_px * 0.99), 0.05))
    ask = float(st.number_input("Quote ask ₹ (manual simulation)", 0.01, 1_000_000.0, limit_px, 0.05))
    bid_q = int(st.number_input("Visible bid qty", 0, 1_000_000, 100))
    ask_q = int(st.number_input("Visible ask qty", 0, 1_000_000, 100))
    entry_cost = float(st.number_input("Modeled entry fees ₹ (whole order)", 0.0, 10_000.0, 40.0))
    entry_slippage_pct = float(st.number_input("Modeled entry slippage %", 0.0, 5.0, 0.0, step=0.05)) / 100.0
    st.caption("Entry fees and slippage are LOCAL PAPER simulation — not verified broker pricing.")
    if ask < bid:
        st.error("Quote bid/ask crossed — correct inputs before preview.")
    ack_stop = st.checkbox("I acknowledge protective stop is NOT placed at broker (required for stock live path)")

    quote = QuoteSnapshot(
        bid=bid,
        ask=ask,
        bid_qty=bid_q,
        ask_qty=ask_q,
        instrument_key=ikey,
        evaluated_at=datetime.now(timezone.utc),
        source="manual_ticket_input",
    )
    candidate = TradeCandidate(
        mode=mode,
        kind=kind,
        instrument_key=ikey,
        trading_symbol=symbol,
        underlying=underlying,
        side=OrderSide.BUY,
        quantity=qty,
        limit_price_inr=limit_px,
        product=product,
        stop_reference_inr=stop_ref if kind != InstrumentKind.NIFTY_OPTION else None,
        entry_cost_inr=entry_cost,
        exit_cost_reserve_inr=entry_cost,
        user_ack_stop_not_placed=ack_stop,
        quote=quote,
        lot_size=lot,
    )

    ledger = get_ledger(mode)
    ctx = ledger.portfolio_context()
    st.caption(
        f"Ledger equity ₹{ctx.equity_inr:,.2f} · cash ₹{ctx.cash_inr:,.2f} · open positions {ctx.open_position_count}"
    )

    if mode == ExecutionMode.PAPER:
        st.subheader("Close Paper position")
        holdings = ledger.list_closeable_positions()
        closeable = [h for h in holdings if int(h.get("closeable") or 0) == 1 and int(h["quantity"]) > 0]
        if not closeable:
            st.caption("No closeable Paper holdings with complete metadata.")
        else:
            pick = st.selectbox("Holding", closeable, format_func=lambda h: f"{h['symbol']} · {h['quantity']} @ ₹{h['avg_price']:.2f}")
            holding_kind = InstrumentKind(pick.get("instrument_kind") or InstrumentKind.CASH_STOCK.value)
            holding_fp = f"{pick['instrument_key']}|{int(pick['quantity'])}|{float(pick['avg_price']):.4f}"
            if st.session_state.get("close_holding_fp") != holding_fp:
                st.session_state["close_holding_fp"] = holding_fp
                st.session_state.pop(SESSION_BROKER_CLOSE, None)
                st.session_state.pop("close_preview", None)
            stored_cap = st.session_state.get(SESSION_BROKER_CLOSE)
            if stored_cap and stored_cap.get("holding_key") != pick["instrument_key"]:
                st.session_state.pop(SESSION_BROKER_CLOSE, None)
                stored_cap = None
                st.session_state.pop("close_preview", None)
            cq = int(st.number_input("Close quantity", 1, int(pick["quantity"]), min(1, int(pick["quantity"]))))
            climit = float(st.number_input("Close limit ₹", 0.01, 1_000_000.0, float(pick["avg_price"])))
            exit_fee = float(st.number_input("Modeled exit fees ₹", 0.0, 10_000.0, 10.0))
            slippage_pct = float(st.number_input("Modeled slippage %", 0.0, 5.0, 0.0, step=0.05)) / 100.0
            prev_source = st.session_state.get(SESSION_CLOSE_SOURCE, CLOSE_SOURCE_MANUAL)
            broker_capable = holding_kind in (InstrumentKind.CASH_STOCK, InstrumentKind.CASH_ETF)
            if broker_capable:
                source_label = st.radio(
                    "Close quote source",
                    ["Broker snapshot", "Manual simulation"],
                    index=0 if prev_source == CLOSE_SOURCE_BROKER else 1,
                    horizontal=True,
                    key="paper_close_quote_source_ui",
                )
                close_source = CLOSE_SOURCE_BROKER if source_label == "Broker snapshot" else CLOSE_SOURCE_MANUAL
            else:
                close_source = CLOSE_SOURCE_MANUAL
                st.caption("Broker close quote applies to cash stocks/ETFs only.")
            if close_source != prev_source:
                st.session_state[SESSION_CLOSE_SOURCE] = close_source
                st.session_state.pop(SESSION_BROKER_CLOSE, None)
                st.session_state.pop("close_preview", None)
                stored_cap = None
            else:
                st.session_state[SESSION_CLOSE_SOURCE] = close_source

            broker_capture: BrokerCloseQuoteCapture | None = None
            close_quote: QuoteSnapshot | None = None
            if close_source == CLOSE_SOURCE_BROKER and broker_capable:
                if stored_cap and stored_cap.get("holding_key") == pick["instrument_key"]:
                    broker_capture = stored_cap.get("capture")
                if st.button("Fetch broker close quote", key="fetch_broker_close_quote"):
                    try:
                        cap = fetch_broker_close_quote(
                            pick["instrument_key"],
                            instrument_kind=holding_kind,
                            transport=RequestsTransport(),
                            expected_instrument_token=pick["instrument_key"],
                        )
                        st.session_state[SESSION_BROKER_CLOSE] = {
                            "holding_key": pick["instrument_key"],
                            "capture": cap,
                        }
                        st.session_state.pop("close_preview", None)
                        broker_capture = cap
                    except (UpstoxError, ValueError) as exc:
                        st.session_state.pop(SESSION_BROKER_CLOSE, None)
                        st.session_state.pop("close_preview", None)
                        broker_capture = None
                        st.error(str(exc))
            elif close_source == CLOSE_SOURCE_MANUAL:
                st.session_state.pop(SESSION_BROKER_CLOSE, None)

            pending = dict(ctx.pending_sell_qty_by_instrument).get(pick["instrument_key"], 0)
            sellable = int(pick["quantity"]) - int(pending)
            st.caption(
                f"Owned {int(pick['quantity'])} · reserved for close {pending} · sellable now {sellable}. "
                f"Cumulative realized (Paper) ₹{ledger.cumulative_realized_net():,.2f}."
            )
            now_ui = datetime.now(timezone.utc)
            if close_source == CLOSE_SOURCE_BROKER and broker_capture is not None:
                close_quote = broker_capture.quote
                prov_age = _age_seconds(broker_capture.provider_ts_utc, now=now_ui)
                trade_age = _age_seconds(broker_capture.trade_ts_utc, now=now_ui)
                ret_age = _age_seconds(broker_capture.retrieved_at, now=now_ui)
                st.info(
                    "**LOCAL PAPER** · broker snapshot · simulated sell on **bid** depth · "
                    f"no broker stop/order. Provider age {prov_age:.1f}s · trade age {trade_age:.1f}s · "
                    f"fetched {ret_age:.1f}s ago · bid ₹{close_quote.bid:.2f} × {close_quote.bid_qty}."
                )
            elif close_source == CLOSE_SOURCE_MANUAL:
                cbid = float(st.number_input("Close bid ₹", 0.01, climit, max(0.01, climit * 0.99)))
                cask = float(st.number_input("Close ask ₹ (reference)", climit, climit * 1.1, climit))
                cbid_q = int(st.number_input("Bid depth", 0, 1_000_000, int(pick["quantity"])))
                close_quote = QuoteSnapshot(
                    cbid,
                    cask,
                    cbid_q,
                    cbid_q,
                    pick["instrument_key"],
                    datetime.now(timezone.utc),
                    source="manual_ticket_input",
                )
                st.caption("**Manual simulation** — not a broker snapshot.")
            elif close_source == CLOSE_SOURCE_BROKER:
                st.warning("Fetch broker close quote before preview.")

            close_cand: TradeCandidate | None = None
            if close_quote is not None:
                close_cand = TradeCandidate(
                    mode=ExecutionMode.PAPER,
                    kind=holding_kind,
                    instrument_key=pick["instrument_key"],
                    trading_symbol=pick["symbol"],
                    underlying=pick["underlying"],
                    side=OrderSide.SELL,
                    quantity=cq,
                    limit_price_inr=climit,
                    product=ProductType(pick.get("product") or ProductType.DELIVERY.value),
                    quote=close_quote,
                    lot_size=int(pick.get("lot_size") or 1),
                )
            if close_cand is not None and st.button("Preview Paper close"):
                st.session_state["close_preview"] = build_close_preview(
                    close_cand,
                    ledger.portfolio_context(),
                    exit_fees_inr=exit_fee,
                    slippage_pct=slippage_pct,
                )
            close_t = st.session_state.get("close_preview")
            if close_t and close_cand is not None and close_t.candidate.ticket_identity() == close_cand.ticket_identity():
                st.write(close_t.gate.status.value)
                if close_t.observation_id:
                    st.caption(f"Source observation id `{close_t.observation_id[:12]}…` · reviewed {close_t.reviewed_at.isoformat()}")
                if close_t.gate.allowed and st.button(close_t.confirm_label):
                    ok, msg = confirm_close_preview(
                        close_t, ledger.portfolio_context(), exit_fees_inr=exit_fee, slippage_pct=slippage_pct
                    )
                    if ok:
                        try:
                            r = submit_paper_close(
                                ledger,
                                close_t.candidate,
                                intent_id=close_t.close_intent_id or "",
                                observation_id=close_t.observation_id or quote_observation_id(close_t.candidate.quote),
                                exit_fees_inr=close_t.exit_fees_inr or exit_fee,
                                slippage_pct=close_t.slippage_pct or slippage_pct,
                            )
                            st.success(r.message)
                            st.session_state.pop("close_preview", None)
                        except ValueError as exc:
                            st.error(str(exc))
                    else:
                        st.error(msg)
            elif close_t is not None:
                st.warning("Close inputs changed — request a new preview.")

        st.subheader("Paper orders (local)")
        st.caption("Cancel releases unfilled remainder reservations only — fills and positions are preserved.")
        rows = list_paper_order_rows(ledger)
        if not rows:
            st.info("No paper orders in local ledger.")
        else:
            for row in rows:
                st.write(
                    f"`{row.local_id[:8]}…` **{row.symbol}** · {row.status} · "
                    f"filled {row.filled_qty}/{row.quantity} · reserved cash ₹{row.reserved_cash:,.0f}"
                )
                if row.cancellable:
                    ack = st.checkbox(f"I confirm cancel remainder for {row.symbol}", key=f"cancel_ack_{row.local_id}")
                    if ack and st.button(confirm_cancel_label(row), key=f"cancel_btn_{row.local_id}"):
                        try:
                            msg = cancel_paper_remainder(ledger, row.local_id)
                            st.success(msg)
                        except ValueError as exc:
                            st.error(str(exc))
                if row.side == OrderSide.SELL.value and row.remainder > 0 and row.status == "PARTIALLY_FILLED":
                    st.caption(f"Re-evaluate remainder {row.remainder} with a fresh quote (local simulation).")
                    re_bid = float(st.number_input(f"Re-eval bid ₹ ({row.symbol})", 0.01, 1_000_000.0, row.limit_price, key=f"re_bid_{row.local_id}"))
                    re_depth = int(st.number_input(f"Re-eval bid depth ({row.symbol})", 0, row.remainder, row.remainder, key=f"re_depth_{row.local_id}"))
                    re_fee = float(st.number_input(f"Re-eval exit fees ₹ ({row.symbol})", 0.0, 10_000.0, 5.0, key=f"re_fee_{row.local_id}"))
                    if st.button(f"Re-evaluate Paper remainder ({row.symbol})", key=f"reeval_{row.local_id}"):
                        re_quote = QuoteSnapshot(
                            re_bid, re_bid + 0.5, re_depth, re_depth, row.instrument_key,
                            datetime.now(timezone.utc), source="manual_ticket_input",
                        )
                        try:
                            r = re_evaluate_paper_close(
                                ledger,
                                row.local_id,
                                quote=re_quote,
                                observation_id=quote_observation_id(re_quote),
                                exit_fees_inr=re_fee,
                            )
                            st.success(r.message)
                        except ValueError as exc:
                            st.error(str(exc))
        st.caption("Live/Sandbox broker cancel is not available in this build.")
    else:
        st.caption("Paper order cancel is available in Paper mode only.")

    if st.button("Preview order", type="primary"):
        if ask < bid:
            st.error("Cannot preview with crossed quote.")
        else:
            try:
                st.session_state[SESSION_PREVIEW] = build_preview(
                    candidate, ctx, slippage_pct=entry_slippage_pct
                )
            except ValueError as exc:
                st.error(str(exc))

    ticket = st.session_state.get(SESSION_PREVIEW)
    if ticket is None:
        return
    if ticket.candidate.ticket_identity() != candidate.ticket_identity():
        st.warning("Inputs changed since preview — request a new preview.")
        return

    st.subheader("Preview")
    st.write(ticket.gate.status.value, f"— planned risk ₹{ticket.gate.planned_risk_inr:,.2f}")
    for r in ticket.gate.reasons:
        st.error(r)
    for w in ticket.warnings:
        st.caption(w)
    rq = ticket.candidate.quote
    src_label = (
        f"{rq.source} @ {rq.evaluated_at.strftime('%H:%M:%S UTC')}" if rq else "—"
    )
    entry_slip = ticket.slippage_pct if ticket.slippage_pct is not None else entry_slippage_pct
    st.caption(
        f"Quote source {src_label} · modeled slippage {entry_slip * 100:.2f}% · "
        f"modeled entry fees ₹{ticket.candidate.entry_cost_inr:.2f} · "
        f"confirm expires {ticket.expires_at.strftime('%H:%M:%S UTC')}"
    )

    if ticket.gate.allowed and st.button(ticket.confirm_label):
        ok, msg = confirm_preview(
            ticket,
            ledger.portfolio_context(),
            slippage_pct=entry_slippage_pct,
            entry_cost_inr=entry_cost,
        )
        if not ok:
            st.error(msg)
            return
        if mode == ExecutionMode.PAPER:
            try:
                result = submit_paper_entry(
                    ledger, ticket.candidate, slippage_pct=entry_slippage_pct
                )
                st.success(f"{result.message} (local_id {result.local_id[:8]}…)")
            except ValueError as exc:
                st.error(str(exc))
        elif mode == ExecutionMode.LIVE:
            if live_mutations_forbidden():
                st.error("Live mutation guard active (tests/agent). User may disable NSL_FORBID_LIVE_MUTATIONS locally.")
            else:
                st.warning("Live submit path implemented but not invoked from this session without user token readiness review.")
        else:
            st.error(check_readiness(mode).blockers[0] if check_readiness(mode).blockers else "Sandbox unavailable.")
        st.session_state.pop(SESSION_PREVIEW, None)
