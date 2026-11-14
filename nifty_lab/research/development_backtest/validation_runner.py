"""Offline 2024 validation replay (one bounded experiment)."""
from __future__ import annotations

import uuid

import pandas as pd
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from nifty_lab.config import PROJECT_ROOT

from .config import (
    BACKTEST_OUTPUT_ROOT,
    CONTEXT_YEARS_VALIDATION,
    CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
    EVALUATION_YEARS_VALIDATION,
    EXPECTED_VALIDATION_2024_ROWS,
    FROZEN_CORRECTED_RULES_HASH,
    HOLDOUT_YEARS,
    REGISTERED_DATASET_DIR,
    TRIAL_INVENTORY_PATH,
    VALIDATION_2024_PURPOSE,
    frozen_rules_payload,
    rules_config_hash,
)
from .evaluation_config import evaluation_config_hash, evaluation_config_payload
from .engine import SimulationResult
from .io_registration import write_preregistered_artifacts
from .metrics import (
    buy_hold_baseline_independent,
    cash_baseline_final,
    equity_drawdown,
    summarize_trades,
    yearly_trade_breakdown,
)
from .preflight import (
    PreflightResult,
    validation_frame_from_verified,
    verify_registered_dataset,
)
from .report import append_trial_inventory, write_blocked_run, write_error_run, write_validation_success_run
from .runner import _engine_source_digest
from .splits import SplitConfig, simulate_split


def run_validation_2024_backtest(
    *,
    dataset_dir: Path | None = None,
    output_root: Path | None = None,
    run_id: str | None = None,
    trial_inventory_path: Path | None = None,
) -> dict:
    dataset_dir = dataset_dir or REGISTERED_DATASET_DIR
    output_root = output_root or BACKTEST_OUTPUT_ROOT
    run_id = run_id or str(uuid.uuid4())
    run_dir = output_root / run_id
    if run_dir.exists():
        raise FileExistsError("run_directory_exists")
    inventory_path = trial_inventory_path or TRIAL_INVENTORY_PATH

    rules_hash = rules_config_hash()
    if rules_hash != FROZEN_CORRECTED_RULES_HASH:
        raise ValueError("rules_hash_frozen_mismatch")

    eval_hash = evaluation_config_hash()
    engine_digest = _engine_source_digest()
    registration = {
        "run_id": run_id,
        "registered_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": VALIDATION_2024_PURPOSE,
        "split_id": "validation-2024",
        "rules_config_hash": rules_hash,
        "evaluation_config_hash": eval_hash,
        "evaluation_config": evaluation_config_payload(),
        "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
        "correction_reason": None,
        "engine_source_digest": engine_digest,
        "frozen_rules": frozen_rules_payload(),
        "no_optimization": True,
        "future_splits_locked": ["2025 holdout not evaluated in this slice"],
    }
    write_preregistered_artifacts(run_dir, registration)
    append_trial_inventory(
        inventory_path,
        {
            "run_id": run_id,
            "status": "STARTED",
            "purpose": VALIDATION_2024_PURPOSE,
            "split_id": "validation-2024",
            "rules_config_hash": rules_hash,
            "evaluation_config_hash": eval_hash,
            "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
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
            "purpose": VALIDATION_2024_PURPOSE,
            "error_class": pf.error_class,
            "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
            "at_utc": datetime.now(timezone.utc).isoformat(),
        }
        append_trial_inventory(inventory_path, record)
        return {"status": "BLOCKED", "run_id": run_id, "run_dir": str(run_dir), "error_class": pf.error_class}

    try:
        val_frame = validation_frame_from_verified(dataset_dir)
        eval_only = val_frame[val_frame.index.map(lambda t: pd.Timestamp(t).year in EVALUATION_YEARS_VALIDATION)]
        if len(eval_only) != EXPECTED_VALIDATION_2024_ROWS:
            raise ValueError("VALIDATION_ROW_COUNT")
        sim: SimulationResult = simulate_split(val_frame, SplitConfig.validation_2024())
    except Exception:
        write_error_run(
            run_dir,
            error_class="SIMULATION_ERROR",
            preflight=pf_dict,
            run_id=run_id,
            purpose=VALIDATION_2024_PURPOSE,
        )
        append_trial_inventory(
            inventory_path,
            {
                "run_id": run_id,
                "status": "ERROR",
                "purpose": VALIDATION_2024_PURPOSE,
                "error_class": "SIMULATION_ERROR",
                "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
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
        "yearly_evaluation": yearly_trade_breakdown(sim.trades),
        "halted_new_entries": sim.halted_new_entries,
        "ambiguous_same_bar_exits": sim.ambiguous_same_bar,
        "boundary_forced_exits": sim.boundary_forced_exits,
        "evaluation_sessions": len(sim.equity_curve),
        "independent_account_note": "Validation portfolio starts ₹20k; context years do not contribute trades.",
    }
    baselines = {
        "cash": cash_baseline_final(eval_only),
        "buy_and_hold": buy_hold_baseline_independent(eval_only),
    }
    sim_dict = {
        "split_id": "validation-2024",
        "opportunity_count": sim.opportunity_count,
        "admission_skips": sim.admission_skips,
        "skipped_while_holding": sim.skipped_while_holding,
        "skipped_exit_session": sim.skipped_exit_session,
        "skipped_halted": sim.skipped_halted,
        "halted_new_entries": sim.halted_new_entries,
        "ambiguous_same_bar": sim.ambiguous_same_bar,
        "boundary_forced_exits": sim.boundary_forced_exits,
        "trades": [asdict(t) for t in sim.trades],
        "signals": [asdict(s) for s in sim.signals],
        "equity_curve": [asdict(e) for e in sim.equity_curve],
    }
    write_validation_success_run(
        run_dir,
        run_id=run_id,
        preflight=pf_dict,
        rules_hash=rules_hash,
        evaluation_hash=eval_hash,
        simulation=sim_dict,
        summary=summary,
        baselines=baselines,
        engine_source_digest=engine_digest,
        lineage=registration,
        context_hash=pf.validation_context_hash,
        evaluation_bars_hash=pf.validation_evaluation_hash,
        holdout_years=list(HOLDOUT_YEARS),
        holdout_hashes=pf.holdout_hashes,
    )
    append_trial_inventory(
        inventory_path,
        {
            "run_id": run_id,
            "status": "EXPLORATORY_COMPLETE",
            "purpose": VALIDATION_2024_PURPOSE,
            "split_id": "validation-2024",
            "evaluation_config_hash": eval_hash,
            "rules_config_hash": rules_hash,
            "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
            "evaluation_bars_hash": pf.validation_evaluation_hash,
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
        "evaluation_config_hash": eval_hash,
        "parent_run_id": CORRECTED_DEVELOPMENT_PARENT_RUN_ID,
    }
