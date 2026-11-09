import numpy as np
import pandas as pd
import pytest

from nifty_lab.data import generate_synthetic_nifty, validate_ohlcv, DataValidationError
from nifty_lab.indicators import atr, bollinger_bands, compute_indicator_frame, ema, macd, rsi, sma, support_resistance_levels, swing_points, true_range, volatility_regime, vwap


@pytest.fixture(scope="module")
def ds():
    return generate_synthetic_nifty(seed=7)


def test_sma_matches_manual():
    s = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    out = sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[-1] == pytest.approx(5.0)


def test_ema_recursion():
    s = pd.Series([10, 11, 12, 13, 14, 15], dtype=float)
    out = ema(s, 3)
    alpha = 2 / 4
    # pandas ewm(adjust=False) seeds with first value; verify recursion from the seed
    manual = s.iloc[0]
    for v in s.iloc[1:]:
        manual = alpha * v + (1 - alpha) * manual
    assert out.iloc[-1] == pytest.approx(manual)
    assert np.isnan(out.iloc[1])  # min_periods masks early values


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    r = rsi(up, 14)
    assert r.dropna().between(0, 100).all()
    assert r.iloc[-1] == pytest.approx(100.0)
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert rsi(down, 14).iloc[-1] == pytest.approx(0.0)
    flat = pd.Series(np.full(40, 100.0))
    assert rsi(flat, 14).iloc[-1] == pytest.approx(50.0)


def test_rsi_known_value():
    # Classic Wilder example (14 closes) — RSI ≈ 70.53 on the 15th bar
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    r = rsi(pd.Series(closes), 14)
    assert r.iloc[-1] == pytest.approx(70.53, abs=0.5)


def test_macd_shape_and_zero_on_flat():
    flat = pd.Series(np.full(60, 100.0))
    m = macd(flat)
    assert list(m.columns) == ["macd", "signal", "hist"]
    assert m.dropna().abs().max().max() == pytest.approx(0.0)


def test_true_range_includes_gaps():
    df = pd.DataFrame({"open": [100, 110], "high": [101, 112], "low": [99, 109], "close": [100, 111], "volume": [1, 1]}, index=pd.date_range("2024-01-01", periods=2))
    tr = true_range(df)
    assert tr.iloc[1] == pytest.approx(12.0)  # high - prev close dominates


def test_atr_positive_and_scale(ds):
    a = atr(ds.df, 14)
    assert (a.dropna() > 0).all()
    assert a.iloc[-1] < ds.df["close"].iloc[-1] * 0.1


def test_bollinger_symmetry(ds):
    bb = bollinger_bands(ds.df["close"])
    valid = bb.dropna()
    assert np.allclose(valid["bb_upper"] - valid["bb_mid"], valid["bb_mid"] - valid["bb_lower"])
    assert valid["bb_pct_b"].between(-0.5, 1.5).all()


def test_vwap_resets_each_day():
    idx = pd.to_datetime(["2024-01-01 09:15", "2024-01-01 09:30", "2024-01-02 09:15"])
    df = pd.DataFrame({"open": [100, 100, 200], "high": [100, 100, 200], "low": [100, 100, 200], "close": [100, 100, 200], "volume": [10, 10, 10]}, index=idx)
    v = vwap(df)
    assert v.iloc[1] == pytest.approx(100.0)
    assert v.iloc[2] == pytest.approx(200.0)


def test_volatility_regime_labels(ds):
    vr = volatility_regime(ds.df)
    assert set(vr.unique()) <= {"LOW", "NORMAL", "HIGH", "EXTREME", "INSUFFICIENT DATA"}
    assert vr.iloc[-1] != "INSUFFICIENT DATA"


def test_swing_points_no_lookahead(ds):
    sp = swing_points(ds.df, 5, 5)
    confirmed = sp.dropna(subset=["confirmed_at"])
    assert (confirmed["confirmed_at"] >= confirmed.index).all()
    # the last 5 bars cannot be confirmed swings
    assert not sp["swing_high"].iloc[-5:].any()


def test_support_resistance_sides(ds):
    lv = support_resistance_levels(ds.df, as_of=ds.df.index[-1])
    last = ds.df["close"].iloc[-1]
    assert all(s < last for s in lv["support"])
    assert all(r > last for r in lv["resistance"])


def test_indicator_frame_columns(ds):
    ind = compute_indicator_frame(ds.df)
    for c in ["sma20", "sma50", "sma200", "ema9", "ema21", "rsi14", "macd", "signal", "hist", "atr14", "bb_upper", "bb_lower", "rv20", "vol_regime", "vol_ratio"]:
        assert c in ind.columns
    assert len(ind) == len(ds.df)


def test_validate_rejects_bad_bars():
    idx = pd.date_range("2024-01-01", periods=2)
    bad = pd.DataFrame({"open": [100, 100], "high": [99, 101], "low": [98, 99], "close": [100, 100], "volume": [1, 1]}, index=idx)
    with pytest.raises(DataValidationError):
        validate_ohlcv(bad)
    with pytest.raises(DataValidationError):
        validate_ohlcv(pd.DataFrame())
