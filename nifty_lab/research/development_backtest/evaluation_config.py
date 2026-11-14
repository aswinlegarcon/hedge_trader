"""Split/evaluation configuration (separate from strategy rules hash)."""
from __future__ import annotations

import hashlib
import json

from .config import (
    CONTEXT_YEARS_VALIDATION,
    EVALUATION_YEARS_VALIDATION,
    EXPECTED_VALIDATION_2024_ROWS,
    VALIDATION_BASELINE_CONVENTION,
    rules_config_hash,
)


def evaluation_config_payload() -> dict:
    return {
        "split_id": "validation-2024",
        "evaluation_years": list(EVALUATION_YEARS_VALIDATION),
        "context_years_for_indicators_only": list(CONTEXT_YEARS_VALIDATION),
        "expected_evaluation_rows": EXPECTED_VALIDATION_2024_ROWS,
        "independent_account_initial_cash_inr": "20000.00",
        "no_pending_signal_carried_from_context": True,
        "force_split_end_at_last_evaluation_session": True,
        "holdout_years_excluded_from_outcomes": [2025],
        "baseline_convention": VALIDATION_BASELINE_CONVENTION,
        "strategy_rules_hash_ref": rules_config_hash(),
    }


def evaluation_config_hash() -> str:
    raw = json.dumps(evaluation_config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
