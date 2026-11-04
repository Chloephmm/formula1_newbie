"""Pure publication state machine for estimated and actual qualifying forecasts."""
from __future__ import annotations

import copy
import math
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from src.publication.qualifying import (
    QualifyingValidationError,
    validate_qualifying,
)
from src.publication.timing import calculate_publication_timing, next_hourly_tick


SCHEMA_VERSION = 2


@dataclass(frozen=True)
class PublicationUpdate:
    snapshot: dict[str, Any]
    status: dict[str, Any]
    archive_index: dict[str, Any]
    model_ran: bool
    forecast_changed: bool


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("publication time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return _utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _race_id(schedule: Mapping[str, Any]) -> str:
    return f"{int(schedule['season'])}-{int(schedule['round'])}"


def _forecast_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    forecast = snapshot.get("forecast")
    if isinstance(forecast, dict):
        return copy.deepcopy(forecast)
    if "race" in snapshot and "preQualifyingPodium" in snapshot:
        return copy.deepcopy(dict(snapshot))
    raise ValueError("active prediction snapshot has no forecast")


def _base_snapshot(
    active_snapshot: Mapping[str, Any],
    schedule: Mapping[str, Any],
    now: datetime,
    cutoff_at: datetime,
) -> dict[str, Any]:
    forecast = _forecast_from_snapshot(active_snapshot)
    forecast_race = forecast.get("race", {})
    expected = (int(schedule["season"]), int(schedule["round"]), schedule["race_name"])
    actual = (
        int(forecast_race.get("season", -1)),
        int(forecast_race.get("round", -1)),
        forecast_race.get("name"),
    )
    if actual != expected:
        raise ValueError(f"active prediction race {actual!r} does not match schedule {expected!r}")
    prediction_updated_at = active_snapshot.get("prediction_updated_at")
    if not prediction_updated_at:
        generated = active_snapshot.get("generatedAt")
        prediction_updated_at = (
            f"{generated}T00:00:00Z" if isinstance(generated, str) and len(generated) == 10
            else _iso(now)
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "race_id": _race_id(schedule),
        "race": copy.deepcopy(forecast_race),
        "forecast": forecast,
        "input_mode": active_snapshot.get("input_mode", "estimated_qualifying"),
        "prediction_updated_at": prediction_updated_at,
        "qualifying_input_hash": active_snapshot.get("qualifying_input_hash"),
        "publication_cutoff_at": _iso(cutoff_at),
        "frozen_at": active_snapshot.get("frozen_at"),
        "status_reason": active_snapshot.get("status_reason"),
        **({"training_metadata": copy.deepcopy(active_snapshot["training_metadata"])}
           if "training_metadata" in active_snapshot else {}),
    }


def _base_status(
    previous: Mapping[str, Any] | None,
    snapshot: Mapping[str, Any],
    schedule: Mapping[str, Any],
    timing,
    now: datetime,
) -> dict[str, Any]:
    status = copy.deepcopy(dict(previous or {}))
    previous_schedule = status.get("schedule") if isinstance(status.get("schedule"), dict) else {}
    schedule_changed = any(
        previous_schedule.get(field) not in (None, schedule.get(field))
        for field in ("qualifying_start_at", "qualifying_end_at", "race_start_at")
    )
    status.update({
        "schema_version": SCHEMA_VERSION,
        "race_id": snapshot["race_id"],
        "input_mode": snapshot["input_mode"],
        "prediction_updated_at": snapshot["prediction_updated_at"],
        "publication_cutoff_at": _iso(timing.cutoff_at),
        "schedule_updated_at": schedule.get("schedule_updated_at") or _iso(now),
        "schedule": {
            field: schedule.get(field)
            for field in (
                "season", "round", "qualifying_start_at", "qualifying_end_at",
                "end_time_estimated", "race_start_at", "schedule_updated_at",
            )
        },
    })
    status.setdefault("last_data_check_at", None)
    status.setdefault("next_scheduled_check_at", None)
    status.setdefault("final_verification_completed_at", None)
    status.setdefault("status_reason", None)
    if schedule_changed and snapshot.get("frozen_at") is None:
        status["final_verification_completed_at"] = None
    return status


def _index_with_snapshot(
    previous: Mapping[str, Any] | None,
    snapshot: Mapping[str, Any],
    schedule: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    index = copy.deepcopy(dict(previous or {}))
    entries = {
        entry["race_id"]: entry
        for entry in index.get("races", [])
        if isinstance(entry, dict) and entry.get("race_id")
    }
    entries[snapshot["race_id"]] = {
        "race_id": snapshot["race_id"],
        "season": int(schedule["season"]),
        "round": int(schedule["round"]),
        "race_name": schedule["race_name"],
        "race_start_at": schedule["race_start_at"],
        "artifact_url": f"predictions/{snapshot['race_id']}.json",
        "input_mode": snapshot["input_mode"],
        "frozen": snapshot["frozen_at"] is not None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "active_race_id": snapshot["race_id"],
        "updated_at": _iso(now),
        "races": sorted(
            entries.values(),
            key=lambda entry: (entry["season"], entry["round"]),
            reverse=True,
        ),
    }


def validate_forecast_artifact(
    forecast: Mapping[str, Any],
    schedule: Mapping[str, Any],
    expected_codes: set[str],
    *, input_mode: str = "actual_qualifying",
) -> None:
    if forecast.get("error"):
        raise ValueError(f"forecast failed: {forecast['error']}")
    race = forecast.get("race", {})
    if (
        int(race.get("season", -1)) != int(schedule["season"])
        or int(race.get("round", -1)) != int(schedule["round"])
        or race.get("name") != schedule["race_name"]
    ):
        raise ValueError("generated forecast event does not match schedule")
    if input_mode not in {"actual_qualifying", "estimated_qualifying"}:
        raise ValueError("invalid forecast input mode")
    actual = input_mode == "actual_qualifying"
    qualifying = forecast.get("actualQualifying" if actual else "predictedQualifying")
    podium = forecast.get("actualQualifyingPodium" if actual else "preQualifyingPodium")
    expected_count = len(expected_codes)
    if not isinstance(qualifying, list) or len(qualifying) != expected_count:
        raise ValueError("generated actual qualifying coverage is invalid")
    if not isinstance(podium, list) or len(podium) != expected_count:
        raise ValueError("generated actual podium coverage is invalid")
    qualifying_codes = [row.get("code") for row in qualifying]
    podium_codes = [row.get("code") for row in podium]
    if set(qualifying_codes) != expected_codes or len(set(qualifying_codes)) != expected_count:
        raise ValueError("generated actual qualifying entrants are invalid")
    if set(podium_codes) != expected_codes or len(set(podium_codes)) != expected_count:
        raise ValueError("generated actual podium entrants are invalid")
    probabilities = [row.get("podiumProbability") for row in podium]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in probabilities):
        raise ValueError("generated podium probabilities must be finite")
    if any(isinstance(value, bool) or not 0 <= value <= 1 for value in probabilities):
        raise ValueError("generated podium probabilities must be between zero and one")
    if not math.isclose(sum(probabilities), 3.0, abs_tol=0.02):
        raise ValueError("generated podium probabilities must sum to three")
    positions = [row.get("position") for row in qualifying]
    if any(isinstance(p, bool) or not isinstance(p, int) or p <= 0 for p in positions) or len(set(positions)) != expected_count:
        raise ValueError("generated qualifying positions must be unique positive integers")
    gaps = [row.get("gap") for row in qualifying]
    if any(isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g) or g < 0 for g in gaps):
        raise ValueError("generated qualifying gaps must be finite and nonnegative")


def _finish(
    *,
    snapshot: dict[str, Any],
    status: dict[str, Any],
    archive_index: Mapping[str, Any] | None,
    schedule: Mapping[str, Any],
    now: datetime,
    model_ran: bool = False,
    forecast_changed: bool = False,
) -> PublicationUpdate:
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("prediction snapshot schema is invalid")
    if snapshot.get("input_mode") not in {"estimated_qualifying", "actual_qualifying"}:
        raise ValueError("prediction snapshot input mode is invalid")
    for field in ("prediction_updated_at", "publication_cutoff_at"):
        if not snapshot.get(field):
            raise ValueError(f"prediction snapshot is missing {field}")
        _utc(snapshot[field])
    if snapshot.get("frozen_at"):
        _utc(snapshot["frozen_at"])
    return PublicationUpdate(
        snapshot=snapshot,
        status=status,
        archive_index=_index_with_snapshot(archive_index, snapshot, schedule, now),
        model_ran=model_ran,
        forecast_changed=forecast_changed,
    )


def run_publication(
    *,
    now: datetime,
    schedule: Mapping[str, Any],
    active_snapshot: Mapping[str, Any],
    status: Mapping[str, Any] | None,
    archive_index: Mapping[str, Any] | None,
    expected_participants: Iterable[str],
    exceptions: Mapping[str, Any],
    fetch_qualifying: Callable[[], Any],
    build_actual_forecast: Callable[[Any], dict[str, Any]],
) -> PublicationUpdate:
    """Evaluate one hourly run without performing filesystem or network side effects."""
    now = _utc(now)
    timing = calculate_publication_timing(
        qualifying_end_at=schedule["qualifying_end_at"],
        race_start_at=schedule["race_start_at"],
    )
    snapshot = _base_snapshot(active_snapshot, schedule, now, timing.cutoff_at)
    current_status = _base_status(status, snapshot, schedule, timing, now)

    if active_snapshot.get("frozen_at"):
        # A schedule postponement must not reopen a race that was already frozen.
        snapshot = copy.deepcopy(dict(active_snapshot))
        current_status.update(
            state="frozen_actual" if snapshot["input_mode"] == "actual_qualifying" else "frozen_estimated",
            publication_cutoff_at=snapshot["publication_cutoff_at"],
            next_scheduled_check_at=None,
        )
        return _finish(snapshot=snapshot, status=current_status, archive_index=archive_index,
                       schedule=schedule, now=now)

    if now >= timing.cutoff_at:
        snapshot["frozen_at"] = _iso(timing.cutoff_at)
        current_status.update({
            "state": (
                "frozen_actual"
                if snapshot["input_mode"] == "actual_qualifying"
                else "frozen_estimated"
            ),
            "input_mode": snapshot["input_mode"],
            "next_scheduled_check_at": None,
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    if timing.reason:
        snapshot["status_reason"] = timing.reason
        current_status.update({
            "state": "estimated_waiting",
            "status_reason": timing.reason,
            "next_scheduled_check_at": None,
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    if now < timing.first_scheduled_tick_at:
        current_status.update({
            "state": "estimated_waiting",
            "status_reason": "actual_qualifying_not_checked_yet",
            "next_scheduled_check_at": _iso(timing.first_scheduled_tick_at),
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    already_actual = snapshot["input_mode"] == "actual_qualifying"
    final_complete = current_status.get("final_verification_completed_at") is not None
    if final_complete:
        current_status.update({
            "state": "actual_published" if already_actual else "estimated_waiting",
            "input_mode": snapshot["input_mode"],
            "next_scheduled_check_at": None,
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )
    if already_actual and now < timing.final_verification_tick_at:
        current_status.update({
            "state": "actual_published",
            "input_mode": "actual_qualifying",
            "status_reason": None,
            "next_scheduled_check_at": _iso(timing.final_verification_tick_at),
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    if now > timing.latest_processing_start_at:
        reason = "processing_window_closed"
        snapshot["status_reason"] = reason
        current_status.update({
            "state": "actual_published" if already_actual else "estimated_waiting",
            "status_reason": reason,
            "next_scheduled_check_at": None,
        })
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    try:
        validated = validate_qualifying(
            fetch_qualifying(),
            expected_event={
                "season": schedule["season"],
                "round": schedule["round"],
                "race_name": schedule["race_name"],
                "circuit_id": schedule["circuit_id"],
            },
            expected_participants=expected_participants,
            exceptions=exceptions,
        )
    except (QualifyingValidationError, requests.RequestException, KeyError, TypeError, ValueError) as exc:
        final_attempt = now >= timing.final_verification_tick_at
        current_status.update({
            "state": "actual_published" if already_actual else "estimated_waiting",
            "last_data_check_at": _iso(now),
            "status_reason": f"qualifying_unavailable_or_invalid: {exc}",
            "next_scheduled_check_at": (
                None
                if final_attempt
                else _iso(min(next_hourly_tick(now + timedelta(seconds=1)), timing.final_verification_tick_at))
            ),
        })
        if final_attempt:
            current_status["final_verification_completed_at"] = _iso(now)
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    final_attempt = now >= timing.final_verification_tick_at
    unchanged = validated.input_hash == snapshot.get("qualifying_input_hash")
    if unchanged:
        current_status.update({
            "state": "actual_published",
            "input_mode": "actual_qualifying",
            "last_data_check_at": _iso(now),
            "status_reason": None,
            "next_scheduled_check_at": None if final_attempt else _iso(timing.final_verification_tick_at),
        })
        if final_attempt:
            current_status["final_verification_completed_at"] = _iso(now)
        return _finish(
            snapshot=snapshot,
            status=current_status,
            archive_index=archive_index,
            schedule=schedule,
            now=now,
        )

    forecast = build_actual_forecast(validated)
    expected_codes = {
        row.get("code") or row["driver_id"][:3].upper()
        for row in validated.rows
    }
    validate_forecast_artifact(forecast, schedule, expected_codes)
    snapshot.update({
        "forecast": forecast,
        "input_mode": "actual_qualifying",
        "prediction_updated_at": _iso(now),
        "qualifying_input_hash": validated.input_hash,
        "status_reason": None,
    })
    snapshot.pop("training_metadata", None)
    if "training_metadata" in forecast:
        snapshot["training_metadata"] = copy.deepcopy(forecast["training_metadata"])
    current_status.update({
        "state": "actual_published",
        "input_mode": "actual_qualifying",
        "prediction_updated_at": _iso(now),
        "last_data_check_at": _iso(now),
        "status_reason": None,
        "next_scheduled_check_at": None if final_attempt else _iso(timing.final_verification_tick_at),
    })
    if final_attempt:
        current_status["final_verification_completed_at"] = _iso(now)
    return _finish(
        snapshot=snapshot,
        status=current_status,
        archive_index=archive_index,
        schedule=schedule,
        now=now,
        model_ran=True,
        forecast_changed=True,
    )
