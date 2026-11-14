"""Funded-paper recording with save-time eligibility recheck."""

from __future__ import annotations

from ..config import AppConfig, RiskConfig
from ..journal.db import Journal, JournalEntry
from ..options.payoff import Position
from .budget import EligibilityResult, check_position_eligibility
from .context import EligibilityStatus, FundedPaperContext, production_context_blocked


def context_for_production_save(cfg: AppConfig, journal: Journal) -> FundedPaperContext:
    has_open = journal.open_position_count() > 0
    return production_context_blocked(
        initial_capital=cfg.risk.capital,
        loss_ceiling=cfg.risk.max_drawdown,
        profile_authorized=cfg.funded_paper_profile_authorized,
        has_unreconciled_legacy=has_open,
    )


def try_record_funded_paper(
    journal: Journal,
    entry: JournalEntry,
    position: Position,
    risk: RiskConfig,
    context: FundedPaperContext,
) -> tuple[int | None, EligibilityResult]:
    result = check_position_eligibility(position, risk, context=context)
    if result.status != EligibilityStatus.ELIGIBLE:
        return None, result
    tagged = JournalEntry(**{**entry.__dict__, "data_source": journal.qualify_data_source(entry.data_source)})
    return journal.add_entry(tagged), result
