"""Train the Stage-1 qualifying model and print a quick report.

Run from ml/:  python scripts/build_quali_model.py
Outputs: ml/models/quali_model.pkl
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.model.quali import train_quali  # noqa: E402


def main():
    print("Training qualifying model (predict gap-to-pole from history) ...")
    _artifact, m = train_quali()
    print("\n=== QUALIFYING MODEL — quick check (test 2024-2026) ===")
    print(f"  mean grid error : {m['mean_grid_error']:.2f} positions  "
          f"(avg |predicted grid - actual quali pos|)")
    print(f"  pole accuracy   : {m['pole_accuracy']:.1%}  "
          f"(predicted #1 actually took pole)")
    print(f"  test races      : {m['test_races']}")
    print("\nsaved -> ml/models/quali_model.pkl")


if __name__ == "__main__":
    main()
