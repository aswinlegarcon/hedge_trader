"""Versioned execution-v1 risk policy (Spec 08)."""
from __future__ import annotations

from dataclasses import dataclass

EXECUTION_PROFILE_ID = "execution-v1"


@dataclass(frozen=True)
class ExecutionPolicy:
    profile_id: str = EXECUTION_PROFILE_ID
    initial_allocation_inr: float = 20_000.0
    per_position_budget_inr: float = 400.0
    stop_new_risk_drawdown_inr: float = 2_000.0
    aggregate_risk_cap_inr: float = 1_200.0
    per_underlying_cap_inr: float = 800.0
    max_open_positions: int = 3
    quote_ttl_seconds: int = 15
    confirmation_ttl_seconds: int = 30

    def __post_init__(self) -> None:
        if self.per_position_budget_inr <= 0:
            raise ValueError("per_position_budget_inr must be positive")
        if self.stop_new_risk_drawdown_inr <= 0:
            raise ValueError("stop_new_risk_drawdown_inr must be positive")


EXECUTION_V1 = ExecutionPolicy()
