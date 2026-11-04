"""Validated candidates and guarded replacement of estimated predictions."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from src.publication.publisher import (
    SCHEMA_VERSION, PublicationUpdate, _base_status, _index_with_snapshot,
    _iso, _utc, validate_forecast_artifact,
)
from src.publication.service import PublicationPaths, read_json, write_update
from src.publication.timing import calculate_publication_timing, next_hourly_tick


def validate_schedule(schedule: dict):
    """Fail before expensive model work when identity/session metadata is unusable."""
    for field in ("season", "round", "race_name", "circuit_id", "qualifying_start_at",
                  "qualifying_end_at", "race_start_at", "schedule_updated_at"):
        if schedule.get(field) is None or str(schedule[field]).strip() in {"", "nan", "NaT"}:
            raise ValueError(f"schedule is missing {field}")
    if int(schedule["season"]) <= 0 or int(schedule["round"]) <= 0:
        raise ValueError("invalid schedule event identity")
    start, end, race = [_utc(schedule[k]) for k in
                        ("qualifying_start_at", "qualifying_end_at", "race_start_at")]
    _utc(schedule["schedule_updated_at"])
    if not start < end < race:
        raise ValueError("qualifying and race timestamps are out of order")
    if not isinstance(schedule.get("end_time_estimated"), bool):
        raise ValueError("schedule is missing end_time_estimated")
    return calculate_publication_timing(qualifying_end_at=end, race_start_at=race)


def make_candidate(forecast: dict, schedule: dict, expected_codes: set[str], now: datetime) -> dict:
    timing = validate_schedule(schedule)
    now = _utc(now)
    validate_forecast_artifact(forecast, schedule, expected_codes, input_mode="estimated_qualifying")
    for key, field in (("raceStartAt", "race_start_at"), ("qualifyingStartAt", "qualifying_start_at")):
        if _utc(forecast["race"].get(key)) != _utc(schedule[field]):
            raise ValueError(f"forecast {key} does not match schedule")
    result = {
        "schema_version": SCHEMA_VERSION,
        "race_id": f"{int(schedule['season'])}-{int(schedule['round'])}",
        "race": copy.deepcopy(forecast["race"]), "forecast": copy.deepcopy(forecast),
        "input_mode": "estimated_qualifying", "prediction_updated_at": _iso(now),
        "qualifying_input_hash": None, "publication_cutoff_at": _iso(timing.cutoff_at),
        "frozen_at": None, "status_reason": "actual_qualifying_not_checked_yet",
    }
    if "training_metadata" in forecast:
        result["training_metadata"] = copy.deepcopy(forecast["training_metadata"])
    return result


def ensure_estimated_publishable(paths: PublicationPaths, race_id: str, timing, now: datetime,
                                 *, require_active: bool = True, starting: bool = True) -> None:
    now = _utc(now)
    if now >= timing.cutoff_at:
        raise ValueError("publication cutoff has passed; candidate is diagnostic only")
    if starting and now > timing.latest_processing_start_at:
        raise ValueError("processing buffer has closed; candidate is diagnostic only")
    active = read_json(paths.active)
    if require_active and (not active or active.get("race_id") != race_id):
        raise ValueError("candidate is no longer the active race")
    for existing in (active, read_json(paths.archive(race_id))):
        if existing and existing.get("race_id") == race_id:
            if existing.get("frozen_at"):
                raise ValueError("cannot replace a frozen prediction")
            if existing.get("input_mode") == "actual_qualifying":
                raise ValueError("cannot downgrade actual qualifying to estimated")


def publish_candidate(paths: PublicationPaths, candidate: dict, schedule: dict, expected_codes: set[str],
                      *, clock=lambda: datetime.now(timezone.utc), active_only: bool = False) -> None:
    """Publish validated output; weekly jobs retain their active-only commit contract."""
    now = _utc(clock())
    timing = validate_schedule(schedule)
    canonical = make_candidate(candidate["forecast"], schedule, expected_codes,
                               _utc(candidate["prediction_updated_at"]))
    if canonical != candidate or _utc(candidate["prediction_updated_at"]) > now:
        raise ValueError("candidate envelope or timestamps are invalid")
    ensure_estimated_publishable(paths, candidate["race_id"], timing, now,
                                 require_active=not active_only)
    previous_status = read_json(paths.status)
    if previous_status and previous_status.get("race_id") != candidate["race_id"]:
        previous_status = None
    status = _base_status(previous_status, candidate, schedule, timing, now)
    status.update(state="estimated_waiting", status_reason=timing.reason or candidate["status_reason"],
                  next_scheduled_check_at=(None if timing.reason else _iso(
                      timing.first_scheduled_tick_at if now < timing.first_scheduled_tick_at
                      else min(next_hourly_tick(now),
                               timing.final_verification_tick_at))))
    update = PublicationUpdate(candidate, status, _index_with_snapshot(
        read_json(paths.index), candidate, schedule, now), True, True)
    ensure_estimated_publishable(paths, candidate["race_id"], timing, clock(),
                                 require_active=not active_only, starting=False)
    if active_only:
        from src.publication.service import _atomic_json
        _atomic_json(paths.active, candidate)
    else:
        write_update(paths, update, dry_run=False, now=clock())
