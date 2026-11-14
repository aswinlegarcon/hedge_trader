# Spec 03 implementation handoff

Status: **IMPLEMENTED — ready for in-house review.** No commit, merge, live integration, or broker connectivity performed.

## Implementation identity

| Field | Value |
|---|---|
| Agent | Cursor in-house agent (Composer) |
| Start revision | `d6af5451c6c224a0a2e9b468741d27e7d94a1af8` |
| Final diff basis | working tree vs start (uncommitted) |
| Date | 2026-11-13 (Asia/Kolkata) |
| Pre-existing changes preserved | `docs/CODEBASE_RESEARCH.md`, `docs/spec_03/*` package (authoring), prior `docs/SPEC_02*` / historical docs untouched |

## Outcome summary

- Active research profile **`spec-03-v1`**: ₹20,000 capital, ₹2,000 total loss ceiling, **no** minimum position risk, **unconfirmed** per-position ceiling (`risk_per_trade_max = None`).
- **Upstox-only** offline broker registry; Kite/Kotak modules **removed** from runtime (`kite.py`, `kotak.py` deleted).
- **Tri-state** funded-paper gate (`ELIGIBLE` / `REJECTED` / `INSUFFICIENT DATA`) via `FundedPaperContext`; no default-zero drawdown bypass.
- Production UI paths use `production_context_blocked` / `context_for_production_save` → qualification stays **INSUFFICIENT DATA** until reconciled valuation exists.
- Options analyzer still shows educational payoff; funded-paper save uses `try_record_funded_paper` with save-time recheck.
- Manual journal entries labelled `unqualified-manual`; legacy open positions block qualification.
- Legacy `NSL_*` env presence sets `legacy_env_conflict` (value-free message); does not change `.env`.

## Changed files (final line anchors approximate)

| File | Lines (end) | Change |
|---|---|---|
| `nifty_lab/config.py` | 146 | Spec 03 profile, Upstox credentials, legacy conflict, defaults 20k/2k |
| `nifty_lab/risk/context.py` | 103 | `FundedPaperContext`, `EligibilityStatus`, test/production builders |
| `nifty_lab/risk/budget.py` | 183 | Tri-state gate, remaining downside, no min-risk nag |
| `nifty_lab/risk/recording.py` | 44 | Save-time recheck, production context factory |
| `nifty_lab/risk/__init__.py` | 26 | Exports |
| `nifty_lab/brokers/upstox.py` | 63 | Offline Upstox status |
| `nifty_lab/brokers/__init__.py` | 7 | Upstox only |
| `nifty_lab/brokers/kite.py` | — | **Deleted** |
| `nifty_lab/brokers/kotak.py` | — | **Deleted** |
| `nifty_lab/journal/db.py` | 220+ | `open_position_count`, qualify/manual data_source tags |
| `nifty_lab/ui/common.py` | 153 | Upstox-pending sidebar copy |
| `pages/01_Market_Overview.py` | 86 | Profile + legacy warning |
| `pages/04_Options_Strategy_Analyzer.py` | 230 | Fail-closed qualification + funded save |
| `pages/06_Risk_Dashboard.py` | 95 | Profile copy, legacy warning |
| `pages/08_Paper_Trading_Journal.py` | 130+ | Unqualified manual entries |
| `pages/10_Settings_and_API_Connections.py` | 130+ | Upstox-only setup, legacy costs labelled |
| `.env.example` | 16 | Upstox placeholders only |
| `README.md` | 102 | Spec 03 direction banner |
| `docs/ARCHITECTURE.md` | 29 | Upstox broker note |
| `tests/test_risk.py` | 170+ | Explicit fixtures, spec defaults |
| `tests/test_spec03_foundation.py` | 200+ | Normative scenario mapping |

Historical docs (`docs/RESEARCH.md`, `SPEC_HANDOFF.md`, etc.) unchanged as evidence.

## Scenario coverage

| Requirement / scenario | Test / evidence | Result | Gap |
|---|---|---|---|
| New account defaults | `test_profile_defaults` | PASS | — |
| Legacy env conflicts | `test_load_config_legacy_conflict_flag` | PASS | UI: Settings warning when conflict |
| Upstox offline status | `test_upstox_only_registry`, `test_offline_status_never_connected` | PASS | No CONNECTED state by design |
| Legacy creds private | Upstox `_present` ignores Kite keys; Settings copy | PASS | User `.env` not read for Kite |
| Drawdown boundary C0/H/E 20k/20k/18k | `test_drawdown_boundary_rejects` | PASS | — |
| Peak drawdown H 21k E 19k | `test_peak_drawdown_after_gains_rejects` | PASS | — |
| Missing per-position / margin / marks | `test_eligibility_without_context_is_insufficient`, `test_unconfirmed_per_position_insufficient`, `test_production_context_blocks_save` | PASS | Production UI always blocked until provider |
| Remaining risk R/P arithmetic | `test_remaining_downside_arithmetic` | PASS | — |
| No minimum risk encouragement | `test_no_minimum_risk_encouragement` | PASS | — |
| Save-time recheck | `test_save_recheck_with_valid_fixture` | PASS | Uses explicit test fixture context only |
| Educational payoff | Options page still renders section 3 when quotes valid; qualification separate | Manual / UI | No Streamlit e2e test |
| Existing journal preserved | `test_manual_journal_preserved_and_close`, `test_legacy_journal_blocks_qualification` | PASS | Real `data/journal.db` not touched |
| Secret sentinel | `test_offline_status_never_connected`, `test_credential_status_hides_sentinel` | PASS | — |
| Network guard | `block_socket_connect` autouse in `test_spec03_foundation.py` | PASS | — |

## Verification evidence

**Python:** 3.12.15 (`.venv` created for this run). System `python3` remains 3.9.6 without pytest — prior “47 passing” was unverified on that interpreter.

**Dependencies (pip):** pytest 9.2.0, streamlit 1.67.0, pandas 3.1.1, numpy 2.5.4, scipy 1.18.1, python-dotenv 1.2.4.

**Command:**

```bash
cd /Users/sanjain/Documents/hedge_trader
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

**Actual output:** `..................................................................` — **66 passed, 0 failed, 0 skipped** (47 prior + 13 Spec 03 + 6 adjusted risk tests).

**Breakdown:** `test_data` 4, `test_indicators` 14, `test_options` 14, `test_risk` 14, `test_signals_journal_contracts` 7, `test_spec03_foundation` 13.

**Privacy / no-network:** No HTTP, auth, or broker SDK calls added. Upstox `status()` is env-presence only. Tests use `tmp` SQLite DBs and socket connect guard. **`data/journal.db` and user `.env` were not read or modified** for verification.

**Runtime:** `ALL_BROKERS` length 1 (`UpstoxReadOnly`). No `place_order` APIs. `live_trading_enabled` still `False`.

## Open decisions and blockers

1. **Per-position risk ceiling** — still **unconfirmed**; gate returns `INSUFFICIENT DATA` until user confirms a ceiling ≤ ₹2,000.
2. **Reconciled valuation / peak equity / cash** — no provider; production funded-paper qualification **correctly unavailable**.
3. **Options margin** — missing margin → `INSUFFICIENT DATA` for funded options qualification.
4. **Legacy open journal exposure** — blocks qualification until migration/reconciliation spec.
5. **Legacy `NSL_*` in environment** — blocks `funded_paper_profile_authorized` until removed.
6. **Upstox equity/ETF costs** — unknown; educational options `CostSchedule` retained with disclaimer.
7. **`.venv/`** — created locally for verification; not part of spec deliverable (consider gitignore if undesired).

## Tasks checklist (evidence-based)

- [x] T1 Inspect tree; preserve `docs/CODEBASE_RESEARCH.md`
- [x] T2 Profile 20k/2k; unconfirmed per-position; legacy conflict handling
- [x] T3 Upstox only; remove Kite/Kotak runtime; `.env.example` + README
- [x] T4 `FundedPaperContext` + tri-state gate
- [x] T5 Analyzer + journal paths; unqualified manual; no private DB migration
- [x] T6 `tests/test_spec03_foundation.py` + updated `test_risk.py`
- [x] T7 pytest under 3.12 with recorded output
- [x] T8 No legacy brokers; fake data only
- [x] T9 This handoff — **stop here for review**

## Next smallest task proposed for review

**Spec 04 (draft): offline Upstox instrument master + CSV/candle normalization with provenance flags only** — add typed `DataProvenance` for broker-sourced files, validation rules, and completeness diagnostics. **Do not** add OAuth, HTTP, or `CONNECTED` status. Verify with fixture files under `tests/fixtures/upstox/` and zero network.

---

*Reviewer: approve or request changes before any live Upstox integration spec.*
