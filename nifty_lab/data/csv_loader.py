"""Import historical OHLCV CSV files (e.g. exported from a broker or NSE).

Accepted layouts (case-insensitive headers):
- date|timestamp|datetime, open, high, low, close, volume (volume optional -> 0)
- Comment lines starting with '#' are ignored.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .base import DataKind, DataProvenance, DataValidationError, MarketDataset

_DATE_CANDIDATES = ("date", "timestamp", "datetime", "time")
_ALIASES = {
    "open": ("open", "o", "open price"),
    "high": ("high", "h", "high price"),
    "low": ("low", "l", "low price"),
    "close": ("close", "c", "close price", "adj close", "ltp"),
    "volume": ("volume", "vol", "v", "shares traded", "qty"),
}


def _match(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def load_ohlcv_csv(source: str | Path | io.StringIO | io.BytesIO, symbol: str = "IMPORT") -> MarketDataset:
    try:
        raw = pd.read_csv(source, comment="#")
    except Exception as exc:  # pragma: no cover - pandas error passthrough
        raise DataValidationError(f"Could not parse CSV: {exc}") from exc
    if raw.empty:
        raise DataValidationError("CSV has no rows")

    cols = list(raw.columns)
    date_col = _match(cols, _DATE_CANDIDATES)
    if date_col is None:
        raise DataValidationError(f"No date column found. Columns: {cols}")

    renamed: dict[str, str] = {}
    for target, aliases in _ALIASES.items():
        found = _match(cols, aliases)
        if found is not None:
            renamed[found] = target
    df = raw.rename(columns=renamed)
    if "volume" not in df.columns:
        df["volume"] = 0.0

    missing = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if missing:
        raise DataValidationError(f"CSV is missing required columns {missing}; found {cols}")

    # Numeric columns in Indian exports often contain thousands separators.
    for c in ("open", "high", "low", "close", "volume"):
        if not pd.api.types.is_numeric_dtype(df[c]):
            cleaned = df[c].astype(str).str.strip().str.replace(",", "", regex=False)
            df[c] = cleaned.where(cleaned != "-", "0")  # NSE exports use '-' for no volume

    raw_dates = df[date_col].astype(str).str.strip()
    # Indian exports are usually dd-mm-yyyy; ISO (yyyy-mm-dd) is unambiguous either way.
    dmy_like = raw_dates.str.match(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}").mean() > 0.5
    ts = pd.to_datetime(raw_dates, errors="coerce", dayfirst=dmy_like, format="mixed")
    if ts.isna().mean() > 0.5:  # retry with the opposite convention
        ts = pd.to_datetime(raw_dates, errors="coerce", dayfirst=not dmy_like, format="mixed")
    if ts.isna().any():
        raise DataValidationError(f"{int(ts.isna().sum())} rows have unparseable dates")
    df.index = pd.DatetimeIndex(ts)
    df.index.name = "date"

    name = source if isinstance(source, (str, Path)) else "uploaded file"
    ds = MarketDataset(
        df=df,
        provenance=DataProvenance(
            kind=DataKind.IMPORTED_CSV,
            source=str(name),
            symbol=symbol,
            retrieved_at=datetime.now(timezone.utc),
            last_bar_time=df.index.max().to_pydatetime().replace(tzinfo=timezone.utc),
            notes="User-imported historical CSV. Accuracy depends on the export source.",
        ),
    )
    return ds
