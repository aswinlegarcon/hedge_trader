"""Artifact writers for development backtest runs."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nifty_lab.config import FAKE_SECRET_SENTINEL

from .config import rules_config_hash, frozen_rules_payload


def _scrub(text: str) -> str:
    if FAKE_SECRET_SENTINEL in text:
        raise ValueError("sentinel leak")
    return text


def write_blocked_run(run_dir: Path, *, error_class: str, preflight: dict, run_id: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "BLOCKED",
        "error_class": error_class,
        "run_id": run_id,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": "UNTESTED",
        "preflight": preflight,
        "backtest_eligibility": "BLOCKED",
    }
    text = _scrub(json.dumps(manifest, indent=2))
    (run_dir / "manifest.json").write_text(text, encoding="utf-8")
    (run_dir / "report.md").write_text(
        _scrub(f"# Development backtest blocked\n\nerror_class: **{error_class}**\n"),
        encoding="utf-8",
    )


def write_success_run(
    run_dir: Path,
    *,
    run_id: str,
    preflight: dict,
    rules_hash: str,
    simulation: dict,
    summary: dict,
    baselines: dict,
    engine_source_digest: str,
    lineage: dict | None = None,
) -> None:
    payload = {
        "status": "EXPLORATORY_COMPLETE",
        "run_id": run_id,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": "EXPLORATORY",
        "evidence_level": "INSUFFICIENT_FOR_PREDICTION",
        "not_live_ready": True,
        "rules_config_hash": rules_hash,
        "frozen_rules": frozen_rules_payload(),
        "engine_source_digest": engine_source_digest,
        "lineage": lineage or {},
        "preflight": preflight,
        "summary": summary,
        "baselines": baselines,
        "simulation_meta": {
            "opportunity_count": simulation.get("opportunity_count"),
            "skipped_while_holding": simulation.get("skipped_while_holding"),
            "halted_new_entries": simulation.get("halted_new_entries"),
            "ambiguous_same_bar": simulation.get("ambiguous_same_bar"),
            "boundary_forced_exits": simulation.get("boundary_forced_exits"),
        },
        "limitations": [
            "Calendar UNVERIFIED; adjustment UNKNOWN.",
            "Costs illustrative only; not verified Upstox/NSE/STT/GST/DP.",
            "Development 2021-2023 only; 2024 validation and 2025 holdout not evaluated.",
            "No optimization; single frozen strategy variant.",
        ],
    }
    (run_dir / "manifest.json").write_text(_scrub(json.dumps(payload, indent=2)), encoding="utf-8")
    (run_dir / "frozen_rules.json").write_text(_scrub(json.dumps(frozen_rules_payload(), indent=2)), encoding="utf-8")
    (run_dir / "trades.json").write_text(_scrub(json.dumps(simulation.get("trades", []), indent=2)), encoding="utf-8")
    (run_dir / "signals.json").write_text(_scrub(json.dumps(simulation.get("signals", []), indent=2)), encoding="utf-8")
    (run_dir / "equity_daily.json").write_text(
        _scrub(json.dumps(simulation.get("equity_curve", []), indent=2)), encoding="utf-8"
    )
    (run_dir / "summary.json").write_text(_scrub(json.dumps(summary, indent=2)), encoding="utf-8")
    report = [
        "# Development backtest (exploratory)",
        "",
        f"run_id: `{run_id}`",
        "readiness: **EXPLORATORY** — not validated, not Live-ready, not forward PAPER candidate.",
        f"rules hash: `{rules_hash}`",
        "calendar: **UNVERIFIED**; adjustment: **UNKNOWN**.",
        "costs: illustrative 10bps/side slip and fee — not verified broker tariffs.",
        "baseline B&H: first session after 100-bar warmup open; whole shares with fees in sizing.",
        "",
        "## Summary",
        json.dumps(summary, indent=2),
    ]
    (run_dir / "report.md").write_text(_scrub("\n".join(report)), encoding="utf-8")


def write_error_run(
    run_dir: Path,
    *,
    error_class: str,
    preflight: dict,
    run_id: str,
    purpose: str | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "ERROR",
        "error_class": error_class,
        "run_id": run_id,
        "purpose": purpose,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": "UNTESTED",
        "preflight": preflight,
        "backtest_eligibility": "BLOCKED",
    }
    text = _scrub(json.dumps(manifest, indent=2))
    (run_dir / "manifest.json").write_text(text, encoding="utf-8")
    (run_dir / "report.md").write_text(
        _scrub(f"# Backtest error\n\nerror_class: **{error_class}**\n"),
        encoding="utf-8",
    )


def write_validation_success_run(
    run_dir: Path,
    *,
    run_id: str,
    preflight: dict,
    rules_hash: str,
    evaluation_hash: str,
    simulation: dict,
    summary: dict,
    baselines: dict,
    engine_source_digest: str,
    lineage: dict | None = None,
    context_hash: str | None = None,
    evaluation_bars_hash: str | None = None,
    holdout_years: list[int] | None = None,
    holdout_hashes: dict[str, str] | None = None,
) -> None:
    payload = {
        "status": "EXPLORATORY_COMPLETE",
        "run_id": run_id,
        "split_id": "validation-2024",
        "purpose": "FROZEN_2024_VALIDATION",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": "EXPLORATORY",
        "evidence_level": "INSUFFICIENT_FOR_PREDICTION",
        "not_live_ready": True,
        "rules_config_hash": rules_hash,
        "evaluation_config_hash": evaluation_hash,
        "frozen_rules": frozen_rules_payload(),
        "engine_source_digest": engine_source_digest,
        "lineage": lineage or {},
        "preflight": preflight,
        "context_bars_hash": context_hash,
        "evaluation_bars_hash": evaluation_bars_hash,
        "holdout_year_integrity": holdout_hashes,
        "holdout_years_not_used_for_outcomes": holdout_years or [],
        "summary": summary,
        "baselines": baselines,
        "simulation_meta": {
            "opportunity_count": simulation.get("opportunity_count"),
            "skipped_while_holding": simulation.get("skipped_while_holding"),
            "skipped_exit_session": simulation.get("skipped_exit_session"),
            "halted_new_entries": simulation.get("halted_new_entries"),
            "ambiguous_same_bar": simulation.get("ambiguous_same_bar"),
            "boundary_forced_exits": simulation.get("boundary_forced_exits"),
        },
        "limitations": [
            "Calendar UNVERIFIED; adjustment UNKNOWN.",
            "Costs illustrative only; not verified broker charges.",
            "Independent ₹20k validation account; not continuous 2021–2024 return.",
            "2025 holdout not evaluated for outcomes in this slice.",
            "No optimization; single frozen strategy variant.",
        ],
    }
    (run_dir / "manifest.json").write_text(_scrub(json.dumps(payload, indent=2)), encoding="utf-8")
    (run_dir / "frozen_rules.json").write_text(_scrub(json.dumps(frozen_rules_payload(), indent=2)), encoding="utf-8")
    (run_dir / "evaluation_config.json").write_text(
        _scrub(json.dumps(lineage.get("evaluation_config", {}), indent=2) if lineage else "{}"),
        encoding="utf-8",
    )
    (run_dir / "trades.json").write_text(_scrub(json.dumps(simulation.get("trades", []), indent=2)), encoding="utf-8")
    (run_dir / "signals.json").write_text(_scrub(json.dumps(simulation.get("signals", []), indent=2)), encoding="utf-8")
    (run_dir / "equity_daily.json").write_text(
        _scrub(json.dumps(simulation.get("equity_curve", []), indent=2)), encoding="utf-8"
    )
    (run_dir / "summary.json").write_text(_scrub(json.dumps(summary, indent=2)), encoding="utf-8")
    report = [
        "# 2024 validation replay (exploratory)",
        "",
        f"run_id: `{run_id}`",
        "readiness: **EXPLORATORY** — not validated, not Live-ready.",
        f"rules hash: `{rules_hash}`",
        f"evaluation hash: `{evaluation_hash}`",
        "independent account: ₹20k; context 2021–2023 indicators only.",
        "",
        "## Summary",
        json.dumps(summary, indent=2),
    ]
    (run_dir / "report.md").write_text(_scrub("\n".join(report)), encoding="utf-8")


def append_trial_inventory(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _scrub(json.dumps(record, separators=(",", ":"))) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
