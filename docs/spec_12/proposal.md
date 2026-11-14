# Spec 12 — Broker-priced Paper close (proposal)

## Problem

Paper sell-to-close on Trade Ticket today uses manually typed bid/depth. Operators need an explicit, bounded broker snapshot (official full-quote BBO + depth) to preview and confirm local simulated closes without placing broker orders.

## Scope

- **In:** PAPER mode; existing cash stock/ETF holdings with complete ledger metadata; explicit fetch → preview → confirm via Spec 08 close APIs; mocked HTTP + temp ledgers in tests.
- **Out:** New entries, shorts, options close via broker quote, Live/Sandbox order HTTP, mark/risk/Spec 11 overlay changes, automatic trading.

## Success

User can fetch one official quote per click, preview a reduce-only close bound to that observation, confirm a simulated fill through existing gates, and see LOCAL PAPER labeling with snapshot age and no broker order placement.
