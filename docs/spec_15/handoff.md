# Spec 15 — Implementation handoff

Status: NOT IMPLEMENTED — specification only.

## Completion verdict

BLOCKED until implementation and all normative offline scenarios pass. No real LIVE verification has been performed by this spec.

## Implementer must replace this template

- Baseline commit and delivered commit(s):
- Changes by requirement R01–R09:
- Scenario S01–S25 -> test name -> result table:
- Freshness/state transition table and clock policy:
- Lifecycle/lease/lock strategy; measured stop and cleanup bounds:
- Real loopback WebSocket protocol evidence:
- Clean-install command, Python/dependency versions and protobuf compatibility:
- Browser repeatability, final full-suite result and each unrelated skip:
- Secret-handling checks, no-broker/no-ledger/no-holdout confirmation:
- Remaining limitations or blocked requirements:
- READY_FOR_OPERATOR_SMOKE or BLOCKED (never LIVE_VERIFIED from offline evidence):

## Operator runbook to supply after implementation

One attended ICICIBANK read-only LIVE run, maximum 10 minutes streaming / 15 minutes wall clock, only after reviewer acceptance and with live mutations forbidden. Validate market availability from provider status rather than weekday assumptions. Describe explicit Start/Stop, expected source/receipt age and connection states, rollover if naturally observed, stop completion, abort behavior and sanitized evidence. Never request token values, raw authorize traffic, WebSocket URLs or raw logs. Do not lengthen the smoke just to force a 5m rollover. Actual smoke evidence belongs to a later handoff; do not perform it in this task.
