"""Raw and normalized candle quality audit (Spec 09)."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .types import DAILY_ANCHOR_HMS, SUSPICIOUS_JUMP_PCT, RawAuditStats, RawRowFinding

IST = ZoneInfo("Asia/Kolkata")


def _parse_ts(ts_raw: object) -> datetime | None:
    if ts_raw is None or (isinstance(ts_raw, float) and math.isnan(ts_raw)):
        return None
    try:
        ts = pd.Timestamp(ts_raw)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        else:
            ts = ts.tz_convert(IST)
        return ts.to_pydatetime()
    except (TypeError, ValueError):
        return None


def _is_daily_anchor(ts: datetime) -> bool:
    h, m, s = ts.hour, ts.minute, ts.second
    return (h, m, s) == DAILY_ANCHOR_HMS


def _detect_input_order(dates_in_input: list[date]) -> str:
    if len(dates_in_input) < 2:
        return "single_or_empty"
    asc = all(dates_in_input[i] <= dates_in_input[i + 1] for i in range(len(dates_in_input) - 1))
    desc = all(dates_in_input[i] >= dates_in_input[i + 1] for i in range(len(dates_in_input) - 1))
    if asc and not desc:
        return "ascending"
    if desc and not asc:
        return "descending"
    return "unordered"


def all_candidate_weekday_gap_dates(
    window_from: date, window_to: date, present: set[date]
) -> list[date]:
    """All Mon–Fri dates in range without a bar (calendar UNVERIFIED; not a holiday list)."""
    gaps: list[date] = []
    d = window_from
    while d <= window_to:
        if d.weekday() < 5 and d not in present:
            gaps.append(d)
        d += timedelta(days=1)
    return gaps


def _candidate_weekday_gaps(window_from: date, window_to: date, present: set[date]) -> tuple[int, list[date]]:
    full = all_candidate_weekday_gap_dates(window_from, window_to, present)
    return len(full), full[:12]


def audit_raw_candles(
    candles: list,
    *,
    window_from: date,
    window_to: date,
) -> tuple[RawAuditStats, list[list]]:
    """Inspect raw API rows before normalization; daily interval policy enforced."""
    findings: list[RawRowFinding] = []
    accepted: list[list] = []
    seen_ts: dict[str, list[float]] = {}
    seen_dates: dict[date, str] = {}
    dup_identical = 0
    dup_conflicting = 0
    out_of_range = 0
    invalid_ohlc = 0
    invalid_volume = 0
    zero_volume = 0
    bad_timestamp = 0
    intraday_rejected = 0
    same_date_conflicts = 0
    suspicious_jumps = 0
    input_dates: list[date] = []

    for idx, c in enumerate(candles):
        if not isinstance(c, (list, tuple)) or len(c) < 6:
            findings.append(RawRowFinding(idx, "BAD_SHAPE", "row is not a 6+ element list"))
            continue
        ts = _parse_ts(c[0])
        if ts is None:
            bad_timestamp += 1
            findings.append(RawRowFinding(idx, "BAD_TIMESTAMP", "unparseable or NaT timestamp"))
            continue
        d = ts.date()
        input_dates.append(d)
        if not _is_daily_anchor(ts):
            intraday_rejected += 1
            findings.append(
                RawRowFinding(
                    idx,
                    "INTRADAY_TIMESTAMP",
                    f"daily audit rejects non-midnight IST timestamp for {d.isoformat()}",
                )
            )
            continue
        if d < window_from or d > window_to:
            out_of_range += 1
            findings.append(RawRowFinding(idx, "OUT_OF_RANGE", f"date {d} outside requested window"))
            continue
        try:
            o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
            vol = c[5]
            vol_f = float(vol) if vol is not None else float("nan")
        except (TypeError, ValueError):
            findings.append(RawRowFinding(idx, "BAD_NUMERIC", "non-numeric OHLCV"))
            invalid_ohlc += 1
            continue
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, cl)):
            invalid_ohlc += 1
            findings.append(RawRowFinding(idx, "INVALID_OHLC", "non-finite or non-positive OHLC"))
            continue
        if not math.isfinite(vol_f) or vol_f < 0:
            invalid_volume += 1
            findings.append(RawRowFinding(idx, "INVALID_VOLUME", "invalid volume"))
            continue
        if vol_f == 0:
            zero_volume += 1
            findings.append(RawRowFinding(idx, "ZERO_VOLUME", "zero volume bar (investigate; not auto-corrected)"))
        if h < max(o, cl) or l > min(o, cl):
            invalid_ohlc += 1
            findings.append(RawRowFinding(idx, "OHLC_INCONSISTENT", "low/high inconsistent with open/close"))
            continue
        if o > 0 and abs(cl - o) / o >= SUSPICIOUS_JUMP_PCT:
            suspicious_jumps += 1
            findings.append(
                RawRowFinding(
                    idx,
                    "SUSPICIOUS_JUMP",
                    f"|close-open|/open >= {SUSPICIOUS_JUMP_PCT:.0%} (investigate only)",
                )
            )
        if d in seen_dates:
            same_date_conflicts += 1
            findings.append(
                RawRowFinding(
                    idx,
                    "SAME_DATE_CONFLICT",
                    f"duplicate session date {d.isoformat()} (prior {seen_dates[d]})",
                )
            )
            continue
        key = ts.isoformat()
        payload = [o, h, l, cl, vol_f]
        if key in seen_ts:
            if seen_ts[key] == payload:
                dup_identical += 1
                findings.append(RawRowFinding(idx, "DUPLICATE_IDENTICAL", f"duplicate at {key}"))
                continue
            dup_conflicting += 1
            findings.append(RawRowFinding(idx, "DUPLICATE_CONFLICTING", f"conflicting duplicate at {key}"))
            continue
        seen_ts[key] = payload
        seen_dates[d] = key
        accepted.append(list(c))

    present_dates = {d for d in seen_dates}
    gap_count, gap_sample = _candidate_weekday_gaps(window_from, window_to, present_dates)
    if gap_count:
        findings.append(
            RawRowFinding(
                -1,
                "CANDIDATE_WEEKDAY_GAPS",
                f"{gap_count} weekday dates in window without a bar (calendar UNVERIFIED); sample: "
                + ",".join(x.isoformat() for x in gap_sample),
            )
        )

    rejected = (
        len(candles)
        - len(accepted)
        - dup_identical
    )

    stats = RawAuditStats(
        raw_row_count=len(candles),
        accepted_count=len(accepted),
        rejected_count=max(0, rejected),
        duplicate_identical=dup_identical,
        duplicate_conflicting=dup_conflicting,
        out_of_range=out_of_range,
        invalid_ohlc=invalid_ohlc,
        invalid_volume=invalid_volume,
        zero_volume_flags=zero_volume,
        bad_timestamp=bad_timestamp,
        intraday_timestamp_rejected=intraday_rejected,
        same_date_conflicts=same_date_conflicts,
        suspicious_jump_flags=suspicious_jumps,
        candidate_weekday_gap_count=gap_count,
        input_order=_detect_input_order(input_dates),
        findings=findings,
    )
    return stats, accepted


def accepted_to_frame(accepted_rows: list[list]) -> pd.DataFrame:
    if not accepted_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows = []
    for c in accepted_rows:
        ts = _parse_ts(c[0])
        assert ts is not None
        rows.append(
            (
                pd.Timestamp(ts),
                float(c[1]),
                float(c[2]),
                float(c[3]),
                float(c[4]),
                float(c[5]),
            )
        )
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
    return df.sort_index()


def canonical_data_hash(df: pd.DataFrame) -> str:
    """Deterministic hash of normalized OHLCV (stable across fetched_at)."""
    import hashlib

    if df.empty:
        return hashlib.sha256(b"EMPTY").hexdigest()
    lines: list[str] = []
    for ts, row in df.sort_index().iterrows():
        t = pd.Timestamp(ts).tz_convert(IST).isoformat()
        lines.append(
            "|".join(
                [
                    t,
                    f"{row['open']:.6f}",
                    f"{row['high']:.6f}",
                    f"{row['low']:.6f}",
                    f"{row['close']:.6f}",
                    f"{row['volume']:.6f}",
                ]
            )
        )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
