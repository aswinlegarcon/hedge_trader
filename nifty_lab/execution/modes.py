"""Execution mode separation (Spec 08)."""
from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    SANDBOX = "SANDBOX"
    LIVE = "LIVE"
