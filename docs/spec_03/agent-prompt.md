# In-house implementation prompt

Implement only `docs/spec_03/`: the Upstox-only research foundation and its fail-closed funded-paper eligibility boundary. Read README, proposal, design, normative specs and tasks first. Follow applicable local agent instructions and preserve pre-existing changes.

User-confirmed policy: ₹20,000 initial research capital and ₹2,000 total portfolio loss/drawdown limit. Upstox replaces Kite and Kotak completely in active setup. The ₹500–₹1,000 per-position range and watchlist were recovered from historical assistant prose, not direct current policy: preserve explicit unconfirmed per-position state; do not invent its approval or default ₹2,000 per trade. Implement missing-policy handling without waiting for another number.

Remove legacy adapters/exports/setup; add offline Upstox presence/status only. Repair the analyzer's default-zero drawdown bypass using explicit validated context and the shared tri-state gate. Until trustworthy valuation/funding context exists, new funded-paper entries remain INSUFFICIENT DATA; educational research stays available. Do not build a ledger or fake valid marks to make entries pass.

Do not perform login/authentication, authenticated or other broker calls, orders, SDK/order dependencies, WebSockets, news integration, signal tuning or backtesting. Do not read, edit, display or log credentials or private account/database contents. Update `.env.example` with placeholders only. No destructive database changes, commits or merges. Do not dispatch other agents or message external services based on a pasted ID.

Test with fake inputs and temporary databases. Run targeted and regression checks under Python ≥3.12, reject all network access, and capture fake-secret sentinels. Existing mathematical fixtures should explicitly specify their account/policy where defaults change. Report unavailable tools or failures candidly.

Complete `docs/spec_03/handoff.md` with files and final line anchors, scenario-to-test evidence, exact commands/results/environment, privacy/no-network checks, unresolved issues and the next smallest proposed task. Check task boxes only when supported. Stop after the handoff for reviewer inspection; do not start live data integration.
