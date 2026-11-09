# NIFTY Signal Lab

A read-only, beginner-friendly market-research platform for Indian index options: technical analysis,
transparent rule-based signals, defined-risk option payoff analysis with a hard risk-budget gate, and a
SQLite paper-trading journal.

> **Version 1 places no trades.** There is no order-placement code anywhere in this repository.
> Everything is research, backtesting-ready scaffolding, alerting and paper trading.
> Nothing here is investment advice.

## What works today (Phase 1 MVP)

| Area | Status |
|---|---|
| Streamlit dashboard, 10 pages | ✅ |
| Synthetic NIFTY sample data (clearly labelled) + CSV import with validation | ✅ |
| Candlestick chart with SMA 20/50/200, EMA 9/21, Bollinger, support/resistance | ✅ |
| RSI 14, MACD, ATR 14, realised vol, volatility regime, volume analysis, VWAP (intraday) | ✅ |
| Rule-based signal engine: BULLISH / BEARISH / NEUTRAL SETUP, WAIT, INSUFFICIENT DATA, with every rule shown | ✅ |
| Options analyzer: bull put, bear call, iron condor, protective put, covered call — payoff, max P/L, breakevens, R:R, costs, Greeks, IV | ✅ |
| Risk-budget gate (₹1,000–₹2,000 max contractual loss incl. costs), portfolio cap, drawdown, concentration | ✅ |
| SQLite paper journal, research notes, signal log, daily/weekly report | ✅ |
| 47 automated tests | ✅ |
| Live broker data (Kite / Kotak Neo), news feeds | Phase 2 — status only |
| Backtesting | Phase 3 — placeholder page, no numbers shown |

## Install and run

Requires Python 3.12+.

```bash
git clone https://github.com/aswinlegarcon/hedge_trader.git
cd hedge_trader
python3 -m venv .venv && source .venv/bin/activate     # or: uv venv .venv && source .venv/bin/activate
pip install -r requirements.txt                          # or: uv pip install -r requirements.txt
cp .env.example .env                                     # optional; defaults work without it
streamlit run app.py
```

Open http://localhost:8501. In the sidebar pick **Synthetic sample (demo)** or **Import CSV** and upload
`data/sample/nifty_synthetic_daily.csv` (or your own `date,open,high,low,close,volume` export).

Run the tests:

```bash
python -m pytest
```

Regenerate the synthetic sample:

```bash
python scripts/make_sample_data.py
```

## Pages

1. **Market Overview** — NIFTY tile and chart from the active data source; every other tile says `NO DATA` until a source exists.
2. **Global News & Events** — Phase 2 placeholder; a manual event calendar feeds event-risk warnings.
3. **NIFTY Technical Analysis** — all indicators with beginner explanations and a downloadable table.
4. **Options Strategy Analyzer** — enter bid/ask quotes (or a clearly-labelled theoretical chain), pick a strategy, see payoff, max loss, breakevens, Greeks, costs, and the ELIGIBLE / REJECTED verdict. Save eligible positions to the paper journal.
5. **Signal Monitor** — rules passed/failed, supporting vs contradicting indicators, reasons to avoid, invalidation conditions, hypothetical plan.
6. **Risk Dashboard** — open risk vs cap, drawdown vs limit, exposure by underlying, worst-case equity.
7. **Backtesting Lab** — Phase 3 statement of intent; shows no performance numbers.
8. **Paper Trading Journal** — open/close simulated positions, mistakes & lessons, daily/weekly reports, CSV export.
9. **Learning Center** — indicators, strategies, risk rules, how to read a signal.
10. **Settings & API Connections** — credential presence (never values), contract specs with verification dates, cost schedule, regulatory notes.

## Configuration

Copy `.env.example` to `.env`. Risk budget variables (`NSL_*`) default to ₹1,00,000 capital, ₹10,000 max drawdown,
₹1,000–₹2,000 per position. Broker keys are optional in v1 and are only ever reported as *set / not set*.

**Never paste API secrets, passwords, PINs or OTPs into chat or into the app.** `.env` is git-ignored.

## Data honesty rules

- Synthetic data is banded orange on every page and in the CSV header. It must not be used to judge any strategy.
- Missing quotes, margins, VIX or news produce **INSUFFICIENT DATA**, never an estimate.
- Option fills use executable quotes (sell at bid, buy at ask) and include estimated STT, exchange, SEBI, stamp duty, GST and brokerage.
- A stop-loss never guarantees the exit price; eligibility always uses the theoretical maximum spread loss.

## Contract and cost facts (verified 2026-11-09)

NIFTY lot 65 · BANKNIFTY lot 30 · NIFTY strike step 50 · NIFTY expiry Tuesday (monthly = last Tuesday) · BANKNIFTY monthly only ·
STT 0.15 % on option sell premium (since 2026-04-01) · Kite Connect ₹500/month. Sources and dates: [docs/RESEARCH.md](docs/RESEARCH.md).

## Roadmap

- **Phase 2** — read-only Kite Connect / Kotak Neo market data (official SDKs), India VIX, option chains, official news/event feeds.
- **Phase 3** — event-driven backtester with no look-ahead, realistic costs/slippage, walk-forward, per-regime reporting, honest labelling of approximations.
- **Phase 4** — scheduled paper-trading runs and performance review.
- Live execution: **not planned** without a separate design review and explicit authorization.

## Layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT
