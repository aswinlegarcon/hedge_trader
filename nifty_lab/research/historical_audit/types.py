"""Constants and types for historical data audit."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

AUDIT_SYMBOL = "ICICIBANK"
MANIFEST_SCHEMA_VERSION = "spec09_historical_audit_v1.1"
API_VERSION = "Upstox V3 historical-candle"
INTERVAL_LABEL = "daily"
TIMEZONE_LABEL = "Asia/Kolkata"

# Predeclared later study splits (this audit samples only; no strategy use).
RESEARCH_ROLE_LABELS = {
    "2021-01-01_2021-01-31": "development_sample",
    "2023-01-01_2023-01-31": "development_sample",
    "2025-12-01_2025-12-31": "holdout_feasibility_sample",
}

AUDIT_WINDOWS: tuple[tuple[date, date], ...] = (
    (date(2021, 1, 1), date(2021, 1, 31)),
    (date(2023, 1, 1), date(2023, 1, 31)),
    (date(2025, 12, 1), date(2025, 12, 31)),
)

MAX_HISTORICAL_REQUESTS = 3
MAX_INSTRUMENT_MASTER_REQUESTS = 1


class WindowStatus(str, Enum):
    FEASIBLE_SAMPLE = "FEASIBLE_SAMPLE"
    LIMITED = "LIMITED"
    BLOCKED = "BLOCKED"
    NOT_FETCHED = "NOT_FETCHED"
    LIVE_CHECK_UNVERIFIED = "LIVE_CHECK_UNVERIFIED"


class OverallStatus(str, Enum):
    FEASIBLE_SAMPLE = "FEASIBLE_SAMPLE"
    LIMITED = "LIMITED"
    BLOCKED = "BLOCKED"
    LIVE_CHECK_UNVERIFIED = "LIVE_CHECK_UNVERIFIED"


@dataclass
class RawRowFinding:
    index: int
    code: str
    detail: str


# Configurable investigation heuristic — not an automatic correction.
SUSPICIOUS_JUMP_PCT = 0.15

# Upstox V3 daily candles are anchored at 00:00:00 IST for the session date.
DAILY_ANCHOR_HMS = (0, 0, 0)


@dataclass
class RawAuditStats:
    raw_row_count: int
    accepted_count: int
    rejected_count: int
    duplicate_identical: int
    duplicate_conflicting: int
    out_of_range: int
    invalid_ohlc: int
    invalid_volume: int
    zero_volume_flags: int
    bad_timestamp: int = 0
    intraday_timestamp_rejected: int = 0
    same_date_conflicts: int = 0
    suspicious_jump_flags: int = 0
    candidate_weekday_gap_count: int = 0
    input_order: str = "unknown"
    findings: list[RawRowFinding] = field(default_factory=list)


@dataclass
class WindowAuditResult:
    window_key: str
    requested_from: str
    requested_to: str
    research_role: str
    status: WindowStatus
    http_status: int | None
    error_class: str | None
    instrument_key: str | None
    trading_symbol: str | None
    min_source_date: str | None
    max_source_date: str | None
    row_count_normalized: int
    data_hash: str | None
    raw_stats: RawAuditStats | None
    calendar_coverage: str = "UNVERIFIED"
    adjustment_status: str = "UNKNOWN"
    notes: list[str] = field(default_factory=list)


@dataclass
class RequestBudgetSnapshot:
    historical_attempted: int
    historical_limit: int
    master_attempted: int
    master_limit: int


@dataclass
class AuditRunResult:
    run_id: str
    fetched_at_utc: str
    overall_status: OverallStatus
    instrument_key: str | None
    trading_symbol: str | None
    windows: list[WindowAuditResult]
    budget: RequestBudgetSnapshot
    output_dir: str
    manifest_path: str
    report_path: str
    limitations: list[str] = field(default_factory=list)
    proposed_next_step: str = ""
