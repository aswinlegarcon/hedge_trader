"""Pinned archived runs and review namespace (Spec 09 results-cost-review)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from nifty_lab.config import PROJECT_ROOT

FROZEN_RULES_HASH = "d5781d90f3276de37320059a14529c944580fc671c351cbbc04bed90bb191101"
APPROVED_DEVELOPMENT_RUN_ID = "22f4e81b-e66a-4ea1-b77d-325323f61db7"
APPROVED_VALIDATION_RUN_ID = "d1d9016b-3fc0-4dbf-944e-f4dde5353cd2"
VALIDATION_EVALUATION_CONFIG_HASH = "a5e169f0f061eb9d08ce9eacca4c3d0220da0b91a2bb39c2f97abcf66f5b7f58"
VALIDATION_PARENT_RUN_ID = APPROVED_DEVELOPMENT_RUN_ID
VALIDATION_PURPOSE = "FROZEN_2024_VALIDATION"
ORIGINAL_PROVISIONAL_RUN_ID = "cffbcdd3-e725-4ca6-bd01-97d424dbc6a2"
DEVELOPMENT_CORRECTION_REASON = "MECHANICS_CORRECTION"

INITIAL_CASH_INR = Decimal("20000.00")
REPORTING_QUANT = Decimal("0.01")

BACKTEST_RUNS_ROOT = PROJECT_ROOT / "research" / "backtest_runs"
REVIEW_OUTPUT_ROOT = PROJECT_ROOT / "research" / "review_runs"

BROKERAGE_REFERENCE_URL = "https://upstox.com/brokerage-charges/"
BROKERAGE_REFERENCE_CHECKED_DATE = "2026-11-13"

STRESS_SCENARIOS_BPS = (0, 1, 5, 10)
EXTRA_INR_PER_EXECUTION = Decimal("1.00")

ANALYST_CONCLUSION = "INSUFFICIENT_EVIDENCE / COST_FRAGILE_VALIDATION"

PINNED_SOURCE_FILES = (
    "registration.json",
    "manifest.json",
    "summary.json",
    "trades.json",
    "equity_daily.json",
)
