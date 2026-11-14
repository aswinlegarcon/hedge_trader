"""Global guards — automated tests MUST NOT mutate live broker orders (Spec 08)."""
from __future__ import annotations

import os

ENV_FORBID_LIVE = "NSL_FORBID_LIVE_MUTATIONS"


def live_mutations_forbidden() -> bool:
    return os.getenv(ENV_FORBID_LIVE, "1").strip() not in ("0", "false", "False", "")


def assert_live_mutation_allowed() -> None:
    if live_mutations_forbidden():
        raise RuntimeError(
            "Live order mutation blocked (NSL_FORBID_LIVE_MUTATIONS). "
            "This guard is required for automated tests and agent verification."
        )
