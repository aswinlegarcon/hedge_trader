# Spec 15 — Reliable read-only LIVE market data

Status: PROPOSED — implementation authorized by the orchestration prompt, not implemented by this documentation commit.
Date: 2026-11-14.
Evidence baseline: main c969b4ede6a4f87cc04ecbce085bc65f376e42b6; prior chart commit b111e5257212e8b5c73bb7d2a91a5c444f0426c7.

## Why

Spec 14 now renders a bounded REPLAY chart, but its LIVE readiness review reproduces four production defects: receipt-only freshness, future-tick poisoning, production authentication retries, and abandoned-owner workers. An attended operator should not have to compensate for misleading status or restart the application to release a dead tab.

This spec supersedes the Spec 14 review's GO verdict for operational progression: LIVE smoke is BLOCKED until this spec's offline acceptance passes. Preserve that historical review; append a supersession link rather than rewriting its evidence. Passing this spec means READY_FOR_OPERATOR_SMOKE, never LIVE_VERIFIED or approved trading.

## Scope

One coherent reliability increment for the existing ICICIBANK 5m Feed V3 chart:
- source-aware freshness and timestamp admission;
- production authentication/error classification;
- cancellable lifecycle, owner leases, atomic state snapshots;
- accurate automatically refreshed status;
- production WebSocket compatibility proved locally;
- dependencies and secret-safe transport logging;
- repeatable acceptance and a bounded operator runbook.

## Non-goals

No orders, execution wiring, Paper fills/marks/ledger writes, signals, strategies, option chains, multi-symbol feeds, broker SDK migration, streaming data persistence, backtest reruns, or 2025 holdout access. No live broker calls during implementation. Preserve all account/risk policies and NSL_FORBID_LIVE_MUTATIONS=1. Do not make any profitability or predictive-accuracy claim.

## Success

All normative scenarios in capabilities/live-feed-reliability.md pass against the production paths. Existing F1–F4 defect tests become passing regressions, not expected failures. A clean documented Python 3.12 environment can import/decode/connect to a loopback test server using declared dependencies. The real Streamlit page works at shipped pacing, releases abandoned sessions, and never labels stale source data fresh. No worker, monitor, socket, or lease crosses a completed session boundary.

## Delivery

Implement in main with focused commits and normal pushes, no force pushes. Update tasks and handoff with exact tested SHA(s), dependency versions and evidence. Any changes after a test run require rerunning affected checks. Do not self-certify real LIVE verification. Stop after offline acceptance and handoff.
