"""Read-only view-model for Backtesting Lab (no network, no writes on import)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import BACKTEST_RUNS_ROOT, REVIEW_OUTPUT_ROOT
from .diagnostics import fixed_fill_stress_table
from .loader import ArchivedBook, fingerprints_match_stored, load_approved_pair
from .runner import find_latest_review, load_review_manifest


def _book_card(book: ArchivedBook) -> dict[str, Any]:
    if book.load_status != "OK":
        return {"book_id": book.book_id, "status": book.load_status, "error": book.load_error}
    s = book.summary
    dd = s.get("drawdown") or {}
    return {
        "book_id": book.book_id,
        "status": "OK",
        "run_id": book.run_id,
        "readiness": book.manifest.get("readiness", "EXPLORATORY"),
        "split_id": book.manifest.get("split_id") or "development",
        "purpose": book.registration.get("purpose") or book.registration.get("correction_reason"),
        "initial_cash_inr": s.get("initial_cash_inr", "20000.00"),
        "final_cash_inr": s.get("final_cash_inr"),
        "closed_trades": s.get("closed_trades"),
        "net_pnl_inr": s.get("net_pnl_inr"),
        "win_rate_note": "Observed win rate — not next-trade probability",
        "win_rate": s.get("win_rate"),
        "win_rate_wilson_95_lo": s.get("win_rate_wilson_95_lo"),
        "win_rate_wilson_95_hi": s.get("win_rate_wilson_95_hi"),
        "profit_factor": s.get("profit_factor"),
        "max_drawdown_inr": dd.get("max_drawdown_inr"),
        "max_drawdown_pct": dd.get("max_drawdown_pct"),
        "drawdown_denominator": dd.get("denominator"),
        "modeled_fees_entry_inr": s.get("modeled_entry_fees_inr"),
        "modeled_fees_exit_inr": s.get("modeled_exit_fees_inr"),
        "turnover_notional_inr": s.get("turnover_notional_inr"),
        "reconcile": book.reconcile,
        "baselines": book.baselines,
        "equity_points": len(book.equity_curve),
        "holdout_note": book.manifest.get("holdout_years_not_used_for_outcomes"),
        "fingerprints": book.source_fingerprints,
    }


def build_results_review_view(
    *,
    runs_root: Path | None = None,
    review_root: Path | None = None,
) -> dict[str, Any]:
    """Pure function for dashboard/tests. Re-validates sources every call."""
    runs_root = runs_root or BACKTEST_RUNS_ROOT
    review_root = review_root or REVIEW_OUTPUT_ROOT
    dev, val = load_approved_pair(runs_root)
    dev_card = _book_card(dev)
    val_card = _book_card(val)

    stress_dev = fixed_fill_stress_table(dev.trades, book_label="development") if dev.load_status == "OK" else None
    stress_val = fixed_fill_stress_table(val.trades, book_label="validation") if val.load_status == "OK" else None

    artifact_path = find_latest_review(review_root)
    artifact_manifest: dict | None = None
    artifact_stale = False
    artifact_warning: str | None = None
    artifact_label = "in_memory_diagnostics"
    if artifact_path:
        artifact_manifest = load_review_manifest(artifact_path)
        if artifact_manifest is None or not isinstance(artifact_manifest, dict):
            artifact_warning = "Saved review manifest missing or unreadable — using verified in-memory diagnostics only."
        else:
            stored_dev = artifact_manifest.get("source_runs", {}).get("development", {}).get("fingerprints", {})
            stored_val = artifact_manifest.get("source_runs", {}).get("validation", {}).get("fingerprints", {})
            artifact_stale = not fingerprints_match_stored(stored_dev, dev) or not fingerprints_match_stored(
                stored_val, val
            )
            artifact_label = "saved_review_artifact" if not artifact_stale else "saved_artifact_stale"
            if artifact_stale:
                artifact_warning = (
                    "Saved review artifact fingerprints differ from current sources — manifest not treated as verified."
                )

    return {
        "overall_status": "EXPLORATORY / INSUFFICIENT EVIDENCE",
        "live_or_paper_qualification": False,
        "holdout_2025": "NOT EVALUATED",
        "development": dev_card,
        "validation": val_card,
        "books": {"development": dev, "validation": val},
        "cost_diagnostics": {
            "development": stress_dev,
            "validation": stress_val,
            "disclaimer": (
                "A small extra cost can erase this validation gain; these scenarios keep the old trades fixed."
            ),
            "source": artifact_label,
            "artifact_path": str(artifact_path) if artifact_path else None,
            "artifact_stale": artifact_stale,
            "artifact_warning": artifact_warning,
        },
        "limitations": [
            "Calendar UNVERIFIED; adjustment UNKNOWN.",
            "Fees and slippage illustrative (10 bps/side in archived runs).",
            "Single symbol; small sample; daily-bar ordering.",
            "Independent accounts — not a continuous combined return.",
        ],
        "artifact_manifest": artifact_manifest,
    }


def equity_series_for_chart(book: ArchivedBook) -> list[dict[str, str]] | None:
    if book.load_status != "OK":
        return None
    return [
        {"ts": p.get("ts", ""), "net_liquidation_inr": p.get("net_liquidation_inr", "")}
        for p in book.equity_curve
    ]
