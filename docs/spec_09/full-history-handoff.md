# Spec 09 — Full ICICIBANK daily history handoff

Date: 13 November 2026 IST. Status: **INTEGRITY CORRECTIONS APPLIED — stop for review**. Spec 08 unchanged. Original audit and saved live history artifacts **unchanged** (no live re-acquisition in this pass). No strategy/backtest engine.

## Scope delivered

Per `docs/spec_09/full-daily-history.md` + review `spec_09_full_history_review.md`:

- ICICIBANK daily V3, five yearly chunks (2021–2025)
- Persisted checkpoints, config hash, writer lock, atomic artifacts
- Budgets: **5**/invocation, **10**/dataset, **2**/chunk (explicit `--resume` only)
- Offline integrity fixes (findings 1–3 below)

## Review corrections (offline only)

| Finding | Fix | Test evidence |
|---------|-----|---------------|
| **1** Config mismatch overwrote checkpoint/manifest | Resume config conflict writes only `invocations/{id}_config_conflict.json`; `persist_dataset=False` — no checkpoint/manifest/raw/normalized/merged bytes touched; counters preserved | `test_config_hash_conflict_on_resume` (byte equality + 5 dataset attempts) |
| **2** CONFLICT silently refetched | `CONFLICT` persisted on verify failure; resume branch skips HTTP; normalized+raw integrity in `verify_completed_chunk` | `test_corrupt_completed_hash_marks_conflict`, `test_normalized_tamper_persists_conflict_no_refetch` |
| **3** INVALID / missing merge still eligible | `COMPLETE` requires verified five chunks + merged hash on disk; `INVALID` or chunk `CONFLICT` → eligibility **BLOCKED**; raw same-session conflicts → `CONFLICT`, merge withheld | `test_raw_conflicts_block_eligibility`, `test_resume_skips_completed_no_http` (`acquisition=COMPLETE` on zero-fetch resume) |

Saved production dataset: `research/history_runs/icicibank-daily-79d0359eb567/` (**not modified** in this correction pass).

## Code paths

| Area | Path |
|------|------|
| Package | `nifty_lab/research/full_daily_history/` |
| CLI | `scripts/run_full_daily_history.py` |
| Tests | `tests/test_spec09_full_daily_history.py` |

## Verification (this pass — fixtures only)

```bash
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests/test_spec09_full_daily_history.py
TMPDIR=.pytest_tmp .venv/bin/pytest -q tests
```

| Command | Result |
|---------|--------|
| Full-history tests | **12 passed** |
| Full `tests/` | **185 passed** |

## Saved live dataset (unchanged; prior initial acquisition)

| Metric | Value |
|--------|-------|
| Historical (dataset) | **5 / 10** |
| Acquisition (saved manifest) | **COMPLETE** |
| Quality | **LIMITED** |
| Backtest eligibility | **EXPLORATORY_ONLY** (not validated) |
| Merged hash | `9c1a7e2b6f0d8137597d359ad34a4b58fa4033321040f263b8ea61d769a60b3e` |

| Year | Rows | Notes |
|------|------|-------|
| 2021 | 248 | |
| 2022 | 248 | |
| 2023 | 246 | |
| 2024 | **249** | (handoff typo corrected; matches saved manifest) |
| 2025 | 249 | |
| **Sum** | **1240** | |

Calendar **UNVERIFIED**; adjustment **UNKNOWN**.

## Scenario evidence (tests)

| Scenario | Test |
|----------|------|
| Five chunks + merge + budget | `test_five_chunks_merge_and_budget` |
| Resume zero HTTP + `COMPLETE` | `test_resume_skips_completed_no_http` |
| Auth stop | `test_raising_auth_stops_with_checkpoint` |
| Config conflict preserves bytes/counters | `test_config_hash_conflict_on_resume` |
| Hash conflict persisted, dual resume no refetch | `test_corrupt_completed_hash_marks_conflict` |
| Normalized tamper → CONFLICT | `test_normalized_tamper_persists_conflict_no_refetch` |
| Raw conflicts → BLOCKED eligibility | `test_raw_conflicts_block_eligibility` |
| Lock, per-chunk cap, overlap, gaps, sentinel | existing tests |

## Limitations (honest)

- Weekday gaps are candidate sessions only; no in-repo exchange calendar.
- Adjustment **UNKNOWN**; exploratory eligibility is not validated backtest input.
- `CONFLICT` chunks require separately authorized repair/new dataset (not auto-cleared on resume).
- No P&L, signals, optimization, or broker mutations.

## Proposed next task

After review acceptance: **separately frozen cash-equity daily exploratory engine** on development years 2021–2023 only; 2024 validation and 2025 holdout outcomes stay unexamined until engine/rules/cost assumptions are reviewed.

**Stop for review. No commits/merges. No live requests in this pass.**
