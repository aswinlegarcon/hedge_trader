# Tasks — one end-to-end market-data slice

- [x] Inspect current uncommitted Spec 03 work and local instructions; preserve it. Read this package and official linked contracts.
- [x] Implement injected GET-only transport and token loading, sanitized errors, bounds/retries/rate limiting; no order-capable SDK.
- [x] Resolve initial equity/ETF research labels from official NSE JSON and expose exact identity/ambiguity handling.
- [x] Implement days/1 and minutes/5 historical plus intraday fetch/merge, quality checks, completed-bar handling and provenance.
- [x] Wire Upstox source, Load/Refresh, correct selected-symbol/timeframe charts, meaningful status/freshness and local token setup guidance.
- [x] Keep unsupported signal/timeframe outputs unavailable and production funded-paper recording blocked. Do not bundle financial-core repairs.
- [x] Add mocked HTTP and UI-to-chart tests, sentinel/no-unexpected-network checks and existing workflow regressions. Run under Python ≥3.12.
- [x] Provide bounded smoke; run when token absent → BLOCKED with setup steps (no credential values in output).
- [x] Complete handoff with files, requirement/test mapping, actual test output, separate live result and deferred gaps. No commit/merge. Stop for review.
