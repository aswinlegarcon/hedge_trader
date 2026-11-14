# Spec 06 — Upstox news alongside watchlist research

Date: 2026-11-13 (Asia/Kolkata). Status: READY FOR IMPLEMENTATION; NOT IMPLEMENTED.

OpenSpec-style change package under the user's `docs/spec_06/` convention. Read [proposal](proposal.md), [design](design.md), [requirements](specs/watchlist-news/spec.md), [tasks](tasks.md), [agent prompt](agent-prompt.md) and [handoff](handoff.md).

Baseline: Spec 05 implemented in the uncommitted tree. Reviewer reran the existing suite with dotenv loading disabled: 81 tests pass. Spec 05 handoff reports a one-instrument live smoke but stores abbreviated output; reviewer has not independently repeated that live call. Prior Specs 03–05 are not retroactively certified in full.

## Verified upstream contract

[Official Get News API](https://upstox.com/developer/api-documentation/get-news/), opened 2026-11-13, documents bearer-authenticated `GET https://api.upstox.com/v2/news` for the past seven days. This change uses `category=instrument_keys` only, with the existing resolved watchlist keys. The API supports up to 30 keys, page_number 1–100 and page_size 1–100. Response `data` maps instrument keys to articles containing heading, summary, article_link, thumbnail and published_time (Unix milliseconds); `metadata.page` describes pagination.

This contract is not proof of this account's news entitlement. The agent must report the actual read-only result separately. No article scraping, private positions/holdings categories or token scopes are required by this spec. News coverage is not an upcoming-event calendar or a completeness guarantee.

Preserve ₹20,000 capital / ₹2,000 portfolio loss ceiling, unconfirmed per-position policy, no live orders and blocked funded-paper entry. This change adds research context only.
