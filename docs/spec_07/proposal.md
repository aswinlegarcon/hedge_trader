# Change: view the user's macro calendar capture in the app

## Why

The user wants a macro-event calendar like Trading Economics. Their HAR contains usable event HTML, but a clean replay currently returns no data. Deliver a usable captured calendar now with truthful provenance, alongside a bounded public-refresh attempt that never bypasses access restrictions.

## Scope

Add a Macro Calendar section to Global News & Events with import of the sanitized captured JSON, date/country/category filters, event list and exact snapshot status. Show raw displayed times until timezone is established. Keep actual, previous, consensus and provider forecast separate. Provide a manual 'Try public calendar refresh' that sends one ordinary GET to the captured public URL and activates new data only on valid HTTP 200 calendar HTML.

Add the selected source/coverage/known-time upcoming-event context to Watchlist Research as a separate macro panel. Unconfirmed-time snapshots cannot generate countdowns, imminent-event warnings or a blanket 'macro checked' status. No sentiment or technical-summary changes.

Expected files: small `nifty_lab/calendar/` package or equivalent, pages 02/11, narrow shared UI helper, optional local import/extraction helper, tests and setup instructions. No general-purpose browser HAR replay engine.

## Non-goals

Socket.IO/streaming replication, copied browser/session keys, cookie replay, automatic challenge resolution, anti-bot evasion, browser fingerprint emulation, proxy rotation, paid API integration/subscriptions, corporate earnings/holiday completeness, polling, event forecasts, orders, risk/sizing activation, commits and merges.

## Success

The user can import their 432-event sanitized snapshot and browse the captured macro releases. Dates, country, source link and captured values remain traceable. Public refresh either yields validated fresh HTML or an honest unavailable result; stale imported data never becomes live because a request was attempted.
