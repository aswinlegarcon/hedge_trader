# Spec 03 — Upstox-only research foundation

Date: 2026-11-13 (Asia/Kolkata). Status: IMPLEMENTED — see [handoff.md](handoff.md) for evidence; awaiting reviewer sign-off (no live integration).
Baseline inspected: `d6af5451c6c224a0a2e9b468741d27e7d94a1af8`.

This is an OpenSpec-style change package under the user-requested `docs/spec_03/` convention. It is not an initialized OpenSpec CLI workspace and no CLI validation is claimed.

Read in order:
1. [Proposal](proposal.md)
2. [Design and policy decisions](design.md)
3. [Normative requirements and scenarios](specs/research-foundation/spec.md)
4. [Implementation checklist](tasks.md)
5. [Agent prompt](agent-prompt.md)
6. [Handoff template](handoff.md)

The authoring task changes documentation only. Implementation belongs to the in-house agent. Do not commit, merge, connect a broker, or execute trades as part of writing this package.

## Source precedence

- Latest direct user instructions: ₹20,000 initial capital; ₹2,000 total portfolio loss limit (10%, explicitly confirmed); Upstox replaces Kite and Kotak Neo; specs here, implementation and handoff by in-house agent.
- Readable referenced chat `6ae8cd79-f8a8-8320-8035-4e619421bde9`: older assistant recap mentions ₹20,500, ₹500–₹1,000 planned position risk, and ICICI Bank / Gold BeES / Bharti Airtel / L&T. These are historical context, not independently confirmed policy or current recommendations. The latest ₹20,000 overrides ₹20,500. Do not invent a separate ₹500 reserve.
- Supplied ID `846bab3a-ebb1-455c-9e6c-e4d9f7c78353`: read attempted; no readable chat found. It is not verified agent identity or dispatch authorization.
- Existing [Spec 02](../SPEC_02_FINANCIAL_CORE_REVIEW.md) remains a draft and backlog source. This package supersedes its capital/broker assumptions and narrows the immediate task. It does not approve every accounting proposal in that draft.
- Preserve [original brief](../ORIGINAL_SPEC.md), [historical handoff](../SPEC_HANDOFF.md) and [research](../RESEARCH.md) as historical records. Current setup instructions must identify this package as the revised direction.

## Subsequent sequence — not authorized by this implementation prompt

1. Review this implementation's handoff and remaining financial-core issues.
2. Separate spec: offline Upstox instrument/candle normalization, provenance, completeness and quality diagnostics; then tightly bounded read-only historical/intraday HTTP access, authentication and error handling.
3. Separate spec: current quotes, equity/ETF research, Upstox-specific cost models and cash sizing. Options chains and funded strategy eligibility require their own full identity, funding and risk contracts.
4. Licensed event/news integration, realistic backtesting and paper-performance validation. No predictive accuracy claim before evidence.

Upstox official references consulted 2026-11-13: [authentication](https://upstox.com/developer/api-documentation/authentication/), [V3 historical candles](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/). These document OAuth and candle capabilities, not proof of this account's API entitlements or a working connection. Reverify when drafting the network integration.
