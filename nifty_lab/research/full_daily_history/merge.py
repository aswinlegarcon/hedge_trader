"""Deterministic merge of completed yearly chunks."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from nifty_lab.research.historical_audit.quality import accepted_to_frame, audit_raw_candles, canonical_data_hash

from .checkpoint import ChunkCheckpoint


def merge_completed_chunks(dataset_dir: Path, chunks: dict[str, ChunkCheckpoint]) -> tuple[pd.DataFrame | None, str | None, list[str]]:
    """Merge COMPLETED chunks by IST session date; conflicting session dates block clean merge."""
    frames: list[pd.DataFrame] = []
    notes: list[str] = []
    for year in sorted(chunks.keys()):
        cp = chunks[year]
        if cp.status != "COMPLETED" or not cp.raw_path:
            continue
        raw_path = dataset_dir / cp.raw_path
        if not raw_path.is_file():
            notes.append(f"Missing raw for completed chunk {year}.")
            continue
        candles = json.loads(raw_path.read_text(encoding="utf-8")).get("candles", [])
        stats, accepted = audit_raw_candles(
            candles,
            window_from=date.fromisoformat(cp.from_date),
            window_to=date.fromisoformat(cp.to_date),
        )
        if stats.duplicate_conflicting or stats.same_date_conflicts:
            notes.append(f"Chunk {year} has conflicting duplicates; merge blocked for clean status.")
            return None, None, notes
        df = accepted_to_frame(accepted)
        if not df.empty:
            frames.append(df)
    if not frames:
        return None, None, notes
    merged = pd.concat(frames).sort_index()
    merged = merged[~merged.index.duplicated(keep="first")]
    data_hash = canonical_data_hash(merged)
    return merged, data_hash, notes
