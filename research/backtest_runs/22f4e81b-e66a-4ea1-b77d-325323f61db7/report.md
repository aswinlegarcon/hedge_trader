# Development backtest (exploratory)

run_id: `22f4e81b-e66a-4ea1-b77d-325323f61db7`
readiness: **EXPLORATORY** — not validated, not Live-ready, not forward PAPER candidate.
rules hash: `d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101`
calendar: **UNVERIFIED**; adjustment: **UNKNOWN**.
costs: illustrative 10bps/side slip and fee — not verified broker tariffs.
baseline B&H: first session after 100-bar warmup open; whole shares with fees in sizing.

## Summary
{
  "closed_trades": 16,
  "wins": 6,
  "losses": 10,
  "breakevens": 0,
  "win_rate": 0.375,
  "win_rate_wilson_95_lo": 0.18480982554752806,
  "win_rate_wilson_95_hi": 0.613593529020652,
  "avg_net_win": "261.36",
  "avg_net_loss": "-243.73",
  "net_expectancy_per_trade": "-54.32",
  "profit_factor": 0.64,
  "net_pnl_inr": "-869.13",
  "modeled_entry_fees_inr": "270.00",
  "modeled_exit_fees_inr": "269.69",
  "modeled_entry_slippage_inr": "270.09",
  "modeled_exit_slippage_inr": "269.63",
  "fees_note": "Fees reported separately; slippage already in fill prices.",
  "modeled_fees_note": "Illustrative 10bps/side; not verified real tariffs.",
  "cash_reconcile_delta_inr": "0.00",
  "turnover_notional_inr": "539668.04",
  "exposure_note": "Daily exposure_pct uses mark close; denominator gross_equity.",
  "signal_opportunities": 16,
  "admission_skips": 0,
  "signals_skipped_while_holding": 2,
  "skipped_exit_session": 16,
  "skipped_halted": 0,
  "initial_cash_inr": "20000.00",
  "final_cash_inr": "19130.87",
  "final_net_liquidation_inr": "19130.87",
  "drawdown": {
    "max_drawdown_inr": "1972.86",
    "max_drawdown_pct": 0.09620023551956934,
    "denominator": "net_liquidation_peak"
  },
  "yearly_development": {
    "2021": {
      "trades": 4,
      "wins": 1,
      "losses": 3
    },
    "2022": {
      "trades": 7,
      "wins": 2,
      "losses": 5
    },
    "2023": {
      "trades": 5,
      "wins": 3,
      "losses": 2
    }
  },
  "halted_new_entries": false,
  "ambiguous_same_bar_exits": 0,
  "boundary_forced_exits": 0
}