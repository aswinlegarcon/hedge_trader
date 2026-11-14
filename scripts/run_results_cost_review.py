#!/usr/bin/env python3
"""One offline results/cost sensitivity review (Spec 09). No simulation rerun."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from nifty_lab.research.results_review.runner import run_results_cost_review


def main() -> int:
    try:
        out = run_results_cost_review()
    except FileExistsError:
        print("BLOCKED: review directory already exists.")
        return 3
    except ValueError:
        print("BLOCKED: source runs not loadable.")
        return 2
    except Exception:
        print("BLOCKED: sanitized failure")
        return 1
    print(f"status={out['status']}")
    print(f"review_dir={out['review_dir']}")
    print(f"conclusion={out['analyst_conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
