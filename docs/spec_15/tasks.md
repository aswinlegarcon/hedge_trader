# Tasks — Spec 15

Status: NOT IMPLEMENTED. Check only completed work supported by evidence.

- [ ] Inspect baseline F1–F4 tests and map requirements to current code.
- [ ] Implement injectable clocks, source freshness and non-poisoning timestamp admission (R01–R02).
- [ ] Normalize production auth/protocol/retry classification (R03).
- [ ] Implement generation-safe responsive stop, accounted I/O cleanup and lock strategy (R04).
- [ ] Add independent owner lease expiry and repeated-cycle leak/concurrency tests (R05).
- [ ] Render current status/fault/freshness in the auto-refreshing page; preserve chart behavior (R06).
- [ ] Exercise the real WebSocket client with a loopback server and real protobuf (R07).
- [ ] Protect transport diagnostics at DEBUG without globally disabling logs (R08).
- [ ] Declare compatible dependencies and verify a clean Python 3.12 installation (R09).
- [ ] Convert defect xfails/characterizations into positive regression tests.
- [ ] Run deterministic targeted tests, repeat browser acceptance three times at shipped pacing, then run the full suite once after final changes. Repeat affected checks if further changes land.
- [ ] Append a Spec 15 supersession note to the historical LIVE readiness verdict without deleting its evidence.
- [ ] Complete handoff and operator runbook with scenario mapping and actual results.
- [ ] Commit focused changes on main; use normal push only; return exact commit(s) and stop.

## Scope controls

No live broker requests, credential reads, Paper/real executions, ledger writes, strategy/backtest changes, or holdout access. Offline HTTP tests use dummy credentials via injection/environment, never .env. Browser tests may load the existing pinned chart CDN; loopback sockets are explicitly allowed only in marked transport/browser tests. Default unit tests remain socket-blocked. Dependency installation may use package registries, not broker APIs. Do not lower unrelated test protections to accommodate loopback.
