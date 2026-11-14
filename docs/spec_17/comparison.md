# Spec 17 — Evidence-backed comparison

Legend for evidence class: **T** tested here (bounded offline demo), **I** inspected source at the pinned commit,
**D** documentation claim (not verified by running), **U** unknown. Paths are relative to each repository at its pin.

Pins: hedge_trader `9f61c5a`; OpenAlgo `f456b32` (AGPL-3.0, `License.md`); Lean `82d2604` (Apache-2.0, `LICENSE`);
Upstox docs checked 2026-11-14.

## 1. Chart workspace, symbol catalogue, watchlists, indicators

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Charts | Streamlit pages; Plotly + TradingView Lightweight Charts 4.2.1 custom component for the stream chart (`nifty_lab/stream_chart/frontend/index.html`), browser-tested at shipped pacing (**T**, 3 Playwright tests) | React 19 + Vite frontend; every chart uses `openalgo-charts` 2.7.2, a separate Apache-2.0 dependency-free canvas engine (`frontend/package.json:62`; npm metadata **D**) with drawing tools (**D**) | No charting; research notebooks via Jupyter image (**D**) |
| Symbol catalogue | Upstox instrument master filtered to NSE_EQ/INDEX labels (`nifty_lab/brokers/upstox_instruments.py:78-90`, **I**); 4 provisional labels | Full master into SQLite `symtoken` table with FUT/CE/PE symbol reformatting (`broker/upstox/database/master_contract_db.py:98-167`, **I**); plugin declares NSE, BSE, NFO, BFO, CDS, BCD, MCX, indices, GLOBAL_INDEX (`broker/upstox/plugin.json`, **I**) | Symbol/market model with `Market.India` and India equity map/factor files (`Common/Market.cs:148`, `Data/equity/india/`, **I**); no Upstox keys |
| Watchlists | Fixed research labels + custom symbol; observations engine (Spec 05, **T**) | Watchlist UI + multi-quote (`get_multiquotes`, **I**) | Universe selection in algorithms (**I**) |
| Indicators | 11 indicators with explanations, no look-ahead (**T**) | Indicator library for agent/chart (`services/agent/tools/indicators.py`, **I**) | 170 indicator classes (`Indicators/`, **I**) |

**Decision: KEEP OUR IMPLEMENTATION** (chart, indicators, explanations). Gap to close ourselves: symbol search over the
already-cached master (`research/audit_cache/nse_instruments.json.gz`) and persisted watchlists with reasons/timestamps.
`openalgo-charts`: **DEFER** (trigger: drawing tools or multi-pane needs that Lightweight Charts cannot meet).

## 2. Authentication, historical data, streaming, instrument identity

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Upstox auth | Authorization-code flow, managed 0600 store, receive/complete initiator binding, loopback gate, durable rejection marks (Spec 16, **T** 25 tests) | Same token endpoint and form fields (`broker/upstox/api/auth_api.py:22-30`, **I**); redirect convention `http://127.0.0.1:5000/<broker>/callback` (`.sample.env:22`); logs full error response bodies at error level (`auth_api.py:51-57`, **I**) | No Upstox brokerage; Zerodha model only (`Common/Brokerages/ZerodhaBrokerageModel.cs`, **I**), live plugin in a separate repo (**D**) |
| Historical | V3 intraday/daily via our GET-only transport with host allowlist; empty-bootstrap tolerance (Spec 15, **T**) | V3 interval map and chunking table (`broker/upstox/api/data.py:109-130, 563-600`, **I**): minutes 1–300, hours, D/W/M; 500-key quote batches | Local Lean-format zip/csv; India equity minute/daily samples exist (`Data/equity/india/minute/yesbank`, **I**); conversion tooling required |
| Streaming | Feed V3 protobuf, ltpc mode, source-vs-receipt freshness, owner lease, loopback-tested (Spec 15, **T**) | Feed V3 protobuf; modes LTP/Quote/Depth with `full_d30` noted as Plus-only and 50-key cap (`streaming/upstox_adapter.py:189-194`, **I**); ZeroMQ proxy (`pyzmq`, **I**) | Websocket brokerage base classes; nothing for Upstox |
| Schema interop | **T (Demo 1):** our `MarketDataFeedV3.proto` and OpenAlgo's differ only in trailing comments; OpenAlgo's generated `_pb2` decoded all five of our fixture frames identically. OpenAlgo pins protobuf runtime 6.33.5, we pin 7.36.2 | | |

**Decision: KEEP OUR IMPLEMENTATION.** Reference (not copy): OpenAlgo's interval/chunk table and its `full_d30`
entitlement note. Our secret handling is stricter (OpenAlgo logs raw auth error bodies).

## 3. Screening, news/event discovery, candidate prioritisation

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Screening | None (**I**: no screener module) | OI tracker/range, max pain, straddle, vol surface, GEX, sector rotation, arbitrage (README **D**; `services/arbitrage_service.py` **I**) — live-market analytics, not a news/event screener | Universe selection + alpha framework (**I**), US-data oriented |
| News | Upstox `/v2/news` watchlist news, dedupe, staleness (Spec 06, **T**) | None found for news (**I**) | None |
| Research watchlist with reasons/timestamps | Observations + coverage notes; no persisted auto-maintained candidate list yet | None | None |

**Decision: KEEP + build custom (DEFER upstream).** No upstream implements Indian news/event-driven candidate discovery
with provenance; this remains custom regardless of platform.

## 4. Strategy definitions, backtesting, fill/cost models, options contracts

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Backtesting | `research/development_backtest` with ₹20k allocation ceiling, raw-open-below-stop gate, fee/slippage fields, preregistration and config-hash manifests (Spec 09, **T**) | Portfolio and SIP backtesters (README **D**); no event-driven strategy backtester found (`grep -rn "def backtest|class .*Backtest"` → none, **I**); Python Strategy Host runs *live/scheduled* scripts (`strategies/README.md`, **I**) | Full event-driven engine, fee/slippage/fill models, 458 Python examples (**I**) — US option data only (`Data/option/readme.md`, **I**) |
| Options contracts | Lot sizes/strike steps dated+sourced (`contracts.py`), Black-Scholes/Greeks/IV, payoff engine (**T**) | Option chain, Greeks history computed from candles (`services/iv_chart_service.py`, **I**), strategy builder (**D**) | Option universe model; no Indian contracts |
| Indian options history | Not implemented; Upstox provides `GET /expired-instruments/historical-candle/...` for NSE_FO (1/3/5/15/30 minute, day) **requiring an Upstox Plus subscription** (docs **D**); `GET /option/contract` gives lot size, tick size, freeze qty, weekly flag (**D**) | No expired-instrument support (`grep -i expired broker/upstox` → none, **I**) | Would need a custom Indian options data writer |

**Decision: KEEP OUR IMPLEMENTATION; DEFER Lean.** Trigger for Lean: a strategy family needing portfolio-level,
multi-asset, event-driven simulation beyond our daily/5m single-instrument mechanics, *and* an Indian F&O dataset in Lean
format whose provenance we can document.

## 5. Paper accounting, reservations, risk gates, reconciliation

| | hedge_trader | OpenAlgo Analyzer/sandbox | Lean paper |
|---|---|---|---|
| Capital model | ₹20,000 allocation, ₹400 position risk, ₹2,000 loss ceiling (`config.py`, **T**) | ₹1 crore starting capital, leverage-based margin, weekly auto-reset (`sandbox/fund_manager.py:1-15`, **I**) | `PaperBrokerage` with brokerage models (**I**) |
| Invariants | Reduce-only reservations, intent idempotency, fee/basis replay, fill-sequence ambiguity fail-closed, reconciliation (Specs 08–13, **T**) | Margin block/release/reconcile, square-off schedules, position locks (**I**); no per-trade ₹ risk or drawdown gate found (**I**) | Portfolio/margin models; no ₹ policy |

**Decision: KEEP OUR IMPLEMENTATION.** An upstream paper mode does not satisfy our invariants merely by existing.

## 6. Agent tools, research persistence, provenance, experiment versioning

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Agent | Bounded CLI jobs (`scripts/run_*.py`) writing run directories with manifests; no LLM in the loop | FastMCP server with 51 tools carrying risk levels and an envelope; chat agent via Agno + LiteLLM/ChatGPT/Ollama; order tools need explicit approval (`mcp/mcpserver.py`, `services/agent/stream.py:1127`, **I**; README **D**) | API/CLI, no agent |
| Persistence | `research/{audit,backtest,history,review}_runs/<uuid>/` with `registration.json`, config hashes, `trial_inventory.jsonl` (**I/T**) | SQLite databases per concern (`.sample.env:60-65`, **I**) | Result JSON per backtest (**I**) |

**Decision: KEEP persistence; ADAPT A PATTERN** (tool envelope + risk level + approval) when we expose bounded jobs to an
agent. Any MCP surface we build is read-only and ours.

## 7. Local Mac operation, restart recovery, dependencies, maintenance

| | hedge_trader | OpenAlgo | Lean |
|---|---|---|---|
| Runtime | Python 3.12 venv, 9 direct deps, Streamlit; loopback-bound; restart-safe stores (0600 token, SQLite) | Python 3.12, 150 pinned packages, Flask + eventlet/gthread, ZeroMQ, APScheduler, React build (Node); SQLite by default; Docker/Caddy optional (**I**) | .NET 10 SDK + pythonnet or Docker image (`DockerfileLeanFoundation:413`, **I**); 4,569 C# files; `dotnet` not present on this Linux host (**T**: `which dotnet` → none) |

**Decision: KEEP.** OpenAlgo is runnable locally on a Mac as a *separate* service (pilot); Lean is a heavyweight stack.

## Integration uncertainties (Section 3 of the brief)

| Question | Finding | Class |
|---|---|---|
| Does OpenAlgo support our Upstox workflow? | Same OAuth token endpoint, V3 history, V3 protobuf feed (schema identical by demo). Its login expects `REDIRECT_URL=http://127.0.0.1:5000/upstox/callback`, i.e. a **second** registered redirect URI or a second Upstox app. Whether a second daily login invalidates our managed token is **U** (Upstox docs do not say). | I / T / U |
| US stocks (e.g., NVIDIA) via Upstox API? | Instrument master segments: `NSE_EQ, NSE_INDEX, NSE_FO, NCD_FO, BSE_EQ, BSE_INDEX, BSE_FO, BCD_FO, MCX_FO, NSE_COM, GLOBAL_INDEX, GLOBAL_INDICATOR`. **No US equities.** The US investing product is not a developer API capability. | D |
| Indian options history + metadata | Upstox: `GET /option/contract` (metadata), `GET /option/chain` (snapshot only, no MCX), expired-instrument candles (NSE_FO, Plus plan). OpenAlgo: none for expired contracts. Lean: needs custom data. | D / I |
| Which advertised features are implemented & tested? | OpenAlgo: 449 test files, 21 mention Upstox, sandbox tests present (`test/sandbox/`, **I**; not run here). Analytics pages are live-data tools (**D**). No event-driven backtester (**I**). Lean: engine thoroughly tested upstream (**D**, not run here). | I / D |
| What remains custom regardless? | Indian news/event discovery with provenance; our ₹ risk invariants and ledger; research memory; Upstox-specific freshness/lease/secret handling; symbol search + watchlist persistence. | — |

## Demonstrations performed (all offline, no broker calls, no credentials)

1. **Proto interop (T):** `diff` of both `MarketDataFeedV3.proto` → comment-only differences; OpenAlgo's generated module
   parsed our 5 fixture frames (4 `live_feed` ltpc, 1 `market_info`) with identical values.
2. **Runtime check (T):** `dotnet` absent on this host; Lean targets `net10.0` → Docker or SDK install required.
3. **Source greps (I):** no per-trade risk/drawdown gate in OpenAlgo sandbox; no expired-instrument support in its Upstox
   plugin; no event-driven backtester; agent order tools gated by confirmation.

Not performed: running either upstream, installing their stacks, any Upstox request.

## Unknowns to resolve in the pilot

- Whether OpenAlgo's Upstox login coexists with our managed token (token invalidation on re-login).
- OpenAlgo's option-chain/Greeks accuracy vs our Black-Scholes on the same snapshot.
- Resource footprint on the owner's Mac (RAM/CPU of Flask + eventlet + ZeroMQ + React build).
- Cost of Upstox Plus for expired-instrument history (not priced here; no purchase).
