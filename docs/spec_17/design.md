# Spec 17 — Proposed component boundaries

## Principle

hedge_trader remains the system of record and the only writer of financial state. External open-source software, if used,
runs as a **separate process behind a loopback boundary** and is **read** by our application. No upstream code is copied into
`nifty_lab/` (OpenAlgo is AGPL-3.0; Lean is Apache-2.0 but architecturally foreign).

## Responsibilities retained by hedge_trader (unchanged ownership)

| Responsibility | Module(s) | Why retained |
|---|---|---|
| Credentials, token lifecycle, secret handling | `brokers/upstox_auth.py`, `brokers/upstox_transport.py` | Spec 16 invariants (0600 store, durable rejection, initiator-bound completion) |
| Market data access and freshness semantics | `stream_chart/`, `brokers/upstox_market_data.py` | Spec 15 source-vs-receipt freshness, owner lease, bounded reconnect |
| Instrument identity | `brokers/upstox_instruments.py` | Upstox keys are the canonical identity for every ledger row |
| Risk policy and gates | `config.py`, `risk/`, `execution/` | ₹20,000 / ₹400 / ₹2,000 — product policy, not platform config |
| Paper ledger, reservations, reconciliation | `paper_account/`, `execution/`, `journal/` | Audited invariants with numeric oracles |
| Backtest mechanics, cost models, preregistration | `research/development_backtest/` | Allocation ceiling, raw-open gate, config-hash lineage |
| Research memory | `research/*_runs`, manifests, `trial_inventory.jsonl`, `docs/spec_*` | Provenance, versions, failures, decisions |
| Options math and contract facts | `options/`, `contracts.py` | Dated, sourced constants; deterministic Greeks |
| UI and explanations | `pages/`, `ui/` | Beginner-friendly wording is a product requirement |

## Optional external service (pilot only): OpenAlgo analytics

```
owner's Mac
┌──────────────────────────────────────────────────────────────────────────┐
│ hedge_trader (Streamlit, 127.0.0.1:8501)  ──HTTP GET (loopback)──▶ OpenAlgo (Flask, 127.0.0.1:5000) │
│   • our token store (0600)                                           │   • its own SQLite, its own Upstox login │
│   • our ledger/journal (SQLite)                                      │   • Analyzer (sandbox) mode ON            │
│   • display-only "Options analytics (external)" panel                │   • no API key shared with hedge_trader   │
└──────────────────────────────────────────────────────────────────────────┘
```

Boundary rules for the pilot:
- hedge_trader calls only documented read endpoints (option chain, Greeks history, OI) with a dedicated loopback-only
  `AnalyticsTransport` (host allowlist `127.0.0.1`, GET only). No order, position or funds endpoints are ever called.
- Results are displayed with provenance (`source: openalgo@<version>, fetched_at`) and are never written to the ledger,
  journal or research runs except as explicitly labelled research observations.
- OpenAlgo's own Upstox login is used by the owner inside OpenAlgo; hedge_trader never sees that token. Our managed token is
  not shared. The pilot measures whether the two logins coexist.
- The service is optional: when it is down, the panel shows "external analytics unavailable", nothing else degrades.
- AGPL-3.0: running an unmodified copy locally and reading its HTTP API creates no obligation to relicense hedge_trader.
  If OpenAlgo were modified and offered to others over a network, its source would have to be provided; the pilot avoids
  modification.

## Deferred alternatives and their triggers

| Alternative | Trigger to revisit |
|---|---|
| Lean as backtest engine (Docker on Mac) | Need for multi-asset/portfolio event-driven simulation **and** an Indian F&O dataset converted to Lean format with documented provenance |
| `openalgo-charts` renderer | Drawing tools or multi-pane requirements beyond Lightweight Charts |
| US equities | Only if Upstox publishes developer-API coverage for US equities (currently none) or a second broker is chosen |
| Agent/MCP surface | After bounded jobs have a stable read-only contract; follow OpenAlgo's envelope/risk-level pattern conceptually |

## Preservation of history under any adoption

- Research runs and manifests stay immutable; new sources are recorded as new runs with `source` fields.
- Ledger and journal schemas are not touched by the pilot; any future data import is a separate spec with a reconciliation
  oracle, as in Specs 10–13.
- `docs/spec_*` remains the narrative of record; this spec records what was *not* adopted and why.
