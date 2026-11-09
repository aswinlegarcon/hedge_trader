# Architecture

```
app.py                      Streamlit router (st.navigation) — 10 pages
pages/                      One script per dashboard page (UI only, no math)
nifty_lab/
  config.py                 Risk budget + env handling (never prints secrets)
  contracts.py              Lot sizes, strike steps, expiry rules (dated + sourced)
  data/                     MarketDataset + provenance; synthetic generator; CSV import
  indicators/               SMA/EMA/RSI/MACD/ATR/Bollinger/VWAP/S&R/volume/vol-regime + explanations
  signals/                  Rule-based engine → SignalReport (passed/failed/avoid/invalidation)
  options/                  Black-Scholes + Greeks + IV; cost schedule; payoff engine; strategy builders
  risk/                     Eligibility vs budget; portfolio exposure/drawdown/concentration
  journal/                  SQLite paper journal, notes, signal log, performance summary
  brokers/                  Read-only broker interface + Kite/Kotak status stubs (Phase 2)
  ui/common.py              Shared Streamlit helpers, charts, banners
tests/                      pytest suite for all mathematical and risk logic
scripts/                    make_sample_data.py regenerates the synthetic CSV
data/sample/                Synthetic CSV (clearly labelled)
docs/RESEARCH.md            Ecosystem facts with sources and dates
```

Design rules
- Deterministic code owns every financial number. No model-generated numbers reach the UI.
- Every dataset carries `DataProvenance` (kind, source, timestamp); the UI shows it on every page.
- Indicators never use future bars; swing points record when they became known.
- Missing inputs produce `INSUFFICIENT DATA`, never a guess.
- `ReadOnlyBroker` has no order methods. `AppConfig.live_trading_enabled` is hard-coded `False`.
- Adding a broker = implement `ReadOnlyBroker` in `nifty_lab/brokers/` and register it in `ALL_BROKERS`.
