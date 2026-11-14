# Spec 14 — Requirements (post-acceptance)

| ID | Requirement | Evidence |
|----|-------------|----------|
| R14-01 | Fixed ICICIBANK 5m scope | constants + page 14 |
| R14-02 | One bootstrap per Start (LIVE HTTP only) | `stream_session._bootstrap_once` |
| R14-03 | REPLAY fully offline | `replay_fixture`, AppTest |
| R14-04 | No secrets in browser | sanitize + typed `FeedAuthError` |
| R14-05 | Owner-safe Start/Stop/snapshot | `test_owner_conflict_*`, `test_snapshot_requires_owner` |
| R14-06 | Unique ascending chart times | `test_late_tick_acceptance_timeline`, `assert_chart_invariants` |
| R14-07 | Separate bootstrap vs stream; overlap policy | `CandleBook.chart_rows`, coverage notes in UI |
| R14-08 | Persistent LWC updates | custom component + `test_playwright_persistent_chart_updates` |
| R14-09 | NOTICE / attribution visible | `LWC_ATTRIBUTION`, `NOTICE_LIGHTWEIGHT_CHARTS.md` |
| R14-10 | Truthful staleness (trade vs heartbeat) | `last_trade_receipt_ts` vs `last_heartbeat_ts` |