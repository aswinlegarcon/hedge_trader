# Original brief — NIFTY Signal Lab (received 2026-11-09)

> Verbatim copy of the user's Phase 1 brief, kept for traceability. See `SPEC_HANDOFF.md` for status.

# Project: NIFTY Signal Lab — AI-Assisted Indian Market Research & Options Trading System

You are my **Senior Quantitative Researcher, Algorithmic Trading Engineer, Financial Markets Analyst, and Python Architect**.

I want you to help me build a production-quality, beginner-friendly market intelligence and trading research platform.

**Your role is to design, implement, test, and explain the system—not just provide suggestions.**

## 1. My background and investment objectives

I am an Indian retail investor and a beginner in technical analysis and options strategies.

My financial parameters:

- Investment capital: ₹1,00,000
- Investment horizon: 6–12 months
- Maximum tolerable portfolio drawdown: 10% (₹10,000)
- Initial options risk budget: ₹1,000–₹2,000 per position
- Brokers: Zerodha Kite and Kotak Neo
- Primary market: NIFTY 50
- Secondary markets: BANK NIFTY, Indian equities, U.S. equities and ETFs
- Primary interest: Monthly expiry options, particularly hedged option-selling strategies

I am not interested in gambling, excessive leverage, or unrealistic profit guarantees.

My objective is to identify evidence-based opportunities, manage downside risk, understand market behavior, and learn systematic investing.

**Critical restriction: Version 1 must not place live trades. It must operate in read-only, backtesting, alerting, and paper-trading modes.**

## 2. Research the current ecosystem first

Before writing code, research and verify:

1. Zerodha Kite Connect API documentation, subscription pricing, historical market data, WebSocket capabilities, authentication, and rate limits.
2. Kotak Neo API capabilities and current documentation.
3. NSE option-chain availability, supported expiries, current contract lot sizes and strike intervals.
4. SEBI and exchange requirements relevant to retail API-based trading.
5. Available open-source Python libraries for technical indicators, backtesting, options pricing and risk analytics.
6. Existing platforms such as Sensibull, Streak and TradingView, including their capabilities and limitations.

Use official documentation whenever possible. Provide sources and dates.

Do not assume that historical API capabilities, option lot sizes, brokerage fees or regulatory rules are unchanged.

Do not scrape websites in violation of their terms or bypass access restrictions.

## 3. Build the application

Preferred technology stack:

- Python 3.12+
- Streamlit for the initial dashboard
- Pandas and NumPy for data analysis
- Plotly for interactive charts
- SQLite for the research journal
- pytest for automated tests
- Official broker SDKs where available
- Environment variables for credentials
- Modular architecture so brokers can be added or replaced

Use clean, maintainable, well-documented code.

The application must work without paid APIs initially by supporting clearly labeled sample data and imported historical CSV files.

Add live read-only market-data connectivity later, once API access is configured.

## 4. Market intelligence dashboard

Build a dashboard that monitors:

**Indian markets**
- NIFTY 50
- BANK NIFTY
- NIFTY Next 50
- India VIX
- Sector indices
- Market breadth

**Global markets**
- S&P 500
- Nasdaq
- U.S. Treasury yields
- USD/INR
- Brent crude oil
- Gold
- Relevant global economic events

**News intelligence**

Research reliable sources such as Moneycontrol, Reuters, NSE, RBI, SEBI, and official central-bank publications.

Build a news-analysis module that identifies:

- Upcoming economic announcements
- Earnings events
- RBI and Federal Reserve policy decisions
- Inflation releases
- Geopolitical developments
- Potential market-moving catalysts

Separate confirmed facts from interpretations.

Every news item must include its source, publication time, and a link.

Never invent live market information when data is unavailable.

## 5. Technical analysis engine

Implement and test:

- 20-day, 50-day and 200-day moving averages
- EMA 9 and EMA 21
- RSI 14
- MACD
- ATR 14
- Bollinger Bands
- VWAP for intraday data
- Support and resistance
- Volume analysis
- Market volatility regimes

Each indicator should include a beginner-friendly explanation.

For every potential signal, display:

- Market regime: bullish, bearish, neutral or uncertain
- Indicator values
- Signal conditions that passed
- Signal conditions that failed
- Data timestamp
- Reasons to avoid trading

Avoid arbitrary AI-generated confidence percentages.

## 6. Options research engine

Focus initially on NIFTY monthly expiry contracts.

Support:

- Bull put credit spreads
- Bear call credit spreads
- Iron condors for research
- Protective puts
- Covered calls where position size permits

For each candidate strategy, calculate:

- Exact option contracts and expiry
- Bid and ask prices
- Strike prices
- Net debit or credit
- Maximum theoretical profit
- Maximum contractual loss
- Breakeven points
- Reward-to-risk ratio
- Margin requirement, where verifiable
- Estimated transaction costs
- Days to expiry
- Implied volatility
- Delta, theta, gamma and vega
- Expiry payoff diagram

**Reject any position whose maximum contractual loss exceeds the configured trade-risk budget.**

Use executable-side quotes for conservative estimates rather than relying on last-traded prices.

Account for bid-ask spreads, liquidity, slippage and applicable taxes and fees.

If current option-chain data or margin information is unavailable, display "INSUFFICIENT DATA" rather than inventing an opportunity.

## 7. Signal engine

Build a transparent, rule-based signal system.

Possible outputs:

- BULLISH SETUP
- BEARISH SETUP
- NEUTRAL SETUP
- WAIT
- INSUFFICIENT DATA

Every signal must show:

1. What triggered the signal.
2. Which indicators support it.
3. Which indicators contradict it.
4. The market conditions under which it becomes invalid.
5. The strategy being evaluated.
6. The maximum possible loss.
7. The hypothetical entry and exit conditions.

Do not equate a technical signal with a profitable trade.

AI may explain signals and summarize news, but deterministic calculations must control financial metrics and risk checks.

## 8. Risk management

Portfolio capital: ₹1,00,000.

Maximum acceptable portfolio drawdown: ₹10,000.

Initial research risk per options position: ₹1,000–₹2,000.

Implement:

- Position sizing
- Portfolio exposure tracking
- Maximum-loss calculations
- Drawdown monitoring
- Correlation and concentration checks
- Liquidity checks
- Event-risk warnings
- Daily and weekly risk reports
- A configurable risk budget

The system must never claim that a stop-loss guarantees execution at a specified price.

Use theoretical maximum spread loss, including estimated costs, when checking position eligibility.

## 9. Backtesting and validation

Build a realistic backtesting framework.

Requirements:

- No look-ahead bias
- No survivorship bias where applicable
- Realistic transaction costs
- Conservative slippage assumptions
- Out-of-sample validation
- Walk-forward testing
- Different volatility regimes
- Historical options data when legally available

Calculate:

- Total return
- Maximum drawdown
- Win rate
- Profit factor
- Average profit and loss
- Expectancy per trade
- Sharpe ratio where appropriate
- Number of trades
- Exposure duration

Clearly distinguish between real historical option-chain backtests and approximations based on underlying index data.

Do not claim a strategy has been validated using synthetic or incomplete data.

## 10. Paper trading and learning journal

Build a paper-trading simulator.

Record:

- Date and time
- Instrument
- Strategy
- Market regime
- Entry thesis
- Hypothetical fill prices
- Position size
- Maximum risk
- Profit target
- Planned exit
- Actual simulated outcome
- Mistakes and lessons learned

Generate a daily research report and a weekly performance review.

Keep simulated performance completely separate from real investment results.

## 11. Application interface

Create the following dashboard pages:

1. Market Overview
2. Global News & Events
3. NIFTY Technical Analysis
4. Options Strategy Analyzer
5. Signal Monitor
6. Risk Dashboard
7. Backtesting Lab
8. Paper Trading Journal
9. Learning Center
10. Settings & API Connections

Show data freshness, connection status and source attribution prominently.

Use a clean, professional financial-dashboard design.

## 12. Security and operational requirements

- Never hardcode API keys.
- Never print or store access tokens in logs.
- Use `.env.example` with placeholder credentials.
- Exclude secrets from Git.
- Use read-only API operations initially.
- Do not implement live order submission in Version 1.
- Never request my broker password, PIN, OTP or API secret in chat.
- Do not use unofficial authentication bypasses.
- Provide clear error messages for missing or stale data.

## 13. Implementation plan

Do not attempt to build everything simultaneously.

**Phase 1 — Working MVP**

Build:

- Streamlit dashboard
- CSV/sample-data import
- NIFTY candlestick chart
- Moving averages, RSI and ATR
- Basic rule-based signal engine
- Defined-risk options payoff calculator
- Portfolio risk-budget calculator
- SQLite research journal
- Automated tests
- README and installation instructions

**Phase 2 — Data integration**

Integrate verified read-only broker APIs and supported news sources.

**Phase 3 — Backtesting**

Implement realistic historical analysis, performance reports and out-of-sample testing.

**Phase 4 — Paper trading**

Run simulated strategies and measure their performance.

Do not implement live automated execution without a separate design review and explicit authorization.

## 14. Your first task — Start coding now

First, inspect the available development environment.

Then:

1. Create the project folder and modular architecture.
2. Generate the initial working Streamlit application.
3. Implement the technical indicators and risk calculations.
4. Create a sample NIFTY dataset clearly marked as synthetic.
5. Implement the options payoff calculator using configurable contract lot sizes.
6. Add unit tests covering the mathematical calculations and risk limits.
7. Run the application and fix any errors.
8. Provide a screenshot or verified preview of the dashboard if the environment supports it.
9. Provide clear instructions for running the application locally.

Do not stop after producing an architecture document.

Actually create and test the MVP.

At the end, report:

- Files created
- Features implemented
- Tests executed and results
- Known limitations
- Data sources used
- Next development milestone

**Success criterion:** I should be able to run the application, inspect NIFTY charts, calculate indicators, evaluate hypothetical option spreads, and maintain a research journal without placing any real trade.

Start with Phase 1 now.
