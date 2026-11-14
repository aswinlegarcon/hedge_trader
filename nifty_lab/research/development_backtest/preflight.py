"""Read-only dataset verification; no acquisition or master calls."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nifty_lab.research.full_daily_history.checkpoint import load_checkpoint_raw, verify_completed_chunk
from nifty_lab.research.full_daily_history.config import config_hash as expected_config_hash, dataset_config_payload
from nifty_lab.research.full_daily_history.types import YEARLY_CHUNKS
from nifty_lab.research.historical_audit.quality import canonical_data_hash

from .config import (
    CONTEXT_YEARS_VALIDATION,
    DEVELOPMENT_YEARS,
    EVALUATION_YEARS_VALIDATION,
    EXPECTED_CHUNK_HASHES,
    EXPECTED_DATASET_CONFIG_HASH,
    EXPECTED_MERGED_HASH,
    EXPECTED_MERGED_ROWS,
    HOLDOUT_YEARS,
    INSTRUMENT_KEY,
    REGISTERED_DATASET_ID,
    SYMBOL,
)


@dataclass
class PreflightResult:
    ok: bool
    error_class: str | None
    merged_hash: str | None
    development_hash: str | None
    development_rows: int
    development_from: str | None
    development_to: str | None
    instrument_key: str
    symbol: str
    dataset_id: str
    notes: list[str]
    validation_context_hash: str | None = None
    validation_evaluation_hash: str | None = None
    holdout_hashes: dict[str, str] | None = None


def _load_merged_frame(dataset_dir: Path) -> pd.DataFrame:
    path = dataset_dir / "merged_daily.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("merged_shape")
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    rows = []
    for rec in records:
        ts = pd.Timestamp(rec["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        rows.append(
            (
                ts,
                float(rec["open"]),
                float(rec["high"]),
                float(rec["low"]),
                float(rec["close"]),
                float(rec["volume"]),
            )
        )
    return (
        pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        .set_index("ts")
        .sort_index()
    )


def _safe_nonneg_int(value) -> int | None:
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    if iv < 0:
        return None
    return iv


def _blocked(**kwargs) -> PreflightResult:
    notes = kwargs.pop(
        "notes",
        [
            "Calendar coverage UNVERIFIED; adjustment status UNKNOWN.",
            "Candidate weekday gaps from acquisition remain undisclosed here.",
            "Modeled costs are illustrative, not verified broker charges.",
        ],
    )
    return PreflightResult(notes=notes, **kwargs)


def verify_registered_dataset(dataset_dir: Path) -> PreflightResult:
    base = dict(
        merged_hash=None,
        development_hash=None,
        development_rows=0,
        development_from=None,
        development_to=None,
        instrument_key=INSTRUMENT_KEY,
        symbol=SYMBOL,
    )
    if dataset_dir.name != REGISTERED_DATASET_ID:
        return _blocked(
            ok=False,
            error_class="DATASET_ID_MISMATCH",
            dataset_id=dataset_dir.name,
            **base,
        )
    try:
        cp = load_checkpoint_raw(dataset_dir)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _blocked(ok=False, error_class="CHECKPOINT_INVALID", dataset_id=REGISTERED_DATASET_ID, **base)
    for key, val in (cp.per_chunk_attempts or {}).items():
        if not isinstance(key, str) or _safe_nonneg_int(val) is None:
            return _blocked(ok=False, error_class="CHECKPOINT_COUNTER_INVALID", dataset_id=REGISTERED_DATASET_ID, **base)
    if _safe_nonneg_int(cp.cumulative_historical_attempts) is None:
        return _blocked(ok=False, error_class="CHECKPOINT_COUNTER_INVALID", dataset_id=REGISTERED_DATASET_ID, **base)
    if _safe_nonneg_int(cp.cumulative_master_attempts) is None:
        return _blocked(ok=False, error_class="CHECKPOINT_COUNTER_INVALID", dataset_id=REGISTERED_DATASET_ID, **base)
    if cp.dataset_id != REGISTERED_DATASET_ID:
        return _blocked(ok=False, error_class="CHECKPOINT_DATASET_ID", dataset_id=REGISTERED_DATASET_ID, **base)
    if cp.config_hash != EXPECTED_DATASET_CONFIG_HASH or cp.config_hash != expected_config_hash():
        return _blocked(ok=False, error_class="CONFIG_HASH_MISMATCH", dataset_id=REGISTERED_DATASET_ID, **base)
    cfg_path = dataset_dir / "dataset_config.json"
    if not cfg_path.is_file():
        return _blocked(ok=False, error_class="DATASET_CONFIG_MISSING", dataset_id=REGISTERED_DATASET_ID, **base)
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blocked(ok=False, error_class="DATASET_CONFIG_PARSE", dataset_id=REGISTERED_DATASET_ID, **base)
    if not isinstance(cfg, dict):
        return _blocked(ok=False, error_class="DATASET_CONFIG_SHAPE", dataset_id=REGISTERED_DATASET_ID, **base)
    expected_payload = dataset_config_payload() | {"config_hash": EXPECTED_DATASET_CONFIG_HASH}
    for key, expected in expected_payload.items():
        if cfg.get(key) != expected:
            return _blocked(ok=False, error_class="DATASET_CONFIG_MISMATCH", dataset_id=REGISTERED_DATASET_ID, **base)
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        return _blocked(ok=False, error_class="MANIFEST_MISSING", dataset_id=REGISTERED_DATASET_ID, **base)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blocked(ok=False, error_class="MANIFEST_PARSE", dataset_id=REGISTERED_DATASET_ID, **base)
    if not isinstance(manifest, dict):
        return _blocked(ok=False, error_class="MANIFEST_SHAPE", dataset_id=REGISTERED_DATASET_ID, **base)
    readiness = manifest.get("readiness")
    if not isinstance(readiness, dict):
        return _blocked(ok=False, error_class="MANIFEST_SHAPE", dataset_id=REGISTERED_DATASET_ID, **base)
    if readiness.get("backtest_eligibility") == "BLOCKED" or readiness.get("quality") == "INVALID":
        return _blocked(ok=False, error_class="MANIFEST_QUALITY_BLOCKED", dataset_id=REGISTERED_DATASET_ID, **base)
    chunks = manifest.get("chunks")
    if chunks is not None and not isinstance(chunks, list):
        return _blocked(ok=False, error_class="MANIFEST_SHAPE", dataset_id=REGISTERED_DATASET_ID, **base)
    if isinstance(chunks, list) and any(
        isinstance(ch, dict) and ch.get("status") == "CONFLICT" for ch in chunks
    ):
        return _blocked(ok=False, error_class="MANIFEST_CHUNK_CONFLICT", dataset_id=REGISTERED_DATASET_ID, **base)
    for year, expected in EXPECTED_CHUNK_HASHES.items():
        chunk = cp.chunks.get(year)
        if chunk is None:
            return _blocked(ok=False, error_class="CHUNK_NOT_COMPLETE", dataset_id=REGISTERED_DATASET_ID, **base)
        if chunk.status == "CONFLICT":
            return _blocked(ok=False, error_class="CHUNK_CONFLICT", dataset_id=REGISTERED_DATASET_ID, **base)
        if chunk.status != "COMPLETED":
            return _blocked(ok=False, error_class="CHUNK_NOT_COMPLETE", dataset_id=REGISTERED_DATASET_ID, **base)
        expected_window = next((f, t) for y, f, t in YEARLY_CHUNKS if y == year)
        if chunk.from_date != expected_window[0].isoformat() or chunk.to_date != expected_window[1].isoformat():
            return _blocked(ok=False, error_class="CHUNK_WINDOW_MISMATCH", dataset_id=REGISTERED_DATASET_ID, **base)
        if chunk.data_hash != expected:
            return _blocked(ok=False, error_class="CHUNK_HASH_MISMATCH", dataset_id=REGISTERED_DATASET_ID, **base)
        ok, err = verify_completed_chunk(dataset_dir, chunk)
        if not ok:
            return _blocked(
                ok=False, error_class=err or "CHUNK_VERIFY_FAILED", dataset_id=REGISTERED_DATASET_ID, **base
            )
    try:
        merged = _load_merged_frame(dataset_dir)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return _blocked(ok=False, error_class="MERGED_PARSE_ERROR", dataset_id=REGISTERED_DATASET_ID, **base)
    merged_hash = canonical_data_hash(merged)
    meta_path = dataset_dir / "merged_meta.json"
    if not meta_path.is_file():
        return _blocked(
            ok=False,
            error_class="MERGED_META_MISSING",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blocked(
            ok=False,
            error_class="MERGED_META_PARSE",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    if not isinstance(meta, dict):
        return _blocked(
            ok=False,
            error_class="MERGED_META_SHAPE",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    if meta.get("data_hash") != merged_hash or merged_hash != EXPECTED_MERGED_HASH:
        return _blocked(
            ok=False,
            error_class="MERGED_HASH_MISMATCH",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    row_count_raw = meta.get("row_count")
    if not isinstance(row_count_raw, int) or row_count_raw < 0:
        return _blocked(
            ok=False,
            error_class="MERGED_META_ROW_COUNT_TYPE",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    meta_rows = row_count_raw
    if meta_rows != len(merged) or len(merged) != EXPECTED_MERGED_ROWS:
        return _blocked(
            ok=False,
            error_class="MERGED_ROW_COUNT",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    dev = merged[merged.index.map(lambda t: pd.Timestamp(t).year in DEVELOPMENT_YEARS)]
    if dev.empty:
        return _blocked(
            ok=False,
            error_class="DEVELOPMENT_EMPTY",
            merged_hash=merged_hash,
            dataset_id=REGISTERED_DATASET_ID,
            **{k: base[k] for k in base if k not in ("merged_hash",)},
        )
    dev_hash = canonical_data_hash(dev)
    val_ctx = merged[merged.index.map(lambda t: pd.Timestamp(t).year in CONTEXT_YEARS_VALIDATION)]
    val_eval = merged[merged.index.map(lambda t: pd.Timestamp(t).year in EVALUATION_YEARS_VALIDATION)]
    holdout_hashes = {
        str(y): canonical_data_hash(merged[merged.index.map(lambda t: pd.Timestamp(t).year == y)])
        for y in HOLDOUT_YEARS
    }
    return PreflightResult(
        ok=True,
        error_class=None,
        merged_hash=merged_hash,
        development_hash=dev_hash,
        development_rows=int(len(dev)),
        development_from=dev.index.min().date().isoformat(),
        development_to=dev.index.max().date().isoformat(),
        validation_context_hash=canonical_data_hash(val_ctx),
        validation_evaluation_hash=canonical_data_hash(val_eval),
        holdout_hashes=holdout_hashes,
        instrument_key=INSTRUMENT_KEY,
        symbol=SYMBOL,
        dataset_id=REGISTERED_DATASET_ID,
        notes=[
            "Calendar coverage UNVERIFIED; adjustment status UNKNOWN.",
            "Candidate weekday gaps from acquisition remain undisclosed here.",
            "Modeled costs are illustrative, not verified broker charges.",
        ],
    )


def development_frame_from_verified(dataset_dir: Path) -> pd.DataFrame:
    pf = verify_registered_dataset(dataset_dir)
    if not pf.ok:
        raise ValueError(pf.error_class or "preflight_failed")
    full = _load_merged_frame(dataset_dir)
    return full[full.index.map(lambda t: pd.Timestamp(t).year in DEVELOPMENT_YEARS)].copy()


def validation_frame_from_verified(dataset_dir: Path) -> pd.DataFrame:
    pf = verify_registered_dataset(dataset_dir)
    if not pf.ok:
        raise ValueError(pf.error_class or "preflight_failed")
    full = _load_merged_frame(dataset_dir)
    years = set(CONTEXT_YEARS_VALIDATION) | set(EVALUATION_YEARS_VALIDATION)
    return full[full.index.map(lambda t: pd.Timestamp(t).year in years)].copy()
