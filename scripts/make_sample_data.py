"""Regenerate the bundled synthetic sample CSV.  Usage: python scripts_make_sample.py"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from pathlib import Path

from nifty_lab.data import write_sample_csv

out = Path(__file__).resolve().parent.parent / "data" / "sample" / "nifty_synthetic_daily.csv"
out.parent.mkdir(parents=True, exist_ok=True)
write_sample_csv(str(out), seed=42)
print(f"wrote {out}")
