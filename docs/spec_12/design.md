# Spec 12 — Design

## Flow

```text
[Holding pick] → (explicit) Fetch broker close quote → session stores QuoteSnapshot + retrieved_at
     → qty/limit/fees/slippage → Preview Paper close (no HTTP)
     → Confirm → submit_paper_close (ledger gates, observation consume)
```

## Quote module (`execution/broker_close_quote.py`)

- Reuse allowlisted `build_quotes_url` pattern (same path as Spec 11 overlay).
- Parse `depth.buy[0]` / `depth.sell[0]` price and `quantity`; reject empty, zero, crossed book, nonfinite, wrong `instrument_token`.
- Both provider `timestamp` and `last_trade_time` required; 15s freshness at receipt on each; `QuoteSnapshot.evaluated_at = min(provider, trade)` (no fallback, no restamp).
- Row selection by `instrument_token` only; duplicate tokens rejected.
- `retrieved_at` returned alongside for UI age display.

## Freshness

- Preview/confirm use existing `QuoteSnapshot.is_fresh()` (15s on **source** time). Stale preview requires new fetch + preview.
- Spec 11 overlay freshness does not satisfy close bid evidence.

## UI (`ui/trade_ticket.py`)

- PAPER close: **Fetch broker close quote** (≤1 GET). Manual bid/depth under labeled expander for legacy simulation.
- Show LOCAL PAPER, provider snapshot age, retrieval time, simulated execution disclaimer.
- Input change invalidates preview (existing identity hash).

## Confirmation

Unchanged Spec 08 path: `build_close_preview` → `confirm_close_preview` → `submit_paper_close` with `intent_id` + `observation_id`.
