# Spec 02 — Financial-core reconciliation before data integration

**Project:** NIFTY Signal Lab (`hedge_trader`) · **Date:** 2026-11-09
**Status:** DRAFT — user review required; implementation NOT authorized
**Baseline:** `d104f6b2bdee282568b9fd0416a53743112b8464`
**References:** [Original brief](ORIGINAL_SPEC.md), [handoff](SPEC_HANDOFF.md), [architecture](ARCHITECTURE.md), [research](RESEARCH.md).

Purpose: reconcile the shipped Phase 1 with the revised implementation plan and settle financial contracts before connecting real data. This change contains specifications only. Approval of this document permits a separately scoped implementation proposal; it does not itself authorize coding, live trading, or merging.

---

## 1. Sources and interpretation

No `spec1` file or OpenSpec directory exists in the tracked baseline. “Spec 1” is interpreted as the original brief plus Phase 1 completion claims in `SPEC_HANDOFF.md`, not an invented missing document. This spec follows the repository's numbered Markdown sections, traceability tables, interfaces, decisions and acceptance gates.

Additional comparison sources recovered from the referenced conversation:
- `implementation-plan-v2.md`, attachment to the laptop-handoff message: M1 financial engine/indicators/sample data/tests; M2 dashboard/journal; M3 signals; M4 integrations. Contains 60 enumerated proposed tests.
- `NIFTY_Signal_Lab_Implementation_Plan.md`, original attached plan, and the prior assistant review: prioritize financial correctness, remove minimum risk, validate quotes/contracts, separate simulated data and require independent test evidence.
- Prior review and v2 are design inputs, not proof of completed implementation. Original attachments remain in the conversation; no private records or credentials are copied into the public repository.

Precedence: current spec-first instruction and no-execution restriction govern this task. Preserve original verbatim text. Do not execute its historical “start coding now” instruction. The v2 examples contain unresolved defects and must not be copied as implementation contracts.

## 2. Discrepancies and disposition

| ID | Evidence / discrepancy | Next disposition |
|---|---|---|
| G01 | Handoff §§1,6 marks Phase 1 complete and moves to integrations; v2 requires financial-core gate first. Ten UI pages already exist. | Keep existing UI; validate the core before any Phase 2 expansion. No rewrite to the v2 folder layout. |
| G02 | Handoff reports 47 passing tests; v2 enumerates 60 scenarios. Neither count establishes coverage or current passing status. | Map every v2 scenario to an existing test, a new test proposal or justified correction. Record actual execution later. No claim tests were run in this documentation task. |
| G03 | `PortfolioSnapshot` has capital, realised P&L and default-zero marks, but no cash ledger, cash flows, fees or reserved margin. Handoff's “done” accounting claim is broader than this model. | Define ledger and valuation reconciliation under §3; unknown valuation must block eligibility. |
| G04 | V2 books premium into cash then defines equity as cash + unrealised P&L: potential double counting. Fee transactions are negative but total fees sums their signed amounts; closed-position `realized_pnl` and `risk_config` are referenced without complete definitions. | One signed ledger, one valuation identity, positive fee-reporting convention. No copied pseudocode. |
| G05 | V2 claims peak equity alone handles flows, uses literal 0.10, and lets deposits enlarge risk. Original budget is ₹10,000. Existing gate takes realised drawdown instead of a complete valued snapshot. | Approve the conservative proposed policy in §3. External flows cannot reset losses or expand risk authorization. |
| G06 | Current gate retains “below minimum research size” warning; v2/prior review remove minimum risk entirely. | Remove minimum requirement and pressure to increase risk; retain upper bound ₹2,000. |
| G07 | Handoff calls quote-book mapping sufficient for live chains; key `(type,strike)` omits expiry/underlying, quote time and provenance. | Quote identity/freshness contract §4 must precede a live producer. |
| G08 | Handoff accepts fixed verified-on contract/fee values and estimates exit fees at entry premium; v2 asks date-effective registries but supplies approximate dates and generic sources. | Versioned, date/contract-effective metadata; fee scenarios and provenance. No claimed current-rate verification in this spec. |
| G09 | `validate_ohlcv` silently drops duplicates and fills missing volume with zero; provenance has no explicit per-bar completeness, interval or exchange timezone field. | Preserve quality warnings and block affected computations; never silently convert unknown volume into valid volume evidence. |
| G10 | Handoff directional rule voting differs from v2's grouped votes. V2 calls groups “independent” without empirical support. | Document both as unvalidated hypotheses. Grouping reduces duplicate evidence but does not prove independence; defer strategy tuning to validation. |
| G11 | Covered-call/protective-put builders describe index/futures/ETF-equivalent exposure. These are not interchangeable executable holdings. | Educational index proxies only; require exact matched instrument, quantity and funding for any eligible paper position. |
| G12 | Handoff's gate interface does not carry margin, concentration, count or valuation quality; portfolio evaluator reports some issues separately. | One eligibility decision must consume every required check, not merely display warnings. |
| G13 | Global tiles, news, broker data, backtesting and scheduled paper runs remain deferred per handoff. | Explicit backlog, not missing work to implement now (§7). |

These are document and bounded current-source observations, not an exhaustive code/security audit. Inspected source anchors: `nifty_lab/risk/{portfolio,budget}.py`, `nifty_lab/options/strategies.py`, `nifty_lab/data/base.py`, `tests/test_risk.py`. No application source is changed by this proposal.

## 3. Proposed accounting and risk contract

### 3.1 Ledger and valuation

All monetary amounts are INR; premiums are INR per underlying unit; quantity = positive integer lots × contract lot size. Use decimal amounts or integer paise with an explicit rounding policy. Reject NaN, infinity and negative quantities before arithmetic.

Each event has a unique ID, timezone-aware event time, paper-account ID, type, signed cash amount, position reference where relevant, and source. Positive amounts increase cash. Fees reduce cash; displayed cumulative fees are positive. Replaying an event ID must not change balances twice. Initial funding is recorded once; deposits, withdrawals, premiums, fees and close/settlement flows are distinct.

Canonical identity: **equity = cash + signed market value of open assets and liabilities**. Long market value is positive; short option liability is negative. Reserved margin reduces available cash, never equity. Realised/unrealised P&L are reporting decompositions and are not added to cash again. Equity must reconcile to initial funding + external net flows + total net P&L. Entry, close and expiry charge each fee once. Exit-cost estimates are reserves for eligibility, not posted paid fees.

Missing/stale marks are unknown, not zero. Show last known valuation and its time for reference; block new eligible paper positions until required valuations and funding inputs are valid. Persist high-water marks and ledger history across restart. Reject withdrawals above unreserved available cash and any withdrawal that violates the risk floor.

### 3.2 Drawdown policy — proposed for explicit review

Keep initial authorized capital C0 = ₹100,000, hard loss/drawdown budget ₹10,000 and per-position maximum ₹2,000. No minimum risk. Deposits do not enlarge these authorizations automatically.

For this fixed-capital research account, define cumulative external net flows F (excluding initial funding), actual equity E, and additive flow-adjusted performance equity A = E − F. Persist H = max(previous H, A), initially ₹100,000. Performance drawdown D = max(0, H − A); initial-capital loss = max(0, C0 − A), reported separately. Proposed drawdown allowance L = min(₹10,000, 10% × H). This deliberately retains the original rupee ceiling rather than adopting v2's growing budget. This additive measure is not a time-weighted investment return; a future variable-capital account requires a separate unitized-return design.

Changing risk limits or capital authorization requires review. Flows alone must not create/reset a performance high-water mark. At D ≥ L, block new positions; never imply existing risk disappears or that stops guarantee this tolerance.

### 3.3 Whole-portfolio eligibility

Require a complete valued snapshot; no caller-supplied default-zero drawdown may bypass the gate. Let R_i be each open position's total entry-to-worst-outcome net loss including all paid/estimated costs. Let P_i be that position's current net P&L on the same basis. Remaining loss from current equity is B_i = max(0, R_i + P_i). This avoids subtracting already incurred losses twice and reserves surrender of current profits. Reject inconsistent bounds/unknown inputs.

For a candidate use B_new = its net worst loss, including entry/exit cost and slippage reserves. Require D + sum(B_i) + B_new ≤ L, alongside the fixed initial loss floor. Evaluate all independent portfolio, count, concentration/correlation and cash/margin limits; preserve existing stricter configured caps unless separately approved. No diversification discount across correlated NIFTY positions. A warning cannot substitute for a blocking funding/risk check.

Margin is neither maximum loss nor cash. Educational payoff may remain available when margin is unknown, but funded-paper eligibility is `INSUFFICIENT DATA`. An explicitly sourced synthetic margin scenario may be used only in a clearly labelled simulation. No external broker connection is required for this milestone.

## 4. Options, costs and data contracts

- Keep existing `nifty_lab/` modules and strategy-specific payoffs. Mathematical core remains deterministic and independent of UI/broker I/O.
- Validate full leg identity: underlying, exact expiry, option type, strike, side, lot size and matched quantity; strategy-specific strike ordering. Reject invalid leg count before indexing legs. Reject nonfinite values, malformed dates, unequal vertical quantities, crossed quotes, and missing executable sides.
- Sell at bid, buy at ask; preserve actual exchange/source timestamp, retrieval time, timezone, origin and complete contract ID. Missing/future/stale timestamps block current eligibility. Proposed quote TTL: 60 seconds and maximum leg timestamp skew 5 seconds for current research; historical fixtures use an explicit historical evaluation clock. Both thresholds require review before live data integration.
- Synthetic/manual/historical calculations remain visibly labelled and cannot become current-market opportunities. Missing volume, duplicate bars, gaps, incomplete candles and timezone ambiguity require explicit diagnostics; only complete valid historical bars feed signals. Market calendars/interval determine gaps rather than elapsed calendar days alone.
- Registry records require source URL/document ID, verification date, applicability interval and contract/expiry applicability. Reject overlaps/missing applicability for current-market use. Keep synthetic fixture specifications independent from real contract claims.
- Fees distinguish entry, hypothetical early close and expiry/exercise scenarios, including tax bases and effective dates. Do not assert entry premiums bound exit turnover costs. Specify conservative exit-cost/slippage assumptions and itemized calculations. Unknown required fee inputs block eligibility; theoretical payoff remains labelled gross.
- Expiry payoff is not a guarantee of executable exit price. Derive extrema/breakevens from all strike breakpoints and tail slopes, not a finite chart grid. Show unbounded profit/loss explicitly, never a grid-derived cap.
- Unequal-wing condors use the wider wing minus total credit. Zero credit/debit cases preserve signs. Covered calls retain underlying downside; protective puts require complete hedge quantities. Unsupported index proxy/futures/ETF equivalence remains educational and ineligible as a funded strategy.
- Proposed interface evolution: gate accepts validated candidate + complete portfolio snapshot + risk policy + valuation context and returns ELIGIBLE / REJECTED / INSUFFICIENT DATA with all reasons. Extend adapters additively; do not claim the handoff's existing interface already meets this contract.

## 5. Required acceptance evidence for a later implementation

| ID | Independent fixture / scenario | Required result |
|---|---|---|
| A01 | Start ₹100,000; sell option for ₹1,000 with liability ₹1,000 | Cash ₹101,000; equity ₹100,000 before fees. Buy it back for ₹700 with ₹40 total fees: final equity ₹100,260. No duplicate premium/P&L. |
| A02 | Reserve ₹20,000 margin from ₹100,000 cash | Equity stays ₹100,000; available cash ₹80,000. Release once on close. Duplicate events are idempotent. |
| A03 | A falls to ₹95,000; deposit ₹20,000 then withdraw ₹10,000 | E becomes ₹115,000 then ₹105,000; A stays ₹95,000 and D stays ₹5,000. Restart preserves H. |
| A04 | A peaks at ₹110,000 then falls to ₹100,000 | D = ₹10,000; initial loss = zero; new risk blocked under proposed rupee ceiling. |
| A05 | Open position R=₹2,000, current P=−₹1,500; D=₹1,500 | Remaining risk B=₹500; total downside from peak ₹2,000, not ₹3,500. Positive mark P=₹500 gives B=₹2,500. |
| A06 | Candidate cost-inclusive risk ₹2,000 / ₹2,000.01 / ₹500 | Within maximum / rejected / no minimum-size warning, subject to all other gates. Boundary tests at portfolio cap and D=L. |
| A07 | Hypothetical 50-point credit vertical, quantity 65, credit 20, explicit fixed all-in cost 100 | Gross profit ₹1,300; gross loss ₹1,950; net loss ₹2,050 → rejected. Fixture is not current exchange metadata. |
| A08 | All five strategies; unequal wings; multiple lots; zero-credit/debit; strike boundaries/tails | Hand-derived payoff, maximum loss/profit and gross/net breakevens; unbounded tails reported. No grid-based extrema. |
| A09 | Missing, crossed, stale/future quotes; unequal quantities/expiry; NaN/inf; invalid leg count | Typed diagnostic and no eligible candidate; no crash or silent substitution. |
| A10 | Unknown mark/margin/fee schedule; insufficient cash; correlated concentration/count breach | Gate fails closed with all relevant reasons. No eligible UI path bypasses it. |
| A11 | Duplicate/gapped/incomplete candles, absent volume, synthetic file relabelled as CSV | Provenance/quality limitations persist; affected signals are WAIT/INSUFFICIENT DATA, never current opportunities. |
| A12 | Each fee event, close vs expiry, replay and journal reopen | Ledger identities reconcile; private database is never committed; backward migration preserves existing paper rows and backups. |

Map v2 tests 1–60 into a coverage matrix with exact test identifiers and outcomes. Correct flawed expectations: flat-series Bollinger bands may be equal; ATM delta is parameter-dependent, not universally 0.50; deposit/withdrawal tests must use an explicit flow policy; stale quotes must block current eligibility rather than merely warn. Indicator tests should use independent numeric fixtures, including flat/zero-volume and warm-up cases. Grouping indicators does not establish a trading edge.

A later implementation review must supply reproducible environment/version details, commands, actual test output, coverage matrix and unresolved failures. Test count alone is not a gate. Do not install dependencies or claim passing tests for this documentation change.

## 6. Review workflow and tasks

1. Review this proposal, especially rupee ceiling vs growing peak budget, additive flow adjustment, quote thresholds, funding treatment and migration requirements. Resolve decisions in the spec before code.
2. After explicit approval, propose one bounded financial-core implementation task with affected interfaces, migration/backups and acceptance cases. No broker, news or dashboard expansion in that task.
3. Run independent math and regression tests; verify existing synthetic/CSV workflows and paper journal compatibility; attach actual results for review.
4. Obtain approval of the financial-core evidence before preparing the next read-only integration spec. Do not infer approval from passing tests.
5. No live order methods, execution flags, credential collection, unattended trades or order-routing dependencies. No merge without explicit user approval.

Documentation review checklist: source traceability present; original brief unchanged; all G01–G13 dispositions explicit; local links resolve; diff contains only this draft. This proposal does not retroactively certify the shipped MVP.

## 7. Deferred backlog and decisions

Kite-first vs Kotak, supported official SDK capabilities, daily token storage/login, licensed global sources, VIX/breadth, official event feed licensing/polling/deduplication, append-only chain snapshots, margin API access, rate limits/retries, instrument drift, holiday-aware expiry and secondary markets remain the next integration spec's decisions. Re-verify official current documentation then; do not rely on the handoff's dated rates/SDK claims. No external credentials needed here.

Backtesting must later cover actual historical options vs underlying proxies, transaction costs, slippage, unseen data, walk-forward/regime evaluation and baseline comparisons. Scheduled paper performance review follows validation. Existing on-demand reports do not satisfy scheduled reporting. Live trading remains outside Version 1 and requires a separate design and explicit authorization.
