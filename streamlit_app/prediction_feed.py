"""Read and validate the static prediction feed from HTTP or local files."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


SCHEMA_VERSION = 2


class FeedError(ValueError):
    """The published feed is unavailable or incompatible."""


@dataclass(frozen=True)
class PredictionBundle:
    index: dict[str, Any]
    artifact: dict[str, Any]
    status: dict[str, Any] | None


def _read_json(local_root: Path, base_url: str | None, relative: str) -> dict[str, Any]:
    try:
        if base_url:
            response = requests.get(
                urljoin(base_url.rstrip("/") + "/", relative),
                params={"_poll": int(time.time())},
                headers={"Cache-Control": "no-cache"},
                timeout=(2, 4),
            )
            response.raise_for_status()
            value = response.json()
        else:
            value = json.loads((local_root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, requests.RequestException) as exc:
        raise FeedError(f"could not read {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise FeedError(f"{relative} must contain a JSON object")
    return value


def _schema(value: dict[str, Any], label: str) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise FeedError(f"{label} has an incompatible schema_version")


def validate_index(index: dict[str, Any]) -> None:
    _schema(index, "archive index")
    if not isinstance(index.get("active_race_id"), str):
        raise FeedError("archive index has no active_race_id")
    races = index.get("races")
    if not isinstance(races, list) or not races:
        raise FeedError("archive index has no races")
    ids = [entry.get("race_id") for entry in races if isinstance(entry, dict)]
    if len(ids) != len(races) or len(set(ids)) != len(ids):
        raise FeedError("archive index race IDs must be present and unique")


def validate_artifact(artifact: dict[str, Any], race_id: str) -> None:
    _schema(artifact, "prediction artifact")
    if artifact.get("race_id") != race_id:
        raise FeedError("prediction artifact race_id does not match the selection")
    if artifact.get("input_mode") not in {"estimated_qualifying", "actual_qualifying"}:
        raise FeedError("prediction artifact input_mode is invalid")
    forecast = artifact.get("forecast")
    if not isinstance(forecast, dict) or forecast.get("error"):
        raise FeedError("prediction artifact forecast is invalid")
    if not isinstance(forecast.get("predictedQualifying"), list):
        raise FeedError("prediction artifact has no estimated qualifying rows")
    estimated_podium = forecast.get("preQualifyingPodium")
    if not isinstance(estimated_podium, list) or not estimated_podium:
        raise FeedError("prediction artifact has no estimated podium rows")
    if artifact["input_mode"] == "actual_qualifying":
        if not isinstance(forecast.get("actualQualifying"), list):
            raise FeedError("prediction artifact has no actual qualifying rows")
        podium = forecast.get("actualQualifyingPodium")
        if not isinstance(podium, list) or not podium:
            raise FeedError("prediction artifact has no actual podium rows")
    else:
        podium = estimated_podium
    probabilities = [row.get("podiumProbability") for row in podium]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in probabilities):
        raise FeedError("prediction artifact has invalid podium probabilities")
    if not math.isclose(sum(probabilities), 3.0, abs_tol=0.02):
        raise FeedError("prediction artifact podium probabilities are not normalized")
    for field in ("prediction_updated_at", "publication_cutoff_at"):
        if not isinstance(artifact.get(field), str):
            raise FeedError(f"prediction artifact has no {field}")
        try:
            parsed = datetime.fromisoformat(artifact[field].replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeedError(f"prediction artifact {field} is invalid") from exc
        if parsed.tzinfo is None:
            raise FeedError(f"prediction artifact {field} is not timezone-aware")


def load_index(local_root: Path, *, base_url: str | None) -> dict[str, Any]:
    index = _read_json(local_root, base_url, "predictions/index.json")
    validate_index(index)
    # Monday's existing workflow is intentionally allowed to commit only the active
    # compatibility snapshot. Merge it in-memory so the website rolls forward at once;
    # the next hourly publisher persists the matching archive/index/status files.
    try:
        active = _read_json(local_root, base_url, "next_race_prediction.json")
        active_race_id = active.get("race_id")
        validate_artifact(active, active_race_id)
    except FeedError:
        return index
    race = active.get("race") or active["forecast"]["race"]
    entry = {
        "race_id": active_race_id,
        "season": int(race["season"]),
        "round": int(race["round"]),
        "race_name": race["name"],
        "race_start_at": race.get("raceStartAt") or race.get("date"),
        "artifact_url": "next_race_prediction.json",
        "input_mode": active["input_mode"],
        "frozen": active.get("frozen_at") is not None,
    }
    entries = {item["race_id"]: item for item in index["races"]}
    entries[active_race_id] = entry
    index = dict(index)
    index["active_race_id"] = active_race_id
    index["races"] = sorted(
        entries.values(), key=lambda item: (item.get("season", 0), item.get("round", 0)),
        reverse=True,
    )
    return index


def load_bundle(
    local_root: Path,
    *,
    base_url: str | None,
    race_id: str,
    index: dict[str, Any] | None = None,
) -> PredictionBundle:
    index = index or load_index(local_root, base_url=base_url)
    validate_index(index)
    entry = next((item for item in index["races"] if item["race_id"] == race_id), None)
    if entry is None:
        raise FeedError(f"race {race_id} is not in the archive index")
    relative = entry.get("artifact_url")
    if not isinstance(relative, str) or not (
        relative.startswith("predictions/") or relative == "next_race_prediction.json"
    ):
        raise FeedError("archive artifact_url is invalid")
    artifact = _read_json(local_root, base_url, relative)
    validate_artifact(artifact, race_id)
    status = None
    if race_id == index["active_race_id"]:
        status = _read_json(local_root, base_url, "prediction_status.json")
        _schema(status, "prediction status")
        if status.get("race_id") != race_id:
            status = None
    return PredictionBundle(index=index, artifact=artifact, status=status)


def load_race_results(local_root: Path, *, base_url: str | None, race_id: str) -> dict[str, Any]:
    """Load recorded results separately so frozen forecasts are never modified."""
    if not isinstance(race_id, str) or not all(part.isdigit() for part in race_id.split("-")) or len(race_id.split("-")) != 2:
        raise FeedError("invalid race ID")
    result = _read_json(local_root, base_url, f"predictions/{race_id}-results.json")
    _schema(result, "race results")
    if result.get("race_id") != race_id:
        raise FeedError("race results belong to a different event")
    rows = result.get("results")
    if not isinstance(rows, list) or not rows:
        raise FeedError("race results are not available yet")
    positions, drivers = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise FeedError("race result row is invalid")
        position, driver = row.get("position"), row.get("driver_id")
        points = row.get("points")
        if (type(position) is not int or position <= 0 or position in positions
                or not isinstance(driver, str) or not driver or driver in drivers
                or not isinstance(points, (int, float)) or not math.isfinite(points) or points < 0
                or not all(isinstance(row.get(key), str) and row[key] for key in ("driver_name", "constructor_name", "status"))):
            raise FeedError("race result classification is invalid")
        positions.add(position)
        drivers.add(driver)
    return result


def choose_race(
    active_race_id: str,
    available: list[str],
    selected: str | None,
    previous_active_race_id: str | None = None,
) -> str:
    if (
        previous_active_race_id
        and previous_active_race_id != active_race_id
        and selected == previous_active_race_id
    ):
        return active_race_id
    if selected in available:
        return selected
    if active_race_id in available:
        return active_race_id
    if not available:
        raise FeedError("archive index has no selectable races")
    return available[0]
