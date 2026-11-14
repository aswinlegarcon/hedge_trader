# Design

## 1. Current evidence

| Source | Observed gap |
|---|---|
| `nifty_lab/config.py:33–39,65–81` | Old capital/risk defaults and Kite/Kotak-only credential list. |
| `nifty_lab/brokers/base.py:32–44`, `brokers/__init__.py:5` | Read-only abstraction; two legacy adapters only; no order methods. |
| `pages/04_Options_Strategy_Analyzer.py:126,146,187` | Eligibility called without drawdown; missing margin is a caption while recording may remain enabled. |
| `nifty_lab/risk/budget.py:36–70` | Default-zero drawdown, minimum-risk warning, no complete portfolio/count/funding context. |
| `nifty_lab/risk/portfolio.py:19–49,58–80` | Marks default to zero; no cash ledger; portfolio checks separate from entry gate. |
| `nifty_lab/options/costs.py` | Existing options schedule is not an Upstox equity/ETF cost model. |
| `nifty_lab/ui/common.py:56–95` | Broker selection is placeholder; non-synthetic banner assumes CSV. Future data contract work required. |

These line anchors refer to the inspected baseline; agent must report final anchors. An existing untracked `docs/CODEBASE_RESEARCH.md` was observed; preserve it and other pre-existing changes.

## 2. Revised policy

| Parameter | Decision |
|---|---|
| Initial research capital C0 | ₹20,000, latest direct user instruction. |
| Total loss/drawdown limit L | ₹2,000 fixed rupee ceiling; also show 10% of initial capital. User confirmed. |
| Initial-capital floor | ₹18,000 before external flows; do not let gains or deposits expand the authorized ₹2,000 loss budget automatically. |
| Per-position risk ceiling | Unconfirmed. Historical assistant recap proposed ₹500–₹1,000; do not silently adopt either value. Keep explicit unset state until the user confirms a ceiling ≤ ₹2,000. |
| Minimum risk | None. Never encourage increasing a small position to meet a minimum. |
| Position count/concentration | Existing 3-position, 6% aggregate risk and 4% per-underlying caps remain conservative interim constraints; do not loosen them automatically. At ₹20,000 they imply ₹1,200 / ₹800. Clearly report interaction with the ₹2,000 ceiling; these are not stock allocation recommendations. |
| Initial watchlist | Provisional research labels: ICICI Bank, Gold BeES, Bharti Airtel, L&T. Do not invent instrument keys, quantities or quotes. Resolve exact instruments in a later spec. |
| Mode | Read-only research and clearly separated paper activity. No leverage, short-selling or derivative funding assumed for the eventual stock/ETF profile. Existing options tools remain educational. |

Use an explicit profile version/identity so an old environment cannot silently turn this account back into the ₹100,000 plan. `load_config` must not auto-load legacy risk overrides as authorization. Conflicting `NSL_*` overrides should show a value-free configuration diagnostic and keep funded-paper entry unavailable, while allowing calculators. Never rewrite `.env`. Keep explicit custom fixtures possible in unit tests, separate from active-profile policy.

Unknown per-position policy is an expected state, not a reason to block this implementation. The agent implements the safe unset state and reports it; it must not request or invent missing numbers.

## 3. Eligibility context and accounting boundary

Introduce a typed context passed explicitly to the gate: profile/version, evaluation clock, validated policy, initial capital, equity, peak equity, current net position P&Ls and total worst losses, open position count and underlying exposure, available cash, candidate cash/margin requirement and source/valuation-quality flags. Every required numeric input must be finite and have coherent units. Missing values stay unknown; never coerce to zero.

Use money-safe arithmetic with an explicit rounding policy (integer paise or Decimal). The decision exposes status (`ELIGIBLE`, `REJECTED`, `INSUFFICIENT DATA`), reasons and warnings. Keep a derived `.eligible` compatibility property if useful. Known breaches dominate status as REJECTED; otherwise missing/invalid required context yields INSUFFICIENT DATA; aggregate all relevant reasons. Theoretical calculations can continue independently.

For the bounded zero-external-flow account, validated E is equity and H is persistent peak equity, initialized at C0. D = max(0, H − E). Initial loss = max(0, C0 − E). Let each R_i be total entry-to-worst loss including costs, and P_i its current net P&L on the same basis. Remaining risk B_i = max(0, R_i + P_i). Candidate B_new includes all required cost/slippage reserves. Require both D + sum(B_i) + B_new ≤ L and initial_loss + sum(B_i) + B_new ≤ L, plus per-position, aggregate risk, count, concentration and available-cash checks. At D ≥ L block new entries even when candidate risk is zero. Missing required margin blocks options funded-paper qualification; cash equity funding would require full notional plus charges, not option margin.

Examples at C0=₹20,000: H=₹20,000, E=₹18,000 blocks new entries; H=₹21,000, E=₹19,000 also blocks (peak drawdown ₹2,000). If R=₹1,000, P=−₹600, E=₹19,400, H=₹20,000, remaining risk is ₹400 and current drawdown plus remaining risk is ₹1,000, not ₹1,600. If P=₹200 then B=₹1,200.

This change must not fabricate trustworthy E/H from the present journal: it lacks a reconciled ledger and reliable marks. Implement/test the gate against explicit independent fixtures; production UI returns INSUFFICIENT DATA until a trustworthy provider exists. Nonzero external flows, missing persistent peaks, unreconciled legacy history, unknown fees or stale marks remain unsupported and block qualification. Full flow-adjusted ledger/migration work stays in a later reviewed spec. Do not persist mock valuations as actual account data.

Recheck the same gate at funded-paper save time. The journal's generic manual recording path may retain educational notes/history, but must label them unqualified/manual and never silently treat them as validated open positions. Existing records must not disappear from risk exposure or be promoted into qualified data; unresolved legacy exposure blocks qualification. No need to migrate the private database in this task; if schema changes prove essential, stop that substep and report a migration proposal without touching the database.

## 4. Upstox-only offline adapter

Remove legacy broker module exports/imports and active onboarding. New status adapter performs no network I/O, token validation or login. It reports NOT_CONFIGURED or CONFIGURED_NOT_CONNECTED from presence checks only, never CONNECTED. Use environment key names `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI`, `UPSTOX_ACCESS_TOKEN`; placeholder/blank values count as absent. Accept an externally prepared token without requiring every OAuth field for a presence-only token status. Never display values, token prefixes, callback query strings or raw exceptions containing headers. No secrets in Streamlit session state or cached arguments.

Keep historical/option-chain methods explicitly unavailable. Update sidebar copy to explain Upstox integration is pending; do not feed a fabricated BROKER_LIVE dataset. Do not add a broker SDK or networking dependency for this status-only work. Update placeholder-only `.env.example` without reading/copying actual `.env` values. Removing legacy setup must not delete user credentials. Preserve historical fee-source citations; label existing cost calculations as legacy educational options estimates, not current Upstox equity costs. Current fees unknown means qualification unavailable.

## 5. Verification and rollout

Use Python ≥3.12 and reproducible dependency versions. Prior inspection found system Python 3.9.6 and no pytest/core dependencies, so 47 historical passing tests remain unverified. Record actual environment and test results; never copy historical success claims.

No authenticated smoke test in this package. Tests must reject unexpected network access, exercise absent/placeholder/present credentials with fake sentinels, capture output to verify sentinels never appear, and cover actual recording paths. Preserve synthetic/CSV calculations and journal viewing/closing. Run meaningful regression tests; do not alter independent mathematical expectations to hide failures caused by new defaults. Keep numerical fixtures explicit about policy and account size.

No commits, merges or automatic continuation into later integrations. Reviewer checks the handoff before the next spec.
