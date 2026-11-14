# Spec 17 — Open-source comparison: retain, reuse or integrate (evaluation only)

Status: EVALUATION COMPLETE — no migration, no code adopted. Date: 2026-11-14.

**hedge_trader revision evaluated:** `9f61c5a30b4e0f08477e18b6ed02fecbc11bc73c` (399 passing tests, 1 unrelated skip).
**Upstream pins:** OpenAlgo `f456b3216b302888e640bc3df8b49a7551430ae5` (2026-11-13, AGPL-3.0); QuantConnect Lean
`82d26047e95a89b53c9cbe02b67efaa3c4455ed9` (2026-11-13, Apache-2.0); `openalgo-charts` npm 2.7.2 (Apache-2.0, repo
`marketcalls/openalgo-charts`, inspected via registry metadata only).

## Supplied operator evidence (not performed by this evaluation)

From the owner's Mac on 2026-11-14 at code revision `9f61c5a`: the dashboard OAuth reconnection succeeded, a managed token
was installed (directory 0700, file 0600), a subsequent authenticated request loaded 271 completed ICICIBANK daily candles
(latest session 2026-11-13), and no orders were placed. Fresh streaming and candle rollover remain unverified. This does not
change the Linux machine's credentials and no token was copied or requested.

## Alternatives considered

| Option | What it is | Verdict |
|---|---|---|
| A. Continue our implementation | Streamlit + `nifty_lab/` (deterministic math, provenance, ₹20k/₹400/₹2,000 invariants, audited paper ledger, research run manifests) | **Retain as the product core** |
| B. Adopt OpenAlgo as the platform | Flask + React 19 self-hosted trading platform, 38 broker plugins incl. Upstox, Analyzer (sandbox) mode, MCP agent, options analytics | **Not as platform**: AGPL-3.0 copyleft, ₹1-crore leverage-margin sandbox that does not encode our risk invariants, 150 pinned deps + Node build, our ledger/research history would not carry over |
| C. Adopt Lean as the backtest/paper engine | .NET 10 engine with Python algorithms via pythonnet, 170 indicators, US option data model | **Defer**: no Upstox brokerage, options data model is USA-only, Indian F&O data would have to be built and converted, requires Docker/.NET on the Mac |
| D. Integrate OpenAlgo as a *separate read-only service* for Indian options analytics | Run OpenAlgo locally (loopback, Analyzer mode) and read its option-chain/Greeks/OI endpoints from our dashboard | **Pilot** (bounded, measurable, reversible); AGPL obligations stay with the unmodified service |
| E. Reuse `openalgo-charts` as chart renderer | Apache-2.0 dependency-free canvas engine with drawing tools | **Defer** until multi-symbol/drawing needs are concrete; Lightweight Charts (also Apache-2.0) already satisfies Spec 14/15 |

## Recommendation

1. **Keep our implementation** for authentication, data, streaming, instrument identity, paper accounting, risk gates,
   reconciliation, backtesting mechanics and research persistence. Evidence: 399 tests pin behaviours (fee/basis replay,
   fill sequencing, reservation ownership, freshness, owner leases, secret handling) that neither upstream encodes.
2. **Run one bounded pilot (Option D)**: OpenAlgo as a separate, loopback-only, read-only analytics service for Indian
   options (option chain, Greeks history, OI), consumed for display only. Measurable acceptance criteria and the
   comparison with building the same via Upstox `/option/chain` + `/option/contract` ourselves are in `tasks.md`.
3. **Defer** Lean, US equities (Upstox developer API exposes no US equities — only `GLOBAL_INDEX`/`GLOBAL_INDICATOR`),
   and `openalgo-charts`. Record the concrete trigger for each (comparison.md §"Unknowns").
4. **Adopt patterns, not code**: OpenAlgo's MCP tool envelope with per-tool risk levels and explicit approval, and its
   Upstox V3 interval/chunk table, are documented references for our own bounded agent jobs. No upstream code is copied.

A wholesale rewrite is not recommended: feature counts (OpenAlgo's 20 analytics tools, Lean's 170 indicators) do not
substitute for our audited accounting and provenance, and both uprstreams' paper modes model margin/leverage, not our
₹400-per-position / ₹2,000-ceiling policies.

## Preservation

All research artifacts (`research/*_runs`, `trial_inventory.jsonl`, run manifests with config hashes), the SQLite journal
and paper ledger, and `docs/spec_*` remain the system of record. Any pilot is additive: a separate process with its own
database, read through HTTP, with no write path into our ledger. Nothing in this spec authorises migration of accounting
data or strategy promotion.
