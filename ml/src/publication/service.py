"""Filesystem boundary and historical entrant lookup for publication runs."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.publication.publisher import PublicationUpdate


@dataclass(frozen=True)
class PublicationPaths:
    """Published JSON locations rooted at ``web/public/data``."""

    root: Path

    @property
    def active(self) -> Path:
        return self.root / "next_race_prediction.json"

    @property
    def status(self) -> Path:
        return self.root / "prediction_status.json"

    @property
    def index(self) -> Path:
        return self.root / "predictions" / "index.json"

    def archive(self, race_id: str) -> Path:
        return self.root / "predictions" / f"{race_id}.json"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_update(paths: PublicationPaths, update: PublicationUpdate, *, dry_run: bool,
                 now: datetime | None = None) -> None:
    """Atomically publish an update while preserving a frozen race artifact."""
    if dry_run:
        return
    existing_archive = read_json(paths.archive(update.snapshot["race_id"]))
    frozen_archive = bool(existing_archive and existing_archive.get("frozen_at"))
    active = read_json(paths.active)
    if active and active.get("race_id") != update.snapshot["race_id"]:
        raise ValueError("active race changed during prediction processing")
    for existing in (active, existing_archive):
        if (existing and existing.get("input_mode") == "actual_qualifying"
                and update.snapshot["input_mode"] == "estimated_qualifying"):
            raise ValueError("cannot downgrade actual qualifying to estimated")
    if active and not update.forecast_changed:
        for field in ("prediction_updated_at", "qualifying_input_hash", "forecast"):
            if active.get(field) != update.snapshot.get(field):
                raise ValueError("status-only update has a stale forecast; retry from active snapshot")
    if update.forecast_changed:
        cutoff = datetime.fromisoformat(update.snapshot["publication_cutoff_at"].replace("Z", "+00:00"))
        if (now or datetime.now(timezone.utc)) >= cutoff:
            raise ValueError("publication cutoff has passed; keeping last valid forecast")
        if frozen_archive or (active and active.get("race_id") == update.snapshot["race_id"] and active.get("frozen_at")):
            raise ValueError("cannot replace a frozen prediction")
    snapshot = existing_archive if frozen_archive else update.snapshot
    _atomic_json(paths.active, snapshot)
    _atomic_json(paths.status, update.status)
    _atomic_json(paths.index, update.archive_index)
    if not frozen_archive:
        _atomic_json(paths.archive(update.snapshot["race_id"]), update.snapshot)


def latest_completed_participants(raw_dir: Path, *, race_start_at: str) -> set[str]:
    """Return entrants from the latest completed race before the target event."""
    files = sorted(Path(raw_dir).glob("results_*.parquet"))
    if not files:
        raise ValueError("no cached race results are available for participant validation")
    results = pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)
    required = {"season", "round", "date", "driver_id"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"race results are missing columns: {', '.join(sorted(missing))}")
    results["date"] = pd.to_datetime(results["date"], utc=True, errors="coerce")
    cutoff = pd.Timestamp(race_start_at)
    if cutoff.tzinfo is None:
        raise ValueError("race_start_at must be timezone-aware")
    completed = results[results["date"] < cutoff.normalize()].dropna(subset=["date", "driver_id"])
    if completed.empty:
        raise ValueError("no completed race exists before the target event")
    latest = completed.sort_values(["date", "season", "round"]).iloc[-1]
    entrants = completed[
        (completed["season"] == latest["season"])
        & (completed["round"] == latest["round"])
    ]["driver_id"]
    values = {str(value).strip() for value in entrants if str(value).strip()}
    if not values:
        raise ValueError("latest completed race contains no participant IDs")
    return values
