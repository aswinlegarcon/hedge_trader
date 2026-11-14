# Tasks

- [ ] Inspect actual Paper schema, accounting and navigation without opening/migrating the real DB through ExecutionLedger.
- [ ] Implement separate read-only consistent snapshot reader and provenance-aware accounting view-model.
- [ ] Add dedicated Paper Account UI, local-only refresh, explicit missing/unknown states, no mutation controls.
- [ ] Prove hand-calculated partial/flat accounting, pending BUY/SELL/cancel reserves, missing marks, replay, invalid/mixed mode/schema cases using temp fixtures.
- [ ] Prove no DB creation/migrations/peak/mark writes/network/adapter calls and consistent read behavior; fixtures own their test writes.
- [ ] Run existing Spec08 accounting regressions/full suite. AppTest valid/missing/inconsistent fixture pages with no side effects.
- [ ] Write docs/spec_10/handoff.md with scenario-to-code/test mapping, commands/counts, screenshots only if safely available, read-only evidence, valuation/fee limitations and remaining gaps. No real trade creation for smoke.
- [ ] STOP for review. No commits/merges/live mutation or strategy promotion.
