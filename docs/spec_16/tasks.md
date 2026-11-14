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

## Review corrections (2026-11-14, second pass)
- [x] Loopback-listener gate enforced before login initiation and callback processing (config-based, not Host header); `.streamlit/config.toml` binds `127.0.0.1`.
- [x] Two-step receive/complete binding: exchange only in the initiating session; wrong session refused; approval replay refused.
- [x] Known-expired managed token never resurrected through an identical environment token; different env credential documented.
- [x] Rejection/expiry marks durable (never cleared by success); shared per-path lock + `fcntl` file lock for concurrent writers.
- [x] Tests S05 (extended), S10 (+replayed completion), S11, S15, S16, S17, S18, S19; full suite rerun.

Not done by design: real renewal (needs an attended owner approval); webhook/approval path; TOTP path.
