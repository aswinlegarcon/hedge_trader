"""Types and constants for resumable ICICIBANK full daily history (Spec 09)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

SYMBOL = "ICICIBANK"
MANIFEST_SCHEMA_VERSION = "spec09_full_daily_history_v1"
API_VERSION = "Upstox V3 historical-candle"
INTERVAL_LABEL = "days/1"
TIMEZONE_LABEL = "Asia/Kolkata"

MAX_HISTORICAL_PER_INVOCATION = 5
MAX_HISTORICAL_PER_DATASET = 10
MAX_HISTORICAL_PER_CHUNK = 2
MAX_MASTER_PER_INVOCATION = 1

YEARLY_CHUNKS: tuple[tuple[str, date, date], ...] = (
    ("2021", date(2021, 1, 1), date(2021, 12, 31)),
    ("2022", date(2022, 1, 1), date(2022, 12, 31)),
    ("2023", date(2023, 1, 1), date(2023, 12, 31)),
    ("2024", date(2024, 1, 1), date(2024, 12, 31)),
    ("2025", date(2025, 1, 1), date(2025, 12, 31)),
)

RESEARCH_SPLITS = {
    "development": ("2021", "2022", "2023"),
    "validation": ("2024",),
    "holdout": ("2025",),
}

ORIGINAL_AUDIT_RUN_ID = "38e457b0-5004-4731-bb68-f79118621d2a"
OVERLAP_WINDOWS = (
    ("2021-01-01_2021-01-31", "2021"),
    ("2023-01-01_2023-01-31", "2023"),
    ("2025-12-01_2025-12-31", "2025"),
)

STOP_ERROR_CLASSES = frozenset({"AUTH_BLOCKED", "RATE_LIMITED", "UNAVAILABLE"})


class ChunkStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    INTENT = "INTENT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NOT_FETCHED = "NOT_FETCHED"
    CONFLICT = "CONFLICT"
    LIVE_CHECK_UNVERIFIED = "LIVE_CHECK_UNVERIFIED"


class AcquisitionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class QualityStatus(str, Enum):
    CLEAN_WITHIN_CHECKS = "CLEAN_WITHIN_CHECKS"
    LIMITED = "LIMITED"
    INVALID = "INVALID"


class BacktestEligibility(str, Enum):
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"
    BLOCKED = "BLOCKED"


@dataclass
class ChunkQualityRecord:
    chunk_year: str
    from_date: str
    to_date: str
    status: ChunkStatus
    http_status: int | None
    error_class: str | None
    min_source_date: str | None
    max_source_date: str | None
    row_count_normalized: int
    data_hash: str | None
    raw_path: str | None
    normalized_path: str | None
    duplicate_identical: int = 0
    duplicate_conflicting: int = 0
    same_date_conflicts: int = 0
    intraday_rejected: int = 0
    suspicious_jump_flags: int = 0
    candidate_weekday_gap_dates: list[str] = field(default_factory=list)
    input_order: str = "unknown"
    notes: list[str] = field(default_factory=list)


@dataclass
class BudgetSnapshot:
    invocation_historical_attempted: int
    invocation_historical_limit: int
    dataset_historical_attempted: int
    dataset_historical_limit: int
    invocation_master_attempted: int
    invocation_master_limit: int
    dataset_master_attempted: int
    per_chunk_attempts: dict[str, int]


@dataclass
class FullHistoryResult:
    dataset_id: str
    invocation_id: str
    fetched_at_utc: str
    acquisition: AcquisitionStatus
    quality: QualityStatus
    calendar_coverage: str
    adjustment_status: str
    backtest_eligibility: BacktestEligibility
    instrument_key: str | None
    trading_symbol: str | None
    config_hash: str
    merged_hash: str | None
    chunks: list[ChunkQualityRecord]
    budget: BudgetSnapshot
    split_coverage: dict[str, str]
    overlap_comparisons: list[dict]
    output_dir: str
    manifest_path: str
    report_path: str
    limitations: list[str]
    proposed_next_step: str
