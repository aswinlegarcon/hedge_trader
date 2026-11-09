import io

import pytest

from nifty_lab.data import DataKind, DataValidationError, generate_synthetic_nifty, load_ohlcv_csv, write_sample_csv


def test_synthetic_is_labelled_and_deterministic():
    a = generate_synthetic_nifty(seed=42)
    b = generate_synthetic_nifty(seed=42)
    assert a.provenance.kind == DataKind.SYNTHETIC
    assert a.provenance.is_synthetic
    assert "SYNTHETIC" in a.provenance.notes
    assert a.df.equals(b.df)
    assert (a.df["high"] >= a.df[["open", "close"]].max(axis=1)).all()
    assert (a.df["low"] <= a.df[["open", "close"]].min(axis=1)).all()


def test_csv_roundtrip(tmp_path):
    p = tmp_path / "s.csv"
    write_sample_csv(str(p), seed=3)
    txt = p.read_text()
    assert txt.startswith("# SYNTHETIC DATA")
    ds = load_ohlcv_csv(p, symbol="NIFTY")
    assert ds.provenance.kind == DataKind.IMPORTED_CSV
    assert len(ds.df) == len(generate_synthetic_nifty(seed=3).df)


def test_csv_aliases_and_indian_formats():
    csv = "Date,Open,High,Low,Close,Shares Traded\n01-02-2024,\"22,000.5\",\"22,100\",\"21,900\",\"22,050\",\"1,000\"\n02-02-2024,22050,22200,22000,22150,1200\n"
    ds = load_ohlcv_csv(io.StringIO(csv))
    assert ds.df["close"].iloc[0] == pytest.approx(22050.0)
    assert ds.df["volume"].iloc[0] == 1000
    assert ds.df.index[0].month == 2  # day-first parsing applied


def test_csv_missing_columns():
    with pytest.raises(DataValidationError):
        load_ohlcv_csv(io.StringIO("date,close\n2024-01-01,100\n"))
