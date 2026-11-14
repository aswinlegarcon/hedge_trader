# Tasks — Spec 16

Status: IMPLEMENTED (2026-11-14). Evidence in `handoff.md`.

- [x] Read official Upstox authentication / get-token / access-token-request docs; choose the authorization-code flow; document why approval/webhook renewal is deferred.
- [x] Managed token store: atomic 0600 writes, failure-safe replacement, fingerprint marks (R1).
- [x] Precedence, rejection handling, value-free status with documented expiry (R2).
- [x] Narrowly scoped auth transport; `begin_login`/`complete_login` with random single-use expiring state; stop active streams on replacement (R3).
- [x] Settings section with Reconnect workflow, callback processing, query-param clearing, loopback-only controls (R4).
- [x] Tests for success/failure paths incl. replay, atomic failure, precedence, no-retry, DEBUG-log leakage; existing REPLAY/stream/chart acceptance intact.
- [x] Operator guide (setup, daily reconnection, Linux callback access, LIVE chart use).
- [x] Spec 15 operator smoke handoff (baseline vs later check).
- [x] Final full suite; focused commits to main; normal push.

Not done by design: real renewal (needs an attended owner approval); webhook/approval path; TOTP path.
