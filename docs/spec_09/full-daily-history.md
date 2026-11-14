# Spec 09 next slice — resumable ICICIBANK daily history

Date: 13 November 2026 IST. Status: IMPLEMENTED — integrity review corrections applied offline; stop for review. This is a bounded acquisition slice, not the entire Spec 09 backtest/research roadmap. The corrected audit passed 173 existing tests in independent review. Its 20/21/22 saved sample counts establish access feasibility only. Preserve Spec 08 and prior audit artifacts.

## Proposal
Acquire and audit one stock's 2021–2025 daily history with deterministic yearly chunks, checkpoints, interruption-safe public artifacts and explicit calendar/adjustment limitations. Make a reproducible dataset available for a separately scoped experimental backtest. No strategy, optimization, Paper strategy automation or broker integration in this slice.

## Design

### Fixed dataset and budgets
ICICIBANK, resolved exact NSE equity identity, daily V3 candles. Five non-overlapping inclusive chunks: 2021-01-01..2021-12-31, 2022-01-01..2022-12-31, 2023-01-01..2023-12-31, 2024-01-01..2024-12-31 and 2025-01-01..2025-12-31. Reuse read-only transport/master cache and corrected raw audit. Read the official current V3 daily range contract before request construction: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/ . Do not fetch other instruments, intraday data, option contracts or account information.

Max five historical attempts per invocation. Persist cumulative attempts in the logical dataset checkpoint, max ten total and at most two per yearly chunk. Retrying a failed chunk requires an explicit --resume invocation; no automatic retries. A completed validated/hash-matching chunk is reused without HTTP. Auth/rate/unavailable errors stop the invocation immediately and mark remaining chunks NOT_FETCHED. At most one public master GET per invocation on missing/invalid cache; persist total master attempts too. No credential headers to public host. Invalid token gets a sanitized blocker without OAuth/settings changes.

Fixture tests first. For this handoff permit at most ONE initial live acquisition invocation, <=5 authenticated historical attempts plus <=1 public master GET. Do not execute a second live resume to force success; test resumes offline. If credentials/setup are unavailable, deliver the tested downloader and explicit LIVE_CHECK_UNVERIFIED with no invented historical results. Do not open/read/display .env; runtime may consume existing server-side token privately.

### Durable artifacts and resume
Use a dedicated versioned research/history_runs/<dataset_id>/, distinct from the original audit folders and execution databases. Persist config/schema version, immutable instrument identity, date/interval boundaries, request budget/attempt history, predeclared splits, per-chunk raw/normalized paths and hashes, HTTP/error status (actual HTTP code only when known), and quality/provenance state. Unknown transport response status remains null with typed error code, not invented HTTP503 for a timeout.

Commit intent/checkpoint before a network attempt; store responses/results atomically using temporary files plus rename. A crash after fetch but before result commit cannot mark a chunk completed. A resume verifies configuration and artifact hashes before skipping a chunk; changed symbol/dates/schema or corrupt/missing output must cause explicit conflict/corrupt status rather than silent reuse or blind refetch. Preserve old runs. Prevent concurrent writers for the same dataset with a lock/transaction, including consistent request counters. No deleting user data or resetting attempt history.

After success, merge accepted chunks deterministically by IST session date and save canonical daily data plus a dataset hash. Keep both raw and normalized evidence, date coverage and row counts. Identical duplicates are counted/deduped transparently; conflicting session dates/values quarantine the candidate dataset. Fix the audit's current date-first duplicate check so identical duplicates are distinguished from conflicting ones; a conservative warning must not hide actual source counts.

Never forward-fill or interpolate tradable bars, auto-adjust corporate actions, discard outliers silently or turn incomplete data into success. Any partial dataset can be saved as PARTIAL/LIMITED but is not a complete acquisition. Expose earliest/latest returned dates and boundary gaps rather than assuming a yearly request returned a whole year.

### Coverage and adjustment review
Carry forward raw daily-midnight IST policy and chronological input-order recording, quality findings, volume checks and candidate weekday gaps. Keep every candidate missing date in machine-readable output, not just a 12-date sample. Weekends/holidays/special sessions need a sourced exchange calendar to verify actual expected sessions; no new calendar/network source is authorized here. If an authoritative existing local calendar is available, record source/version/date coverage and use it explicitly; otherwise calendar remains UNVERIFIED.

Assess large close-to-close gaps and intraday open-to-close changes with predeclared heuristic thresholds, flagging investigate-only; these are neither proof of a split nor reasons to automatically repair prices. Record corporate-action and adjustment status UNKNOWN unless authoritative evidence is present. List unresolved dates/jumps and what evidence is needed for a later review. No present-day constituent membership used as a historical universe; this is a single currently chosen stock study with selection bias.

Compare yearly outputs offline to overlapping original saved monthly samples without additional requests. Record matching hashes/values or revisions. Differences may reflect changed vendor data/adjustment treatment; preserve both versions and explain, do not overwrite original evidence or silently select the favorable version.

### Splits and readiness
Store development 2021-01-01..2023-12-31, validation 2024-01-01..2024-12-31 and final holdout 2025-01-01..2025-12-31. Mark all three as data acquired or not acquired separately. Do not reuse audit report wording that 2024 was not fetched or 2025 is only a December sample. Do not compute signals, strategy outcomes, returns ranking or parameter sweeps. Holdout remains unused for strategy selection.

Report acquisition completeness independently of data validation. Suggested fields: acquisition COMPLETE/PARTIAL/BLOCKED/UNVERIFIED; quality CLEAN_WITHIN_CHECKS/LIMITED/INVALID; calendar UNVERIFIED/VERIFIED with evidence; adjustment UNKNOWN/KNOWN with evidence; backtest eligibility EXPLORATORY_ONLY/BLOCKED. A complete download with unknown calendar/adjustment is not a validated backtest dataset or guaranteed return. Report current eligibility and exact next smallest task: remaining quality resolution or a separately specified fixed experimental cash-equity backtest with explicit limitations/cost model. No automatic continuation.

## ADDED Requirements

### Requirement: Bounded reproducible full-daily acquisition
The system SHALL acquire only the fixed one-stock five-year dataset and stop within persisted request budgets.

#### Scenario: Five chunks complete
GIVEN five valid mocked yearly responses
WHEN acquisition runs
THEN exactly five historical requests produce non-overlapping raw/normalized chunks, one deterministic merged dataset and manifest with accurate split coverage and unresolved quality limitations.

#### Scenario: Resume after interruption
GIVEN two completed chunks and an interrupted third
WHEN an explicit offline-tested resume occurs
THEN verified completed chunks make no HTTP requests, request counters survive restart and incomplete work is retried only within per-window/invocation/dataset limits.

#### Scenario: Auth/rate/network failure
GIVEN a production-style raised transport exception
WHEN any chunk fetch fails
THEN a readable sanitized checkpoint/report persists actual attempted counts and successful work, stops further requests, and marks remaining chunks NOT_FETCHED without automatic retry.

### Requirement: Corruption-safe provenance and data quality
#### Scenario: Changed configuration or corrupted cache
GIVEN a resume with changed instrument/dates/schema or mismatched artifact hash
WHEN state is loaded
THEN it cannot silently reuse, overwrite or refetch; it explains the conflict while preserving earlier evidence.

#### Scenario: Duplicate dates and gaps
GIVEN identical/conflicting duplicates, malformed bars, boundary gaps and holiday-unknown weekdays
WHEN merging
THEN counts/findings and all candidate gap dates are saved, conflicting data blocks clean status, and no executable prices are invented.

#### Scenario: Vendor revision versus sample
GIVEN an overlapping yearly bar differs from a saved monthly sample
WHEN offline comparison runs
THEN both versions remain, differences are disclosed and no extra network request occurs.

### Requirement: No strategy or live promotion
#### Scenario: Complete five-year download
GIVEN complete acquisition but unknown adjustment/session coverage
WHEN readiness is reported
THEN it explicitly remains exploratory/limited, with no win rate, P&L, prediction or permission to trade.

## Tasks
- [x] Inspect applicable instructions and existing audit transport/artifacts. Preserve all current work and private files.
- [x] Implement yearly config, persisted budgets, locking/checkpoints and safe atomic outputs/resume.
- [x] Audit/merge/hash full daily data, distinguish duplicate types, retain all candidate gaps and investigate-only jumps.
- [x] Compare saved monthly samples offline and report source/adjustment/calendar limitations and proper split coverage.
- [x] Test complete run, interruption/resume/no refetch, corrupt state/hash/config, concurrent writers, per-window and total budget, real raising exceptions, sentinel safety and deterministic hashes/quality regressions with fixtures/temp dirs.
- [x] Run focused/full checks. Optional ONE initial bounded live acquisition only after tests, <=5 historical + <=1 master; no additional live retries/resume. Use existing token only privately server-side; unavailable setup remains unverified.
- [x] Write docs/spec_09/full-history-handoff.md with exact paths, test/request counts, completeness/quality/eligibility, artifact locations and proposed next task. Stop for review, no commits/merges or auto-backtest.
- [x] Review corrections (`spec_09_full_history_review.md`): config-conflict preservation, persisted `CONFLICT` no-refetch, eligibility gating — offline fixture tests only (`docs/spec_09/full-history-handoff.md`).

## Implementer prompt
Implement ONLY docs/spec_09/full-daily-history.md in /Users/sanjain/Documents/hedge_trader. Keep live mutations disabled; no order/private account endpoints, .env inspection/secret output, new subscription/feed/calendar fetch, Spec08 edits or strategy/backtest. Follow hard request budgets, fixture tests first and at most one initial live acquisition. Preserve original audit and all user data; use existing hedge_trader IDE chat, not Agents Window. Complete full-history-handoff.md with actual evidence and honest unknowns and stop.
