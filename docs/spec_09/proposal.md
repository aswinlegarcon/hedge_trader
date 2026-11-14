# Change: daily research loop and versioned strategy evidence

## Why
The user wants a tool that considers pre-market and post-market reports, observes live reactions and index leadership, tests strategies, and improves from recorded evidence. Charts and a Live selector do not meet this goal. Emotional decisions should be reduced through consistent rules, visible uncertainty, no-trade outcomes and reviewable history.

## First bounded delivery
Implement a research-only daily session record and a versioned strategy register/evaluation report. Reuse existing Upstox completed candles and watchlist; no new order routes. Show existing news and macro coverage limitations. Record a pre-market hypothesis, observable invalidation and end-of-day review without rewriting the original hypothesis. Introduce one explicitly experimental cash-equity strategy, freeze its rules before evaluation, and report out-of-sample results with costs or INSUFFICIENT EVIDENCE.

## Roadmap, not acceptance scope for the first delivery
1. Finish Spec 08 gate/ledger/confirmation corrections; complete paper close/cancel and reconciliation.
2. First Spec 09 daily research loop and strategy evidence.
3. Expand sourced market context: actual NIFTY price, breadth, point-in-time constituent weights, synchronized constituent returns and event reaction tracking. Add feeds only with explicit provenance/access and separate scoped specs.
4. Forward-paper candidate execution with accepted ledger and eligible strategies; compare observed fills to assumptions.
5. Review full Live prerequisites and connect user-confirmed orders under existing risk policy.
6. NIFTY option strategy evaluation using actual historical option quotes, spreads, costs and contract metadata. Individual-stock options require separate corporate-action, expiry and physical-settlement specifications; they are not enabled by this proposal.

No guaranteed performance, unattended orders, automatic risk increases or self-modifying live strategy. Published/book/web strategies are hypotheses until independently tested. Data access, licensing, quality and cost can limit available research; do not promise that all web information is usable or free.
