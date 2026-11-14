# Tasks — Spec 15

Status: IMPLEMENTED (2026-11-14). Every box below is backed by evidence recorded in `handoff.md`.

- [x] Inspect baseline F1–F4 tests and map requirements to current code.
- [x] Implement injectable clocks, source freshness and non-poisoning timestamp admission (R01–R02).
- [x] Normalize production auth/protocol/retry classification (R03).
- [x] Implement generation-safe responsive stop, accounted I/O cleanup and lock strategy (R04).
- [x] Add independent owner lease expiry and repeated-cycle leak/concurrency tests (R05).
- [x] Render current status/fault/freshness in the auto-refreshing page; preserve chart behavior (R06).
- [x] Exercise the real WebSocket client with a loopback server and real protobuf (R07).
- [x] Protect transport diagnostics at DEBUG without globally disabling logs (R08).
- [x] Declare compatible dependencies and verify a clean Python 3.12 installation (R09).
- [x] Convert defect xfails/characterizations into positive regression tests.
- [x] Run deterministic targeted tests, repeat browser acceptance three times at shipped pacing, then run the full suite once after final changes.
- [x] Append a Spec 15 supersession note to the historical LIVE readiness verdict without deleting its evidence.
- [x] Complete handoff and operator runbook with scenario mapping and actual results.
- [x] Commit focused changes on main; use normal push only; return exact commit(s) and stop.

Not done by design: the real Upstox LIVE smoke test (operator task after review). No live broker request was made.

## Scope controls

No live broker requests, credential reads, Paper/real executions, ledger writes, strategy/backtest changes, or holdout access. Offline HTTP tests use dummy credentials via injection/environment, never .env. Browser tests may load the existing pinned chart CDN; loopback sockets are explicitly allowed only in marked transport/browser tests (`@pytest.mark.loopback`, `tests/test_spec15_loopback_ws.py`). Default unit tests remain socket-blocked. Dependency installation may use package registries, not broker APIs. Do not lower unrelated test protections to accommodate loopback.
