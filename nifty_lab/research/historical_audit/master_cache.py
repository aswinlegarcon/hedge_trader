"""On-disk public instrument master cache for audit."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from nifty_lab.brokers.upstox_instruments import InstrumentMasterCache, _parse_master_bytes
from nifty_lab.brokers.upstox_instruments import NSE_JSON_URL, load_master
from nifty_lab.brokers.upstox_transport import HttpTransport

from .budget import AuditRequestBudget

CACHE_MAX_AGE_SEC = 86_400


def _cache_meta_valid(cache_path: Path) -> bool:
    if not cache_path.is_file():
        return False
    age = datetime.now(timezone.utc).timestamp() - cache_path.stat().st_mtime
    return age < CACHE_MAX_AGE_SEC


def load_master_for_audit(
    transport: HttpTransport,
    cache_path: Path,
    budget: AuditRequestBudget,
) -> InstrumentMasterCache:
    if _cache_meta_valid(cache_path):
        raw = cache_path.read_bytes()
        records = _parse_master_bytes(raw)
        return InstrumentMasterCache(records=records, loaded_at=datetime.now(timezone.utc))
    budget.consume_master(label="NSE.json.gz")
    loaded = load_master(transport, force=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache_path.write_bytes(gzip.compress(json.dumps(loaded.records).encode("utf-8")))
    except OSError:
        pass
    return loaded
