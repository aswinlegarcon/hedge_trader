# Spec handoff — Phase 1 → Phase 2

**Project:** NIFTY Signal Lab (`hedge_trader`) · **Phase 1 completed:** 2026-11-09 · **Commit:** `main` @ Phase 1 MVP
**Original brief:** [ORIGINAL_SPEC.md](ORIGINAL_SPEC.md) · **Research facts:** [RESEARCH.md](RESEARCH.md) · **Layout:** [ARCHITECTURE.md](ARCHITECTURE.md)

Purpose of this document: give whoever writes the Phase 2 spec a precise picture of what exists,
what was deliberately deferred, which interfaces to build against, and which decisions are open.

---

## 1. Requirement traceability (brief section → status)

Legend: ✅ done · 🟡 partial / placeholder · ⏳ deferred to a later phase · ❌ not started

| Brief § | Requirement | Status | Where | Notes |
|---|---|---|---|---|
| 1 | Capital ₹1,00,000, DD ₹10,000, ₹1,000–₹2,000 per position | ✅ | `nifty_lab/config.py` `RiskConfig` | Env-overridable via `NSL_*`. Validated on load. |
| 1 | **No live trades in v1** | ✅ | `brokers/base.py` (no order methods), `AppConfig.live_trading_enabled=False` | Enforced by absence of code, not a flag check. |
| 2 | Ecosystem research with sources & dates | ✅ | `docs/RESEARCH.md` | SEBI circular full text not fetched (secondary sources used). |
| 3 | Stack: Py 3.12, Streamlit, pandas, numpy, Plotly, SQLite, pytest, env creds, modular brokers | ✅ | repo root | Actual versions: Streamlit 1.67, pandas 3.1, numpy 2.5, plotly 7.1, scipy 1.18. |
| 3 | Works without paid APIs (synthetic + CSV) | ✅ | `data/sample.py`, `data/csv_loader.py` | Synthetic banded on every page and in CSV header. |
| 3 | Live read-only connectivity later | ⏳ Phase 2 | `brokers/kite.py`, `brokers/kotak.py` | Status-only stubs; `historical()`/`option_chain()` raise `NotImplementedError`. |
| 4 | Indian market tiles (NIFTY, BANKNIFTY, NXT50, VIX, sectors, breadth) | 🟡 | `pages/01_Market_Overview.py` | Only NIFTY populated from the active dataset; others show `NO DATA`. |
| 4 | Global tiles (S&P, Nasdaq, UST, USD/INR, Brent, Gold) | 🟡 | same | All `NO DATA`. Source selection is a Phase 2 decision (see §5). |
| 4 | News intelligence module | ⏳ Phase 2 | `pages/02_Global_News_and_Events.py` | Lists candidate official sources; manual event calendar in session state feeds Signal Monitor event-risk warnings. |
| 5 | SMA 20/50/200, EMA 9/21, RSI 14, MACD, ATR 14, Bollinger, VWAP, S/R, volume, vol regime | ✅ | `indicators/core.py` | Wilder smoothing (SMA-seeded) for RSI/ATR. VWAP only meaningful on intraday bars (none in v1). |
| 5 | Beginner explanations | ✅ | `indicators/explain.py` | Shown on TA page and Learning Center. |
| 5 | Per-signal: regime, values, passed, failed, timestamp, reasons to avoid | ✅ | `signals/engine.py` → `SignalReport` | No confidence percentages anywhere. |
| 6 | Bull put, bear call, iron condor, protective put, covered call | ✅ | `options/strategies.py` | Iron condor labelled research-only. |
| 6 | Contracts/expiry, bid/ask, strikes, net credit, max P/L, breakevens, R:R, costs, DTE, IV, Greeks, payoff | ✅ | `options/payoff.py`, `options/pricing.py`, `pages/04_…` | Greeks need an IV per leg (manual or theoretical). |
| 6 | Margin requirement | 🟡 | analyzer page | Reported as `INSUFFICIENT DATA`; needs broker margin API (Phase 2). |
| 6 | Reject if max loss > budget; executable-side quotes; costs/slippage | ✅ | `risk/budget.py`, `options/costs.py` | Sell at bid / buy at ask. Costs: Zerodha schedule incl. STT 0.15% (from 2026-04-01). Exit costs estimated at entry premium. |
| 6 | `INSUFFICIENT DATA` instead of invention | ✅ | throughout | Missing quote → `KeyError("… INSUFFICIENT DATA")`. |
| 7 | Signal outputs + 7 required disclosures | ✅ | `signals/engine.py`, `pages/05_Signal_Monitor.py` | Max possible loss is linked to the analyzer (strategy-dependent). |
| 8 | Position sizing, exposure, max-loss, drawdown, concentration, correlation, liquidity, event-risk, reports, configurable budget | ✅ / 🟡 | `risk/`, `pages/06_…`, `pages/08_…` | Correlation check is a rule (NIFTY+BANKNIFTY flagged), not a statistical estimate. Daily/weekly reports are rendered from journal rows, not emailed/scheduled. |
| 9 | Backtesting framework & metrics | ⏳ Phase 3 | `pages/07_Backtesting_Lab.py` | Placeholder only; deliberately shows no numbers. |
| 10 | Paper-trading journal with all listed fields | ✅ | `journal/db.py` | `is_paper=1` enforced; real-account rows rejected. Performance summary: trades, win rate, PF, expectancy, avg win/loss, largest loss. |
| 10 | Daily report & weekly review | ✅ (basic) | `pages/08_…` Reports tab | Text summary + CSV export. |
| 11 | Ten pages | ✅ | `app.py` + `pages/` | `st.navigation` router. |
| 11 | Freshness, connection status, attribution | ✅ | `ui/common.py` `provenance_banner`, Settings page | |
| 12 | No hardcoded keys, no token logging, `.env.example`, secrets git-ignored, read-only, no order code, no secrets in chat, no bypasses, clear errors | ✅ | `.gitignore`, `.env.example`, `config.credential_status()` | Credentials reported only as set/not-set. |
| 13 | Phase 1 deliverables list | ✅ | — | 47 pytest tests pass. |
| 14 | Env inspection, run, screenshot, instructions, final report | ✅ | README, browser-verified | |

---

## 2. What Phase 1 actually ships (inventory)

```
app.py                                  router
pages/01…10_*.py                        ten pages (UI only)
nifty_lab/config.py                     RiskConfig, AppConfig, credential_status()
nifty_lab/contracts.py                  CONTRACTS (NIFTY 65 / BANKNIFTY 30 / FINNIFTY 60 / MIDCPNIFTY 120), expiry helpers
nifty_lab/data/{base,sample,csv_loader}.py
nifty_lab/indicators/{core,explain}.py
nifty_lab/signals/engine.py
nifty_lab/options/{pricing,costs,payoff,strategies}.py
nifty_lab/risk/{budget,portfolio}.py
nifty_lab/journal/db.py                 SQLite: journal_entries, research_notes, signal_log
nifty_lab/brokers/{base,kite,kotak}.py  ReadOnlyBroker ABC + status stubs
nifty_lab/ui/common.py                  sidebar_data_source(), provenance_banner(), charts
tests/ (47 tests)                       indicators, data, options, risk, signals/journal/contracts
data/sample/nifty_synthetic_daily.csv   750 synthetic bars, header comment marks it synthetic
docs/{RESEARCH,ARCHITECTURE,ORIGINAL_SPEC,SPEC_HANDOFF}.md
```

---

## 3. Stable interfaces Phase 2 should build against

### 3.1 `MarketDataset` / `DataProvenance` (`nifty_lab/data/base.py`)
Every data source must return `MarketDataset(df, provenance)` where `df` is a validated OHLCV frame with a
`DatetimeIndex` and `provenance.kind ∈ {SYNTHETIC, IMPORTED_CSV, BROKER_LIVE, UNAVAILABLE}`.
The UI banner, freshness label and all downstream code already consume this. **Add `BROKER_LIVE` producers; do not add new frame shapes.**

### 3.2 `ReadOnlyBroker` (`nifty_lab/brokers/base.py`)
```python
status() -> BrokerStatus
historical(symbol, interval, start, end) -> pd.DataFrame   # OHLCV, DatetimeIndex
option_chain(underlying, expiry) -> pd.DataFrame           # see 3.3
```
There is intentionally **no** `place_order`, `modify_order`, `cancel_order`. Keep it that way in Phase 2.

### 3.3 Quote book contract (`nifty_lab/options/strategies.py`)
Strategy builders take `QuoteBook = Mapping[(option_type: "CE"|"PE", strike: float) -> Quote(bid, ask)]`
plus an optional `ivs` mapping with the same keys. A live option chain only needs to be converted to this
mapping; the payoff/risk/UI stack then works unchanged. Suggested `option_chain()` columns:
`strike, option_type, bid, ask, ltp, volume, oi, iv (optional), expiry, tradingsymbol, lot_size`.

### 3.4 `SignalReport` (`nifty_lab/signals/engine.py`)
`evaluate(df_ind, as_of=None, india_vix=None, event_risk_notes=None)`. Phase 2 should supply real
`india_vix` and event notes from feeds; the engine already changes its "reasons to avoid" accordingly.

### 3.5 Risk gate (`nifty_lab/risk/budget.py`)
`check_position_eligibility(position, risk, open_risk_inr, realised_drawdown_inr) -> EligibilityResult`.
Any new strategy must pass through this; do not bypass it in UI code.

### 3.6 Journal (`nifty_lab/journal/db.py`)
Schema is additive-friendly (`CREATE TABLE IF NOT EXISTS`). If Phase 2 adds columns, add a migration step
in `Journal.__init__` rather than editing `SCHEMA` destructively.

---

## 4. Decisions made in Phase 1 (and why)

| Decision | Rationale | Revisit? |
|---|---|---|
| Own indicator implementations instead of `pandas-ta`/TA-Lib | Zero native deps, full test coverage, exact Wilder definitions | Only if intraday performance becomes an issue |
| Black-Scholes (European) with r=6.5%, q=1.2% defaults | NIFTY options are European, cash-settled; rates are UI-editable | Phase 2: source r from live T-bill/MIBOR if available |
| Exit costs estimated at entry premium | Conservative placeholder; real exit price unknown at entry | Phase 3 backtester should use actual exit fills |
| Lot sizes/costs hard-coded with `verified_on` dates | No live source in v1; dates surface staleness | Phase 2: pull lot size from broker instrument master and diff against `CONTRACTS` |
| Monthly expiry = last Tuesday, holiday-unadjusted | NSE holiday calendar not bundled | Phase 2: load NSE holiday list or broker instrument expiries |
| Signal votes: setup requires regime + all-but-one directional rules + all filters | Keeps WAIT as the default; avoids over-signalling | Tune only with Phase 3 backtest evidence |
| Vol regime from trailing-252 ATR% percentile | Uses only past data; simple to explain | Could add India VIX percentile when live |
| Correlation check is a static rule | No multi-asset history in v1 | Phase 2/3: rolling correlation from real data |
| Manual event calendar in session state | Honest stop-gap until feeds exist | Replace with persisted events table + feeds |
| `st.navigation` router with numeric-prefixed page files | Stable page order and URLs | — |
| Streamlit `width='stretch'` (not `use_container_width`) | Deprecated in Streamlit ≥1.4x | — |

---

## 5. Open questions the Phase 2 spec must answer

1. **Which broker first?** Kite Connect (₹500/mo, well-documented, 3 req/s historical) vs Kotak Neo (plan-dependent, TOTP+MPIN each session). Recommendation: Kite for historical + chains; Kotak as second adapter to prove the abstraction.
2. **Token handling UX.** Kite `access_token` expires 06:00 daily. Where does the daily login happen — guided flow inside Streamlit (redirect URL to localhost), or a CLI helper that writes to `.env`? Token must never be logged or displayed.
3. **Global market data source.** Broker APIs don't carry S&P/Nasdaq/UST/Brent/Gold/USD-INR. Options: a licensed free API (e.g. a public FX/commodities API with clear ToS), or leave `NO DATA` until a source is approved. The spec must name the source and its ToS.
4. **India VIX & breadth.** Kite exposes `INDIA VIX` as an instrument; breadth (advance/decline) needs constituent data — define whether Phase 2 computes it from NIFTY 50 constituents or defers.
5. **News/event feeds.** RBI, SEBI, NSE, Fed and BLS have official pages/RSS. Define: polling cadence, storage (new SQLite table `events`), de-duplication key, and the "fact vs interpretation" rendering rule. Any commercial news source (Reuters, Moneycontrol) needs an explicit licence decision; scraping is out of scope.
6. **Option-chain snapshot persistence.** Should live chains be cached to SQLite/parquet so Phase 3 can backtest on real quotes going forward? (Recommended: yes, append-only, with retrieval timestamp.)
7. **Margin.** Kite has a margin-calculation API for baskets. Decide whether to call it (read-only) to replace `INSUFFICIENT DATA`.
8. **Rate-limit & retry policy.** Kite: quotes 1/s, historical 3/s. Specify backoff and the UI behaviour when throttled (show stale data with a timestamp vs. block).
9. **Lot-size drift detection.** When broker instrument master disagrees with `CONTRACTS`, warn and prefer which?
10. **Secondary markets.** Brief mentions Indian equities and US ETFs. In or out of Phase 2 scope?

---

## 6. Suggested Phase 2 scope and acceptance criteria (draft for the next spec)

**Scope**
- `KiteReadOnly.historical()` and `.option_chain()` via official `kiteconnect`, with rate limiting and typed errors.
- Guided daily login flow (no secret entry in chat; redirect to localhost; token kept in memory/`.env`, never logged).
- India VIX tile and live NIFTY/BANKNIFTY/NXT50 tiles with provenance `BROKER_LIVE`.
- Live option chain → `QuoteBook` adapter feeding the existing analyzer; IV from chain or solved via `implied_volatility()`.
- Official event feeds (RBI, SEBI circulars, NSE circulars, FOMC, US CPI, MOSPI CPI) into a persisted `events` table with source, published time, link; fact vs interpretation split.
- Chain snapshot persistence for future backtests.
- Instrument-master check against `CONTRACTS` with warning on mismatch.

**Acceptance criteria**
- With valid Kite credentials, Market Overview shows live NIFTY, BANKNIFTY, NXT50, India VIX with freshness ≤ 1 trading day and `BROKER_LIVE` banner.
- Options Analyzer builds a bull put spread from a live chain with zero manual quote entry, and the risk gate verdict matches a hand calculation.
- Without credentials, every page behaves exactly as in Phase 1 (no regressions; tests still pass).
- No secret value ever appears in logs, UI, or git (grep test for `KITE_API_SECRET`/`access_token` in logs).
- Events page shows ≥ 1 real upcoming RBI or Fed event with source, timestamp and link, and shows nothing when feeds are unreachable (no fabricated items).
- New tests: adapter unit tests with recorded fixtures (no live calls in CI), rate-limiter tests, chain→QuoteBook conversion tests.

**Explicitly out of scope for Phase 2**
- Any order placement, basket creation or GTT.
- Backtesting engine (Phase 3).
- Scheduled/automated paper trading (Phase 4).

---

## 7. Known gaps and risks carried forward

- SEBI Feb-2025 circular verified only through secondary sources; fetch the PDF before any execution design.
- Lot sizes and STT were correct on 2026-11-09; both have changed within the last 12 months and may again.
- Synthetic data drifts from real NIFTY levels; never calibrate rules against it.
- The daily/weekly "reports" are on-demand page renders, not scheduled artefacts.
- `data/journal.db` is git-ignored; there is no backup/export automation beyond the CSV download button.

---

## 8. How to continue

```bash
git clone https://github.com/aswinlegarcon/hedge_trader.git && cd hedge_trader
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m pytest        # 47 tests
streamlit run app.py
```
Commit identity for this repo: `aswinlegarcon <aswinkirubanantham@gmail.com>` (set in repo-local git config).
