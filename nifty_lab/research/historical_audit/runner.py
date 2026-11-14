"""Orchestrate bounded ICICIBANK historical audit."""
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

from .budget import AuditBudgetExceeded, AuditRequestBudget
from .client import fetch_historical_candles_raw, sanitized_public_payload
from .manifest import write_manifest, write_report
from .master_cache import load_master_for_audit
from .quality import accepted_to_frame, audit_raw_candles, canonical_data_hash
from .types import (
    AUDIT_SYMBOL,
    AUDIT_WINDOWS,
    RESEARCH_ROLE_LABELS,
    AuditRunResult,
    OverallStatus,
    RequestBudgetSnapshot,
    WindowAuditResult,
    WindowStatus,
)

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "research" / "audit_runs"
DEFAULT_MASTER_CACHE = PROJECT_ROOT / "research" / "audit_cache" / "nse_instruments.json.gz"

LIMITATIONS = [
    "Three separated monthly samples do not verify continuous 2021–2025 coverage.",
    "NSE session calendar not sourced in-repo; weekday gaps are candidate missing sessions, not confirmed.",
    "Corporate-action / adjusted-price status is UNKNOWN; smooth series are not evidence of adjustment.",
    "Single-symbol ICICIBANK sample is not a survivorship-free universe.",
    "No strategy signals, outcomes or parameter search were run.",
    "November 2026 is excluded from historical samples.",
]


def _window_key(from_d, to_d) -> str:
    return f"{from_d.isoformat()}_{to_d.isoformat()}"


def _classify_window(stats, row_count: int, error_class: str | None) -> WindowStatus:
    if error_class in ("AUTH_BLOCKED", "RATE_LIMITED", "UNAVAILABLE"):
        return WindowStatus.BLOCKED
    if error_class:
        return WindowStatus.LIMITED if row_count > 0 else WindowStatus.BLOCKED
    if stats is None:
        return WindowStatus.LIMITED if row_count > 0 else WindowStatus.BLOCKED
    if stats.duplicate_conflicting or stats.same_date_conflicts or stats.intraday_timestamp_rejected:
        return WindowStatus.LIMITED
    if row_count <= 0:
        return WindowStatus.LIMITED
    if stats.rejected_count > 0 or stats.zero_volume_flags > 0 or stats.suspicious_jump_flags > 0:
        return WindowStatus.LIMITED
    return WindowStatus.FEASIBLE_SAMPLE


def _not_fetched_window(
    from_d: date,
    to_d: date,
    *,
    instrument_key: str | None,
    trading_symbol: str | None,
    error_class: str,
    note: str,
) -> WindowAuditResult:
    wkey = _window_key(from_d, to_d)
    return WindowAuditResult(
        window_key=wkey,
        requested_from=from_d.isoformat(),
        requested_to=to_d.isoformat(),
        research_role=RESEARCH_ROLE_LABELS.get(wkey, "sample"),
        status=WindowStatus.NOT_FETCHED,
        http_status=None,
        error_class=error_class,
        instrument_key=instrument_key,
        trading_symbol=trading_symbol,
        min_source_date=None,
        max_source_date=None,
        row_count_normalized=0,
        data_hash=None,
        raw_stats=None,
        notes=[note],
    )


def _planned_window_inventory(
    *,
    instrument_key: str | None,
    trading_symbol: str | None,
    live_unverified: bool,
) -> list[WindowAuditResult]:
    out: list[WindowAuditResult] = []
    for from_d, to_d in AUDIT_WINDOWS:
        wkey = _window_key(from_d, to_d)
        out.append(
            WindowAuditResult(
                window_key=wkey,
                requested_from=from_d.isoformat(),
                requested_to=to_d.isoformat(),
                research_role=RESEARCH_ROLE_LABELS.get(wkey, "sample"),
                status=WindowStatus.LIVE_CHECK_UNVERIFIED if live_unverified else WindowStatus.NOT_FETCHED,
                http_status=None,
                error_class=None if live_unverified else "PLANNED",
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                min_source_date=None,
                max_source_date=None,
                row_count_normalized=0,
                data_hash=None,
                raw_stats=None,
            )
        )
    return out


def _finalize_run(
    *,
    run_id: str,
    fetched_at: str,
    run_dir: Path,
    budget: AuditRequestBudget,
    windows_out: list[WindowAuditResult],
    overall: OverallStatus,
    instrument_key: str | None,
    trading_symbol: str | None,
    limitations: list[str],
    proposed_next_step: str,
) -> AuditRunResult:
    result = AuditRunResult(
        run_id=run_id,
        fetched_at_utc=fetched_at,
        overall_status=overall,
        instrument_key=instrument_key,
        trading_symbol=trading_symbol,
        windows=windows_out,
        budget=RequestBudgetSnapshot(
            historical_attempted=budget.historical_attempted,
            historical_limit=budget.historical_limit,
            master_attempted=budget.master_attempted,
            master_limit=budget.master_limit,
        ),
        output_dir=str(run_dir),
        manifest_path=str(run_dir / "manifest.json"),
        report_path=str(run_dir / "report.md"),
        limitations=limitations,
        proposed_next_step=proposed_next_step,
    )
    write_manifest(result)
    write_report(result)
    (run_dir / "run_meta.json").write_text(
        json.dumps({"run_id": run_id, "symbol": trading_symbol}, indent=2),
        encoding="utf-8",
    )
    return result


def _overall_status(
    windows: list[WindowAuditResult],
    *,
    live_attempted: bool,
    blocked: bool,
) -> OverallStatus:
    if not live_attempted:
        return OverallStatus.LIVE_CHECK_UNVERIFIED
    if blocked and all(w.status in (WindowStatus.BLOCKED, WindowStatus.NOT_FETCHED) for w in windows):
        return OverallStatus.BLOCKED
    statuses = {w.status for w in windows if w.status != WindowStatus.NOT_FETCHED}
    if statuses <= {WindowStatus.FEASIBLE_SAMPLE} and statuses:
        return OverallStatus.FEASIBLE_SAMPLE
    if WindowStatus.BLOCKED in statuses and not statuses - {WindowStatus.BLOCKED, WindowStatus.NOT_FETCHED}:
        return OverallStatus.BLOCKED
    return OverallStatus.LIMITED


def run_historical_data_audit(
    transport: HttpTransport | None = None,
    *,
    output_root: Path | None = None,
    master_cache_path: Path | None = None,
    live_fetch: bool = True,
    run_id: str | None = None,
) -> AuditRunResult:
    transport = transport or RequestsTransport()
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    master_cache_path = master_cache_path or DEFAULT_MASTER_CACHE
    run_id = run_id or str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    budget = AuditRequestBudget()
    can_live = live_fetch and _token_present()

    try:
        return _run_audit_body(
            transport=transport,
            master_cache_path=master_cache_path,
            run_id=run_id,
            fetched_at=fetched_at,
            run_dir=run_dir,
            budget=budget,
            can_live=can_live,
        )
    except Exception:
        windows_out = _planned_window_inventory(
            instrument_key=None, trading_symbol=None, live_unverified=not can_live
        )
        return _finalize_run(
            run_id=run_id,
            fetched_at=fetched_at,
            run_dir=run_dir,
            budget=budget,
            windows_out=windows_out,
            overall=OverallStatus.BLOCKED,
            instrument_key=None,
            trading_symbol=None,
            limitations=list(LIMITATIONS) + ["Runner aborted before inventory completed."],
            proposed_next_step="Re-run audit after fixing unexpected failure.",
        )


def _run_audit_body(
    *,
    transport: HttpTransport,
    master_cache_path: Path,
    run_id: str,
    fetched_at: str,
    run_dir: Path,
    budget: AuditRequestBudget,
    can_live: bool,
) -> AuditRunResult:
    live_attempted = False
    auth_blocked = False
    instrument_key: str | None = None
    trading_symbol: str | None = None
    windows_out: list[WindowAuditResult] = []
    extra_limits: list[str] = []

    try:
        master = load_master_for_audit(transport, master_cache_path, budget)
        matches = find_by_trading_symbol(master.records, AUDIT_SYMBOL)
        if len(matches) != 1:
            raise ValueError("ambiguous_instrument")
        inst = matches[0]
        instrument_key = inst.instrument_key
        trading_symbol = inst.trading_symbol
    except AuditBudgetExceeded:
        extra_limits.append("Instrument master request budget exceeded.")
        windows_out = _planned_window_inventory(
            instrument_key=None, trading_symbol=None, live_unverified=not can_live
        )
        return _finalize_run(
            run_id=run_id,
            fetched_at=fetched_at,
            run_dir=run_dir,
            budget=budget,
            windows_out=windows_out,
            overall=OverallStatus.BLOCKED,
            instrument_key=None,
            trading_symbol=None,
            limitations=list(LIMITATIONS) + extra_limits,
            proposed_next_step="Resolve master budget/instrument resolution before historical sampling.",
        )
    except (ValueError, OSError, UpstoxAuthError):
        extra_limits.append("Instrument master resolution failed (cache corrupt, ambiguous symbol, or transport blocked).")
        windows_out = _planned_window_inventory(
            instrument_key=None, trading_symbol=None, live_unverified=not can_live
        )
        for w in windows_out:
            if not can_live:
                continue
            w.status = WindowStatus.NOT_FETCHED
            w.error_class = "MASTER_RESOLUTION_FAILED"
        return _finalize_run(
            run_id=run_id,
            fetched_at=fetched_at,
            run_dir=run_dir,
            budget=budget,
            windows_out=windows_out,
            overall=OverallStatus.BLOCKED,
            instrument_key=None,
            trading_symbol=None,
            limitations=list(LIMITATIONS) + extra_limits,
            proposed_next_step="Fix instrument master cache or symbol resolution before historical sampling.",
        )

    window_list = list(AUDIT_WINDOWS)
    for idx, (from_d, to_d) in enumerate(window_list):
        wkey = _window_key(from_d, to_d)
        role = RESEARCH_ROLE_LABELS.get(wkey, "sample")
        if not can_live:
            windows_out.append(
                WindowAuditResult(
                    window_key=wkey,
                    requested_from=from_d.isoformat(),
                    requested_to=to_d.isoformat(),
                    research_role=role,
                    status=WindowStatus.LIVE_CHECK_UNVERIFIED,
                    http_status=None,
                    error_class=None,
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    min_source_date=None,
                    max_source_date=None,
                    row_count_normalized=0,
                    data_hash=None,
                    raw_stats=None,
                    notes=["Live historical fetch skipped (no token or live_fetch=False)."],
                )
            )
            continue

        live_attempted = True
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
            windows_out.append(
                WindowAuditResult(
                    window_key=wkey,
                    requested_from=from_d.isoformat(),
                    requested_to=to_d.isoformat(),
                    research_role=role,
                    status=WindowStatus.NOT_FETCHED,
                    http_status=None,
                    error_class="BUDGET_EXCEEDED",
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    min_source_date=None,
                    max_source_date=None,
                    row_count_normalized=0,
                    data_hash=None,
                    raw_stats=None,
                )
            )
            continue

        if err == "AUTH_BLOCKED":
            auth_blocked = True
            windows_out.append(
                WindowAuditResult(
                    window_key=wkey,
                    requested_from=from_d.isoformat(),
                    requested_to=to_d.isoformat(),
                    research_role=role,
                    status=WindowStatus.BLOCKED,
                    http_status=status,
                    error_class=err,
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    min_source_date=None,
                    max_source_date=None,
                    row_count_normalized=0,
                    data_hash=None,
                    raw_stats=None,
                    notes=["Authentication blocked; no retry."],
                )
            )
            for from_r, to_r in window_list[idx + 1 :]:
                windows_out.append(
                    _not_fetched_window(
                        from_r,
                        to_r,
                        instrument_key=instrument_key,
                        trading_symbol=trading_symbol,
                        error_class="AUTH_STOP",
                        note="Not attempted after authentication block.",
                    )
                )
            break

        if candles is None:
            windows_out.append(
                WindowAuditResult(
                    window_key=wkey,
                    requested_from=from_d.isoformat(),
                    requested_to=to_d.isoformat(),
                    research_role=role,
                    status=WindowStatus.BLOCKED,
                    http_status=status,
                    error_class=err,
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    min_source_date=None,
                    max_source_date=None,
                    row_count_normalized=0,
                    data_hash=None,
                    raw_stats=None,
                )
            )
            continue

        raw_path = run_dir / f"raw_{wkey}.json"
        raw_path.write_bytes(sanitized_public_payload(candles))

        stats, accepted = audit_raw_candles(candles, window_from=from_d, window_to=to_d)
        frame = accepted_to_frame(accepted)
        data_hash = canonical_data_hash(frame) if not frame.empty else None
        min_d = max_d = None
        if not frame.empty:
            min_d = frame.index.min().date().isoformat()
            max_d = frame.index.max().date().isoformat()
        norm_path = run_dir / f"normalized_{wkey}.json"
        norm_path.write_text(
            frame.reset_index().to_json(orient="records", date_format="iso"),
            encoding="utf-8",
        )

        notes: list[str] = []
        if stats.duplicate_conflicting:
            notes.append("Conflicting duplicate timestamps in raw payload.")
        if stats.same_date_conflicts or stats.intraday_timestamp_rejected:
            notes.append("Intraday or same-date conflicts rejected under daily policy.")
        if stats.out_of_range:
            notes.append("Raw rows outside requested window present.")
        if stats.zero_volume_flags:
            notes.append("Zero-volume bars flagged; not forward-filled.")
        if stats.candidate_weekday_gap_count:
            notes.append(
                f"{stats.candidate_weekday_gap_count} candidate weekday gaps (calendar UNVERIFIED)."
            )
        if stats.input_order != "unknown":
            notes.append(f"Raw input date order: {stats.input_order}.")

        win_status = _classify_window(stats, len(frame), err)
        windows_out.append(
            WindowAuditResult(
                window_key=wkey,
                requested_from=from_d.isoformat(),
                requested_to=to_d.isoformat(),
                research_role=role,
                status=win_status,
                http_status=status,
                error_class=err,
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                min_source_date=min_d,
                max_source_date=max_d,
                row_count_normalized=len(frame),
                data_hash=data_hash,
                raw_stats=stats,
                notes=notes,
            )
        )

    overall = _overall_status(windows_out, live_attempted=live_attempted, blocked=auth_blocked)
    if overall == OverallStatus.FEASIBLE_SAMPLE:
        next_step = (
            "If acceptable: design resumable bounded full-daily-history acquisition for 2021–2025 "
            "with calendar/adjustment review before any backtest engine work."
        )
    elif overall == OverallStatus.LIVE_CHECK_UNVERIFIED:
        next_step = "Provide UPSTOX_ACCESS_TOKEN locally and re-run scripts/run_historical_data_audit.py once for live verification."
    else:
        next_step = "Resolve blocker (auth, instrument, or data quality) before bulk history design."

    if len(windows_out) < len(AUDIT_WINDOWS):
        have = {w.window_key for w in windows_out}
        for from_d, to_d in AUDIT_WINDOWS:
            wkey = _window_key(from_d, to_d)
            if wkey not in have:
                windows_out.append(
                    _not_fetched_window(
                        from_d,
                        to_d,
                        instrument_key=instrument_key,
                        trading_symbol=trading_symbol,
                        error_class="NOT_ATTEMPTED",
                        note="Window inventory completed after partial run.",
                    )
                )

    return _finalize_run(
        run_id=run_id,
        fetched_at=fetched_at,
        run_dir=run_dir,
        budget=budget,
        windows_out=windows_out,
        overall=overall,
        instrument_key=instrument_key,
        trading_symbol=trading_symbol,
        limitations=list(LIMITATIONS) + extra_limits,
        proposed_next_step=next_step,
    )
