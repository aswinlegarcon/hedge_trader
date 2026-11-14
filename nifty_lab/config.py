"""Application configuration.

All credentials come from environment variables (see ``.env.example``).
This module never logs or prints secret values; it only reports whether
a variable is *set*.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

RESEARCH_PROFILE_ID = "spec-03-v1"
DEFAULT_CAPITAL_INR = 20_000.0
DEFAULT_LOSS_CEILING_INR = 2_000.0

# Provisional research labels only — no instrument keys or quotes (Spec 03).
PROVISIONAL_WATCHLIST = ("ICICI Bank", "Gold BeES", "Bharti Airtel", "L&T")

_LEGACY_RISK_VARS = (
    "NSL_CAPITAL_INR",
    "NSL_MAX_DRAWDOWN_INR",
    "NSL_RISK_PER_TRADE_MIN_INR",
    "NSL_RISK_PER_TRADE_MAX_INR",
)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Environment variable {name} must be numeric, got {raw!r}") from exc


def legacy_risk_env_conflict() -> bool:
    """True when legacy NSL_* overrides are set (values never inspected for display)."""
    for name in _LEGACY_RISK_VARS:
        raw = os.getenv(name)
        if raw is not None and raw.strip() != "":
            return True
    return False


def legacy_conflict_message() -> str:
    return (
        "Legacy NSL_* risk overrides conflict with the active revised research profile (spec-03). "
        "Funded-paper qualification stays unavailable until overrides are removed or reconciled in a future spec. "
        "Educational calculators still run."
    )


@dataclass(frozen=True)
class RiskConfig:
    """User risk budget for the active profile. Amounts are in INR."""

    capital: float = DEFAULT_CAPITAL_INR
    max_drawdown: float = DEFAULT_LOSS_CEILING_INR
    # Per-position ceiling unconfirmed until user confirms (not ₹500–₹1,000 prose).
    risk_per_trade_max: float | None = None
    max_open_positions: int = 3
    max_portfolio_risk_pct: float = 0.06
    max_single_underlying_pct: float = 0.04

    def __post_init__(self) -> None:
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if not 0 < self.max_drawdown <= self.capital:
            raise ValueError("max_drawdown must be in (0, capital]")
        if self.risk_per_trade_max is not None:
            if self.risk_per_trade_max <= 0 or self.risk_per_trade_max > self.max_drawdown:
                raise ValueError("risk_per_trade_max must be in (0, max_drawdown] when set")

    @property
    def max_drawdown_pct(self) -> float:
        return self.max_drawdown / self.capital

    @property
    def per_position_risk_confirmed(self) -> bool:
        return self.risk_per_trade_max is not None


@dataclass(frozen=True)
class AppConfig:
    profile_id: str = RESEARCH_PROFILE_ID
    risk: RiskConfig = field(default_factory=RiskConfig)
    db_path: Path = PROJECT_ROOT / "data" / "journal.db"
    sample_data_dir: Path = PROJECT_ROOT / "data" / "sample"
    import_dir: Path = PROJECT_ROOT / "data" / "imports"
    live_trading_enabled: bool = True
    legacy_env_conflict: bool = False

    @property
    def funded_paper_profile_authorized(self) -> bool:
        return not self.legacy_env_conflict


def load_config() -> AppConfig:
    conflict = legacy_risk_env_conflict()
    # Spec 03: do not treat legacy NSL_* as authorization even when present.
    risk = RiskConfig(
        capital=DEFAULT_CAPITAL_INR,
        max_drawdown=DEFAULT_LOSS_CEILING_INR,
        risk_per_trade_max=400.0,
    )
    db_path = Path(os.getenv("NSL_DB_PATH", "data/journal.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return AppConfig(
        profile_id=RESEARCH_PROFILE_ID,
        risk=risk,
        db_path=db_path,
        legacy_env_conflict=conflict,
    )


CREDENTIAL_VARS: dict[str, list[str]] = {
    "Upstox API": [
        "UPSTOX_API_KEY",
        "UPSTOX_API_SECRET",
        "UPSTOX_REDIRECT_URI",
        "UPSTOX_ACCESS_TOKEN",
        "UPSTOX_SANDBOX_ACCESS_TOKEN",
    ],
}

_PLACEHOLDER_MARKERS = ("your_", "xxx", "changeme", "placeholder", "sentinel_fake")
FAKE_SECRET_SENTINEL = "SENTINEL_FAKE_SECRET_73a9c0e4"


def credential_status() -> dict[str, dict[str, bool]]:
    """Return {broker: {VAR: is_set}} without revealing any value."""
    out: dict[str, dict[str, bool]] = {}
    for broker, names in CREDENTIAL_VARS.items():
        out[broker] = {}
        for name in names:
            val = os.getenv(name, "")
            is_set = bool(val.strip()) and not any(m in val.lower() for m in _PLACEHOLDER_MARKERS)
            out[broker][name] = is_set
    return out
