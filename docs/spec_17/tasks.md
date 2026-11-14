# Tasks — Spec 17

## Completed evaluation (2026-11-14)

- [x] Pin hedge_trader `9f61c5a`; clone OpenAlgo (`f456b32`, AGPL-3.0) and Lean (`82d2604`, Apache-2.0) into an isolated directory outside the repo; record `openalgo-charts` 2.7.2 (Apache-2.0) from registry metadata.
- [x] Compare seven areas against our code with evidence classes (tested / inspected / documented / unknown) — `comparison.md`.
- [x] Verify integration uncertainties from official docs and source: Upstox segments (no US equities), V3 history limits, option chain (snapshot), option contracts metadata, expired-instrument candles (NSE_FO, Plus plan), OpenAlgo Upstox plugin scope, Lean brokerage/data coverage.
- [x] Bounded offline demonstrations: protobuf schema diff + cross-decode of our fixtures with OpenAlgo's generated module; .NET presence check; targeted source greps. No upstream stacks installed, no test suites run, no broker calls.
- [x] Licensing and cost separation — `handoff.md`.
- [x] Recommendation, component boundaries, pilot — `proposal.md`, `design.md`, below.

## Proposed adoption stages (not authorised by this spec; each needs its own review)

### Stage 0 — Pilot: OpenAlgo as a separate read-only options-analytics service (smallest useful adoption)

Scope: run OpenAlgo locally on the owner's Mac in Analyzer mode, bound to 127.0.0.1, with its own Upstox login; add one
display-only panel in hedge_trader that reads option chain / Greeks / OI for one underlying through a loopback-only GET
transport. No writes, no orders, no shared tokens.

Acceptance criteria (all measurable):
1. Install from the pinned commit on the Mac within a documented ≤ 60-minute procedure using only `venv`/`uv` and `npm`; no global installs beyond Node/Python already present; footprint recorded (RSS of the OpenAlgo process at idle and during one chain fetch).
2. OpenAlgo's Upstox login completes **and our managed token keeps working afterwards** (one authenticated daily-candle request from hedge_trader succeeds after the OpenAlgo login). If it does not, the pilot **fails** and is recorded.
3. Option chain for one near expiry of ICICIBANK returns ≥ 30 strikes within 2 s over loopback.
4. For ATM ± 3 strikes, OpenAlgo IV and delta agree with our Black-Scholes (`nifty_lab/options`) within ±5 % / ±0.05 on the same snapshot timestamp; disagreements are recorded, not hidden.
5. Zero order/position/funds endpoints called (transport allowlist test); Analyzer mode confirmed on; `NSL_FORBID_LIVE_MUTATIONS=1` throughout.
6. Service down → panel degrades to "external analytics unavailable"; nothing else on the dashboard changes (AppTest).
7. Provenance shown on every external number (`source`, version, `fetched_at`).

Estimated effort: 2–3 working days (install + transport + panel + AppTest + attended acceptance).

### Comparison: continue our own implementation instead

Build the same panel from Upstox `GET /option/contract` + `GET /option/chain` with our existing transport, Greeks and
payoff engine. Estimated 2 days, no second login, no AGPL process, 0 new dependencies; lacks OpenAlgo's OI/GEX/vol-surface
tools. **Default if the pilot fails criterion 2 or shows no analytics we actually use.**

### Stage 1 (conditional) — symbol search and persisted research watchlist (ours)
Search over the cached instrument master; watchlist rows with reason, source and timestamp; exposes the research memory
requirement regardless of platform. Estimated 2–3 days.

### Stage 2 (conditional) — Indian options history via Upstox expired-instrument candles
Requires an Upstox Plus subscription decision by the owner (no purchase in this task); data stored as research runs with
provenance. Estimated 3–4 days after the decision.

### Not planned
Lean adoption; US equities via Upstox; replacing the paper ledger or risk gates with any upstream simulator.
