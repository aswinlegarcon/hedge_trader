"""Generate one immutable results/cost review artifact."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    ANALYST_CONCLUSION,
    APPROVED_DEVELOPMENT_RUN_ID,
    APPROVED_VALIDATION_RUN_ID,
    BACKTEST_RUNS_ROOT,
    BROKERAGE_REFERENCE_CHECKED_DATE,
    BROKERAGE_REFERENCE_URL,
    FROZEN_RULES_HASH,
    REVIEW_OUTPUT_ROOT,
    VALIDATION_EVALUATION_CONFIG_HASH,
)
from .diagnostics import fixed_fill_stress_table
from .loader import load_approved_pair


def _stress_definitions() -> dict:
    return {
        "method": "FIXED_FILL_DIAGNOSTIC",
        "base": "Archived modeled net P&L unchanged",
        "bps_formula": "extra_cost = turnover * bps / 10000; turnover = sum(qty*entry_fill + qty*exit_fill)",
        "bps_rounding": "ROUND_HALF_EVEN to 0.01 INR once on total extra cost",
        "inr_per_execution": "₹1 per modeled entry plus ₹1 per modeled exit (2 * closed_trades)",
        "no_double_count": "Illustrative fees/slippage already embedded in archived fills and net P&L",
        "bps_scenarios": [1, 5, 10],
    }


def run_results_cost_review(
    *,
    output_root: Path | None = None,
    review_id: str | None = None,
    runs_root: Path | None = None,
) -> dict:
    output_root = output_root or REVIEW_OUTPUT_ROOT
    runs_root = runs_root or BACKTEST_RUNS_ROOT
    review_id = review_id or str(uuid.uuid4())
    review_dir = output_root / review_id
    if review_dir.exists():
        raise FileExistsError("review_directory_exists")

    dev, val = load_approved_pair(runs_root)
    if dev.load_status != "OK" or val.load_status != "OK":
        raise ValueError("approved_runs_not_loadable")

    dev_stress = fixed_fill_stress_table(dev.trades, book_label="development_2021_2023")
    val_stress = fixed_fill_stress_table(val.trades, book_label="validation_2024")

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "review_id": review_id,
        "generated_at_utc": generated_at,
        "status": "REVIEW_COMPLETE",
        "analyst_conclusion": ANALYST_CONCLUSION,
        "readiness": "EXPLORATORY",
        "evidence_level": "INSUFFICIENT_EVIDENCE",
        "not_live_ready": True,
        "not_forward_paper_candidate": True,
        "holdout_2025": "NOT_EVALUATED",
        "frozen_rules_hash": FROZEN_RULES_HASH,
        "source_runs": {
            "development": {
                "run_id": APPROVED_DEVELOPMENT_RUN_ID,
                "fingerprints": dev.source_fingerprints,
                "reconcile": dev.reconcile,
            },
            "validation": {
                "run_id": APPROVED_VALIDATION_RUN_ID,
                "evaluation_config_hash": VALIDATION_EVALUATION_CONFIG_HASH,
                "fingerprints": val.source_fingerprints,
                "reconcile": val.reconcile,
                "holdout_year_integrity": val.manifest.get("holdout_year_integrity"),
            },
        },
        "stress_definitions": _stress_definitions(),
        "per_book_diagnostics": {
            "development": dev_stress,
            "validation": val_stress,
        },
        "brokerage_reference": {
            "url": BROKERAGE_REFERENCE_URL,
            "checked_date": BROKERAGE_REFERENCE_CHECKED_DATE,
            "note": "Reference only; no rates applied to historical fills in this review",
        },
        "limitations": [
            "FIXED_FILL_DIAGNOSTIC only — no re-simulation of sizing, admission, or exits.",
            "Illustrative 10 bps/side fees and slippage in archived runs; actual tariffs unresolved.",
            "Independent accounts; do not pool development and validation returns.",
            "Observed win rates are descriptive, not next-trade probability.",
            "Single symbol ICICIBANK; small trade sample.",
        ],
    }

    review_dir.mkdir(parents=True, exist_ok=False)
    (review_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (review_dir / "development_stress.json").write_text(json.dumps(dev_stress, indent=2), encoding="utf-8")
    (review_dir / "validation_stress.json").write_text(json.dumps(val_stress, indent=2), encoding="utf-8")
    (review_dir / "report.md").write_text(
        "\n".join(
            [
                "# Results and cost sensitivity review",
                "",
                f"review_id: `{review_id}`",
                f"conclusion: **{ANALYST_CONCLUSION}**",
                "",
                "## Validation fixed-fill highlights",
                f"- Turnover: {val_stress.get('executed_turnover_inr')}",
                f"- Archived net: {val_stress.get('archived_net_pnl_inr')}",
                f"- Break-even extra bps: {val_stress.get('break_even_extra_bps')}",
                "",
                "See manifest.json for full scenario table and source fingerprints.",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "status": "REVIEW_COMPLETE",
        "review_id": review_id,
        "review_dir": str(review_dir),
        "analyst_conclusion": ANALYST_CONCLUSION,
        "validation_turnover_inr": val_stress.get("executed_turnover_inr"),
    }


def find_latest_review(review_root: Path | None = None) -> Path | None:
    root = review_root or REVIEW_OUTPUT_ROOT
    if not root.is_dir():
        return None
    candidates = sorted(
        (p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_review_manifest(review_dir: Path) -> dict | None:
    path = review_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
