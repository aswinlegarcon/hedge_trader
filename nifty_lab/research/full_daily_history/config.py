"""Immutable dataset configuration and config hash."""
from __future__ import annotations

import hashlib
import json

from .types import API_VERSION, INTERVAL_LABEL, MANIFEST_SCHEMA_VERSION, SYMBOL, TIMEZONE_LABEL, YEARLY_CHUNKS


def dataset_config_payload() -> dict:
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "symbol": SYMBOL,
        "interval": INTERVAL_LABEL,
        "api_version": API_VERSION,
        "timezone": TIMEZONE_LABEL,
        "chunks": [
            {"year": y, "from": f.isoformat(), "to": t.isoformat()} for y, f, t in YEARLY_CHUNKS
        ],
    }


def config_hash() -> str:
    raw = json.dumps(dataset_config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_dataset_id() -> str:
    """Stable logical dataset id derived from config (not a random UUID)."""
    h = config_hash()
    return f"icicibank-daily-{h[:12]}"
