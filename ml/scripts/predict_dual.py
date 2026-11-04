"""CLI: estimated-qualifying prediction for the next race (prints to terminal).

Usage:
    python scripts/predict_dual.py              # today
    python scripts/predict_dual.py 2026-06-12   # any as-of date (backtest)

Actual qualifying publication is handled by publish_qualifying_prediction.py.
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
    print(f"Qualifying : {race.get('qualifyingStartAt') or 'schedule time unavailable'}\n")

    print("  PREDICTED QUALIFYING (Stage 1) — top 10:")
    for row in r["predictedQualifying"][:10]:
        print(f"    P{row['position']:<2} {row['code']:4} {row['team']:14} (+{row['gap']:.2f}s)")

    print("\n  PREDICTED PODIUM — USING ESTIMATED QUALIFYING")
    a = r["preQualifyingPodium"]
    for i in range(min(8, len(a))):
        print(f"  {i+1}. {a[i]['code']:4} {a[i]['team']:13} {a[i]['podiumProbability']:.0%}")
    print(f"\n  Predicted podium: {' / '.join(x['code'] for x in a[:3])}")


if __name__ == "__main__":
    main()
