"""One-command weekend refresh for the next Grand Prix.

Runs the recurring chores in order:
  1. (re)fetch the in-progress season from Jolpica  -> ml/data/raw/*.parquet
  2. precompute the next-race snapshot              -> web/public/data/next_race_prediction.json
  3. (optional) regenerate the accuracy backtest    -> ml/models/live_metrics.json

Step 2 is the weekly must-do (instant first paint for the upcoming race). Step 3 is
occasional (refreshes the bottom accuracy bar; ~a few minutes).

Run from the repo root (macOS needs libomp — see ml/scripts/fix_libomp_macos.sh):
    python ml/scripts/refresh_for_next_race.py                 # fetch + snapshot
    python ml/scripts/refresh_for_next_race.py --backtest      # + refresh the accuracy bar
    python ml/scripts/refresh_for_next_race.py --no-fetch      # use cached data (skip Jolpica)
    python ml/scripts/refresh_for_next_race.py --asof 2026-07-02
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
sys.path.insert(0, str(SCRIPTS))

from src.data import cache, jolpica  # noqa: E402

_ENDPOINTS = {
    "results": jolpica.get_race_results,
    "qualifying": jolpica.get_qualifying,
    "driver_standings": jolpica.get_driver_standings,
    "constructor_standings": jolpica.get_constructor_standings,
    "schedule": jolpica.get_schedule,
}


def _fetch(seasons) -> None:
    for s in seasons:
        for name, fn in _ENDPOINTS.items():
            df = cache.cached(f"{name}_{s}", lambda fn=fn, s=s: fn(s), refresh=True)
            print(f"  {name}_{s} rows={len(df)}")


def _precompute(asof: str) -> None:
    import precompute_next_race  # sibling script
    precompute_next_race.main(asof)


def _backtest() -> None:
    from backtest_live import _podium_backtest, _quali_backtest  # sibling script
    from src.features.build_features import build_feature_table
    payload = {"podium": _podium_backtest(build_feature_table()), "quali": _quali_backtest()}
    out = ML_DIR / "models" / "live_metrics.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"  wrote {out.relative_to(ML_DIR.parent)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().isoformat(),
                    help="as-of date (YYYY-MM-DD); defaults to today")
    ap.add_argument("--seasons", type=int, nargs="*", default=[date.today().year],
                    help="seasons to refresh (default: current year)")
    ap.add_argument("--no-fetch", action="store_true", help="use cached data, skip Jolpica")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="skip the next-race snapshot (e.g. the Monday accuracy-bar job)")
    ap.add_argument("--backtest", action="store_true",
                    help="also regenerate live_metrics.json for the accuracy bar (slow)")
    args = ap.parse_args()

    if args.no_fetch:
        print("[1/3] Skipping fetch (--no-fetch).")
    else:
        print(f"[1/3] Fetching {args.seasons} from Jolpica …")
        _fetch(args.seasons)

    if args.no_snapshot:
        print("[2/3] Skipping next-race snapshot (--no-snapshot).")
    else:
        print("[2/3] Precomputing next-race snapshot …")
        _precompute(args.asof)

    if args.backtest:
        print("[3/3] Regenerating accuracy backtest (a few minutes) …")
        _backtest()
    else:
        print("[3/3] Skipping backtest (pass --backtest to refresh the accuracy bar).")

    print("Done.")


if __name__ == "__main__":
    main()
