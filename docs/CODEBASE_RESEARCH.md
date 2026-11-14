# Codebase research — NIFTY Signal Lab

Researched **2026-11-13** against primary sources in this repository (README, `docs/*`, `nifty_lab/*`, `pages/*`, `tests/*`).  
Companion doc: [RESEARCH.md](./RESEARCH.md) covers **external** ecosystem facts (brokers, NSE, SEBI); this file covers **what the code is and how it fits together**.

---

## 1. Purpose and domain

| Claim | Source |
|---|---|
| **Product name:** NIFTY Signal Lab (`nifty-signal-lab` on PyPI metadata). Git repo folder is `hedge_trader`. | [README.md](../README.md), [pyproject.toml](../pyproject.toml) |
| **Domain:** Read-only market research for **Indian index options**, centered on **NIFTY 50**, with beginner-friendly explanations. | [README.md](../README.md) L3–5, [docs/ORIGINAL_SPEC.md](./ORIGINAL_SPEC.md) L13–26 |
| **Not a live trading bot:** Version 1 places **no orders**; no order-placement code; `live_trading_enabled` is hard-coded `False`. | [README.md](../README.md) L7–8, [nifty_lab/config.py](../nifty_lab/config.py) L62, [nifty_lab/brokers/base.py](../nifty_lab/brokers/base.py) L1–5 |
| **User goals (from original brief):** ₹1L capital, 10% max drawdown, ₹1k–₹2k per-position risk, hedged option-selling research, paper trading and journaling—not gambling or leverage. | [docs/ORIGINAL_SPEC.md](./ORIGINAL_SPEC.md) L17–32 |
| **Phases:** Phase 1 MVP (current) = Streamlit + synthetic/CSV data + full math/risk/signals; Phase 2 = read-only broker data; Phase 3 = backtester; Phase 4 = scheduled paper runs. Live execution explicitly not planned without separate review. | [README.md](../README.md) L87–92 |

Despite the repo name `hedge_trader`, the implemented product is a **signal lab / research dashboard**, not an automated hedging execution engine.

---

## 2. High-level architecture

```
streamlit run app.py
        │
        ▼
  app.py (st.navigation) ──► pages/*.py  (UI only — charts, forms, copy)
        │
        └── imports ──► nifty_lab/  (all financial numbers & rules)
```

| Layer | Role | Source |
|---|---|---|
| **Entry** | `app.py` registers 10 `st.Page` routes and runs navigation. | [app.py](../app.py) |
| **UI** | `pages/01_…` through `pages/10_…` — presentation; math stays in `nifty_lab`. | [docs/ARCHITECTURE.md](./ARCHITECTURE.md) L4–6, L24–25 |
| **Core library** | `nifty_lab/` — data, indicators, signals, options, risk, journal, broker stubs, shared UI helpers. | [docs/ARCHITECTURE.md](./ARCHITECTURE.md) L6–16 |
| **Persistence** | SQLite at `data/journal.db` — tables `journal_entries`, `research_notes`, `signal_log` (paper-only, `is_paper = 1`). | [nifty_lab/config.py](../nifty_lab/config.py) L59–75, [nifty_lab/journal/db.py](../nifty_lab/journal/db.py) |
| **Tests** | `tests/` — pytest over indicators, options, risk, signals, data. | [README.md](../README.md) L23, [pyproject.toml](../pyproject.toml) L18–20 |

### Data flow (Phase 1)

1. User selects **synthetic sample** or **CSV import** in the sidebar (via shared UI helpers).
2. `nifty_lab/data` produces a `MarketDataset` with **provenance** (synthetic vs import vs future live).
3. `indicators/core.py` builds an indicator frame **without look-ahead**.
4. `signals/engine.py` evaluates fixed rules → `SignalReport` (passed/failed, avoid reasons, invalidation).
5. Options pages use `options/pricing.py`, `payoff.py`, `strategies.py`, `costs.py` for P/L, Greeks, eligibility.
6. `risk/` gates positions against `RiskConfig`; eligible setups can be saved to the paper journal.

Design invariant: **deterministic code owns every financial number**; missing inputs → `INSUFFICIENT DATA`, not guesses. ([docs/ARCHITECTURE.md](./ARCHITECTURE.md) L23–28)

Cross-page flow: **News & Events** stores user-entered `manual_events` in `st.session_state`; **Signal Monitor** reads high-impact items for event-risk warnings ([pages/02_Global_News_and_Events.py](../pages/02_Global_News_and_Events.py), [pages/05_Signal_Monitor.py](../pages/05_Signal_Monitor.py)).

---

## 3. Tech stack

| Component | Choice | Source |
|---|---|---|
| Language | Python ≥ 3.12 | [README.md](../README.md) L29, [pyproject.toml](../pyproject.toml) L5 |
| Dashboard | Streamlit ≥ 1.38 | [pyproject.toml](../pyproject.toml) L7 |
| Analytics | pandas, numpy, scipy | [pyproject.toml](../pyproject.toml) L8–11 |
| Charts | Plotly | [pyproject.toml](../pyproject.toml) L10 |
| Config | python-dotenv, `NSL_*` env vars | [nifty_lab/config.py](../nifty_lab/config.py), [.env.example](../.env.example) |
| Dev | pytest, ruff (optional) | [pyproject.toml](../pyproject.toml) L16–17 |
| CI | None in repo (no `.github/workflows` as of 2026-11-13) | repository tree |

---

## 4. Package map (`nifty_lab/`)

| Module | Responsibility | Primary files |
|---|---|---|
| `config.py` | `RiskConfig`, `AppConfig`, env loading, credential *presence* checks (never values) | [nifty_lab/config.py](../nifty_lab/config.py) |
| `contracts.py` | Lot sizes, strike steps, expiry rules (dated) | [nifty_lab/contracts.py](../nifty_lab/contracts.py) |
| `data/` | `MarketDataset`, synthetic generator, CSV loader + validation | [nifty_lab/data/](../nifty_lab/data/) |
| `indicators/` | SMA/EMA/RSI/MACD/ATR/Bollinger/VWAP/S&R/volume/regime; `explain.py` for UI copy | [nifty_lab/indicators/](../nifty_lab/indicators/) |
| `signals/` | Rule-based engine → `SignalReport` | [nifty_lab/signals/engine.py](../nifty_lab/signals/engine.py) |
| `options/` | Black-Scholes, IV, Greeks, Indian cost schedule, payoff, strategy builders | [nifty_lab/options/](../nifty_lab/options/) |
| `risk/` | Per-trade eligibility vs budget; portfolio exposure, drawdown, concentration | [nifty_lab/risk/](../nifty_lab/risk/) |
| `journal/` | SQLite: positions, notes, signal log, reports | [nifty_lab/journal/](../nifty_lab/journal/) |
| `brokers/` | `ReadOnlyBroker` ABC; Kite/Kotak **status stubs** for Phase 2 | [nifty_lab/brokers/](../nifty_lab/brokers/) |
| `ui/common.py` | Shared Streamlit widgets, provenance banners, charts | [nifty_lab/ui/common.py](../nifty_lab/ui/common.py) |

### Streamlit pages (user-facing surface)

| # | Page | Typical `nifty_lab` deps |
|---|---|---|
| 1 | Market Overview | `data`, `ui` |
| 2 | Global News & Events | Phase 2 placeholder |
| 3 | NIFTY Technical Analysis | `indicators`, `data` |
| 4 | Options Strategy Analyzer | `options`, `risk`, `journal` |
| 5 | Signal Monitor | `signals`, `indicators` |
| 6 | Risk Dashboard | `risk`, `journal` |
| 7 | Backtesting Lab | Phase 3 placeholder (no performance numbers) |
| 8 | Paper Trading Journal | `journal` |
| 9 | Learning Center | static / explanatory content |
| 10 | Settings & API Connections | `config`, `brokers`, `contracts` |

Page list and titles: [app.py](../app.py) L11–21; narrative: [README.md](../README.md) L55–66.

---

## 5. Configuration and secrets

| Variable group | Purpose | Source |
|---|---|---|
| `NSL_CAPITAL_INR`, `NSL_MAX_DRAWDOWN_INR`, `NSL_RISK_PER_TRADE_*` | Risk budget defaults aligned with original brief | [.env.example](../.env.example), [nifty_lab/config.py](../nifty_lab/config.py) L66–71 |
| `NSL_DB_PATH` | Journal SQLite path | [.env.example](../.env.example) |
| `KITE_*`, `KOTAK_*` | Optional; Phase 2 read-only connectivity; only reported as set/not set in UI | [.env.example](../.env.example), [nifty_lab/config.py](../nifty_lab/config.py) L78+ |

`.env` is gitignored; secrets must not be committed or pasted into chat ([README.md](../README.md) L73).

---

## 6. How to run and maintain

```bash
# From README — primary dev workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
streamlit run app.py    # http://localhost:8501

python -m pytest        # ~47 tests per README
python scripts/make_sample_data.py  # regenerate synthetic CSV
```

Sample OHLCV: [data/sample/nifty_synthetic_daily.csv](../data/sample/nifty_synthetic_daily.csv) (must stay clearly labelled synthetic in UI).

---

## 7. Tests

| Area | Test files |
|---|---|
| Data / CSV | [tests/test_data.py](../tests/test_data.py) |
| Indicators | [tests/test_indicators.py](../tests/test_indicators.py) |
| Options / payoff / costs | [tests/test_options.py](../tests/test_options.py) |
| Risk budget | [tests/test_risk.py](../tests/test_risk.py) |
| Signals, journal, contracts | [tests/test_signals_journal_contracts.py](../tests/test_signals_journal_contracts.py) |

Shared fixtures: [tests/conftest.py](../tests/conftest.py) (adds project root to `sys.path`).

**Count:** 47 test functions — matches [README.md](../README.md) and [SPEC_HANDOFF.md](./SPEC_HANDOFF.md).

---

## 8. Notable patterns (for future work)

1. **Provenance everywhere** — datasets carry kind/source/timestamp; UI shows banners (especially orange for synthetic).
2. **Transparent signals** — no ML probabilities; every rule is listed pass/fail in `SignalReport`; engine requires **`MIN_BARS = 200`** (SMA200 regime) or returns `INSUFFICIENT DATA` ([nifty_lab/signals/engine.py](../nifty_lab/signals/engine.py)).
3. **Risk gate before journal** — max contractual loss including costs must fit ₹1k–₹2k band (configurable); unbounded strategies rejected ([nifty_lab/risk/budget.py](../nifty_lab/risk/budget.py)).
4. **Broker boundary** — `ReadOnlyBroker` has historical/quote hooks but **no** `place_order`; extending to live trade requires new interface and review.
5. **Contract/cost constants** — centralized in `contracts.py` and `options/costs.py` with verification dates; external citations in [RESEARCH.md](./RESEARCH.md).
6. **Streamlit state** — `sidebar_data_source()` sets `active_dataset` / `uploaded_dataset`; `get_journal()` caches a `Journal` in `st.session_state["journal"]`; synthetic OHLCV uses `@st.cache_data` by seed ([nifty_lab/ui/common.py](../nifty_lab/ui/common.py)).
7. **Quote convention** — fills use sell @ bid, buy @ ask; costs from `CostSchedule` ([nifty_lab/options/payoff.py](../nifty_lab/options/payoff.py), [nifty_lab/options/costs.py](../nifty_lab/options/costs.py)).
8. **Gitignored secrets/data** — `.env`, `data/journal.db`, `data/imports/*`, `.streamlit/secrets.toml` ([.gitignore](../.gitignore)).

### Related internal docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — module tree and design rules  
- [SPEC_HANDOFF.md](./SPEC_HANDOFF.md) — spec traceability and Phase 2 inputs  
- [ORIGINAL_SPEC.md](./ORIGINAL_SPEC.md) — full Phase 1 brief  
- [SPEC_02_FINANCIAL_CORE_REVIEW.md](./SPEC_02_FINANCIAL_CORE_REVIEW.md) — financial core review notes (if present on branch)

---

## 9. One-sentence summary

**NIFTY Signal Lab** is a Phase-1, **read-only** Streamlit application that turns NIFTY OHLCV (synthetic or CSV) into explained indicators, auditable rule-based signals, defined-risk options payoff analysis with Indian costs and a strict risk budget, and a SQLite paper-trading journal—deliberately **without** live order placement.
