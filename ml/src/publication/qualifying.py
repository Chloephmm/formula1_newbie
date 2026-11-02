"""Round-scoped qualifying validation and deterministic normalization."""
from __future__ import annotations

import hashlib
import json
import math
import numbers
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from src.data.jolpica import QualifyingFetchResult, laptime_to_seconds


EVENT_KEY = re.compile(r"^[0-9]{4}-[1-9][0-9]*$")
IDENTITY_FIELDS = ("season", "round", "race_name", "circuit_id")
LAP_FIELDS = ("q1", "q2", "q3")
LAP_TIME = re.compile(r"^(?:[0-9]+:[0-5][0-9](?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)$")


class QualifyingValidationError(ValueError):
    """Raised when qualifying input is unsafe to publish."""


@dataclass(frozen=True)
class ValidatedQualifying:
    rows: tuple[dict[str, Any], ...]
    input_hash: str
    exceptions_version: int


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualifyingValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_exception_list(items: Any, label: str) -> None:
    if not isinstance(items, list):
        raise QualifyingValidationError(f"{label} must be a list")
    expected_keys = {"driver_id", "reason"}
    for item in items:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise QualifyingValidationError(
                f"{label} entries require exactly driver_id and reason"
            )
        _require_nonempty_string(item["driver_id"], f"{label} driver_id")
        _require_nonempty_string(item["reason"], f"{label} reason")


def validate_exceptions_config(config: Any) -> dict[str, Any]:
    """Validate the versioned, season-round-keyed qualifying exception contract."""
    if not isinstance(config, dict) or set(config) != {"version", "events"}:
        raise QualifyingValidationError("exceptions require exactly version and events")
    version = config["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise QualifyingValidationError("exceptions version must be a positive integer")
    events = config["events"]
    if not isinstance(events, dict):
        raise QualifyingValidationError("exceptions events must be an object")

    for event_key, event in events.items():
        if not isinstance(event_key, str) or not EVENT_KEY.fullmatch(event_key):
            raise QualifyingValidationError(
                "exception event keys must use the season-round form, e.g. 2026-4"
            )
        if not isinstance(event, dict) or set(event) != {
            "withdrawn",
            "excluded",
            "substitutions",
        }:
            raise QualifyingValidationError(
                f"exceptions for {event_key} require withdrawn, excluded, and substitutions"
            )
        _validate_exception_list(event["withdrawn"], f"{event_key} withdrawn")
        _validate_exception_list(event["excluded"], f"{event_key} excluded")

        substitutions = event["substitutions"]
        if not isinstance(substitutions, list):
            raise QualifyingValidationError(f"{event_key} substitutions must be a list")
        expected_keys = {"out_driver_id", "in_driver_id", "reason"}
        for item in substitutions:
            if not isinstance(item, dict) or set(item) != expected_keys:
                raise QualifyingValidationError(
                    f"{event_key} substitutions require exactly out_driver_id, "
                    "in_driver_id, and reason"
                )
            out_driver = _require_nonempty_string(
                item["out_driver_id"], f"{event_key} substitution out_driver_id"
            )
            in_driver = _require_nonempty_string(
                item["in_driver_id"], f"{event_key} substitution in_driver_id"
            )
            _require_nonempty_string(item["reason"], f"{event_key} substitution reason")
            if out_driver == in_driver:
                raise QualifyingValidationError(
                    f"{event_key} substitution must change the driver"
                )

    return config


def load_exceptions_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return validate_exceptions_config(json.load(handle))


def _positive_position(value: Any) -> int:
    if isinstance(value, bool):
        raise QualifyingValidationError("classification position must be a positive integer")
    if isinstance(value, numbers.Integral):
        position = int(value)
    elif isinstance(value, numbers.Real) and math.isfinite(float(value)):
        if not float(value).is_integer():
            raise QualifyingValidationError(
                "classification position must be a positive integer"
            )
        position = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        position = int(value.strip())
    else:
        raise QualifyingValidationError("classification position must be a positive integer")
    if position <= 0:
        raise QualifyingValidationError("classification position must be a positive integer")
    return position


def _is_missing(value: Any) -> bool:
    return value is None or (not isinstance(value, (list, dict)) and bool(pd.isna(value)))


def _optional_value(value: Any) -> Any:
    return None if _is_missing(value) else value


def _adjust_expected_participants(
    expected_participants: Iterable[str],
    event_exceptions: Mapping[str, Any],
) -> set[str]:
    expected = {
        _require_nonempty_string(driver, "expected participant")
        for driver in expected_participants
    }
    for category in ("withdrawn", "excluded"):
        for item in event_exceptions.get(category, []):
            driver = item["driver_id"].strip()
            if driver not in expected:
                raise QualifyingValidationError(
                    f"{category} driver {driver!r} is not an expected participant"
                )
            expected.remove(driver)
    for item in event_exceptions.get("substitutions", []):
        out_driver = item["out_driver_id"].strip()
        in_driver = item["in_driver_id"].strip()
        if out_driver not in expected:
            raise QualifyingValidationError(
                f"substitution driver {out_driver!r} is not an expected participant"
            )
        if in_driver in expected:
            raise QualifyingValidationError(
                f"substitution driver {in_driver!r} is already expected"
            )
        expected.remove(out_driver)
        expected.add(in_driver)
    return expected


def _pagination_metadata_complete(pagination: Any) -> bool:
    if (
        pagination.pages_fetched <= 0
        or pagination.pages_fetched != len(pagination.offsets)
        or pagination.pages_fetched != len(pagination.limits)
    ):
        return False
    expected_offset = 0
    for index, (offset, limit) in enumerate(
        zip(pagination.offsets, pagination.limits)
    ):
        if index > 0 and expected_offset >= pagination.reported_total:
            return False
        if offset != expected_offset or limit <= 0:
            return False
        expected_offset += limit
    return expected_offset >= pagination.reported_total


def validate_qualifying(
    fetched: QualifyingFetchResult,
    *,
    expected_event: Mapping[str, Any],
    expected_participants: Iterable[str],
    exceptions: Mapping[str, Any],
) -> ValidatedQualifying:
    """Validate one event and return canonical rows suitable for model input."""
    config = validate_exceptions_config(dict(exceptions))
    pagination = fetched.pagination
    if (
        not pagination.complete
        or not _pagination_metadata_complete(pagination)
        or pagination.fetched_count != pagination.reported_total
        or pagination.fetched_count != len(fetched.data)
    ):
        raise QualifyingValidationError(
            "qualifying pagination is incomplete: fetched count must equal reported total"
        )

    missing_identity = [field for field in IDENTITY_FIELDS if field not in expected_event]
    if missing_identity:
        raise QualifyingValidationError(
            f"expected event is missing identity fields: {', '.join(missing_identity)}"
        )
    for field in IDENTITY_FIELDS:
        if field not in fetched.data.columns:
            raise QualifyingValidationError(f"qualifying data is missing {field}")
        expected = expected_event[field]
        if field in ("season", "round"):
            expected = int(expected)
        for actual in fetched.data[field].tolist():
            if field in ("season", "round"):
                try:
                    actual = int(actual)
                except (TypeError, ValueError):
                    pass
            if actual != expected:
                raise QualifyingValidationError(
                    f"qualifying {field} {actual!r} does not match expected {expected!r}"
                )

    required_columns = {"driver_id", "quali_position", *LAP_FIELDS}
    missing_columns = required_columns - set(fetched.data.columns)
    if missing_columns:
        raise QualifyingValidationError(
            f"qualifying data is missing columns: {', '.join(sorted(missing_columns))}"
        )

    event_key = f"{int(expected_event['season'])}-{int(expected_event['round'])}"
    event_exceptions = config["events"].get(
        event_key, {"withdrawn": [], "excluded": [], "substitutions": []}
    )
    expected_drivers = _adjust_expected_participants(
        expected_participants, event_exceptions
    )

    driver_ids = [
        _require_nonempty_string(value, "classified driver_id")
        for value in fetched.data["driver_id"].tolist()
    ]
    if len(driver_ids) != len(set(driver_ids)):
        raise QualifyingValidationError("classified driver IDs must be unique")
    actual_drivers = set(driver_ids)
    if actual_drivers != expected_drivers:
        missing = sorted(expected_drivers - actual_drivers)
        extra = sorted(actual_drivers - expected_drivers)
        raise QualifyingValidationError(
            f"qualifying participant coverage mismatch; missing={missing}, extra={extra}"
        )

    positions = [_positive_position(value) for value in fetched.data["quali_position"]]
    if len(positions) != len(set(positions)):
        raise QualifyingValidationError("classification positions must be unique")

    normalized = []
    for (_, source), driver_id, position in zip(
        fetched.data.iterrows(), driver_ids, positions
    ):
        lap_values = {}
        valid_laps = []
        for field in LAP_FIELDS:
            value = source[field]
            if _is_missing(value):
                lap_values[field] = None
                continue
            if not isinstance(value, str):
                raise QualifyingValidationError(
                    f"invalid supplied lap time for {driver_id} {field}: {value!r}"
                )
            normalized_lap = value.strip()
            if not LAP_TIME.fullmatch(normalized_lap):
                raise QualifyingValidationError(
                    f"invalid supplied lap time for {driver_id} {field}: {value!r}"
                )
            seconds = laptime_to_seconds(normalized_lap)
            if seconds is None or not math.isfinite(seconds) or seconds <= 0:
                raise QualifyingValidationError(
                    f"invalid supplied lap time for {driver_id} {field}: {value!r}"
                )
            lap_values[field] = normalized_lap
            valid_laps.append(seconds)

        best_lap = round(min(valid_laps), 6) if valid_laps else None
        normalized.append({
            "season": int(expected_event["season"]),
            "round": int(expected_event["round"]),
            "race_name": str(expected_event["race_name"]),
            "circuit_id": str(expected_event["circuit_id"]),
            "driver_id": driver_id,
            "code": _optional_value(source.get("code")),
            "driver_name": _optional_value(source.get("driver_name")) or driver_id,
            "constructor_id": _optional_value(source.get("constructor_id")),
            "constructor_name": _optional_value(source.get("constructor_name"))
            or _optional_value(source.get("constructor_id"))
            or "Unknown",
            "qualifying_position": position,
            **lap_values,
            "best_lap_seconds": best_lap,
        })

    valid_best_laps = [row["best_lap_seconds"] for row in normalized if row["best_lap_seconds"] is not None]
    if not valid_best_laps:
        raise QualifyingValidationError("qualifying must contain at least one valid lap")
    pole_lap = min(valid_best_laps)
    valid_gaps = [round(lap - pole_lap, 6) for lap in valid_best_laps]
    slowest_valid_gap = max(valid_gaps)
    for row in normalized:
        best_lap = row["best_lap_seconds"]
        row["qualifying_gap_seconds"] = (
            slowest_valid_gap if best_lap is None else round(best_lap - pole_lap, 6)
        )

    normalized.sort(key=lambda row: (row["qualifying_position"], row["driver_id"]))
    rows = tuple(normalized)
    hash_payload = {
        "schema_version": 1,
        "exceptions_version": config["version"],
        "rows": rows,
    }
    canonical = json.dumps(
        hash_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    input_hash = hashlib.sha256(canonical).hexdigest()
    return ValidatedQualifying(
        rows=rows,
        input_hash=input_hash,
        exceptions_version=config["version"],
    )
