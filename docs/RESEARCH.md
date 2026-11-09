# Ecosystem research (Phase 1) — verified 2026-11-09

All facts below were checked against the cited pages on **2026-11-09**. Everything in this
domain changes (pricing, lot sizes, taxes, regulations). Re-verify before relying on a number.
Items marked **[secondary]** were confirmed through broker bulletins or reputable secondary
pages because the primary page could not be fetched at the time.

## 1. Zerodha Kite Connect

| Item | Finding | Source |
|---|---|---|
| Pricing | ₹500 / month per API app. Historical-data add-on fee abolished 2025-02-08; historical data now included. From Oct-2026, ₹2,000+ monthly brokerage earns 500 developer credits that renew the app. | [Zerodha support: charges for Kite APIs](https://support.zerodha.com/category/trading-and-markets/kite-api/articles/what-are-the-charges-for-kite-apis), [Kite forum: historical data now free](https://kite.trade/forum/discussion/comment/49184) |
| Auth | Browser login at `https://kite.zerodha.com/connect/login?v=3&api_key=…` → `request_token` on redirect → `POST /session/token` with `checksum = SHA256(api_key + request_token + api_secret)` → `access_token`. Token expires **06:00 next day** (regulatory). 2FA TOTP must be enabled on the account. | [Kite Connect v3 — User](https://kite.trade/docs/connect/v3/user/) |
| Rate limits | Quote 1 req/s · Historical 3 req/s · Orders 10 req/s (also 400/min, 5,000/day) · others 10 req/s. | [Kite Connect v3 — Exceptions](https://kite.trade/docs/connect/v3/exceptions/) |
| Historical | Intervals: `minute, 3/5/10/15/30/60minute, day`; `continuous=1` for F&O continuity; `oi=1` for open interest. | [Kite Connect v3 — Historical](https://kite.trade/docs/connect/v3/historical/) |
| WebSocket | `wss://ws.kite.trade`; up to **3,000 instruments per connection, 3 connections per API key**; modes `ltp` / `quote` / `full` (5-level depth and OI). | [Kite Connect v3 — WebSocket](https://kite.trade/docs/connect/v3/websocket/) |
| SDK | Official `kiteconnect` Python package. | https://github.com/zerodha/pykiteconnect |

## 2. Kotak Neo API

| Item | Finding | Source |
|---|---|---|
| SDK | Official, actively maintained **`kotak-neo-python`** (v3.0.x). Legacy `kotak-neo-api-v2` is retired. | [Kotak-Neo GitHub org](https://github.com/Kotak-Neo/Kotak-Neo) |
| Auth | Consumer key/secret + mobile; interactive **TOTP + MPIN** two-step login. | same |
| Market data | Quotes, scrip-master search, expiry lists, option chains, historical candles, WebSocket streaming (per README). | same |
| Pricing | Depends on account plan; verify in the Neo app before budgeting. | — |

## 3. NSE index derivatives — contract specs

| Item | Finding | Source |
|---|---|---|
| Lot sizes (contracts expiring from Jan-2026) | NIFTY 75 → **65**; BANKNIFTY 35 → **30**; FINNIFTY 65 → **60**; MIDCPNIFTY 140 → **120**; NIFTYNXT50 **25** (unchanged). First monthly contracts on new lots expire 27-Jan-2026. | NSE circular FAOP70616 (03-Oct-2025) via [Zerodha bulletin 429705](https://zerodha.com/marketintel/bulletin/429705/revision-in-lot-size-of-index-derivative-contracts-from-december-30-2025) **[secondary]** |
| Strike interval | NIFTY **50** points (35 ITM / 1 ATM / 35 OTM for near expiries). | [NSE contract specifications](https://www.nseindia.com/products-services/equity-derivatives-contract-specifications) |
| Expiry day | NIFTY weekly & monthly expire on **Tuesday** (monthly = last Tuesday; previous trading day if holiday). | [NSE NIFTY 50 page](https://nseindia.com/products-services/equity-derivatives-nifty50), [AlgoTest expiry calendar](https://algotest.in/blog/all-index-expiry-day/) **[secondary]** |
| Weekly expiries | Only NIFTY retains weekly contracts on NSE. BANKNIFTY, FINNIFTY, MIDCPNIFTY weekly contracts discontinued from 20-Nov-2024 (SEBI Oct-2024 measures: one weekly index per exchange). | [Zerodha support](https://support.zerodha.com/category/trading-and-markets/trading-faqs/f-otrading/articles/weekly-expiries-discontinued-for-certain-index-derivatives) |

## 4. Transaction costs (options, NSE)

| Charge | Rate | Source |
|---|---|---|
| Brokerage (Zerodha) | Flat ₹20 per executed order | [zerodha.com/charges](https://zerodha.com/charges/) |
| STT | **0.15 %** of premium on sell side; **0.15 %** of intrinsic value on bought options exercised (both raised from 0.10 % / 0.125 % on **2026-04-01**). Futures sell 0.05 %. | [Zerodha bulletin 445377](https://zerodha.com/marketintel/bulletin/445377/revision-in-stt-securities-transaction-tax-from-1st-april-2026) |
| NSE transaction charge | 0.03553 % of premium | zerodha.com/charges |
| SEBI turnover fee | ₹10 / crore | same |
| Stamp duty | 0.003 % of premium, buy side | same |
| GST | 18 % on brokerage + transaction + SEBI charges | same |
| NSE IPFT | ₹0.01 / crore (+GST), negligible | same |

Encoded in `nifty_lab/options/costs.py` with a `verified_on` date.

## 5. SEBI / exchange requirements for retail API trading

- SEBI circular **SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (4-Feb-2025)** “Safer participation of retail investors in Algorithmic trading”: brokers may offer API access only through unique vendor-/client-specific API keys with **static-IP whitelisting**; order flows above an exchange-defined per-second threshold must be registered/tagged as algos; brokers are responsible for all API orders. Exchange implementation standards phased in during 2025 and became applicable to all brokers by 2026. Sources: [SEBI circular page](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html) (primary; full PDF text not fetched), [IndiaLaw summary](https://www.indialaw.in/blog/civil/sebi-retail-investors-algorithmic-trading/), [Moneylife](https://moneylife.in/article/sebi-introduces-new-framework-for-safer-algo-trading-for-investors/76294.html) **[secondary]**.
- Implication: **v1 sends no orders**, so it is a pure data consumer. Any future execution module must be designed against static-IP, order-rate and algo-registration rules and reviewed separately.
- Kite access tokens expire daily by regulation; automated credential replay or unofficial login bypasses are not used.

## 6. Open-source Python libraries considered

| Need | Chosen for v1 | Alternatives (Phase 2/3) |
|---|---|---|
| Indicators | Own pandas implementations (`nifty_lab/indicators`) — fully tested, no C deps | `pandas-ta`, `ta`, `TA-Lib` |
| Options pricing / Greeks | Own Black-Scholes with SciPy | `py_vollib`, `QuantLib` |
| Backtesting (Phase 3) | — | `vectorbt`, `backtrader`, custom event-driven engine |
| Broker SDKs | — (Phase 2) | `kiteconnect`, `kotak-neo-python` |
| Dashboard | Streamlit + Plotly | — |

## 7. Existing platforms (what they do, what this project adds)

- **Sensibull** — option-chain analytics, strategy builder, payoff graphs, broker-linked execution. Paid tiers. No custom code or backtests on your own rules.
- **Streak** (Zerodha) — no-code strategy backtesting and live deployment for equities/F&O; limited options-strategy backtesting; subscription.
- **TradingView** — charting/indicators/Pine scripting; Indian option-chain data limited; execution via partner brokers.
- **This project** — transparent, rule-based, locally run, with explicit risk-budget gating and a journal; no execution in v1; free with synthetic/CSV data; broker data read-only in Phase 2.
