# Spec 17 — Handoff (evaluation only)

## Pinned revisions

| Repository | Commit | Date | Licence | Notes |
|---|---|---|---|---|
| hedge_trader (evaluated) | `9f61c5a30b4e0f08477e18b6ed02fecbc11bc73c` | 2026-11-14 | project | 399 passed, 1 unrelated skip at this revision |
| marketcalls/openalgo | `f456b3216b302888e640bc3df8b49a7551430ae5` | 2026-11-13 | AGPL-3.0 (`License.md`) | cloned `--depth 1` into the session scratch directory; not installed, tests not run |
| QuantConnect/Lean | `82d26047e95a89b53c9cbe02b67efaa3c4455ed9` | 2026-11-13 | Apache-2.0 (`LICENSE`) | cloned `--depth 1`; `net10.0`; not built |
| openalgo-charts (npm) | 2.7.2 | — | Apache-2.0 (registry metadata) | repository `marketcalls/openalgo-charts`; not cloned; independent reuse deferred |

Official documentation consulted (2026-11-14): Upstox instruments, V3 historical candles, option contracts, put/call option
chain, expired historical candles; upstream READMEs and source at the pins above. No private endpoints, no credentials.

## Supplied operator evidence (owner's Mac, 2026-11-14; not performed by this evaluation)

Dashboard OAuth reconnection succeeded on code revision `9f61c5a`; managed token installed (dir 0700, file 0600); an
authenticated request loaded 271 completed ICICIBANK daily candles (latest 2026-11-13); no orders placed; fresh streaming
and rollover unverified; Linux credentials unchanged; no token copied or requested.

## Demonstrations performed (bounded, offline, fixtures and dummy data only)

| # | Question | Method | Result |
|---|---|---|---|
| 1 | Is OpenAlgo's Upstox Feed V3 schema the same as ours? | `diff` of both `.proto` files ignoring comments/blank lines | Differences are trailing comments only (`iep`, `rp`, `ieq`, `iiqTotal`, `iiqM`, `casEligible` annotations); message structure identical |
| 1b | Does its generated module decode our frames? | Loaded `broker/upstox/streaming/MarketDataFeedV3_pb2.py` by path and parsed our 5 replay fixture frames | 4 `live_feed` ltpc frames and 1 `market_info` decoded with identical prices/timestamps. OpenAlgo pins protobuf runtime 6.33.5; we pin 7.36.2 |
| 2 | Can Lean run here without Docker? | `which dotnet` | absent; Lean targets `net10.0` (Docker image or SDK install required) |
| 3 | Does OpenAlgo's sandbox encode our invariants? | source grep for risk/drawdown gates | none; leverage-margin model with ₹1 crore capital and weekly reset |
| 4 | Expired-instrument support in OpenAlgo Upstox plugin? | grep | none |
| 5 | Event-driven backtester in OpenAlgo? | grep for backtest classes/functions | none (portfolio/SIP backtesters only, per README) |

Socket restrictions were not touched; no loopback or network test was added; no upstream test suite executed.

## Findings (summary; details in `comparison.md`)

- Retain: auth/secret handling, streaming freshness, instrument identity, ledger/reservations/reconciliation, backtest
  mechanics, research persistence, options math, UI.
- Reuse as a separate service (pilot): OpenAlgo options analytics, read-only over loopback, unmodified (AGPL stays with it).
- Adapt as pattern only: MCP tool envelope with risk levels and approval; Upstox V3 interval/chunk table.
- Defer: Lean; `openalgo-charts`; US equities (not in Upstox developer API segments).
- Custom regardless: Indian news/event discovery with provenance; auto-maintained research watchlist; ₹ risk policy.

## Ownership, licensing and cost

| Item | Classification | Obligation / cost |
|---|---|---|
| OpenAlgo run locally, unmodified, read over HTTP | External-service integration | AGPL-3.0: no obligation on hedge_trader; if modified **and** offered over a network to others, modified source must be provided. Keep unmodified; keep loopback-only |
| OpenAlgo source copied into hedge_trader | **Not done, not recommended** | Would pull hedge_trader under AGPL-3.0 |
| `openalgo-charts` as npm dependency (deferred) | Dependency | Apache-2.0: keep LICENSE/NOTICE attribution (as we do for Lightweight Charts) |
| Lean (deferred) | Dependency/platform | Apache-2.0 attribution; .NET/Docker footprint |
| Software licence cost | — | ₹0 for all three |
| Data subscriptions | — | Upstox developer API: existing account; **expired-instrument history requires Upstox Plus** (price not checked; no purchase). Live depth `full_d30` is Plus-only per OpenAlgo's note |
| Model/API usage | — | OpenAlgo agent needs an LLM provider or local Ollama; not part of the pilot |
| Local resources | — | OpenAlgo: Python 3.12 + 150 packages + Node build + SQLite; Lean: multi-GB Docker image |
| Integration & maintenance | — | Pilot 2–3 days; ongoing: track OpenAlgo releases, re-pin |

## Recommendation and pilot

Keep our implementation as the core. Run the Stage 0 pilot in `tasks.md` (OpenAlgo as a separate read-only analytics
service) with its seven acceptance criteria; default to building the option-chain panel ourselves if criterion 2 (token
coexistence) fails or the analytics add nothing we use. Do not adopt Lean or pursue US equities via Upstox now.

## Limitations

- Upstream behaviour was inspected and cross-checked offline, not executed; test counts are file counts, not pass counts.
- Upstox documentation pages for expired *contract lists* were not fetched (guessed paths 404); the expired-candle page was.
- Whether a second Upstox login invalidates an existing access token is unknown; the pilot resolves it.
- Fresh LIVE streaming and candle rollover remain unverified for hedge_trader (Spec 15 verdict CONNECTIVITY_ONLY).
- No performance or resource measurements of upstream software were made.
