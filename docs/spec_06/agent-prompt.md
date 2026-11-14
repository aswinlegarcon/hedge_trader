# In-house agent prompt

Implement only `/Users/sanjain/Documents/hedge_trader/docs/spec_06/`. Read README, proposal, design, normative specs and tasks first. Add real Upstox company-news context to Global News & Events and selected Watchlist Research cards using the official GET /v2/news API, category fixed to instrument_keys for up to four exact resolved watchlist keys.

Reuse existing backend token/transport and public instrument identities. Manual Refresh News only; no automatic candle refresh, portfolios, holdings/positions categories, order SDK, scraping, sentiment scores, generated summaries, forecasts, scheduled macro-calendar ingestion, commits or merges. Show safe article links, provider publication times, retrieval times, partial/empty/unknown coverage and stale-cache states. Retain manual event calendar and macro/events NOT CHECKED; no headlines does not mean no risk.

Preserve all uncommitted Spec 03–05 work and blocked paper qualification. Do not open/print .env or secrets. Runtime may consume the token privately. Test with fake tokens, mocked HTTP and no unexpected network/private journal. Implement the small end-to-end panel, not a broad news platform. Prior review/test gaps remain recorded without blocking this read-only slice.

Optional live smoke is limited to one news request for one instrument (plus one public master lookup if needed), sanitized counts/timestamps only. If access is denied, return the actual limitation rather than widening permissions or inventing results. Write docs/spec_06/handoff.md with file references, scenario mapping, commands/results, separate live outcome and remaining limits, then stop for review.
