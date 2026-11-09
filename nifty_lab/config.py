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


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Environment variable {name} must be numeric, got {raw!r}") from exc


@dataclass(frozen=True)
class RiskConfig:
    """User-configurable risk budget. Amounts are in INR."""

    capital: float = 100_000.0
    max_drawdown: float = 10_000.0
    risk_per_trade_min: float = 1_000.0
    risk_per_trade_max: float = 2_000.0
    max_open_positions: int = 3
    max_portfolio_risk_pct: float = 0.06  # 6% of capital at risk across all open positions
    max_single_underlying_pct: float = 0.04  # concentration cap per underlying

    def __post_init__(self) -> None:
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if not 0 < self.max_drawdown <= self.capital:
            raise ValueError("max_drawdown must be in (0, capital]")
        if not 0 < self.risk_per_trade_min <= self.risk_per_trade_max:
            raise ValueError("risk_per_trade_min must be in (0, risk_per_trade_max]")
        if self.risk_per_trade_max > self.max_drawdown:
            raise ValueError("risk_per_trade_max cannot exceed max_drawdown")

    @property
    def max_drawdown_pct(self) -> float:
        return self.max_drawdown / self.capital


@dataclass(frozen=True)
class AppConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    db_path: Path = PROJECT_ROOT / "data" / "journal.db"
    sample_data_dir: Path = PROJECT_ROOT / "data" / "sample"
    import_dir: Path = PROJECT_ROOT / "data" / "imports"
    live_trading_enabled: bool = False  # Hard-coded False in v1. No order APIs exist.


def load_config() -> AppConfig:
    risk = RiskConfig(
        capital=_env_float("NSL_CAPITAL_INR", 100_000),
        max_drawdown=_env_float("NSL_MAX_DRAWDOWN_INR", 10_000),
        risk_per_trade_min=_env_float("NSL_RISK_PER_TRADE_MIN_INR", 1_000),
        risk_per_trade_max=_env_float("NSL_RISK_PER_TRADE_MAX_INR", 2_000),
    )
    db_path = Path(os.getenv("NSL_DB_PATH", "data/journal.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return AppConfig(risk=risk, db_path=db_path)


# Credential presence checks (never expose values) -------------------------
CREDENTIAL_VARS: dict[str, list[str]] = {
    "Zerodha Kite Connect": ["KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN"],
    "Kotak Neo": ["KOTAK_CONSUMER_KEY", "KOTAK_CONSUMER_SECRET", "KOTAK_MOBILE"],
}

_PLACEHOLDER_MARKERS = ("your_", "xxx", "changeme", "placeholder")


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
