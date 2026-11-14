"""Live / sandbox readiness without exposing secrets (Spec 08)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..config import CREDENTIAL_VARS, credential_status, legacy_risk_env_conflict
from .modes import ExecutionMode


@dataclass(frozen=True)
class ReadinessReport:
    mode: ExecutionMode
    ready: bool
    blockers: tuple[str, ...]


def _token_present(var: str) -> bool:
    status = credential_status()
    for _broker, vars_ in status.items():
        if var.replace("UPSTOX_", "") in str(vars_):
            pass
    val = os.getenv(var, "").strip()
    if not val:
        return False
    low = val.lower()
    return not any(m in low for m in ("your_", "xxx", "changeme", "placeholder"))


def check_readiness(mode: ExecutionMode) -> ReadinessReport:
    blockers: list[str] = []
    if legacy_risk_env_conflict():
        blockers.append("Legacy NSL_* overrides conflict with execution-v1 policy.")
    if mode == ExecutionMode.PAPER:
        return ReadinessReport(mode, True, tuple(blockers))
    if mode == ExecutionMode.SANDBOX:
        if not _token_present("UPSTOX_SANDBOX_ACCESS_TOKEN"):
            blockers.append("Set UPSTOX_SANDBOX_ACCESS_TOKEN for sandbox adapter (separate from live).")
        return ReadinessReport(mode, not blockers, tuple(blockers))
    if mode == ExecutionMode.LIVE:
        up = credential_status().get("Upstox API", {})
        if not up.get("UPSTOX_ACCESS_TOKEN"):
            blockers.append("Missing UPSTOX_ACCESS_TOKEN for live data/order scope.")
        blockers.append(
            "Live placement requires current broker session, order permissions, and any registered static IP/app rules — verify in Upstox developer console."
        )
        return ReadinessReport(mode, False, tuple(blockers))
    return ReadinessReport(mode, False, ("Unknown mode",))
