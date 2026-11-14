# Spec 07 — Trading Economics captured calendar and bounded public refresh

Date: 2026-11-13 (Asia/Kolkata). Status: READY FOR IMPLEMENTATION; NOT IMPLEMENTED.

OpenSpec-style package under `docs/spec_07/`. Read [proposal](proposal.md), [design](design.md), [requirements](specs/macro-calendar/spec.md), [tasks](tasks.md), [agent prompt](agent-prompt.md), [handoff](handoff.md).

## User direction and verified evidence

The user supplied `/Users/sanjain/Downloads/tradingeconomics.com.har` and asked to extract/reuse the calendar request instead of assuming paid API access. Author inspected request metadata without exposing credentials.

- Captured request: GET `https://tradingeconomics.com/calendar?partial=calendar`.
- Captured response: HTTP 200, HTML containing `table#calendar` and 432 `tr[data-id]` event rows. No Cookie or Authorization request header was present on this captured HTML request.
- Capture start: 2026-11-13T04:53:50.319Z. Display dates span 2026-11-12 through 2026-11-23; this is a finite snapshot, not 'all events'.
- Independent ordinary GET without captured headers/cookies: HTTP 202, zero-byte response, zero event rows. Live automated refresh is NOT VERIFIED. Do not call this a confirmed CAPTCHA or invent the reason for 202.
- Socket.IO requests in HAR include keys/session parameters. Do not extract, export, replay or persist them.
- Displayed event timezone and CSS importance mapping are not established from the inspected HTML. Keep unknown; do not assign UTC/IST or importance from an undocumented CSS class.

Author supplied sanitized user-facing JSON snapshot and minimal curl script separately under this chat's outputs folder. No full HAR, raw browser response, cookies or keys belong in the repository. The JSON is a reviewable extraction, not an official API payload or verified realtime feed.

## Sources and boundaries

[Calendar reference](https://tradingeconomics.com/calendar) and [site terms](https://tradingeconomics.com/terms.aspx) reviewed 2026-11-13. The terms describe personal analysis use; this spec is a local research workflow, not authorization to redistribute/rehost their data. No purchase, login, challenge handling or paid API key reuse.

The [official API schema](https://docs.tradingeconomics.com/economic_calendar/schema/) describes API fields; do not assume its UTC/importance guarantees apply to website HTML. Preserve source-specific contracts.

Spec 06 reviewer reran 94 tests successfully with dotenv disabled; no additional live Upstox news call was performed. No orders or funded-paper unlock.
