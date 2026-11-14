# In-house agent prompt

Implement only the end-to-end Upstox market-data slice specified in `docs/spec_04/`. Read README/proposal/design/specs/tasks first. The user explicitly chose actual integration rather than an offline-only milestone; do not make unrelated Spec 03 perfection a prerequisite.

Deliver: select Upstox and a resolved NSE watchlist equity/ETF, click Load/Refresh, fetch real V3 historical/daily or five-minute historical plus today's intraday candles, and display them with correct identity, timestamps and source in existing charts. Use official docs linked in README, a locally configured UPSTOX_ACCESS_TOKEN and a small injected GET-only transport. No need for an OAuth server or WebSocket in this slice. User can obtain/set token locally; never ask for secret values in chat or inspect/print their private configuration.

Implement essential candle normalization and instrument lookup as part of this slice, not a separate offline project. Show missing/expired token and network/empty-data states clearly. No secret output, raw headers/responses in errors, synthetic fallback, wrong-symbol cached chart or incomplete-candle signals. Tests use fake tokens, mocked HTTP and temp storage. A single bounded read-only smoke with a locally prepared token is authorized; if absent, complete code/tests and report exact setup steps without inventing connection success.

Preserve uncommitted Spec 03 changes, ₹20,000/₹2,000 policy, and blocked production funded-paper qualification. Do not repair the deferred gate issues, add orders, portfolio/funds/margins, chains, news, backtests or automated login. Keep unsupported equity/intraday signal voting unavailable while enabling charts/basic indicators. Do not commit or merge.

Write `docs/spec_04/handoff.md` with actual files/line references, scenario-test mapping, test results, separate live verification outcome and remaining gaps. Stop after the handoff.
