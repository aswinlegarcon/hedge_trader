"""Technical indicators — pure pandas/numpy, no look-ahead.

Every function takes a validated OHLCV frame (or a price Series) and returns a
Series/DataFrame aligned to the input index. Rolling windows produce NaN until
enough history exists; callers must treat NaN as INSUFFICIENT DATA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --- Moving averages -------------------------------------------------------
def sma(series: pd.Series, window: int) -> pd.Series:
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (standard alpha = 2/(span+1)).

    The first ``span`` values are set to NaN so downstream code does not treat a
    poorly-seeded EMA as a valid reading.
    """
    if span < 1:
        raise ValueError("span must be >= 1")
    out = series.ewm(span=span, adjust=False, min_periods=span).mean()
    return out



def wilder_smooth(x: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seed with the simple mean of the first ``period`` valid
    values, then y_t = (y_{t-1} * (period - 1) + x_t) / period.

    Equivalent to an EWM with alpha = 1/period seeded by an SMA, which is how
    RSI and ATR are defined in Wilder's original work. Leading NaNs are skipped.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    valid = x.dropna()
    out = pd.Series(np.nan, index=x.index, dtype=float)
    if len(valid) < period:
        return out
    seed_pos = x.index.get_loc(valid.index[period - 1])
    seed = float(valid.iloc[:period].mean())
    rest = x.iloc[seed_pos + 1 :]
    seeded = pd.concat([pd.Series([seed], index=[x.index[seed_pos]]), rest])
    smoothed = seeded.ewm(alpha=1.0 / period, adjust=False).mean()
    out.iloc[seed_pos:] = smoothed.values
    return out

# --- Momentum --------------------------------------------------------------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (smoothed with alpha = 1/period)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder_smooth(gain, period)
    avg_loss = wilder_smooth(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    # When avg_loss is 0 and avg_gain > 0, RSI is 100 by definition.
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    if not fast < slow:
        raise ValueError("fast span must be < slow span")
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - sig
    return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})


# --- Volatility ------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    tr = true_range(df)
    return wilder_smooth(tr, period)


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width, "bb_pct_b": pct_b})


def realized_volatility(close: pd.Series, window: int = 20, periods_per_year: int = 252) -> pd.Series:
    """Annualised close-to-close realised volatility (as a fraction, e.g. 0.14)."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(periods_per_year)


def volatility_regime(df: pd.DataFrame, atr_period: int = 14, lookback: int = 252) -> pd.Series:
    """Classify volatility as LOW / NORMAL / HIGH / EXTREME using ATR% percentile
    over the trailing ``lookback`` bars (only past data is used)."""
    atr_pct = atr(df, atr_period) / df["close"]
    rank = atr_pct.rolling(window=lookback, min_periods=max(60, atr_period * 3)).rank(pct=True)

    def _label(p: float) -> str:
        if np.isnan(p):
            return "INSUFFICIENT DATA"
        if p < 0.25:
            return "LOW"
        if p < 0.75:
            return "NORMAL"
        if p < 0.95:
            return "HIGH"
        return "EXTREME"

    return rank.map(_label)


# --- Volume ----------------------------------------------------------------
def vwap(df: pd.DataFrame, session: str = "D") -> pd.Series:
    """Volume-weighted average price, reset each session (intraday data).

    For daily bars this reduces to a single-bar typical price and is NOT
    meaningful; callers should only use VWAP on intraday frames.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    grp = df.index.to_period(session) if isinstance(df.index, pd.DatetimeIndex) else None
    if grp is None:
        raise ValueError("VWAP requires a DatetimeIndex")
    cum_pv = pv.groupby(grp).cumsum()
    cum_v = df["volume"].groupby(grp).cumsum()
    return cum_pv / cum_v.replace(0.0, np.nan)


def volume_analysis(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    avg = df["volume"].rolling(window=window, min_periods=window).mean()
    ratio = df["volume"] / avg
    direction = np.sign(df["close"] - df["open"])
    obv = (np.sign(df["close"].diff()).fillna(0.0) * df["volume"]).cumsum()
    return pd.DataFrame({"vol_avg": avg, "vol_ratio": ratio, "bar_direction": direction, "obv": obv})


# --- Support / resistance --------------------------------------------------
def swing_points(df: pd.DataFrame, left: int = 5, right: int = 5) -> pd.DataFrame:
    """Mark confirmed swing highs/lows. A swing at bar i is only *known* at bar
    i+right, so the output includes a ``confirmed_at`` column to avoid look-ahead."""
    high, low = df["high"], df["low"]
    n = len(df)
    is_high = np.zeros(n, dtype=bool)
    is_low = np.zeros(n, dtype=bool)
    hv, lv = high.values, low.values
    for i in range(left, n - right):
        window_h = hv[i - left : i + right + 1]
        window_l = lv[i - left : i + right + 1]
        if hv[i] == window_h.max() and (window_h == hv[i]).sum() == 1:
            is_high[i] = True
        if lv[i] == window_l.min() and (window_l == lv[i]).sum() == 1:
            is_low[i] = True
    confirmed_at = pd.Series(df.index, index=df.index).shift(-right)
    return pd.DataFrame({"swing_high": is_high, "swing_low": is_low, "confirmed_at": confirmed_at}, index=df.index)


def support_resistance_levels(
    df: pd.DataFrame, as_of: pd.Timestamp | None = None, left: int = 5, right: int = 5, cluster_pct: float = 0.004, max_levels: int = 6
) -> dict[str, list[float]]:
    """Cluster confirmed swing highs/lows into levels. Only swings confirmed on or
    before ``as_of`` are used (no look-ahead)."""
    sp = swing_points(df, left, right)
    if as_of is not None:
        sp = sp[sp["confirmed_at"].notna() & (sp["confirmed_at"] <= as_of)]
    else:
        sp = sp[sp["confirmed_at"].notna()]
    highs = df.loc[sp.index[sp["swing_high"]], "high"].tolist()
    lows = df.loc[sp.index[sp["swing_low"]], "low"].tolist()

    def _cluster(vals: list[float]) -> list[float]:
        if not vals:
            return []
        vals = sorted(vals)
        clusters: list[list[float]] = [[vals[0]]]
        for v in vals[1:]:
            if abs(v - np.mean(clusters[-1])) / np.mean(clusters[-1]) <= cluster_pct:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        clusters.sort(key=len, reverse=True)
        return [round(float(np.mean(c)), 2) for c in clusters[:max_levels]]

    last_close = float(df["close"].loc[:as_of].iloc[-1]) if as_of is not None else float(df["close"].iloc[-1])
    resistance = sorted([lv for lv in _cluster(highs) if lv > last_close])
    support = sorted([lv for lv in _cluster(lows) if lv < last_close], reverse=True)
    return {"support": support, "resistance": resistance}


# --- Convenience: compute everything --------------------------------------
def compute_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return the input frame joined with the standard indicator set."""
    out = df.copy()
    close = out["close"]
    out["sma20"] = sma(close, 20)
    out["sma50"] = sma(close, 50)
    out["sma200"] = sma(close, 200)
    out["ema9"] = ema(close, 9)
    out["ema21"] = ema(close, 21)
    out["rsi14"] = rsi(close, 14)
    out = out.join(macd(close))
    out["atr14"] = atr(out, 14)
    out["atr_pct"] = out["atr14"] / close
    out = out.join(bollinger_bands(close))
    out["rv20"] = realized_volatility(close, 20)
    out["vol_regime"] = volatility_regime(out)
    out = out.join(volume_analysis(out))
    return out
