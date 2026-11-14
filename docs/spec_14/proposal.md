# Spec 14 — ICICIBANK 5m stream chart (proposal)

## Problem

The dashboard today loads broker candles via explicit refresh. Operators want a bounded, read-only streaming prototype that bootstraps intraday 5m history once per Start, then updates a forming bar from Feed V3 ltpc ticks without tying into Paper execution.

## Scope

- **In:** Single symbol `NSE_EQ|INE090A01021` (ICICIBANK), 5m candles, Upstox Feed V3 ltpc decode, one intraday HTTP bootstrap per Start, Start/Stop, REPLAY transport for tests, Lightweight Charts embed, Streamlit page 14.
- **Out:** Trade Ticket / ledger integration, volume bars, multi-symbol watchlists, Pine/drawings, order endpoints, marks/risk changes.

## Success

User opens **Stream Chart**, starts REPLAY or LIVE feed, sees bootstrap bars plus incremental candle updates with explicit connection state, stops the stream with no duplicate background owners, and tests prove decode/aggregation/session rules without live broker dependence.