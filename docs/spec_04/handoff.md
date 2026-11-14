# Spec 04 implementation handoff

Status: **IMPLEMENTED — ready for review.** No commits, merges, orders, or funded-paper activation.

## Identity

| Field | Value |
|---|---|
| Baseline | Uncommitted tree after Spec 03 (`spec-03-v1` profile preserved) |
| Date | 2026-11-13 (Asia/Kolkata) |
| Scope | Read-only Upstox V3 candles → `MarketDataset` → existing charts |

## Outcome summary

- Sidebar **Upstox (read-only)** with research labels, optional exact NSE symbol, **5m / daily**, **Load/Refresh** (no import-time I/O).
- Official NSE JSON master (gzip asset), instrument_key resolution with ambiguity handling.
- GET-only transport to `api.upstox.com` + `assets.upstox.com` with timeouts, 1 req/s pacing, auth failure handling.
- Candle normalize/merge (historical + intraday for 5m), drop incomplete bars, extended `DataProvenance` (`instrument_key`, `bar_interval`, `exchange_tz`).
- **Market Overview**, **Technical Analysis**, **Settings** updated for selected symbol/interval; **Signal Monitor** blocks non-NIFTY daily synthetic/CSV voting.
- **Funded-paper qualification unchanged** (still fail-closed via Spec 03 `production_context_blocked`).
- Upstox **CONNECTED** status only after a successful authorized candle fetch (`ACCESS_STATE`).

## Changed / added files

| File | Role |
|---|---|
| `nifty_lab/brokers/upstox_transport.py` | Allowlisted GET transport |
| `nifty_lab/brokers/upstox_instruments.py` | Master cache + resolution |
| `nifty_lab/brokers/upstox_candles.py` | Parse/normalize/merge |
| `nifty_lab/brokers/upstox_market_data.py` | `UpstoxMarketDataService`, token read, `ACCESS_STATE` |
| `nifty_lab/brokers/upstox_errors.py` | Sanitized error types |
| `nifty_lab/brokers/upstox.py` | Status reflects verified fetch |
| `nifty_lab/data/base.py` | Provenance extensions, freshness label |
| `nifty_lab/ui/common.py` | Upstox sidebar, broker banner, signal guard helpers |
| `pages/01_Market_Overview.py` | Selected broker symbol tile |
| `pages/03_NIFTY_Technical_Analysis.py` | Renamed; intraday-aware labels/metrics |
| `pages/05_Signal_Monitor.py` | Blocks unsupported sources |
| `pages/10_Settings_and_API_Connections.py` | Token setup guidance |
| `requirements.txt` | `requests>=2.31` |
| `scripts/upstox_market_data_smoke.py` | Bounded live smoke |
| `tests/test_spec04_upstox.py` | Mocked HTTP + normalization |

Spec 03 files not rolled back.

## Scenario coverage

| Scenario | Test / evidence | Result |
|---|---|---|
| Load watchlist (mocked) | `test_load_dataset_mocked` | PASS |
| Daily completed bars | `load_dataset` + drop incomplete daily | PASS (mock) |
| 5m forming bar excluded | `test_normalize_and_drop_forming_5m` | PASS |
| Ambiguous instrument | UI second-step picker + `find_by_label` | UI/manual |
| Malformed/conflict candles | `test_reject_conflicting_duplicate` | PASS |
| Missing token | smoke `BLOCKED`, UI load error | BLOCKED (no token in env) |
| 401 clears verified | `test_auth_failure_clears_verified` | PASS |
| No secret leakage | sentinel test + mock header check | PASS |
| No unexpected network | `block_socket` autouse in spec04 tests | PASS |
| Signal voting blocked on broker | `supports_nifty_signal_voting` + page stop | PASS |
| Funded paper still blocked | Spec 03 tests unchanged | PASS (66+ prior) |
| Source switch | `_data_source_choice` clears broker dataset | Implemented |

## Verification

**Python:** 3.12.15 (`.venv`)

**Commands:**

```bash
cd /Users/sanjain/Documents/hedge_trader
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/upstox_market_data_smoke.py
```

**Pytest:** **74 passed** (`test_spec04_upstox` 8 + prior 66).

**Live smoke (this run):**

```
BLOCKED: Set UPSTOX_ACCESS_TOKEN in .env locally, then restart the app.
```

No token was configured in the runtime environment used for verification; connectivity is **unverified** until the user sets `UPSTOX_ACCESS_TOKEN` and re-runs smoke or uses Load/Refresh in the app.

**Privacy:** Agent did not open or print `.env`. Token used only via `os.getenv` at runtime/smoke.

## Deferred (unchanged from Spec 03 / out of scope)

- Funded-paper eligibility / reconciled valuation provider
- Per-position risk ceiling confirmation
- OAuth callback server / auto token refresh
- WebSocket quotes, option chains, portfolio/margin APIs
- Spec 03 gate edge cases noted in design (candidate risk NaN, stale save context) — **not repaired** in this slice

## Next smallest task

OAuth redirect helper or CLI token capture **document-only** plus instrument refresh button on Settings — still no orders, no funded-paper unlock.

---

*Stop for review — no live trading integration.*
