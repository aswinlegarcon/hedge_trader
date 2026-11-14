"""Read-only loader for approved archived backtest runs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import (
    APPROVED_DEVELOPMENT_RUN_ID,
    APPROVED_VALIDATION_RUN_ID,
    DEVELOPMENT_CORRECTION_REASON,
    FROZEN_RULES_HASH,
    INITIAL_CASH_INR,
    ORIGINAL_PROVISIONAL_RUN_ID,
    PINNED_SOURCE_FILES,
    VALIDATION_EVALUATION_CONFIG_HASH,
    VALIDATION_PARENT_RUN_ID,
    VALIDATION_PURPOSE,
)
from .trade_arithmetic import validate_summary_trades_equity, validate_trade_record


@dataclass
class ArchivedBook:
    book_id: str
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]
    registration: dict[str, Any]
    summary: dict[str, Any]
    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]
    baselines: dict[str, Any] | None
    source_fingerprints: dict[str, str]
    reconcile: dict[str, str]
    load_status: str = "OK"
    load_error: str | None = None
    notes: list[str] = field(default_factory=list)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fail_book(
    book_id: str,
    run_id: str,
    run_dir: Path,
    *,
    status: str,
    error: str,
    fingerprints: dict[str, str] | None = None,
    partial: dict | None = None,
) -> ArchivedBook:
    partial = partial or {}
    return ArchivedBook(
        book_id=book_id,
        run_id=run_id,
        run_dir=run_dir,
        manifest=partial.get("manifest", {}),
        registration=partial.get("registration", {}),
        summary=partial.get("summary", {}),
        trades=partial.get("trades", []),
        equity_curve=partial.get("equity", []),
        baselines=None,
        source_fingerprints=fingerprints or {},
        reconcile={},
        load_status=status,
        load_error=error,
    )


def _cross_validate_documents(
    *,
    run_id: str,
    manifest: dict,
    registration: dict,
    summary: dict,
    development_lineage: bool,
    validation_split: bool,
) -> str | None:
    if not isinstance(registration, dict):
        return "REGISTRATION_SHAPE"
    if registration.get("run_id") != run_id:
        return "REGISTRATION_RUN_ID"
    if manifest.get("run_id") != run_id:
        return "MANIFEST_RUN_ID"
    reg_rules = registration.get("rules_config_hash")
    man_rules = manifest.get("rules_config_hash")
    if reg_rules != FROZEN_RULES_HASH or man_rules != FROZEN_RULES_HASH or reg_rules != man_rules:
        return "RULES_HASH"
    if development_lineage:
        if registration.get("correction_reason") != DEVELOPMENT_CORRECTION_REASON:
            return "DEVELOPMENT_CORRECTION"
        if registration.get("parent_run_id") != ORIGINAL_PROVISIONAL_RUN_ID:
            return "DEVELOPMENT_PARENT"
    if validation_split:
        purpose = registration.get("purpose")
        if purpose != VALIDATION_PURPOSE:
            return "PURPOSE"
        man_purpose = manifest.get("purpose")
        if man_purpose is not None and man_purpose != VALIDATION_PURPOSE:
            return "MANIFEST_PURPOSE"
        if registration.get("parent_run_id") != VALIDATION_PARENT_RUN_ID:
            return "LINEAGE"
        reg_eval = registration.get("evaluation_config_hash")
        man_eval = manifest.get("evaluation_config_hash")
        if reg_eval != VALIDATION_EVALUATION_CONFIG_HASH or man_eval != VALIDATION_EVALUATION_CONFIG_HASH:
            return "EVAL_HASH"
        if reg_eval != man_eval:
            return "EVAL_HASH_MISMATCH"
    man_summary = manifest.get("summary")
    if isinstance(man_summary, dict):
        if man_summary.get("net_pnl_inr") != summary.get("net_pnl_inr"):
            return "MANIFEST_SUMMARY_NET"
        if man_summary.get("closed_trades") != summary.get("closed_trades"):
            return "MANIFEST_SUMMARY_TRADES"
        if man_summary.get("final_cash_inr") != summary.get("final_cash_inr"):
            return "MANIFEST_SUMMARY_CASH"
    return None


def load_archived_book(
    run_id: str,
    *,
    runs_root: Path,
    book_id: str,
    development_lineage: bool = False,
    validation_split: bool = False,
) -> ArchivedBook:
    run_dir = runs_root / run_id
    fingerprints: dict[str, str] = {}
    notes = [
        "Descriptive signal counts may differ from pre-correction summaries; trade economics are authoritative.",
        "Calendar UNVERIFIED; adjustment UNKNOWN.",
    ]
    if not run_dir.is_dir():
        return _fail_book(book_id, run_id, run_dir, status="RESULT_UNAVAILABLE", error="RUN_DIR_MISSING")

    for name in PINNED_SOURCE_FILES:
        path = run_dir / name
        if not path.is_file():
            return _fail_book(
                book_id,
                run_id,
                run_dir,
                status="RESULT_UNAVAILABLE",
                error=f"MISSING_{name.upper().replace('.', '_')}",
                fingerprints=fingerprints,
            )
        fingerprints[name] = _sha256_file(path)

    try:
        manifest = _read_json(run_dir / "manifest.json")
        registration = _read_json(run_dir / "registration.json")
        summary = _read_json(run_dir / "summary.json")
        trades = _read_json(run_dir / "trades.json")
        equity = _read_json(run_dir / "equity_daily.json")
    except (OSError, json.JSONDecodeError):
        return _fail_book(
            book_id,
            run_id,
            run_dir,
            status="RESULT_UNAVAILABLE",
            error="JSON_PARSE",
            fingerprints=fingerprints,
        )

    partial = {
        "manifest": manifest if isinstance(manifest, dict) else {},
        "registration": registration if isinstance(registration, dict) else {},
        "summary": summary if isinstance(summary, dict) else {},
        "trades": trades if isinstance(trades, list) else [],
        "equity": equity if isinstance(equity, list) else [],
    }

    if not isinstance(manifest, dict) or not isinstance(summary, dict) or not isinstance(trades, list):
        return _fail_book(book_id, run_id, run_dir, status="RESULT_UNAVAILABLE", error="SHAPE", fingerprints=fingerprints, partial=partial)

    if manifest.get("status") != "EXPLORATORY_COMPLETE":
        return _fail_book(book_id, run_id, run_dir, status="RESULT_UNAVAILABLE", error="NOT_COMPLETE", fingerprints=fingerprints, partial=partial)

    cross_err = _cross_validate_documents(
        run_id=run_id,
        manifest=manifest,
        registration=registration if isinstance(registration, dict) else {},
        summary=summary,
        development_lineage=development_lineage,
        validation_split=validation_split,
    )
    if cross_err:
        return _fail_book(
            book_id,
            run_id,
            run_dir,
            status="RESULT_INCONSISTENT",
            error=cross_err,
            fingerprints=fingerprints,
            partial=partial,
        )

    if not isinstance(equity, list):
        return _fail_book(book_id, run_id, run_dir, status="RESULT_UNAVAILABLE", error="EQUITY_SHAPE", fingerprints=fingerprints, partial=partial)

    for i, t in enumerate(trades):
        err = validate_trade_record(t, i)
        if err:
            return _fail_book(
                book_id,
                run_id,
                run_dir,
                status="RESULT_INCONSISTENT",
                error=err,
                fingerprints=fingerprints,
                partial=partial,
            )

    reconcile, rec_err = validate_summary_trades_equity(trades, summary, equity)
    if rec_err:
        return _fail_book(
            book_id,
            run_id,
            run_dir,
            status="RESULT_INCONSISTENT",
            error=rec_err,
            fingerprints=fingerprints,
            partial=partial,
        )

    baselines = manifest.get("baselines")
    if baselines is not None and not isinstance(baselines, dict):
        baselines = None

    return ArchivedBook(
        book_id=book_id,
        run_id=run_id,
        run_dir=run_dir,
        manifest=manifest,
        registration=registration if isinstance(registration, dict) else {},
        summary=summary,
        trades=trades,
        equity_curve=equity,
        baselines=baselines,
        source_fingerprints=fingerprints,
        reconcile=reconcile,
        load_status="OK",
        notes=notes,
    )


def load_approved_pair(runs_root: Path | None = None) -> tuple[ArchivedBook, ArchivedBook]:
    root = runs_root or Path(__file__).resolve().parents[3] / "research" / "backtest_runs"
    dev = load_archived_book(
        APPROVED_DEVELOPMENT_RUN_ID,
        runs_root=root,
        book_id="development_2021_2023",
        development_lineage=True,
    )
    val = load_archived_book(
        APPROVED_VALIDATION_RUN_ID,
        runs_root=root,
        book_id="validation_2024",
        validation_split=True,
    )
    return dev, val


def fingerprints_match_stored(stored: dict[str, str], book: ArchivedBook) -> bool:
    if book.load_status != "OK":
        return False
    return stored == book.source_fingerprints
