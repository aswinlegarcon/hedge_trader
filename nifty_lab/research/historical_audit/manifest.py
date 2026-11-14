"""Manifest and sanitized report output."""
from __future__ import annotations

import json
from pathlib import Path

from nifty_lab.config import FAKE_SECRET_SENTINEL

from .types import (
    MANIFEST_SCHEMA_VERSION,
    API_VERSION,
    INTERVAL_LABEL,
    TIMEZONE_LABEL,
    AuditRunResult,
    OverallStatus,
)


def _scrub_text(text: str) -> str:
    if FAKE_SECRET_SENTINEL in text:
        raise ValueError("Secret sentinel would leak into audit artifact.")
    return text


def write_manifest(result: AuditRunResult) -> None:
    path = Path(result.manifest_path)
    payload = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": result.run_id,
        "fetched_at_utc": result.fetched_at_utc,
        "overall_status": result.overall_status.value,
        "symbol": result.trading_symbol,
        "instrument_key": result.instrument_key,
        "api_version": API_VERSION,
        "interval": INTERVAL_LABEL,
        "timezone_interpretation": TIMEZONE_LABEL,
        "request_budget": {
            "historical_attempted": result.budget.historical_attempted,
            "historical_limit": result.budget.historical_limit,
            "master_attempted": result.budget.master_attempted,
            "master_limit": result.budget.master_limit,
        },
        "research_boundaries_declared": {
            "2021_2023": "development (not verified by this sample alone)",
            "2024": "validation (not fetched in this audit)",
            "2025": "final holdout (December sample only; untouched for strategy tuning)",
        },
        "calendar_coverage": "UNVERIFIED",
        "adjustment_status": "UNKNOWN",
        "limitations": result.limitations,
        "windows": [],
    }
    for w in result.windows:
        entry = {
            "window_key": w.window_key,
            "requested_from": w.requested_from,
            "requested_to": w.requested_to,
            "research_role": w.research_role,
            "status": w.status.value,
            "http_status": w.http_status,
            "error_class": w.error_class,
            "min_source_date": w.min_source_date,
            "max_source_date": w.max_source_date,
            "row_count_normalized": w.row_count_normalized,
            "data_hash": w.data_hash,
            "calendar_coverage": w.calendar_coverage,
            "adjustment_status": w.adjustment_status,
            "notes": w.notes,
        }
        if w.raw_stats is not None:
            entry["raw_audit"] = {
                "raw_row_count": w.raw_stats.raw_row_count,
                "accepted_count": w.raw_stats.accepted_count,
                "rejected_count": w.raw_stats.rejected_count,
                "duplicate_identical": w.raw_stats.duplicate_identical,
                "duplicate_conflicting": w.raw_stats.duplicate_conflicting,
                "out_of_range": w.raw_stats.out_of_range,
                "invalid_ohlc": w.raw_stats.invalid_ohlc,
                "invalid_volume": w.raw_stats.invalid_volume,
                "zero_volume_flags": w.raw_stats.zero_volume_flags,
                "bad_timestamp": w.raw_stats.bad_timestamp,
                "intraday_timestamp_rejected": w.raw_stats.intraday_timestamp_rejected,
                "same_date_conflicts": w.raw_stats.same_date_conflicts,
                "suspicious_jump_flags": w.raw_stats.suspicious_jump_flags,
                "candidate_weekday_gap_count": w.raw_stats.candidate_weekday_gap_count,
                "input_order": w.raw_stats.input_order,
                "finding_codes": sorted({f.code for f in w.raw_stats.findings}),
            }
        payload["windows"].append(entry)
    text = json.dumps(payload, indent=2, sort_keys=True)
    _scrub_text(text)
    path.write_text(text, encoding="utf-8")


def write_report(result: AuditRunResult) -> None:
    path = Path(result.report_path)
    lines = [
        "# Spec 09 — ICICIBANK historical data audit (sanitized)",
        "",
        f"- **Run ID:** `{result.run_id}`",
        f"- **Fetched at (UTC):** {result.fetched_at_utc}",
        f"- **Overall status:** `{result.overall_status.value}`",
        f"- **Instrument:** {result.trading_symbol or 'unresolved'} ({result.instrument_key or 'n/a'})",
        "",
        "## Request budget",
        f"- Historical attempts: {result.budget.historical_attempted} / {result.budget.historical_limit}",
        f"- Master attempts: {result.budget.master_attempted} / {result.budget.master_limit}",
        "",
        "## Predeclared research boundaries",
        "- 2021–2023: development (sample windows only; continuity unverified)",
        "- 2024: validation split — **not fetched** in this audit",
        "- 2025: holdout — December 2025 sample only; no strategy outcomes",
        "",
        "## Per-window results",
    ]
    for w in result.windows:
        lines.append(f"### {w.window_key}")
        lines.append(f"- Status: `{w.status.value}`")
        if w.http_status is not None:
            lines.append(f"- HTTP: {w.http_status}")
        if w.error_class:
            lines.append(f"- Error class: {w.error_class}")
        lines.append(f"- Normalized rows: {w.row_count_normalized}")
        if w.data_hash:
            lines.append(f"- Data hash: `{w.data_hash[:16]}…`")
        lines.append(f"- Calendar: {w.calendar_coverage}; Adjustment: {w.adjustment_status}")
        if w.notes:
            for note in w.notes:
                lines.append(f"- Note: {note}")
        lines.append("")
    lines.extend(["## Limitations", ""])
    lines.extend([f"- {lim}" for lim in result.limitations])
    lines.extend(["", "## Proposed next step", "", result.proposed_next_step or "(none)", ""])
    text = "\n".join(lines)
    _scrub_text(text)
    path.write_text(text, encoding="utf-8")
