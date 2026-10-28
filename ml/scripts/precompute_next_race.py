"""Precompute the live-model forecast for the *next upcoming race* and write it to
``web/public/data/next_race_prediction.json``.

The Streamlit app reads this JSON on first paint so the page shows the live model's
predictions INSTANTLY (no 10–15s retrain spinner). The RUN button still triggers a
fresh retrain — this snapshot is only the fast-first-paint shortcut.

Re-run this script before each Grand Prix weekend (or in CI on a schedule) to keep the
snapshot current. The script is idempotent and writes nothing else.

Usage:
    python ml/scripts/precompute_next_race.py
    python ml/scripts/precompute_next_race.py --asof 2026-06-16
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

from src.model.forecast import forecast, next_race  # noqa: E402
from src.model.retrain import retrain_live  # noqa: E402

OUT = ROOT / "web" / "public" / "data" / "next_race_prediction.json"


def main(asof: str) -> None:
    tgt = next_race(asof)
    if tgt is None:
        raise SystemExit(f"No race on/after {asof} in cached data. Run fetch_data.py first.")
    season, rnd = int(tgt.season), int(tgt["round"])
    target_iso = tgt["date"].date().isoformat()
    print(f"Next race: {tgt.race_name}  (round {rnd}, race {target_iso})")

    print("Retraining (live model) …")
    models = retrain_live(target_iso, season, rnd)

    print("Forecasting …")
    result = forecast(asof, models=models)
    if result.get("error"):
        raise SystemExit(result["error"])

    payload = {
        "asof": asof,
        "generatedAt": date.today().isoformat(),
        "race": result["race"],
        "forecast": result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {OUT.relative_to(ROOT)}")
    podium = result["preQualifyingPodium"][:3]
    for i, p in enumerate(podium, 1):
        print(f"  {['🥇','🥈','🥉'][i-1]} {p['driverName']:<20} {p['team']:<14} {p['podiumProbability']*100:4.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().isoformat(),
                    help="as-of date (YYYY-MM-DD); defaults to today")
    args = ap.parse_args()
    main(args.asof)
