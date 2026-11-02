"""Export completed classifications without changing archived forecasts."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .service import _atomic_json, read_json


def result_artifacts(raw_root: Path, archive_index: dict) -> dict[str, dict]:
    artifacts = {}
    seasons = {}
    for entry in archive_index.get("races", []):
        season, round_number = int(entry["season"]), int(entry["round"])
        if season not in seasons:
            path = raw_root / f"results_{season}.parquet"
            seasons[season] = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        frame = seasons[season]
        if frame.empty:
            continue
        rows = frame[(frame["season"] == season) & (frame["round"] == round_number)]
        if rows.empty:
            continue
        columns = ["position", "driver_id", "code", "driver_name", "constructor_id",
                   "constructor_name", "points", "laps", "status"]
        rows = rows.sort_values("position")[columns]
        if (rows["driver_id"].isna().any() or rows["driver_id"].duplicated().any()
                or rows["position"].isna().any() or rows["position"].duplicated().any()
                or (rows["position"] <= 0).any()):
            raise ValueError(f"Invalid recorded classification for {season}-{round_number}")
        race_id = f"{season}-{round_number}"
        artifacts[race_id] = {
            "schema_version": 2,
            "race_id": race_id,
            "season": season,
            "round": round_number,
            "source": f"ml/data/raw/results_{season}.parquet",
            "results": rows.where(pd.notna(rows), None).to_dict(orient="records"),
        }
    return artifacts


def export_race_results(raw_root: Path, data_root: Path, archive_index: dict, *, dry_run: bool) -> None:
    for race_id, artifact in result_artifacts(raw_root, archive_index).items():
        target = data_root / "predictions" / f"{race_id}-results.json"
        if not dry_run and read_json(target) != artifact:
            _atomic_json(target, artifact)
