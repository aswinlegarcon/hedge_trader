"""Manifest and report for full daily history runs."""
from __future__ import annotations

import json
from pathlib import Path

from nifty_lab.config import FAKE_SECRET_SENTINEL

from .types import (
    API_VERSION,
    INTERVAL_LABEL,
    MANIFEST_SCHEMA_VERSION,
    TIMEZONE_LABEL,
    BacktestEligibility,
    FullHistoryResult,
)


def _scrub(text: str) -> str:
    if FAKE_SECRET_SENTINEL in text:
        raise ValueError("Secret sentinel would leak into history artifact.")
    return text


def write_manifest(result: FullHistoryResult) -> None:
    path = Path(result.manifest_path)
    payload = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": result.dataset_id,
        "invocation_id": result.invocation_id,
        "fetched_at_utc": result.fetched_at_utc,
        "config_hash": result.config_hash,
        "symbol": result.trading_symbol,
        "instrument_key": result.instrument_key,
        "api_version": API_VERSION,
        "interval": INTERVAL_LABEL,
        "timezone_interpretation": TIMEZONE_LABEL,
        "readiness": {
            "acquisition": result.acquisition.value,
            "quality": result.quality.value,
            "calendar_coverage": result.calendar_coverage,
            "adjustment_status": result.adjustment_status,
            "backtest_eligibility": result.backtest_eligibility.value,
        },
        "split_coverage": result.split_coverage,
        "merged_data_hash": result.merged_hash,
        "request_budget": {
            "invocation_historical_attempted": result.budget.invocation_historical_attempted,
            "invocation_historical_limit": result.budget.invocation_historical_limit,
            "dataset_historical_attempted": result.budget.dataset_historical_attempted,
            "dataset_historical_limit": result.budget.dataset_historical_limit,
            "invocation_master_attempted": result.budget.invocation_master_attempted,
            "invocation_master_limit": result.budget.invocation_master_limit,
            "dataset_master_attempted": result.budget.dataset_master_attempted,
            "per_chunk_attempts": result.budget.per_chunk_attempts,
        },
        "chunks": [],
        "overlap_comparisons": result.overlap_comparisons,
        "limitations": result.limitations,
        "proposed_next_step": result.proposed_next_step,
    }
    for c in result.chunks:
        payload["chunks"].append(
            {
                "chunk_year": c.chunk_year,
                "from_date": c.from_date,
                "to_date": c.to_date,
                "status": c.status.value,
                "http_status": c.http_status,
                "error_class": c.error_class,
                "min_source_date": c.min_source_date,
                "max_source_date": c.max_source_date,
                "row_count_normalized": c.row_count_normalized,
                "data_hash": c.data_hash,
                "raw_path": c.raw_path,
                "normalized_path": c.normalized_path,
                "quality": {
                    "duplicate_identical": c.duplicate_identical,
                    "duplicate_conflicting": c.duplicate_conflicting,
                    "same_date_conflicts": c.same_date_conflicts,
                    "intraday_rejected": c.intraday_rejected,
                    "suspicious_jump_flags": c.suspicious_jump_flags,
                    "candidate_weekday_gap_dates": c.candidate_weekday_gap_dates,
                    "input_order": c.input_order,
                },
                "notes": c.notes,
            }
        )
    text = _scrub(json.dumps(payload, indent=2))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_report(result: FullHistoryResult) -> None:
    lines = [
        "# ICICIBANK full daily history (Spec 09 slice)",
        "",
        f"- dataset_id: `{result.dataset_id}`",
        f"- invocation_id: `{result.invocation_id}`",
        f"- acquisition: **{result.acquisition.value}**",
        f"- quality: **{result.quality.value}**",
        f"- calendar: **{result.calendar_coverage}**",
        f"- adjustment: **{result.adjustment_status}**",
        f"- backtest eligibility: **{result.backtest_eligibility.value}**",
        f"- merged hash: `{result.merged_hash or 'n/a'}`",
        "",
        "## Split coverage",
    ]
    for k, v in result.split_coverage.items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Chunks"])
    for c in result.chunks:
        lines.append(
            f"- {c.chunk_year}: {c.status.value} rows={c.row_count_normalized} "
            f"gaps_listed={len(c.candidate_weekday_gap_dates)}"
        )
    lines.extend(["", "## Limitations"])
    for lim in result.limitations:
        lines.append(f"- {lim}")
    lines.extend(["", "## Proposed next step", result.proposed_next_step, ""])
    text = _scrub("\n".join(lines))
    Path(result.report_path).write_text(text, encoding="utf-8")
