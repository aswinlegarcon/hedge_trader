# Spec 04 — Upstox candles in the research dashboard

Date: 2026-11-13, Asia/Kolkata. Status: IMPLEMENTED — see [handoff.md](handoff.md); live token verification left to user.

OpenSpec-style package using the user's `docs/spec_04/` convention, not an initialized OpenSpec CLI workspace.

Read [proposal](proposal.md), [design](design.md), [requirements](specs/upstox-market-data/spec.md), [tasks](tasks.md), [agent prompt](agent-prompt.md) and [handoff template](handoff.md).

Latest user direction explicitly prioritizes actual Upstox integration over a separate offline-only milestone. User says they can obtain and locally set both API credentials and an access token. Do not ask for values in chat. This spec supersedes the offline-first sequence in Spec 03, without certifying Spec 03's financial gate.

User policy remains ₹20,000 capital / ₹2,000 total portfolio loss ceiling, per-position ceiling unconfirmed. Broker access in this change is market-data GET operations only. Data access does not unlock funded-paper eligibility or trading.

## Research, consulted 2026-11-13

- [Authentication](https://upstox.com/developer/api-documentation/authentication/): OAuth authorization-code flow; customer signs in on Upstox; token used for subsequent requests. Developer app/redirect settings are distinct from account activation. For the first slice use a token generated through an official supported flow and set locally; no OAuth callback implementation required.
- [V3 historical candles](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/): bearer-authenticated GET, instrument key and unit/interval/date range. Five-minute requests are within the 1–15 minute band with a one-month request window. Daily requests use days/1.
- [V3 intraday candles](https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/): current-day candles; minutes/5 supported. Candle timestamp is the interval start; response fields are timestamp/OHLC/volume/OI.
- [Instruments](https://upstox.com/developer/api-documentation/instruments/): JSON BOD lists recommended; identify with instrument_key rather than exchange_token.
- [Rate limits](https://upstox.com/developer/api-documentation/rate-limiting/): other standard APIs list 50/s, 500/min, 2,000/30min. This spec uses a much smaller manual-refresh budget.

These sources establish API contracts, not account entitlement or actual connectivity. Recheck relevant docs while implementing; no need to research unrelated endpoints.
