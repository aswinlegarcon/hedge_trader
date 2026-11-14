# Spec 13 — Paper workflow acceptance (proposal)

## Goal

End-to-end acceptance of the **existing** local Paper stack: Trade Ticket controls, preview/confirm gates, broker-priced close (Spec 12), cancel, execution ledger accounting, and read-only Paper Account reconciliation.

## Non-goals

New execution features, broker remainder re-eval, live/sandbox wiring, mark writes, real `data/paper_execution.db` use, or production DB mutation.

## Pass criteria

Independent numeric oracle (temporary ₹20k ledger), mocked broker HTTP with exact call counts, readonly reader checkpoints, negative safeguards (replay, observation, stale state), and ≥1 AppTest UI journey.
