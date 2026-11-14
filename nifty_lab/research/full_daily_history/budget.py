"""Invocation + dataset + per-chunk request budgets (persisted)."""
from __future__ import annotations

from nifty_lab.research.historical_audit.budget import AuditBudgetExceeded

from .checkpoint import DatasetCheckpoint, save_checkpoint
from .types import (
    MAX_HISTORICAL_PER_CHUNK,
    MAX_HISTORICAL_PER_DATASET,
    MAX_HISTORICAL_PER_INVOCATION,
    MAX_MASTER_PER_INVOCATION,
)


class FullHistoryBudget:
    """Drop-in for AuditRequestBudget during one acquisition invocation."""

    historical_limit: int = MAX_HISTORICAL_PER_INVOCATION
    master_limit: int = MAX_MASTER_PER_INVOCATION
    historical_attempted: int = 0
    master_attempted: int = 0

    def __init__(
        self,
        checkpoint: DatasetCheckpoint,
        dataset_dir,
        *,
        chunk_year: str | None = None,
    ) -> None:
        self._checkpoint = checkpoint
        self._dataset_dir = dataset_dir
        self._chunk_year = chunk_year
        self._attempt_log: list[str] = []

    def set_chunk(self, chunk_year: str) -> None:
        self._chunk_year = chunk_year

    def consume_master(self, *, label: str) -> None:
        if self.master_attempted >= self.master_limit:
            raise AuditBudgetExceeded("Instrument master request budget exceeded for this invocation.")
        self.master_attempted += 1
        self._checkpoint.cumulative_master_attempts += 1
        self._attempt_log.append(f"master:{label}")
        save_checkpoint(self._dataset_dir, self._checkpoint)

    def consume_historical(self, *, label: str) -> None:
        chunk = self._chunk_year or label
        if self.historical_attempted >= self.historical_limit:
            raise AuditBudgetExceeded("Historical invocation budget exceeded.")
        if self._checkpoint.cumulative_historical_attempts >= MAX_HISTORICAL_PER_DATASET:
            raise AuditBudgetExceeded("Historical dataset budget exceeded.")
        attempts = self._checkpoint.per_chunk_attempts.get(chunk, 0)
        if attempts >= MAX_HISTORICAL_PER_CHUNK:
            raise AuditBudgetExceeded(f"Per-chunk attempt budget exceeded for {chunk}.")
        self.historical_attempted += 1
        self._checkpoint.cumulative_historical_attempts += 1
        self._checkpoint.per_chunk_attempts[chunk] = attempts + 1
        chunk_cp = self._checkpoint.chunks.get(chunk)
        if chunk_cp is not None:
            chunk_cp.attempts = self._checkpoint.per_chunk_attempts[chunk]
        self._attempt_log.append(f"historical:{label}")
        save_checkpoint(self._dataset_dir, self._checkpoint)

    def snapshot_dict(self) -> dict:
        return {
            "invocation_historical_attempted": self.historical_attempted,
            "invocation_historical_limit": self.historical_limit,
            "dataset_historical_attempted": self._checkpoint.cumulative_historical_attempts,
            "dataset_historical_limit": MAX_HISTORICAL_PER_DATASET,
            "invocation_master_attempted": self.master_attempted,
            "invocation_master_limit": self.master_limit,
            "dataset_master_attempted": self._checkpoint.cumulative_master_attempts,
            "per_chunk_attempts": dict(self._checkpoint.per_chunk_attempts),
        }
