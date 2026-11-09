"""Beginner-friendly explanations for every indicator shown in the UI."""

EXPLANATIONS: dict[str, str] = {
    "sma20": "20-day Simple Moving Average: the average close of the last 20 trading days (about one month). Price above it suggests short-term strength; below it, weakness.",
    "sma50": "50-day SMA: average of the last ~10 weeks. Widely watched as the medium-term trend line.",
    "sma200": "200-day SMA: average of the last ~10 months. Many institutions treat price above the 200-day as a bull market and below it as a bear market.",
    "ema9": "9-day Exponential Moving Average: like an SMA but weights recent days more heavily, so it reacts faster. Used for short-term momentum.",
    "ema21": "21-day EMA: a faster-reacting one-month trend line. EMA9 crossing above EMA21 is a common short-term bullish cue (and vice versa).",
    "rsi14": "Relative Strength Index (14): measures the speed of recent gains vs losses on a 0-100 scale. Above 70 = overbought (stretched up), below 30 = oversold (stretched down). It does not predict reversals on its own.",
    "macd": "MACD: difference between the 12-day and 26-day EMAs. Positive and rising = bullish momentum. The 'signal' line is a 9-day EMA of MACD; the histogram is the gap between them.",
    "atr14": "Average True Range (14): the typical daily price movement in points, including overnight gaps. Used to size stops and judge how 'wide' the market is moving. It says nothing about direction.",
    "bollinger": "Bollinger Bands: the 20-day SMA with bands ±2 standard deviations. Narrow bands = quiet market (often precedes a big move); price at a band = stretched relative to recent history.",
    "vwap": "VWAP: volume-weighted average price for the current session. Intraday traders treat it as the day's 'fair value'. Only meaningful on intraday bars.",
    "support_resistance": "Support/Resistance: price zones where the market repeatedly reversed. Derived from confirmed swing highs/lows clustered within ~0.4%. Levels are zones, not exact lines.",
    "volume": "Volume analysis: today's volume vs its 20-day average. A move on high volume (ratio > 1.5) has more participation behind it; a move on low volume is less trustworthy. NOTE: index 'volume' is aggregated constituent volume and some data sources omit it.",
    "vol_regime": "Volatility regime: where today's ATR% sits in the last year (LOW < 25th percentile, NORMAL, HIGH > 75th, EXTREME > 95th). Option sellers prefer HIGH-but-falling volatility; EXTREME regimes are dangerous for everyone.",
    "rv20": "Realised volatility (20-day, annualised): how much the index actually moved recently. Compare with India VIX (implied volatility) — when implied is well above realised, options are relatively expensive.",
}


def explain(key: str) -> str:
    return EXPLANATIONS.get(key, "No explanation available.")
