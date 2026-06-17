"""CLI: date-driven dual-mode prediction for the next race (prints to terminal).

Usage:
    python scripts/predict_dual.py              # today
    python scripts/predict_dual.py 2026-06-12   # any as-of date (backtest)

The actual logic lives in src/model/forecast.py (shared with the Streamlit app).
Each invocation retrains both stages on every race before the target GP, so first
run takes ~10–15s; subsequent runs in the same process reuse the trained models.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.model.forecast import forecast  # noqa: E402


def main():
    asof = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today())
    r = forecast(asof)
    if r.get("error"):
        print(r["error"])
        return

    race = r["race"]
    print(f"As-of date : {r['asof']}")
    print(f"Next race  : {race['name']}  (season {race['season']}, round {race['round']}, {race['date']})")
    print(f"Qualifying : ~{race['qualifyingDate']}\n")

    print("  PREDICTED QUALIFYING (Stage 1) — top 10:")
    for row in r["predictedQualifying"][:10]:
        print(f"    P{row['position']:<2} {row['code']:4} {row['team']:14} (+{row['gap']:.2f}s)")

    print("\n  PREDICTED PODIUM")
    a = r["preQualifyingPodium"]
    if r["hasRealGrid"]:
        b = r["realGridPodium"]
        print("  MODE 1 — PRE-QUALIFYING                          MODE 2 — REAL GRID")
        for i in range(min(8, len(a))):
            la = f"  {i+1}. {a[i]['code']:4} {a[i]['team']:13} {a[i]['podiumProbability']:.0%}"
            lb = f"{i+1}. {b[i]['code']:4} {b[i]['team']:13} {b[i]['podiumProbability']:.0%}"
            print(f"{la:48}{lb}")
        print(f"\n  PRED podium (pre-quali): {' / '.join(x['code'] for x in a[:3])}")
        print(f"  PRED podium (real grid): {' / '.join(x['code'] for x in b[:3])}")
    else:
        print("  MODE 1 — PRE-QUALIFYING (predicted grid)   |   MODE 2 — (qualifying not available yet)")
        for i in range(min(8, len(a))):
            print(f"  {i+1}. {a[i]['code']:4} {a[i]['team']:13} {a[i]['podiumProbability']:.0%}")
        print(f"\n  PRED podium (pre-quali): {' / '.join(x['code'] for x in a[:3])}")
        print("  (re-run on/after qualifying day for the real-grid mode)")


if __name__ == "__main__":
    main()
