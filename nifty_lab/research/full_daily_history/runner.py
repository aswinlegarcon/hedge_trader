"""Resumable five-year ICICIBANK daily history acquisition."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from nifty_lab.brokers.upstox_errors import UpstoxAuthError
from nifty_lab.brokers.upstox_instruments import find_by_trading_symbol
from nifty_lab.brokers.upstox_market_data import _token_present
from nifty_lab.brokers.upstox_transport import HttpTransport, RequestsTransport
from nifty_lab.config import PROJECT_ROOT

from nifty_lab.research.historical_audit.budget import AuditBudgetExceeded
from nifty_lab.research.historical_audit.client import fetch_historical_candles_raw, sanitized_public_payload
from nifty_lab.research.historical_audit.master_cache import load_master_for_audit
from nifty_lab.research.historical_audit.quality import (
    accepted_to_frame,
    all_candidate_weekday_gap_dates,
    audit_raw_candles,
    canonical_data_hash,
)

from .budget import FullHistoryBudget
from .checkpoint import (
    CheckpointConflictError,
    ChunkCheckpoint,
    DatasetCheckpoint,
    init_checkpoint,
    load_checkpoint,
    load_checkpoint_raw,
    save_checkpoint,
    verify_completed_chunk,
)
from .config import config_hash, default_dataset_id
from .io_utils import atomic_write_bytes, atomic_write_json, atomic_write_text, dataset_lock
from .manifest import write_manifest, write_report
from .merge import merge_completed_chunks
from .overlap import compare_overlaps
from .types import (
    AcquisitionStatus,
    BacktestEligibility,
    BudgetSnapshot,
    ChunkQualityRecord,
    ChunkStatus,
    FullHistoryResult,
    QualityStatus,
    RESEARCH_SPLITS,
    STOP_ERROR_CLASSES,
    SYMBOL,
    YEARLY_CHUNKS,
)

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "research" / "history_runs"
DEFAULT_MASTER_CACHE = PROJECT_ROOT / "research" / "audit_cache" / "nse_instruments.json.gz"

LIMITATIONS = [
    "NSE session calendar not sourced in-repo; weekday gap lists are candidate missing sessions only.",
    "Corporate-action and price-adjustment status remains UNKNOWN without authoritative evidence.",
    "Single-symbol ICICIBANK study; not a survivorship-free universe.",
    "No strategy signals, outcomes, optimization or broker mutations in this slice.",
    "Candidate jump flags are investigate-only; not split/corporate-action proof.",
]


def _chunk_quality(cp: ChunkCheckpoint, stats=None) -> ChunkQualityRecord:
    gap_dates: list[str] = []
    if stats is not None and stats.candidate_weekday_gap_count:
        present = set()
        gap_dates = [d.isoformat() for d in all_candidate_weekday_gap_dates(
            date.fromisoformat(cp.from_date), date.fromisoformat(cp.to_date), present
        )]
    elif cp.status == ChunkStatus.COMPLETED.value and cp.data_hash:
        pass
    st = ChunkStatus(cp.status) if cp.status in {e.value for e in ChunkStatus} else ChunkStatus.FAILED
    return ChunkQualityRecord(
        chunk_year=cp.year,
        from_date=cp.from_date,
        to_date=cp.to_date,
        status=st,
        http_status=cp.http_status,
        error_class=cp.error_class,
        min_source_date=cp.min_source_date,
        max_source_date=cp.max_source_date,
        row_count_normalized=cp.row_count,
        data_hash=cp.data_hash,
        raw_path=cp.raw_path,
        normalized_path=cp.normalized_path,
        duplicate_identical=getattr(stats, "duplicate_identical", 0) if stats else 0,
        duplicate_conflicting=getattr(stats, "duplicate_conflicting", 0) if stats else 0,
        same_date_conflicts=getattr(stats, "same_date_conflicts", 0) if stats else 0,
        intraday_rejected=getattr(stats, "intraday_timestamp_rejected", 0) if stats else 0,
        suspicious_jump_flags=getattr(stats, "suspicious_jump_flags", 0) if stats else 0,
        candidate_weekday_gap_dates=gap_dates,
        input_order=getattr(stats, "input_order", "unknown") if stats else "unknown",
    )


def _split_coverage(checkpoint: DatasetCheckpoint) -> dict[str, str]:
    out: dict[str, str] = {}
    for split, years in RESEARCH_SPLITS.items():
        states = [checkpoint.chunks[y].status for y in years if y in checkpoint.chunks]
        if all(s == ChunkStatus.COMPLETED.value for s in states):
            out[split] = "data_acquired_for_split"
        elif any(s == ChunkStatus.COMPLETED.value for s in states):
            out[split] = "partial_acquisition"
        elif all(s in (ChunkStatus.LIVE_CHECK_UNVERIFIED.value, ChunkStatus.NOT_STARTED.value) for s in states):
            out[split] = "not_acquired"
        else:
            out[split] = "incomplete_or_blocked"
    return out


def _merged_hash_on_disk(dataset_dir: Path) -> str | None:
    meta = dataset_dir / "merged_meta.json"
    if not meta.is_file():
        return None
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
        return payload.get("data_hash")
    except (json.JSONDecodeError, OSError):
        return None


def _has_chunk_conflicts(checkpoint: DatasetCheckpoint) -> bool:
    return any(c.status == ChunkStatus.CONFLICT.value for c in checkpoint.chunks.values())


def _usable_dataset_complete(
    checkpoint: DatasetCheckpoint,
    dataset_dir: Path,
    *,
    merged_hash: str | None,
) -> bool:
    completed = sum(1 for c in checkpoint.chunks.values() if c.status == ChunkStatus.COMPLETED.value)
    if completed != len(YEARLY_CHUNKS):
        return False
    if _has_chunk_conflicts(checkpoint):
        return False
    if not merged_hash:
        return False
    on_disk = _merged_hash_on_disk(dataset_dir)
    return on_disk == merged_hash


def _acquisition_status(
    checkpoint: DatasetCheckpoint,
    *,
    live_attempted: bool,
    dataset_dir: Path,
    merged_hash: str | None,
) -> AcquisitionStatus:
    if _usable_dataset_complete(checkpoint, dataset_dir, merged_hash=merged_hash):
        return AcquisitionStatus.COMPLETE
    completed = sum(1 for c in checkpoint.chunks.values() if c.status == ChunkStatus.COMPLETED.value)
    if _has_chunk_conflicts(checkpoint) or (completed == len(YEARLY_CHUNKS) and not merged_hash):
        return AcquisitionStatus.PARTIAL
    if not live_attempted and completed == 0:
        return AcquisitionStatus.UNVERIFIED
    if completed > 0:
        return AcquisitionStatus.PARTIAL
    if any(
        c.status == ChunkStatus.FAILED.value and c.error_class in STOP_ERROR_CLASSES
        for c in checkpoint.chunks.values()
    ):
        return AcquisitionStatus.BLOCKED
    return AcquisitionStatus.PARTIAL


def _backtest_eligibility(
    *,
    acquisition: AcquisitionStatus,
    quality: QualityStatus,
    merged_hash: str | None,
    has_conflicts: bool,
) -> BacktestEligibility:
    if quality == QualityStatus.INVALID or not merged_hash or has_conflicts:
        return BacktestEligibility.BLOCKED
    if acquisition == AcquisitionStatus.COMPLETE:
        return BacktestEligibility.EXPLORATORY_ONLY
    return BacktestEligibility.BLOCKED


def _write_invocation_sidecar(
    dataset_dir: Path,
    invocation_id: str,
    *,
    fetched_at: str,
    kind: str,
    detail: str,
    budget_snapshot: dict | None = None,
) -> None:
    payload = {
        "invocation_id": invocation_id,
        "fetched_at_utc": fetched_at,
        "kind": kind,
        "detail": detail,
    }
    if budget_snapshot is not None:
        payload["budget"] = budget_snapshot
    sidecars = dataset_dir / "invocations"
    sidecars.mkdir(parents=True, exist_ok=True)
    atomic_write_json(sidecars / f"{invocation_id}_{kind}.json", payload)


def _quality_status(records: list[ChunkQualityRecord]) -> QualityStatus:
    if any(c.status == ChunkStatus.CONFLICT for c in records):
        return QualityStatus.INVALID
    if any(c.duplicate_conflicting or c.same_date_conflicts for c in records):
        return QualityStatus.INVALID
    if any(
        c.intraday_rejected or c.suspicious_jump_flags or c.candidate_weekday_gap_dates or c.error_class
        for c in records
        if c.status != ChunkStatus.NOT_FETCHED
    ):
        return QualityStatus.LIMITED
    completed = [c for c in records if c.status == ChunkStatus.COMPLETED]
    if completed and all(
        not c.duplicate_conflicting and not c.same_date_conflicts and not c.intraday_rejected
        for c in completed
    ):
        return QualityStatus.CLEAN_WITHIN_CHECKS
    return QualityStatus.LIMITED


def _finalize(
    *,
    dataset_dir: Path,
    checkpoint: DatasetCheckpoint,
    budget: FullHistoryBudget,
    invocation_id: str,
    fetched_at: str,
    instrument_key: str | None,
    trading_symbol: str | None,
    chunk_records: list[ChunkQualityRecord],
    merged_hash: str | None,
    live_attempted: bool,
    overlap: list[dict],
    extra_limits: list[str],
    proposed_next_step: str,
    persist_dataset: bool = True,
    config_mismatch: bool = False,
) -> FullHistoryResult:
    acquisition = _acquisition_status(
        checkpoint,
        live_attempted=live_attempted,
        dataset_dir=dataset_dir,
        merged_hash=merged_hash,
    )
    quality = _quality_status(chunk_records)
    has_conflicts = _has_chunk_conflicts(checkpoint)
    eligibility = _backtest_eligibility(
        acquisition=acquisition,
        quality=quality,
        merged_hash=merged_hash,
        has_conflicts=has_conflicts,
    )
    if config_mismatch:
        acquisition = AcquisitionStatus.BLOCKED
        eligibility = BacktestEligibility.BLOCKED
    snap = budget.snapshot_dict()
    result = FullHistoryResult(
        dataset_id=checkpoint.dataset_id,
        invocation_id=invocation_id,
        fetched_at_utc=fetched_at,
        acquisition=acquisition,
        quality=quality,
        calendar_coverage="UNVERIFIED",
        adjustment_status="UNKNOWN",
        backtest_eligibility=eligibility,
        instrument_key=instrument_key,
        trading_symbol=trading_symbol,
        config_hash=checkpoint.config_hash,
        merged_hash=merged_hash,
        chunks=chunk_records,
        budget=BudgetSnapshot(
            invocation_historical_attempted=snap["invocation_historical_attempted"],
            invocation_historical_limit=snap["invocation_historical_limit"],
            dataset_historical_attempted=snap["dataset_historical_attempted"],
            dataset_historical_limit=snap["dataset_historical_limit"],
            invocation_master_attempted=snap["invocation_master_attempted"],
            invocation_master_limit=snap["invocation_master_limit"],
            dataset_master_attempted=snap["dataset_master_attempted"],
            per_chunk_attempts=snap["per_chunk_attempts"],
        ),
        split_coverage=_split_coverage(checkpoint),
        overlap_comparisons=overlap,
        output_dir=str(dataset_dir),
        manifest_path=str(dataset_dir / "manifest.json"),
        report_path=str(dataset_dir / "report.md"),
        limitations=list(LIMITATIONS) + extra_limits,
        proposed_next_step=proposed_next_step,
    )
    if persist_dataset:
        write_manifest(result)
        write_report(result)
        save_checkpoint(dataset_dir, checkpoint)
        atomic_write_json(
            dataset_dir / "invocations" / f"{invocation_id}.json",
            {"invocation_id": invocation_id, "fetched_at_utc": fetched_at, "budget": snap},
        )
    return result


def run_full_daily_history(
    transport: HttpTransport | None = None,
    *,
    output_root: Path | None = None,
    master_cache_path: Path | None = None,
    dataset_id: str | None = None,
    resume: bool = False,
    live_fetch: bool = True,
    invocation_id: str | None = None,
) -> FullHistoryResult:
    transport = transport or RequestsTransport()
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    master_cache_path = master_cache_path or DEFAULT_MASTER_CACHE
    dataset_id = dataset_id or default_dataset_id()
    invocation_id = invocation_id or str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat()
    dataset_dir = output_root / dataset_id
    extra_limits: list[str] = []
    can_live = live_fetch and _token_present()

    with dataset_lock(dataset_dir):
        try:
            if resume:
                if not dataset_dir.is_dir():
                    raise FileNotFoundError("dataset_missing_for_resume")
                checkpoint = load_checkpoint(dataset_dir)
            else:
                if dataset_dir.exists() and (dataset_dir / "checkpoint.json").is_file():
                    raise FileExistsError("dataset_already_exists_use_resume")
                checkpoint = init_checkpoint(dataset_dir, dataset_id)
        except CheckpointConflictError:
            stored = load_checkpoint_raw(dataset_dir)
            budget = FullHistoryBudget(stored, dataset_dir)
            merged_hash = _merged_hash_on_disk(dataset_dir)
            chunk_records = [_chunk_quality(stored.chunks[y]) for y, _, _ in YEARLY_CHUNKS if y in stored.chunks]
            _write_invocation_sidecar(
                dataset_dir,
                invocation_id,
                fetched_at=fetched_at,
                kind="config_conflict",
                detail="config_hash_mismatch",
                budget_snapshot=budget.snapshot_dict(),
            )
            return _finalize(
                dataset_dir=dataset_dir,
                checkpoint=stored,
                budget=budget,
                invocation_id=invocation_id,
                fetched_at=fetched_at,
                instrument_key=None,
                trading_symbol=None,
                chunk_records=chunk_records,
                merged_hash=merged_hash,
                live_attempted=False,
                overlap=[],
                extra_limits=["Config hash mismatch on resume; earlier evidence preserved (no dataset bytes rewritten)."],
                proposed_next_step="Resolve config conflict or use a new dataset_id.",
                persist_dataset=False,
                config_mismatch=True,
            )

        checkpoint.last_invocation_id = invocation_id
        save_checkpoint(dataset_dir, checkpoint)
        budget = FullHistoryBudget(checkpoint, dataset_dir)
        live_attempted = False
        instrument_key: str | None = None
        trading_symbol: str | None = None
        chunk_records: list[ChunkQualityRecord] = []
        chunk_stats: dict[str, object] = {}
        auth_stop = False

        try:
            master = load_master_for_audit(transport, master_cache_path, budget)
            matches = find_by_trading_symbol(master.records, SYMBOL)
            if len(matches) != 1:
                raise ValueError("ambiguous_instrument")
            inst = matches[0]
            instrument_key = inst.instrument_key
            trading_symbol = inst.trading_symbol
        except (AuditBudgetExceeded, ValueError, OSError, UpstoxAuthError):
            extra_limits.append("Instrument master resolution failed or budget exceeded.")
            for year, _, _ in YEARLY_CHUNKS:
                cp = checkpoint.chunks[year]
                if cp.status in (ChunkStatus.COMPLETED.value, ChunkStatus.CONFLICT.value):
                    continue
                cp.status = ChunkStatus.NOT_FETCHED.value
                cp.error_class = "MASTER_RESOLUTION_FAILED"
            return _finalize(
                dataset_dir=dataset_dir,
                checkpoint=checkpoint,
                budget=budget,
                invocation_id=invocation_id,
                fetched_at=fetched_at,
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                chunk_records=[_chunk_quality(checkpoint.chunks[y]) for y, _, _ in YEARLY_CHUNKS],
                merged_hash=None,
                live_attempted=can_live,
                overlap=compare_overlaps(dataset_dir),
                extra_limits=extra_limits,
                proposed_next_step="Fix master cache/resolution then explicit --resume.",
            )

        for year, from_d, to_d in YEARLY_CHUNKS:
            cp = checkpoint.chunks[year]
            if cp.status == ChunkStatus.CONFLICT.value:
                chunk_records.append(_chunk_quality(cp))
                continue

            if cp.status == ChunkStatus.COMPLETED.value:
                ok, verify_err = verify_completed_chunk(dataset_dir, cp)
                if ok:
                    stats = None
                    raw_path = dataset_dir / (cp.raw_path or "")
                    if raw_path.is_file():
                        candles = json.loads(raw_path.read_text(encoding="utf-8")).get("candles", [])
                        stats, _ = audit_raw_candles(candles, window_from=from_d, window_to=to_d)
                        present = {date.fromisoformat(cp.min_source_date)} if cp.min_source_date else set()
                        if stats.accepted_count:
                            _, accepted = audit_raw_candles(candles, window_from=from_d, window_to=to_d)
                            df = accepted_to_frame(accepted)
                            present = {ts.date() for ts in df.index}
                        gaps = all_candidate_weekday_gap_dates(from_d, to_d, present)
                        rec = _chunk_quality(cp, stats)
                        rec.candidate_weekday_gap_dates = [d.isoformat() for d in gaps]
                        chunk_records.append(rec)
                        chunk_stats[year] = stats
                    else:
                        cp.status = ChunkStatus.CONFLICT.value
                        cp.error_class = "ARTIFACT_MISSING"
                        save_checkpoint(dataset_dir, checkpoint)
                        chunk_records.append(_chunk_quality(cp))
                    continue
                cp.status = ChunkStatus.CONFLICT.value
                cp.error_class = verify_err or "HASH_MISMATCH"
                save_checkpoint(dataset_dir, checkpoint)
                chunk_records.append(_chunk_quality(cp))
                extra_limits.append(f"Chunk {year} integrity conflict ({cp.error_class}); no refetch on resume.")
                continue

            if auth_stop:
                cp.status = ChunkStatus.NOT_FETCHED.value
                cp.error_class = "AUTH_STOP"
                chunk_records.append(_chunk_quality(cp))
                continue

            if not can_live:
                cp.status = ChunkStatus.LIVE_CHECK_UNVERIFIED.value
                chunk_records.append(_chunk_quality(cp))
                continue

            attempts = checkpoint.per_chunk_attempts.get(year, 0)
            if attempts >= 2:
                if cp.status != ChunkStatus.COMPLETED.value:
                    cp.status = ChunkStatus.FAILED.value
                    cp.error_class = "CHUNK_ATTEMPT_BUDGET_EXHAUSTED"
                chunk_records.append(_chunk_quality(cp))
                continue

            live_attempted = True
            wkey = f"{year}"
            cp.status = ChunkStatus.INTENT.value
            save_checkpoint(dataset_dir, checkpoint)

            budget.set_chunk(year)
            try:
                status, candles, err = fetch_historical_candles_raw(
                    transport,
                    budget,
                    instrument_key=instrument_key,
                    from_d=from_d,
                    to_d=to_d,
                    window_label=wkey,
                )
            except AuditBudgetExceeded:
                cp.status = ChunkStatus.NOT_FETCHED.value
                cp.error_class = "INVOCATION_BUDGET_EXCEEDED"
                chunk_records.append(_chunk_quality(cp))
                for y2, _, _ in YEARLY_CHUNKS:
                    if y2 == year:
                        continue
                    if checkpoint.chunks[y2].status not in (
                        ChunkStatus.COMPLETED.value,
                        ChunkStatus.NOT_FETCHED.value,
                    ):
                        checkpoint.chunks[y2].status = ChunkStatus.NOT_FETCHED.value
                        checkpoint.chunks[y2].error_class = "NOT_ATTEMPTED_BUDGET"
                break

            cp.http_status = status
            cp.error_class = err

            if err in STOP_ERROR_CLASSES:
                auth_stop = True
                cp.status = ChunkStatus.FAILED.value
                chunk_records.append(_chunk_quality(cp))
                continue

            if candles is None:
                cp.status = ChunkStatus.FAILED.value
                chunk_records.append(_chunk_quality(cp))
                continue

            raw_rel = f"raw_{year}.json"
            raw_path = dataset_dir / raw_rel
            atomic_write_bytes(raw_path, sanitized_public_payload(candles))

            stats, accepted = audit_raw_candles(candles, window_from=from_d, window_to=to_d)
            chunk_stats[year] = stats
            if stats.duplicate_conflicting or stats.same_date_conflicts:
                raw_rel = f"raw_{year}.json"
                atomic_write_bytes(dataset_dir / raw_rel, sanitized_public_payload(candles))
                cp.status = ChunkStatus.CONFLICT.value
                cp.error_class = "RAW_CONFLICT"
                cp.raw_path = raw_rel
                save_checkpoint(dataset_dir, checkpoint)
                rec = _chunk_quality(cp, stats)
                rec.notes = ["Conflicting session dates; chunk blocked from COMPLETED status."]
                chunk_records.append(rec)
                extra_limits.append(f"Chunk {year} raw conflicts block merged usable dataset.")
                continue

            frame = accepted_to_frame(accepted)
            data_hash = canonical_data_hash(frame) if not frame.empty else None
            min_d = max_d = None
            present: set[date] = set()
            if not frame.empty:
                min_d = frame.index.min().date().isoformat()
                max_d = frame.index.max().date().isoformat()
                present = {ts.date() for ts in frame.index}
            norm_rel = f"normalized_{year}.json"
            norm_path = dataset_dir / norm_rel
            atomic_write_text(norm_path, frame.reset_index().to_json(orient="records", date_format="iso"))

            cp.status = ChunkStatus.COMPLETED.value
            cp.raw_path = raw_rel
            cp.normalized_path = norm_rel
            cp.data_hash = data_hash
            cp.min_source_date = min_d
            cp.max_source_date = max_d
            cp.row_count = len(frame)
            save_checkpoint(dataset_dir, checkpoint)

            gaps = all_candidate_weekday_gap_dates(from_d, to_d, present)
            rec = _chunk_quality(cp, stats)
            rec.candidate_weekday_gap_dates = [d.isoformat() for d in gaps]
            notes: list[str] = []
            if stats.duplicate_identical:
                notes.append(f"{stats.duplicate_identical} identical duplicate rows (counted, not merged).")
            if stats.duplicate_conflicting:
                notes.append("Conflicting duplicate timestamps present.")
            if stats.candidate_weekday_gap_count:
                notes.append(f"{stats.candidate_weekday_gap_count} candidate weekday gaps (calendar UNVERIFIED).")
            rec.notes = notes
            chunk_records.append(rec)

        if auth_stop:
            for year, _, _ in YEARLY_CHUNKS:
                if any(c.chunk_year == year for c in chunk_records):
                    continue
                cp = checkpoint.chunks[year]
                cp.status = ChunkStatus.NOT_FETCHED.value
                cp.error_class = "AUTH_STOP"
                chunk_records.append(_chunk_quality(cp))

        for year, _, _ in YEARLY_CHUNKS:
            if not any(c.chunk_year == year for c in chunk_records):
                chunk_records.append(_chunk_quality(checkpoint.chunks[year], chunk_stats.get(year)))

        merged, merged_hash, merge_notes = merge_completed_chunks(dataset_dir, checkpoint.chunks)
        if _has_chunk_conflicts(checkpoint):
            merged = None
            merged_hash = None
            merge_notes.append("Merge withheld: one or more chunks in CONFLICT.")
        elif merged is not None and merged_hash:
            atomic_write_text(
                dataset_dir / "merged_daily.json",
                merged.reset_index().to_json(orient="records", date_format="iso"),
            )
            atomic_write_json(
                dataset_dir / "merged_meta.json",
                {"data_hash": merged_hash, "row_count": int(len(merged))},
            )
        extra_limits.extend(merge_notes)
        overlap = compare_overlaps(dataset_dir)

        completed = sum(1 for c in checkpoint.chunks.values() if c.status == ChunkStatus.COMPLETED.value)
        if completed == len(YEARLY_CHUNKS):
            next_step = (
                "Optional: authoritative calendar/adjustment review before a separately scoped "
                "fixed experimental cash-equity backtest."
            )
        elif not can_live:
            next_step = "Provide UPSTOX_ACCESS_TOKEN and run one bounded acquisition invocation (already used if live ran)."
        elif auth_stop:
            next_step = "Resolve auth/rate/unavailable blocker; remaining chunks need explicit --resume within budgets."
        else:
            next_step = "Explicit --resume to continue acquisition within per-chunk/dataset request budgets."

        return _finalize(
            dataset_dir=dataset_dir,
            checkpoint=checkpoint,
            budget=budget,
            invocation_id=invocation_id,
            fetched_at=fetched_at,
            instrument_key=instrument_key,
            trading_symbol=trading_symbol,
            chunk_records=chunk_records,
            merged_hash=merged_hash,
            live_attempted=live_attempted,
            overlap=overlap,
            extra_limits=extra_limits,
            proposed_next_step=next_step,
        )
