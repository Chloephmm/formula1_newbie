"""Run one schedule-aware qualifying publication check.

The GitHub Action invokes this script hourly. It refreshes event timing every run,
does no model work before an eligible check, and writes only the four published JSON
interfaces and separate recorded race-result files for archived races.
``--dry-run`` performs all eligible network/validation/model work but
does not change files.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ML_DIR = ROOT / "ml"
sys.path.insert(0, str(ML_DIR))

from src.data.jolpica import get_qualifying_round, get_schedule  # noqa: E402
from src.model.forecast import forecast_actual_qualifying  # noqa: E402
from src.model.retrain import train_podium_live  # noqa: E402
from src.publication.publisher import run_publication  # noqa: E402
from src.publication.qualifying import load_exceptions_config  # noqa: E402
from src.publication.race_results import export_race_results  # noqa: E402
from src.publication.service import (  # noqa: E402
    PublicationPaths,
    latest_completed_participants,
    read_json,
    write_update,
)

DATA_ROOT = ROOT / "web" / "public" / "data"
RAW_ROOT = ML_DIR / "data" / "raw"
EXCEPTIONS_PATH = ML_DIR / "config" / "qualifying_exceptions.v1.json"

REQUIRED_SCHEDULE_FIELDS = (
    "season",
    "round",
    "race_name",
    "circuit_id",
    "qualifying_start_at",
    "qualifying_end_at",
    "end_time_estimated",
    "race_start_at",
    "schedule_updated_at",
)


def _active_identity(active: dict) -> tuple[int, int]:
    race = active.get("race") or active.get("forecast", {}).get("race") or {}
    return int(race["season"]), int(race["round"])


def _schedule_record(schedule: pd.DataFrame, season: int, round_number: int) -> dict:
    matches = schedule[
        (schedule["season"].astype(int) == season)
        & (schedule["round"].astype(int) == round_number)
    ]
    if len(matches) != 1:
        raise ValueError(f"schedule must contain exactly one row for {season} round {round_number}")
    record = matches.iloc[0].to_dict()
    missing = [field for field in REQUIRED_SCHEDULE_FIELDS if pd.isna(record.get(field))]
    if missing:
        raise ValueError(f"schedule is missing required values: {', '.join(missing)}")
    return record


def main(
    *,
    season: int | None = None,
    round_number: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> None:
    paths = PublicationPaths(DATA_ROOT)
    active = read_json(paths.active)
    if active is None:
        raise SystemExit("No active prediction exists. Run the Monday refresh first.")
    active_season, active_round = _active_identity(active)
    season = season if season is not None else active_season
    round_number = round_number if round_number is not None else active_round
    if (season is None) != (round_number is None):
        raise SystemExit("--season and --round must be supplied together")
    if not dry_run and (season, round_number) != (active_season, active_round):
        raise SystemExit(
            "A non-dry run may only publish the active race. Use --dry-run to inspect "
            "an archived season/round."
        )

    print(f"Refreshing schedule for {season} round {round_number} …")
    schedule = _schedule_record(get_schedule(season), season, round_number)
    race_id = f"{season}-{round_number}"
    archived = read_json(paths.archive(race_id))
    # Monday may refresh only the active file. Never restore an older same-race
    # estimate from its archive; only a frozen archive has precedence over active.
    source_snapshot = (
        archived if archived and archived.get("frozen_at")
        else active if _active_identity(active) == (season, round_number)
        else archived
    )
    if source_snapshot is None:
        raise SystemExit("The selected event has no prediction snapshot.")
    if _active_identity(source_snapshot) != (season, round_number):
        raise SystemExit(
            "The selected event has no prediction snapshot. Run the Monday refresh "
            "or select the active season/round."
        )

    status = read_json(paths.status)
    if status and status.get("race_id") != race_id:
        status = None
    archive_index = read_json(paths.index)
    exceptions = load_exceptions_config(EXCEPTIONS_PATH)
    participants = latest_completed_participants(
        RAW_ROOT, race_start_at=str(schedule["race_start_at"])
    )
    run_at = now or datetime.now(timezone.utc)

    def build_actual(validated):
        cutoff_date = str(schedule["race_start_at"])[:10]
        model = train_podium_live(cutoff_date)
        base = copy.deepcopy(source_snapshot.get("forecast", source_snapshot))
        if "training_metadata" in source_snapshot:
            base["training_metadata"] = copy.deepcopy(source_snapshot["training_metadata"])
        return forecast_actual_qualifying(
            base_forecast=base,
            actual_qualifying=validated.rows,
            podium_model=model,
            target_date=cutoff_date,
        )

    update = run_publication(
        now=run_at,
        schedule=schedule,
        active_snapshot=source_snapshot,
        status=status,
        archive_index=archive_index,
        expected_participants=participants,
        exceptions=exceptions,
        fetch_qualifying=lambda: get_qualifying_round(season, round_number),
        build_actual_forecast=build_actual,
    )
    write_update(paths, update, dry_run=dry_run)
    export_race_results(RAW_ROOT, DATA_ROOT, update.archive_index, dry_run=dry_run)
    summary = {
        "race_id": race_id,
        "state": update.status["state"],
        "model_ran": update.model_ran,
        "forecast_changed": update.forecast_changed,
        "dry_run": dry_run,
        "next_scheduled_check_at": update.status.get("next_scheduled_check_at"),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--round", dest="round_number", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if (args.season is None) != (args.round_number is None):
        parser.error("--season and --round must be supplied together")
    main(season=args.season, round_number=args.round_number, dry_run=args.dry_run)
