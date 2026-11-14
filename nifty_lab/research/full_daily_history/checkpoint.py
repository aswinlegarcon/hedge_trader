"""Persisted checkpoint and per-chunk state."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import config_hash, dataset_config_payload
from .io_utils import atomic_write_json
from .types import YEARLY_CHUNKS, ChunkStatus


class CheckpointConflictError(Exception):
    """Resume rejected: config or artifact hash mismatch."""


@dataclass
class ChunkCheckpoint:
    year: str
    from_date: str
    to_date: str
    status: str = ChunkStatus.NOT_STARTED.value
    http_status: int | None = None
    error_class: str | None = None
    attempts: int = 0
    raw_path: str | None = None
    normalized_path: str | None = None
    data_hash: str | None = None
    min_source_date: str | None = None
    max_source_date: str | None = None
    row_count: int = 0


@dataclass
class DatasetCheckpoint:
    dataset_id: str
    config_hash: str
    cumulative_historical_attempts: int = 0
    cumulative_master_attempts: int = 0
    per_chunk_attempts: dict[str, int] = field(default_factory=dict)
    chunks: dict[str, ChunkCheckpoint] = field(default_factory=dict)
    last_invocation_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "config_hash": self.config_hash,
            "cumulative_historical_attempts": self.cumulative_historical_attempts,
            "cumulative_master_attempts": self.cumulative_master_attempts,
            "per_chunk_attempts": dict(self.per_chunk_attempts),
            "chunks": {k: asdict(v) for k, v in self.chunks.items()},
            "last_invocation_id": self.last_invocation_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DatasetCheckpoint:
        chunks = {}
        for k, v in (data.get("chunks") or {}).items():
            chunks[k] = ChunkCheckpoint(**v)
        return cls(
            dataset_id=data["dataset_id"],
            config_hash=data["config_hash"],
            cumulative_historical_attempts=int(data.get("cumulative_historical_attempts", 0)),
            cumulative_master_attempts=int(data.get("cumulative_master_attempts", 0)),
            per_chunk_attempts=dict(data.get("per_chunk_attempts") or {}),
            chunks=chunks,
            last_invocation_id=data.get("last_invocation_id"),
        )


CHECKPOINT_FILENAME = "checkpoint.json"
CONFIG_FILENAME = "dataset_config.json"


def init_checkpoint(dataset_dir: Path, dataset_id: str) -> DatasetCheckpoint:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    ch = config_hash()
    atomic_write_json(dataset_dir / CONFIG_FILENAME, dataset_config_payload() | {"config_hash": ch})
    chunks = {
        year: ChunkCheckpoint(year=year, from_date=f.isoformat(), to_date=t.isoformat())
        for year, f, t in YEARLY_CHUNKS
    }
    cp = DatasetCheckpoint(dataset_id=dataset_id, config_hash=ch, chunks=chunks)
    save_checkpoint(dataset_dir, cp)
    return cp


def load_checkpoint_raw(dataset_dir: Path) -> DatasetCheckpoint:
    """Load checkpoint bytes without validating current config (for conflict reporting only)."""
    path = dataset_dir / CHECKPOINT_FILENAME
    if not path.is_file():
        raise FileNotFoundError("checkpoint_missing")
    return DatasetCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_checkpoint(dataset_dir: Path) -> DatasetCheckpoint:
    cp = load_checkpoint_raw(dataset_dir)
    expected = config_hash()
    if cp.config_hash != expected:
        raise CheckpointConflictError("config_hash_mismatch")
    return cp


def save_checkpoint(dataset_dir: Path, cp: DatasetCheckpoint) -> None:
    atomic_write_json(dataset_dir / CHECKPOINT_FILENAME, cp.to_dict())


def _frame_from_normalized_records(records: list) -> "pd.DataFrame":
    import pandas as pd
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    if not records:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows = []
    for rec in records:
        ts = pd.Timestamp(rec["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        rows.append((ts, float(rec["open"]), float(rec["high"]), float(rec["low"]), float(rec["close"]), float(rec["volume"])))
    return (
        pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        .set_index("ts")
        .sort_index()
    )


def verify_completed_chunk(dataset_dir: Path, cp: ChunkCheckpoint) -> tuple[bool, str | None]:
    """Verify raw + normalized artifacts match stored hash and each other."""
    from datetime import date

    from nifty_lab.research.historical_audit.quality import accepted_to_frame, audit_raw_candles, canonical_data_hash

    if cp.status != ChunkStatus.COMPLETED.value:
        return False, "not_completed"
    if not cp.raw_path or not cp.normalized_path or not cp.data_hash:
        return False, "missing_paths_or_hash"
    raw = dataset_dir / cp.raw_path
    norm = dataset_dir / cp.normalized_path
    if not raw.is_file():
        return False, "ARTIFACT_MISSING"
    if not norm.is_file():
        return False, "ARTIFACT_MISSING"
    try:
        raw_payload = json.loads(raw.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "RAW_PARSE_ERROR"
    try:
        norm_records = json.loads(norm.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "NORM_PARSE_ERROR"
    if not isinstance(norm_records, list):
        return False, "NORM_SHAPE_ERROR"
    candles = raw_payload.get("candles", []) if isinstance(raw_payload, dict) else raw_payload
    window_from = date.fromisoformat(cp.from_date)
    window_to = date.fromisoformat(cp.to_date)
    try:
        stats, accepted = audit_raw_candles(candles, window_from=window_from, window_to=window_to)
    except Exception:
        return False, "RAW_AUDIT_ERROR"
    if stats.duplicate_conflicting or stats.same_date_conflicts:
        return False, "RAW_CONFLICT"
    try:
        df_raw = accepted_to_frame(accepted)
        norm_df = _frame_from_normalized_records(norm_records)
    except (TypeError, ValueError, KeyError):
        return False, "NORM_PARSE_ERROR"
    raw_hash = canonical_data_hash(df_raw)
    norm_hash = canonical_data_hash(norm_df)
    if raw_hash != norm_hash:
        return False, "RAW_NORM_MISMATCH"
    if raw_hash != cp.data_hash:
        return False, "HASH_MISMATCH"
    if cp.row_count and len(df_raw) != cp.row_count:
        return False, "ROW_COUNT_MISMATCH"
    return True, None
