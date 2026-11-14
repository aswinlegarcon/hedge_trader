# First implementation slice

- [ ] Read applicable repository instructions, Specs 03–08 and correction reviews; preserve existing uncommitted work and credentials.
- [ ] Inventory current data and backtest functions; record actual provenance, date coverage and limitations. Do not fetch secrets or add feeds speculatively.
- [ ] Implement local daily plan/observation/review store and simple research page with immutable versions, timestamps, source limitations and no-trade reasons.
- [ ] Implement the single frozen experimental strategy, rule/config versions and reproducible dataset/run manifests.
- [ ] Implement chronological evaluation/report with realistic conservative fills, sourced costs or explicit exploratory-only result, uncertainty and baseline. Avoid parameter sweeps.
- [ ] Test look-ahead boundaries, stop/target ambiguity, gaps, costs, late reports, immutable plans, data gaps and research/order isolation with fixtures/temp stores.
- [ ] Verify focused and required existing checks. No live broker mutation, credentials output, commits or merges.
- [ ] Complete handoff with actual paths, test evidence, omissions and per-feature status. Stop for review; no live or strategy promotion.

Dependencies: forward-paper integration requires accepted Spec 08 ledger/lifecycle. Broker context, expanded market feeds, promotion criteria and options evaluation are future separately scoped work, not completed by this package.
