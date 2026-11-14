"""Orchestrate offline development backtest (no network)."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from nifty_lab.config import PROJECT_ROOT

from .config import (
    BACKTEST_OUTPUT_ROOT,
    CORRECTION_REASON,
    ORIGINAL_PROVISIONAL_RUN_ID,
    ORIGINAL_RULES_CONFIG_HASH,
    REGISTERED_DATASET_DIR,
    RULES_MECHANICS_VERSION,
    TRIAL_INVENTORY_PATH,
    frozen_rules_payload,
    rules_config_hash,
)
from .engine import SimulationResult, simulate_development
from .io_registration import write_preregistered_artifacts
from .metrics import (
    buy_hold_baseline,
    cash_baseline_final,
    equity_drawdown,
    summarize_trades,
    yearly_trade_breakdown,
)
from .preflight import PreflightResult, development_frame_from_verified, verify_registered_dataset
from .report import append_trial_inventory, write_blocked_run, write_error_run, write_success_run


def _engine_source_digest() -> str:
    root = PROJECT_ROOT / "nifty_lab" / "research" / "development_backtest"
    parts = sorted(root.glob("*.py"))
    h = hashlib.sha256()
    for p in parts:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def run_development_backtest(
    *,
    dataset_dir: Path | None = None,
    output_root: Path | None = None,
    run_id: str | None = None,
    trial_inventory_path: Path | None = None,
    parent_run_id: str | None = None,
    correction_reason: str | None = None,
) -> dict:
    dataset_dir = dataset_dir or REGISTERED_DATASET_DIR
    output_root = output_root or BACKTEST_OUTPUT_ROOT
    run_id = run_id or str(uuid.uuid4())
    run_dir = output_root / run_id
    if run_dir.exists():
        raise FileExistsError("run_directory_exists")
    inventory_path = trial_inventory_path or TRIAL_INVENTORY_PATH
    parent_run_id = parent_run_id or ORIGINAL_PROVISIONAL_RUN_ID
    correction_reason = correction_reason or CORRECTION_REASON

    rules_hash = rules_config_hash()
    engine_digest = _engine_source_digest()
    registration = {
        "run_id": run_id,
        "registered_at_utc": datetime.now(timezone.utc).isoformat(),
        "rules_mechanics_version": RULES_MECHANICS_VERSION,
        "rules_config_hash": rules_hash,
        "original_rules_config_hash": ORIGINAL_RULES_CONFIG_HASH,
        "parent_run_id": parent_run_id,
        "correction_reason": correction_reason,
        "engine_source_digest": engine_digest,
        "frozen_rules": frozen_rules_payload(),
        "unchanged_economic_rules": [
            "EMA spans/warmup/signal/exit structure",
            "Illustrative 10bps slip and fee per side",
            "₹20k initial cash (now also entry allocation ceiling)",
        ],
        "changed_mechanics": [
            "Entry allocation ceiling enforced",
            "Raw open vs stop gate before entry",
            "Baseline sizing includes fees",
            "Preflight config/manifest/meta validation",
        ],
    }
    write_preregistered_artifacts(run_dir, registration)
    append_trial_inventory(
        inventory_path,
        {
            "run_id": run_id,
            "status": "STARTED",
            "rules_config_hash": rules_hash,
            "parent_run_id": parent_run_id,
            "correction_reason": correction_reason,
            "at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    pf: PreflightResult = verify_registered_dataset(dataset_dir)
    pf_dict = asdict(pf)
    if not pf.ok:
        write_blocked_run(run_dir, error_class=pf.error_class or "PREFLIGHT_FAILED", preflight=pf_dict, run_id=run_id)
        record = {
            "run_id": run_id,
            "status": "BLOCKED",
            "error_class": pf.error_class,
            "parent_run_id": parent_run_id,
            "at_utc": datetime.now(timezone.utc).isoformat(),
        }
        append_trial_inventory(inventory_path, record)
        return {"status": "BLOCKED", "run_id": run_id, "run_dir": str(run_dir), "error_class": pf.error_class}

    try:
        dev = development_frame_from_verified(dataset_dir)
        sim: SimulationResult = simulate_development(dev)
    except Exception:
        write_error_run(
            run_dir,
            error_class="SIMULATION_ERROR",
            preflight=pf_dict,
            run_id=run_id,
            purpose=correction_reason,
        )
        append_trial_inventory(
            inventory_path,
            {
                "run_id": run_id,
                "status": "ERROR",
                "error_class": "SIMULATION_ERROR",
                "parent_run_id": parent_run_id,
                "at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {"status": "ERROR", "run_id": run_id, "run_dir": str(run_dir), "error_class": "SIMULATION_ERROR"}
    trade_summary = summarize_trades(sim.trades, sim)
    dd = equity_drawdown([asdict(e) for e in sim.equity_curve])
    final_cash = sim.equity_curve[-1].cash_inr if sim.equity_curve else "20000.00"
    summary = {
        **trade_summary,
        "signal_opportunities": sim.opportunity_count,
        "admission_skips": sim.admission_skips,
        "signals_skipped_while_holding": sim.skipped_while_holding,
        "skipped_exit_session": sim.skipped_exit_session,
        "skipped_halted": sim.skipped_halted,
        "initial_cash_inr": "20000.00",
        "final_cash_inr": final_cash,
        "final_net_liquidation_inr": sim.equity_curve[-1].net_liquidation_inr if sim.equity_curve else final_cash,
        "drawdown": dd,
        "yearly_development": yearly_trade_breakdown(sim.trades),
        "halted_new_entries": sim.halted_new_entries,
        "ambiguous_same_bar_exits": sim.ambiguous_same_bar,
        "boundary_forced_exits": sim.boundary_forced_exits,
    }
    baselines = {
        "cash": cash_baseline_final(dev),
        "buy_and_hold": buy_hold_baseline(dev),
    }
    sim_dict = {
        "opportunity_count": sim.opportunity_count,
        "admission_skips": sim.admission_skips,
        "skipped_while_holding": sim.skipped_while_holding,
        "halted_new_entries": sim.halted_new_entries,
        "ambiguous_same_bar": sim.ambiguous_same_bar,
        "boundary_forced_exits": sim.boundary_forced_exits,
        "trades": [asdict(t) for t in sim.trades],
        "signals": [asdict(s) for s in sim.signals],
        "equity_curve": [asdict(e) for e in sim.equity_curve],
    }
    write_success_run(
        run_dir,
        run_id=run_id,
        preflight=pf_dict,
        rules_hash=rules_hash,
        simulation=sim_dict,
        summary=summary,
        baselines=baselines,
        engine_source_digest=engine_digest,
        lineage=registration,
    )
    append_trial_inventory(
        inventory_path,
        {
            "run_id": run_id,
            "status": "EXPLORATORY_COMPLETE",
            "development_hash": pf.development_hash,
            "rules_config_hash": rules_hash,
            "parent_run_id": parent_run_id,
            "correction_reason": correction_reason,
            "closed_trades": trade_summary["closed_trades"],
            "at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "status": "EXPLORATORY_COMPLETE",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "summary": summary,
        "rules_config_hash": rules_hash,
        "parent_run_id": parent_run_id,
    }
