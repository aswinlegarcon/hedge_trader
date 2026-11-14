"""Split-aware simulation (development vs validation-2024)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from .config import (
    DEVELOPMENT_YEARS,
    INITIAL_CASH,
    STRATEGY_ID,
    TIME_EXIT_SESSIONS,
)
from .engine import (
    SimulationResult,
    TradeRecord,
    _d,
    _exit_reference,
    _max_shares,
    _net_liquidation,
    _planned_stop_loss,
    _signal_rule,
    SignalRecord,
    EquityPoint,
)
from .indicators import ema_series
from .money import adverse_buy_fill, adverse_sell_fill, modeled_fee
from .config import money_quantize
from .validate import validate_development_frame


@dataclass(frozen=True)
class SplitConfig:
    split_id: str
    context_years: tuple[int, ...]
    evaluation_years: tuple[int, ...]
    record_equity_only_evaluation: bool

    @staticmethod
    def development() -> SplitConfig:
        return SplitConfig(
            split_id="development",
            context_years=DEVELOPMENT_YEARS,
            evaluation_years=DEVELOPMENT_YEARS,
            record_equity_only_evaluation=False,
        )

    @staticmethod
    def validation_2024() -> SplitConfig:
        from .config import CONTEXT_YEARS_VALIDATION, EVALUATION_YEARS_VALIDATION

        return SplitConfig(
            split_id="validation-2024",
            context_years=CONTEXT_YEARS_VALIDATION,
            evaluation_years=EVALUATION_YEARS_VALIDATION,
            record_equity_only_evaluation=True,
        )


def _year(ts) -> int:
    return pd.Timestamp(ts).year


def _eval_indices(bars: pd.DataFrame, years: tuple[int, ...]) -> set[int]:
    return {i for i, ts in enumerate(bars.index) if _year(ts) in years}


def simulate_split(df: pd.DataFrame, split: SplitConfig) -> SimulationResult:
    err = validate_development_frame(df)
    if err:
        raise ValueError(err)
    if df.empty:
        return SimulationResult(strategy_id=STRATEGY_ID)
    bars = df.sort_index()
    n = len(bars)
    eval_idx = _eval_indices(bars, split.evaluation_years)
    last_eval_i = max(i for i in eval_idx if _year(bars.index[i]) in split.evaluation_years)

    closes = [float(x) for x in bars["close"]]
    ema20 = ema_series(closes, 20)
    ema50 = ema_series(closes, 50)
    volumes = [float(x) for x in bars["volume"]]

    cash = INITIAL_CASH
    qty = 0
    entry_fill = Decimal("0")
    stop = Decimal("0")
    target = Decimal("0")
    entry_idx: int | None = None
    entry_fee_paid = Decimal("0")
    entry_raw_open_stored: Decimal | None = None
    peak_net = INITIAL_CASH
    halt_entries = False
    result = SimulationResult(strategy_id=STRATEGY_ID)
    total_fees = Decimal("0")
    turnover = Decimal("0")
    pending: dict | None = None
    candidate_seq = 0
    entered_eval = False

    for i in range(n):
        ts = bars.index[i]
        in_eval = i in eval_idx
        if in_eval and not entered_eval:
            entered_eval = True
            pending = None

        row = bars.iloc[i]
        o, h, l, c = _d(row["open"]), _d(row["high"]), _d(row["low"]), _d(row["close"])
        exited_today = False

        if pending and pending["entry_index"] == i:
            if i not in eval_idx:
                pending = None
            else:
                stop_sig = pending["stop"]
                raw_open = o
                entry_fill = adverse_buy_fill(raw_open)
                if raw_open <= stop_sig or entry_fill <= stop_sig or entry_fill <= 0:
                    result.admission_skips += 1
                    result.signals.append(
                        SignalRecord(
                            str(pending["signal_ts"]),
                            "SKIP",
                            "INVALID_ENTRY_VS_STOP",
                            pending["candidate_id"],
                        )
                    )
                else:
                    shares = _max_shares(cash, entry_fill, stop_sig)
                    if shares <= 0:
                        result.admission_skips += 1
                        result.signals.append(
                            SignalRecord(
                                str(pending["signal_ts"]),
                                "SKIP",
                                "INSUFFICIENT_CASH_OR_RISK",
                                pending["candidate_id"],
                            )
                        )
                    else:
                        buy_notional = Decimal(shares) * entry_fill
                        fee = modeled_fee(buy_notional)
                        cash = money_quantize(cash - buy_notional - fee)
                        qty = shares
                        stop = stop_sig
                        r = entry_fill - stop
                        target = money_quantize(entry_fill + Decimal(2) * r)
                        entry_idx = i
                        entry_fee_paid = fee
                        entry_raw_open_stored = raw_open
                        total_fees += fee
                        turnover += buy_notional
                pending = None

        if qty > 0 and entry_idx is not None and in_eval:
            exit_ref, reason, amb = _exit_reference(
                open_p=o, high_p=h, low_p=l, stop=stop, target=target
            )
            sessions_open = i - entry_idx + 1
            if exit_ref is None and sessions_open >= TIME_EXIT_SESSIONS:
                exit_ref, reason = c, "TIME"
            if i == last_eval_i and exit_ref is None:
                exit_ref, reason = c, "SPLIT_END"
                result.boundary_forced_exits += 1
            if exit_ref is not None:
                if amb:
                    result.ambiguous_same_bar += 1
                sell_fill = adverse_sell_fill(exit_ref)
                notional = Decimal(qty) * sell_fill
                fee = modeled_fee(notional)
                slip_amt = money_quantize(Decimal(qty) * (exit_ref - sell_fill))
                cash = money_quantize(cash + notional - fee)
                total_fees += fee
                turnover += notional
                planned_risk = _planned_stop_loss(qty, entry_fill, stop)
                entry_cost = Decimal(qty) * entry_fill + entry_fee_paid
                exit_proceeds = notional - fee
                trade_pnl = money_quantize(exit_proceeds - entry_cost)
                result.trades.append(
                    TradeRecord(
                        entry_ts=str(bars.index[entry_idx]),
                        exit_ts=str(ts),
                        qty=qty,
                        entry_raw_open=str(entry_raw_open_stored),
                        entry_fill=str(entry_fill),
                        exit_raw_reference=str(exit_ref),
                        exit_fill=str(sell_fill),
                        stop=str(stop),
                        target=str(target),
                        planned_risk_inr=str(planned_risk),
                        entry_fee_inr=str(entry_fee_paid),
                        exit_fee_inr=str(fee),
                        entry_slippage_inr=str(
                            money_quantize(Decimal(qty) * (entry_fill - entry_raw_open_stored))
                        ),
                        exit_slippage_inr=str(slip_amt),
                        net_pnl_inr=str(trade_pnl),
                        exit_reason=reason,
                    )
                )
                qty = 0
                entry_idx = None
                entry_fee_paid = Decimal("0")
                entry_raw_open_stored = None
                exited_today = True

        if in_eval:
            net_eq = _net_liquidation(cash, qty, c)
            gross_eq = money_quantize(cash + Decimal(qty) * c)
            peak_net = max(peak_net, net_eq)
            if not halt_entries:
                if INITIAL_CASH - net_eq >= Decimal("2000"):
                    halt_entries = True
                elif peak_net - net_eq >= Decimal("2000"):
                    halt_entries = True
            exposure = float(Decimal(qty) * c / gross_eq) if gross_eq > 0 and qty else 0.0
            result.equity_curve.append(
                EquityPoint(str(ts), str(cash), str(gross_eq), str(net_eq), str(round(exposure, 6)))
            )

        if not in_eval or i >= last_eval_i:
            if in_eval and i == last_eval_i and _signal_rule(i, c=c, l=l, ema20=ema20, ema50=ema50, volumes=volumes):
                candidate_seq += 1
                result.signals.append(
                    SignalRecord(str(ts), "SKIP", "NO_NEXT_SESSION", f"cand-{candidate_seq}")
                )
                result.opportunity_count += 1
            continue

        if exited_today:
            if _signal_rule(i, c=c, l=l, ema20=ema20, ema50=ema50, volumes=volumes):
                result.skipped_exit_session += 1
                candidate_seq += 1
                result.signals.append(
                    SignalRecord(str(ts), "SKIP", "EXIT_SESSION", f"cand-{candidate_seq}")
                )
                result.opportunity_count += 1
            continue

        rule = _signal_rule(i, c=c, l=l, ema20=ema20, ema50=ema50, volumes=volumes)

        if qty > 0:
            if rule:
                result.skipped_while_holding += 1
                candidate_seq += 1
                result.opportunity_count += 1
                result.signals.append(
                    SignalRecord(str(ts), "SKIP", "POSITION_OPEN", f"cand-{candidate_seq}")
                )
            continue

        if halt_entries:
            if rule:
                result.skipped_halted += 1
                candidate_seq += 1
                result.opportunity_count += 1
                result.signals.append(SignalRecord(str(ts), "SKIP", "HALTED", f"cand-{candidate_seq}"))
            continue

        if pending is not None:
            continue

        if not rule:
            continue

        candidate_seq += 1
        cid = f"cand-{candidate_seq}"
        result.opportunity_count += 1

        next_i = i + 1
        if next_i >= n or next_i not in eval_idx:
            result.signals.append(SignalRecord(str(ts), "SKIP", "NO_NEXT_SESSION", cid))
            continue

        result.signals.append(SignalRecord(str(ts), "OPPORTUNITY", "PULLBACK", cid))
        pending = {"entry_index": next_i, "stop": l, "signal_ts": ts, "candidate_id": cid}

    result.halted_new_entries = halt_entries
    result.total_fees_inr = str(money_quantize(total_fees))
    result.turnover_notional_inr = str(money_quantize(turnover))
    return result


def simulate_development(df: pd.DataFrame) -> SimulationResult:
    return simulate_split(df, SplitConfig.development())
