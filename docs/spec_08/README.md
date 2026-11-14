# Spec 08 — Paper and live execution for stocks and NIFTY long options

Date: 2026-11-13 (Asia/Kolkata). Status: READY FOR IMPLEMENTATION; NOT IMPLEMENTED.

OpenSpec-style package under `docs/spec_08/`. Read [proposal](proposal.md), [design](design.md), [requirements](specs/trade-execution/spec.md), [tasks](tasks.md), [agent prompt](agent-prompt.md) and [handoff](handoff.md).

## Changed authorization

The latest user explicitly requests both paper and actual trading, including stocks and NIFTY options, and delegates the initial risk-policy decision to the analyst. This supersedes the earlier blanket no-live-execution product requirement. It authorizes implementing live capability; it is NOT an instruction to place any particular live order, conduct a live-money test, auto-select trades or trade unattended.

The application must support real Paper and Live workflows, not a permanently hardcoded live=False stub. Sandbox is a separate integration-test mode. A user must personally preview and confirm each live order in the application. Implementation agents must never click/send a live place/modify/cancel order as verification.

Initial executable instruments: unleveraged long NSE cash equities/ETFs and bought NIFTY CE/PE, with sell-to-close only against reconciled owned quantity. Multi-leg NIFTY spreads remain a follow-on execution task because hedge sequencing/partial fills need their own contract. Existing spread calculators remain usable, explicitly not executable in this release. No naked shorts/futures/MTF.

## Initial policy chosen under delegated authority

Profile `execution-v1`: ₹20,000 initial allocation per separate paper/live account; ₹2,000 fixed portfolio drawdown/loss threshold for stopping new risk; ₹400 per-position risk budget, no minimum; preserve interim three-position / ₹1,200 aggregate / ₹800 per-underlying limits. These are initial operating limits, not validated optimal sizing or guarantees of realised loss caps. Stocks use planned stop-loss risk plus costs; options use premium-at-risk plus all required costs. Display stock full-capital downside separately. Profits/deposits do not automatically increase authorization.

[CME's 2% rule explanation](https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule) describes percentage sizing but calls the threshold arbitrary. ₹400 is an analyst-selected initial 2% ceiling, not research proving a winning strategy. [Investor.gov options bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-63) describes premium-at-risk for buyers; use Upstox/NSE metadata for Indian contract details, not US contract examples.

## Upstox primary sources reviewed 2026-11-13

- [Sandbox](https://upstox.com/developer/api-documentation/sandbox/) and [sandbox setup](https://upstox.com/developer/api-documentation/build-using-sandbox/): separate sandbox app/token, phased API support; use for order integration tests, not proof of realistic fill/P&L performance.
- [Place Order V3](https://upstox.com/developer/api-documentation/v3/place-order/), [order status](https://upstox.com/developer/api-documentation/get-order-details/), [order trades](https://upstox.com/developer/api-documentation/get-trades-by-order/): request acceptance and actual fills are different; maintain a durable lifecycle.
- [Full quotes](https://upstox.com/developer/api-documentation/get-full-market-quote/), [NIFTY option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/), [funds](https://upstox.com/developer/api-documentation/get-user-fund-margin/), [margin estimate](https://upstox.com/developer/api-documentation/margin/), [brokerage estimate](https://upstox.com/developer/api-documentation/get-brokerage/).
- [API-order static IP/app requirements](https://upstox.com/developer/api-documentation/announcements/algo-trading-circular/): market-data access alone does not demonstrate order readiness. Do not update static IPs or invalidate tokens automatically. Determine applicable app/Algo-Name settings from current endpoint documentation, not blanket assumptions.

Read-only research/spec07 macro limitations remain visible and need not block building this execution feature. Known financial-gate defects must be fixed before new trade submission, not deferred behind a Live switch.
