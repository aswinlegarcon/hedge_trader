"""Frozen rules, costs and registered dataset identity (Spec 09 development slice)."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from nifty_lab.config import PROJECT_ROOT

STRATEGY_ID = "icicibank_daily_pullback_v1"
SYMBOL = "ICICIBANK"
INSTRUMENT_KEY = "NSE_EQ|INE090A01021"
REGISTERED_DATASET_ID = "icicibank-daily-79d0359eb567"
EXPECTED_MERGED_HASH = "9c1a7e2b6f0d8137597d359ad34a4b58fa4033321040f263b8ea61d769a60b3e"
EXPECTED_MERGED_ROWS = 1240

REGISTERED_DATASET_DIR = PROJECT_ROOT / "research" / "history_runs" / REGISTERED_DATASET_ID
BACKTEST_OUTPUT_ROOT = PROJECT_ROOT / "research" / "backtest_runs"
TRIAL_INVENTORY_PATH = BACKTEST_OUTPUT_ROOT / "trial_inventory.jsonl"

DEVELOPMENT_YEARS = (2021, 2022, 2023)
VALIDATION_YEARS = (2024,)
HOLDOUT_YEARS = (2025,)

INITIAL_CASH = Decimal("20000.00")
ENTRY_ALLOCATION_CEILING = Decimal("20000.00")
SLIPPAGE_BPS = Decimal("10")
FEE_BPS = Decimal("10")
MAX_PLANNED_STOP_INR = Decimal("400.00")
RISK_HALT_INITIAL_LOSS = Decimal("2000.00")
RISK_HALT_PEAK_DRAWDOWN = Decimal("2000.00")
WARMUP_BARS = 100
MEDIAN_VOLUME_LOOKBACK = 20
TIME_EXIT_SESSIONS = 5
REPORTING_DECIMALS = Decimal("0.01")
ROUNDING_MODE = "ROUND_HALF_UP quantize 0.01 INR"

RULES_MECHANICS_VERSION = "mechanics_correction_v1"
ORIGINAL_PROVISIONAL_RUN_ID = "cffbcdd3-e725-4ca6-bd01-97d424dbc6a2"
ORIGINAL_RULES_CONFIG_HASH = "de784daaeabb7642c9ce213a832704a46b8ea60e2461fdc95f715cf7ae9df8fb"
CORRECTION_REASON = "MECHANICS_CORRECTION"
FROZEN_CORRECTED_RULES_HASH = "d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101"
CORRECTED_DEVELOPMENT_PARENT_RUN_ID = "22f4e81b-e66a-4ea1-b77d-325323f61db7"
VALIDATION_2024_PURPOSE = "FROZEN_2024_VALIDATION"

CONTEXT_YEARS_VALIDATION = (2021, 2022, 2023)
EVALUATION_YEARS_VALIDATION = (2024,)
EXPECTED_VALIDATION_2024_ROWS = 249
VALIDATION_BASELINE_CONVENTION = (
    "first_observed_2024_open_to_last_2024_close; independent ₹20k; fees in sizing"
)

EXPECTED_DATASET_CONFIG_HASH = "79d0359eb567524d896633b790c35c63c356910cc5e8cac9c4c30ccf3919d6c6"

EXPECTED_CHUNK_HASHES = {
    "2021": "07d578afb541930dc7c1d8d23a6bfdd079c80ec078ed188117a3ec2775fe3f79",
    "2022": "a59f101cfcbfb93b67f384a65be1f213156a0315799a5d2ae8c6ecb51c6235c0",
    "2023": "9935294fd9fd947027af72486b1c93c8bc36f22c58ec4f4ddc127ef883e9d010",
    "2024": "0313d176ebc9264a1bfc70521afc43feb04e62397e6e9fdacfdea1b6d75b2aaf",
    "2025": "c252d55b31e60f69bf140222cd89f594cb4901006abccac66218ad34f0e07d0d",
}


def frozen_rules_payload() -> dict:
    return {
        "strategy_id": STRATEGY_ID,
        "instrument_key": INSTRUMENT_KEY,
        "development_years": list(DEVELOPMENT_YEARS),
        "warmup_bars": WARMUP_BARS,
        "ema_spans": [20, 50],
        "ema_alpha_rule": "2/(span+1), seed=first_close, adjust=False equivalent",
        "signal": {
            "close_gt_ema20_gt_ema50": True,
            "low_lte_ema20": True,
            "volume_gte_median_prior_20_excl_signal": True,
        },
        "entry": "next_session_open_adverse_slip",
        "entry_skip_if_raw_open_lte_stop_or_modeled_entry_lte_stop": True,
        "exit": {
            "stop_signal_low": True,
            "target_2r": True,
            "stop_before_target_same_bar": True,
            "gap_stop_uses_open": True,
            "gap_target_uses_target": True,
            "time_exit_sessions": TIME_EXIT_SESSIONS,
            "split_end_force_close": True,
        },
        "position": {"max_open": 1, "no_pyramiding": True, "no_entry_on_exit_session": True},
        "costs_illustrative": {
            "slippage_bps_per_side": str(SLIPPAGE_BPS),
            "fee_bps_per_side": str(FEE_BPS),
            "real_costs": "UNKNOWN",
        },
        "sizing": {
            "initial_cash_inr": str(INITIAL_CASH),
            "entry_allocation_ceiling_inr": str(ENTRY_ALLOCATION_CEILING),
            "whole_shares": True,
            "max_planned_stop_inr": str(MAX_PLANNED_STOP_INR),
        },
        "precision": {"reporting": ROUNDING_MODE, "arithmetic": "decimal.Decimal"},
        "risk_latch": {
            "initial_loss_inr": str(RISK_HALT_INITIAL_LOSS),
            "peak_drawdown_inr": str(RISK_HALT_PEAK_DRAWDOWN),
        },
    }


def rules_config_hash() -> str:
    raw = json.dumps(frozen_rules_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def money_quantize(amount: Decimal) -> Decimal:
    return amount.quantize(REPORTING_DECIMALS)
