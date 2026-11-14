# Spec 13 — Design

## Harness

- `ExecutionLedger(tmp_path, PAPER)` only; `paper_db_path()` monkeypatched to fail if it resolves to repo `data/paper_execution.db`.
- Broker: reuse Spec 12 `parse_close_quote_payload` / `fetch_broker_close_quote` with `MockTransport`; socket blocked.
- Time: monotonic `filled_at` via patched `ledger.store._utcnow` for fee-basis replay evidence.
- Paper Account: `load_paper_account_view(db)` at each checkpoint; no migrations/writes from reader.

## Oracle journey (API)

1. `build_preview` → `confirm_preview(slippage_pct, entry_cost_inr)` → `submit_paper_entry(slippage_pct=…)` with ticket `entry_cost_inr` as modeled whole-order fee.
2. Broker fetch → `build_close_preview` → `confirm_close_preview` → `submit_paper_close` (partial depth 3/8).
3. `cancel_paper_remainder` on open SELL.
4. Second broker observation → close 7 @ 105 (flat).

## UI

AppTest on `12_Trade_Ticket.py` with tmp ledger path; broker-close partial confirm; optional cancel controls.
