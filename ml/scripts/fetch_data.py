"""Pull all needed Jolpica data for 2014–2025 into the parquet cache.

Run from the ml/ directory:
    python scripts/fetch_data.py

Idempotent: seasons already cached are loaded from disk and skipped. Use
``--refresh`` to force re-download (e.g. to update the current, in-progress season).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `src` importable when run as `python scripts/fetch_data.py` from ml/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # add ml/ to sys.path

from src.data import cache, jolpica  # noqa: E402

SEASONS = range(2014, 2026)  # 2014..2025 inclusive

ENDPOINTS = {
    "results": jolpica.get_race_results,
    "qualifying": jolpica.get_qualifying,
    "driver_standings": jolpica.get_driver_standings,
    "constructor_standings": jolpica.get_constructor_standings,
    "schedule": jolpica.get_schedule,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch + cache Jolpica F1 data.")
    parser.add_argument("--refresh", action="store_true", help="ignore cache and re-download")
    parser.add_argument("--seasons", type=int, nargs="*", help="specific seasons (default: 2014-2025)")
    args = parser.parse_args()

    seasons = args.seasons if args.seasons else list(SEASONS)
    for season in seasons:
        for name, fn in ENDPOINTS.items():
            key = f"{name}_{season}"
            df = cache.cached(key, lambda fn=fn, s=season: fn(s), refresh=args.refresh)
            print(f"{key:30s} rows={len(df):5d}")
    print("done.")


if __name__ == "__main__":
    main()
