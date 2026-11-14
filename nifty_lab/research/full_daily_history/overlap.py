"""Offline overlap compare vs original bounded audit samples."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from nifty_lab.config import PROJECT_ROOT
from nifty_lab.research.historical_audit.quality import accepted_to_frame, audit_raw_candles, canonical_data_hash

from .types import ORIGINAL_AUDIT_RUN_ID, OVERLAP_WINDOWS


def _audit_run_dir(audit_root: Path | None = None) -> Path:
    root = audit_root or (PROJECT_ROOT / "research" / "audit_runs")
    return root / ORIGINAL_AUDIT_RUN_ID


def compare_overlaps(
    dataset_dir: Path,
    *,
    audit_root: Path | None = None,
) -> list[dict]:
    """Compare yearly chunk normalized data to saved monthly audit windows (no HTTP)."""
    audit_dir = _audit_run_dir(audit_root)
    if not audit_dir.is_dir():
        return [{"status": "AUDIT_BASELINE_MISSING", "detail": str(audit_dir)}]

    out: list[dict] = []
    for window_key, chunk_year in OVERLAP_WINDOWS:
        audit_raw = audit_dir / f"raw_{window_key}.json"
        chunk_raw = dataset_dir / f"raw_{chunk_year}.json"
        row: dict = {
            "audit_window": window_key,
            "chunk_year": chunk_year,
            "audit_raw_path": str(audit_raw),
            "chunk_raw_path": str(chunk_raw),
        }
        if not audit_raw.is_file():
            row["status"] = "AUDIT_SAMPLE_MISSING"
            out.append(row)
            continue
        if not chunk_raw.is_file():
            row["status"] = "CHUNK_NOT_PRESENT"
            out.append(row)
            continue
        audit_candles = json.loads(audit_raw.read_text(encoding="utf-8"))
        if isinstance(audit_candles, dict) and "candles" in audit_candles:
            audit_candles = audit_candles["candles"]
        chunk_candles = json.loads(chunk_raw.read_text(encoding="utf-8")).get("candles", [])
        parts = window_key.split("_")
        w_from = date.fromisoformat(parts[0])
        w_to = date.fromisoformat(parts[1])
        _, audit_acc = audit_raw_candles(audit_candles, window_from=w_from, window_to=w_to)
        yr = int(chunk_year)
        _, chunk_acc = audit_raw_candles(
            chunk_candles,
            window_from=date(yr, 1, 1),
            window_to=date(yr, 12, 31),
        )
        audit_df = accepted_to_frame(audit_acc)
        chunk_df = accepted_to_frame(chunk_acc)
        overlap_idx = audit_df.index.intersection(chunk_df.index)
        mismatches: list[str] = []
        for ts in overlap_idx:
            a = audit_df.loc[ts]
            c = chunk_df.loc[ts]
            if (
                abs(a["close"] - c["close"]) > 1e-6
                or abs(a["open"] - c["open"]) > 1e-6
                or abs(a["volume"] - c["volume"]) > 1e-6
            ):
                mismatches.append(pd.Timestamp(ts).date().isoformat())
        row["audit_hash"] = canonical_data_hash(audit_df) if not audit_df.empty else None
        row["chunk_overlap_hash"] = (
            canonical_data_hash(chunk_df.loc[overlap_idx]) if len(overlap_idx) else None
        )
        row["overlap_session_count"] = int(len(overlap_idx))
        row["value_mismatch_dates"] = mismatches[:50]
        row["status"] = "MATCH" if not mismatches else "VENDOR_OR_REVISION_DIFF"
        row["note"] = (
            "Both versions retained; differences may reflect vendor revision or adjustment treatment."
            if mismatches
            else "Overlapping sessions match within tolerance."
        )
        out.append(row)
    return out
