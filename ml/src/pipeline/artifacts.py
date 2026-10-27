"""Canonical provenance and immutable storage for prediction candidates.

The trusted boundary is explicit: callers supply the exact prepared historical
snapshot and feature rows used for a fit/prediction.  This module validates and
hashes those values; it does not load mutable caches or infer model metadata.
Actual-mode provenance additionally requires Task 3's ``AcceptedQualifying`` type.
"""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
import math
from numbers import Integral, Real
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from src.pipeline.events import (
    EventContractError,
    parse_utc,
    roster_version,
    schedule_hash,
    validate_roster_record,
)


SCHEMA_VERSION = 2
FEATURE_POLICY_VERSION = "qualifying-min-session-v1"
PROBABILITY_POLICY_VERSION = "capped-sum-to-three-v1"
MODES = frozenset({"predicted_qualifying", "actual_qualifying"})
DRIVER_LISTS = (
    "predictedQualifying",
    "preQualifyingPodium",
    "realQualifying",
    "realGridPodium",
)
HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


class ArtifactCollisionError(FileExistsError):
    """An immutable path already contains different canonical bytes."""


def canonical_bytes(payload: Any) -> bytes:
    """Return the sole JSON byte representation used by artifact hashes."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _utc_text(value: Any, *, field: str) -> str:
    try:
        parsed = parse_utc(value)
    except EventContractError as exc:
        raise ValueError(f"{field} must be a timezone-aware UTC timestamp") from exc
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        if not (isinstance(value, str) and value.strip().isdigit()):
            raise ValueError(f"{field} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return result


def _event_identity(event: Mapping[str, Any]) -> tuple[int, int]:
    if not isinstance(event, Mapping):
        raise TypeError("event must be a mapping")
    return (
        _integer(event.get("season"), field="season"),
        _integer(event.get("round"), field="round"),
    )


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            return math.isnan(float(value))
        except (TypeError, ValueError):
            return False
    try:
        result = value != value
        return bool(result) if isinstance(result, (bool,)) else False
    except (TypeError, ValueError):
        return False


def _json_safe(value: Any, *, missing_as_null: bool) -> Any:
    if _is_missing(value):
        if missing_as_null:
            return None
        raise ValueError("model inputs must not contain missing or non-finite values")
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item, missing_as_null=missing_as_null)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item, missing_as_null=missing_as_null) for item in value]
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            if missing_as_null:
                return None
            raise ValueError("model inputs must be finite")
        if isinstance(value, Integral):
            return int(value)
        return float(value)
    if isinstance(value, (str, bool)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _records(value: Any, *, name: str) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict("records")
        except TypeError:
            pass
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a DataFrame or sequence of mappings")
    records = []
    for row in value:
        if not isinstance(row, Mapping):
            raise TypeError(f"{name} rows must be mappings")
        records.append(dict(row))
    return records


def _canonical_driver_rows(value: Any, *, name: str, missing_as_null: bool) -> list[dict]:
    records = [
        _json_safe(row, missing_as_null=missing_as_null)
        for row in _records(value, name=name)
    ]
    driver_ids = [row.get("driver_id") for row in records]
    if any(not isinstance(driver_id, str) or not driver_id for driver_id in driver_ids):
        raise ValueError(f"{name} rows require non-empty driver_id")
    if len(driver_ids) != len(set(driver_ids)):
        raise ValueError(f"{name} rows contain duplicate driver_id")
    return sorted(records, key=lambda row: row["driver_id"])


def _canonical_forecast(forecast: Any) -> dict[str, Any]:
    if not isinstance(forecast, Mapping):
        raise TypeError("forecast must be a mapping")
    result = _json_safe(forecast, missing_as_null=True)
    for key in DRIVER_LISTS:
        value = result.get(key)
        if isinstance(value, list):
            result[key] = sorted(value, key=lambda row: row.get("driver_id", ""))
    return result


def _semantic_prediction(payload: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "schema_version", "season", "round", "mode", "model_version",
        "model_manifest", "training_cutoff", "training_data_hash",
        "training_manifest", "qualifying_source_version", "qualifying_manifest",
        "input_hash", "feature_input_hash", "feature_policy_version",
        "probability_policy_version", "event_schedule_hash", "roster_version",
    )
    semantic = {key: payload.get(key) for key in fields}
    semantic["forecast"] = _canonical_forecast(payload.get("forecast"))
    return semantic


def digest(payload: Any, *, semantic_prediction: bool = False) -> str:
    """Hash a canonical value or only a prediction's semantic version content."""

    if semantic_prediction:
        if not isinstance(payload, Mapping):
            raise TypeError("semantic prediction digest requires a mapping")
        payload = _semantic_prediction(payload)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _normalized_training(
    snapshot: Mapping[str, Any], *, event: Mapping[str, Any], training_cutoff: Any
) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    if not isinstance(snapshot, Mapping) or not {"results", "qualifying"}.issubset(snapshot):
        raise ValueError("training snapshot must contain results and qualifying tables")
    target_season, target_round = _event_identity(event)
    cutoff_text = _utc_text(training_cutoff, field="training_cutoff")
    cutoff = parse_utc(cutoff_text)
    tables: dict[str, list[dict]] = {}
    table_manifest: dict[str, Any] = {}
    total_rows = 0
    for table_name in sorted(snapshot):
        if not isinstance(table_name, str) or not table_name:
            raise ValueError("training table names must be non-empty text")
        rows = _records(snapshot[table_name], name=f"training table {table_name}")
        canonical_rows = []
        event_rows: dict[tuple[int, int], list[str]] = {}
        for raw in rows:
            season = _integer(raw.get("season"), field="training season")
            round_number = _integer(raw.get("round"), field="training round")
            if (season, round_number) >= (target_season, target_round):
                raise ValueError("training snapshot contains target or later rows")
            normalized = _json_safe(raw, missing_as_null=True)
            dates: list[str] = []
            if table_name == "results" and (
                raw.get("date") is None or _is_missing(raw.get("date"))
            ):
                raise ValueError("every training result row requires a recorded date")
            if raw.get("date") is not None and not _is_missing(raw.get("date")):
                date_text = _utc_text(raw["date"], field="training date")
                if parse_utc(date_text) >= cutoff:
                    raise ValueError("training snapshot contains rows at or after cutoff")
                normalized["date"] = date_text
                dates.append(date_text)
            event_rows.setdefault((season, round_number), []).extend(dates)
            canonical_rows.append(normalized)
        canonical_rows.sort(key=canonical_bytes)
        tables[table_name] = canonical_rows
        events = []
        counts = Counter(
            (_integer(row["season"], field="training season"),
             _integer(row["round"], field="training round"))
            for row in canonical_rows
        )
        for identity in sorted(counts):
            entry = {
                "season": identity[0], "round": identity[1],
                "row_count": counts[identity],
            }
            dates = event_rows.get(identity, [])
            if dates:
                entry["min_date"] = min(dates)
                entry["max_date"] = max(dates)
            events.append(entry)
        table_manifest[table_name] = {"row_count": len(rows), "events": events}
        total_rows += len(rows)
    result_events = {
        (row["season"], row["round"]) for row in tables["results"]
    }
    qualifying_events = {
        (row["season"], row["round"]) for row in tables["qualifying"]
    }
    if not result_events or not qualifying_events.issubset(result_events):
        raise ValueError("training qualifying contains an orphan event")
    if total_rows == 0:
        raise ValueError("training snapshot cannot be empty")
    manifest = {"row_count": total_rows, "tables": table_manifest}
    return tables, manifest


def training_snapshot_hash(
    snapshot: Mapping[str, Any], *, event: Mapping[str, Any], training_cutoff: Any
) -> str:
    """Hash the actual historical records used, after leakage validation."""

    tables, _ = _normalized_training(
        snapshot, event=event, training_cutoff=training_cutoff
    )
    return digest(tables)


def _normalize_model_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("model_manifest must be a mapping")
    required = {"code_hash", "parameters", "feature_columns", "library_versions"}
    if not required.issubset(value):
        raise ValueError("model_manifest is missing reproducibility fields")
    code_hash = value["code_hash"]
    if not isinstance(code_hash, str) or not HEX_DIGEST.fullmatch(code_hash):
        raise ValueError("model_manifest code_hash must be a SHA-256 digest")
    parameters = _json_safe(value["parameters"], missing_as_null=False)
    libraries = _json_safe(value["library_versions"], missing_as_null=False)
    columns = value["feature_columns"]
    if (
        not isinstance(parameters, Mapping)
        or not isinstance(libraries, Mapping) or not libraries
        or not isinstance(columns, Sequence) or isinstance(columns, (str, bytes))
        or not columns
        or any(not isinstance(column, str) or not column for column in columns)
        or len(columns) != len(set(columns))
    ):
        raise ValueError("model_manifest reproducibility fields are invalid")
    normalized = _json_safe(value, missing_as_null=False)
    normalized["feature_columns"] = list(columns)
    return normalized


def _eligible_driver_ids(event: Mapping[str, Any]) -> list[str]:
    roster = event.get("roster")
    if not isinstance(roster, list):
        raise ValueError("event requires a canonical roster")
    try:
        normalized = [validate_roster_record(record) for record in roster]
    except EventContractError as exc:
        raise ValueError(f"invalid event roster: {exc}") from exc
    return sorted(
        record["driver_id"] for record in normalized
        if record["expected"] and record["eligible"]
    )


def _qualifying_provenance(event: Mapping[str, Any], qualifying: Any) -> tuple[str, dict]:
    from src.pipeline.qualifying import AcceptedQualifying

    if not isinstance(qualifying, AcceptedQualifying):
        raise TypeError("actual mode requires AcceptedQualifying provenance")
    source_version = qualifying.source_version
    if not isinstance(source_version, str) or not HEX_DIGEST.fullmatch(source_version):
        raise ValueError("accepted qualifying source version is invalid")
    rows = _canonical_driver_rows(
        qualifying.rows, name="accepted qualifying", missing_as_null=True
    )
    season, round_number = _event_identity(event)
    expected = _eligible_driver_ids(event)
    eligible_rows = [row for row in rows if row.get("eligible") is True]
    if [row["driver_id"] for row in eligible_rows] != expected:
        raise ValueError("accepted qualifying does not match the eligible event roster")
    manifest_rows = []
    for row in eligible_rows:
        if (int(row.get("season", -1)), int(row.get("round", -1))) != (
            season, round_number
        ):
            raise ValueError("accepted qualifying has the wrong event identity")
        manifest_rows.append({
            "driver_id": row["driver_id"],
            "position": row.get("quali_position"),
            "gap": row.get("quali_time_gap_to_pole"),
            "modelPosition": row.get("model_position"),
            "modelGap": row.get("model_quali_time_gap_to_pole"),
        })
    manifest = {
        "rows": manifest_rows,
        "imputation_policy": _json_safe(
            qualifying.imputation_policy, missing_as_null=False
        ),
    }
    return source_version, manifest


def _input_payload(provenance: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "season", "round", "mode", "model_version", "training_cutoff",
        "training_data_hash", "training_manifest", "qualifying_source_version",
        "qualifying_manifest", "feature_input_hash", "feature_policy_version",
        "probability_policy_version", "event_schedule_hash", "roster_version",
    )
    return {key: provenance.get(key) for key in keys}


def build_provenance(
    event: Mapping[str, Any], *, mode: str, training_cutoff: Any,
    training_snapshot: Mapping[str, Any], model_manifest: Mapping[str, Any],
    feature_inputs: Any, qualifying: Any = None,
) -> dict[str, Any]:
    """Build pre-model input provenance from exact caller-supplied snapshots."""

    if mode not in MODES:
        raise ValueError(f"unsupported prediction mode: {mode!r}")
    season, round_number = _event_identity(event)
    cutoff_text = _utc_text(training_cutoff, field="training_cutoff")
    if parse_utc(cutoff_text) > parse_utc(event["race_start_at"]):
        raise ValueError("training cutoff cannot be later than the target event")
    normalized_training, training_manifest = _normalized_training(
        training_snapshot, event=event, training_cutoff=cutoff_text
    )
    manifest = _normalize_model_manifest(model_manifest)
    feature_rows = _canonical_driver_rows(
        feature_inputs, name="feature inputs", missing_as_null=False
    )
    expected = _eligible_driver_ids(event)
    if [row["driver_id"] for row in feature_rows] != expected:
        raise ValueError("feature inputs do not match the eligible event roster")
    if len(feature_rows) < 3:
        raise ValueError("at least three eligible feature rows are required")

    source_version = None
    qualifying_manifest = None
    if mode == "actual_qualifying":
        source_version, qualifying_manifest = _qualifying_provenance(event, qualifying)
        by_driver = {row["driver_id"]: row for row in qualifying_manifest["rows"]}
        for row in feature_rows:
            accepted = by_driver[row["driver_id"]]
            if "grid_position" in row and row["grid_position"] != accepted["modelPosition"]:
                raise ValueError("actual feature positions differ from accepted qualifying")
            if (
                "quali_time_gap_to_pole" in row
                and row["quali_time_gap_to_pole"] != accepted["modelGap"]
            ):
                raise ValueError("actual feature gaps differ from accepted qualifying")
    elif qualifying is not None:
        raise ValueError("predicted mode must not include qualifying provenance")

    provenance = {
        "season": season,
        "round": round_number,
        "mode": mode,
        "model_manifest": manifest,
        "model_version": digest(manifest),
        "training_cutoff": cutoff_text,
        "training_data_hash": digest(normalized_training),
        "training_manifest": training_manifest,
        "qualifying_source_version": source_version,
        "qualifying_manifest": qualifying_manifest,
        "feature_input_hash": digest(feature_rows),
        "feature_policy_version": FEATURE_POLICY_VERSION,
        "probability_policy_version": PROBABILITY_POLICY_VERSION,
        "event_schedule_hash": schedule_hash(event),
        "roster_version": roster_version(event["roster"]),
    }
    provenance["input_hash"] = digest(_input_payload(provenance))
    return provenance


def build_prediction(
    event: Mapping[str, Any], *, forecast: Mapping[str, Any], generated_at: Any,
    provenance: Mapping[str, Any], previous_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one versioned candidate, reusing an unchanged validated candidate."""

    season, round_number = _event_identity(event)
    if not isinstance(provenance, Mapping):
        raise TypeError("provenance must be a mapping")
    if previous_candidate is not None:
        if previous_candidate.get("input_hash") == provenance.get("input_hash"):
            validate_prediction(previous_candidate, event)
            return previous_candidate
    payload = {
        "schema_version": SCHEMA_VERSION,
        "season": season,
        "round": round_number,
        "generated_at": _utc_text(generated_at, field="generated_at"),
        **copy.deepcopy(dict(provenance)),
        "forecast": copy.deepcopy(dict(forecast)),
    }
    payload["prediction_id"] = digest(payload, semantic_prediction=True)
    validate_prediction(payload, event)
    return payload


def _require_digest(value: Any, field: str) -> None:
    if not isinstance(value, str) or not HEX_DIGEST.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 digest")


def _validate_training_manifest(
    manifest: Any, *, season: int, round_number: int, cutoff: datetime
) -> None:
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("tables"), Mapping):
        raise ValueError("training manifest is malformed")
    counted = 0
    for table in manifest["tables"].values():
        if not isinstance(table, Mapping) or not isinstance(table.get("events"), list):
            raise ValueError("training manifest is malformed")
        event_count = 0
        for event in table["events"]:
            event_season = _integer(event.get("season"), field="training season")
            event_round = _integer(event.get("round"), field="training round")
            count = _integer(event.get("row_count"), field="training row_count")
            if (event_season, event_round) >= (season, round_number):
                raise ValueError("training manifest contains target or later rows")
            for key in ("min_date", "max_date"):
                if event.get(key) is not None and parse_utc(event[key]) >= cutoff:
                    raise ValueError("training manifest contains rows at or after cutoff")
            event_count += count
        if event_count != table.get("row_count"):
            raise ValueError("training manifest row counts are inconsistent")
        counted += event_count
    if counted <= 0 or counted != manifest.get("row_count"):
        raise ValueError("training manifest row counts are inconsistent")


def _finite_number(value: Any, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("forecast numeric value is invalid")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("forecast numeric value must be finite")
    return result


def _positive_position(value: Any, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) <= 0:
        raise ValueError("qualifying positions must be positive integers")
    return int(value)


def _validate_driver_list(value: Any, *, name: str, expected: list[str]) -> list[dict]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    rows = _canonical_driver_rows(value, name=name, missing_as_null=True)
    if [row["driver_id"] for row in rows] != expected:
        raise ValueError(f"{name} must contain one row per eligible entrant")
    return rows


def _validate_podium(value: Any, *, name: str, expected: list[str]) -> None:
    rows = _validate_driver_list(value, name=name, expected=expected)
    emitted = value
    probabilities = []
    ranks = []
    for row in emitted:
        try:
            probability = _finite_number(row.get("podiumProbability"))
        except ValueError as exc:
            raise ValueError("podium estimates must be finite") from exc
        if probability < 0 or probability > 1:
            raise ValueError("podium estimates must be within [0, 1]")
        probabilities.append(probability)
        ranks.append(_positive_position(row.get("rank")))
    if ranks != list(range(1, len(emitted) + 1)):
        raise ValueError("podium rank must match deterministic emitted order")
    if any(left < right for left, right in zip(probabilities, probabilities[1:])):
        raise ValueError("podium estimates must be in descending order")
    if not math.isclose(sum(probabilities), 3.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("podium estimates must sum to approximately three")


def _validate_qualifying(value: Any, *, name: str, expected: list[str], actual: bool) -> None:
    rows = _validate_driver_list(value, name=name, expected=expected)
    official_positions = []
    model_positions = []
    for row in rows:
        position = _positive_position(row.get("position"), nullable=actual)
        if position is not None:
            official_positions.append(position)
        gap = _finite_number(row.get("gap"), nullable=actual)
        if gap is not None and gap < 0:
            raise ValueError("qualifying gaps must be non-negative")
        if actual:
            model_position = _positive_position(row.get("modelPosition"))
            model_gap = _finite_number(row.get("modelGap"))
            if model_gap < 0:
                raise ValueError("model qualifying gaps must be non-negative")
            model_positions.append(model_position)
    if len(official_positions) != len(set(official_positions)):
        raise ValueError("qualifying positions must be unique")
    if actual and len(model_positions) != len(set(model_positions)):
        raise ValueError("model qualifying positions must be unique")


def validate_prediction(prediction: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    """Fail closed unless a candidate satisfies schema, provenance, and forecasts."""

    if not isinstance(prediction, Mapping):
        raise TypeError("prediction must be a mapping")
    season, round_number = _event_identity(event)
    if (
        prediction.get("schema_version") != SCHEMA_VERSION
        or prediction.get("season") != season
        or prediction.get("round") != round_number
    ):
        raise ValueError("prediction has the wrong event identity or schema")
    mode = prediction.get("mode")
    if mode not in MODES:
        raise ValueError("prediction mode is invalid")
    generated_text = _utc_text(prediction.get("generated_at"), field="generated_at")
    if mode == "predicted_qualifying" and parse_utc(generated_text) >= parse_utc(
        event["qualifying_start_at"]
    ):
        raise ValueError("initial prediction must be generated before qualifying")
    cutoff_text = _utc_text(prediction.get("training_cutoff"), field="training_cutoff")
    cutoff = parse_utc(cutoff_text)
    if cutoff > parse_utc(event["race_start_at"]):
        raise ValueError("training cutoff cannot be later than the target event")
    for field in (
        "prediction_id", "model_version", "training_data_hash", "input_hash",
        "feature_input_hash", "event_schedule_hash", "roster_version",
    ):
        _require_digest(prediction.get(field), field)
    if prediction["event_schedule_hash"] != schedule_hash(event):
        raise ValueError("event schedule hash does not match the event")
    if prediction["roster_version"] != roster_version(event["roster"]):
        raise ValueError("roster version does not match the event")
    manifest = _normalize_model_manifest(prediction.get("model_manifest"))
    if prediction["model_version"] != digest(manifest):
        raise ValueError("model version does not match its manifest")
    if prediction.get("feature_policy_version") != FEATURE_POLICY_VERSION:
        raise ValueError("feature policy version is invalid")
    if prediction.get("probability_policy_version") != PROBABILITY_POLICY_VERSION:
        raise ValueError("probability policy version is invalid")
    _validate_training_manifest(
        prediction.get("training_manifest"), season=season,
        round_number=round_number, cutoff=cutoff,
    )
    source_version = prediction.get("qualifying_source_version")
    if mode == "actual_qualifying":
        if source_version is None:
            raise ValueError("actual prediction requires an accepted source version")
        _require_digest(source_version, "qualifying source version")
        if not isinstance(prediction.get("qualifying_manifest"), Mapping):
            raise ValueError("actual prediction requires qualifying provenance")
    elif source_version is not None or prediction.get("qualifying_manifest") is not None:
        raise ValueError("predicted mode cannot contain actual qualifying provenance")
    if prediction.get("input_hash") != digest(_input_payload(prediction)):
        raise ValueError("input hash does not match prediction provenance")

    forecast = prediction.get("forecast")
    if not isinstance(forecast, Mapping) or forecast.get("error") is not None:
        raise ValueError("forecast output is malformed or empty")
    race = forecast.get("race")
    if (
        not isinstance(race, Mapping)
        or race.get("season") != season or race.get("round") != round_number
        or forecast.get("mode") != mode
    ):
        raise ValueError("forecast has the wrong event identity or mode")
    expected = _eligible_driver_ids(event)
    if mode == "predicted_qualifying":
        if forecast.get("hasRealGrid") not in (None, False):
            raise ValueError("predicted forecast cannot claim a real grid")
        if forecast.get("realQualifying") is not None or forecast.get("realGridPodium") is not None:
            raise ValueError("predicted forecast cannot contain actual labels")
        _validate_qualifying(
            forecast.get("predictedQualifying"), name="predictedQualifying",
            expected=expected, actual=False,
        )
        _validate_podium(
            forecast.get("preQualifyingPodium"), name="preQualifyingPodium",
            expected=expected,
        )
    else:
        if forecast.get("hasRealGrid") is not True:
            raise ValueError("actual forecast must identify its accepted real grid")
        if forecast.get("predictedQualifying") != [] or forecast.get("preQualifyingPodium") != []:
            raise ValueError("actual forecast cannot regenerate the initial forecast")
        _validate_qualifying(
            forecast.get("realQualifying"), name="realQualifying",
            expected=expected, actual=True,
        )
        _validate_podium(
            forecast.get("realGridPodium"), name="realGridPodium", expected=expected
        )
        source_rows = {
            row["driver_id"]: row
            for row in prediction["qualifying_manifest"].get("rows", [])
        }
        for row in forecast["realQualifying"]:
            accepted = source_rows.get(row.get("driver_id"))
            if accepted is None or any(
                row.get(forecast_key) != accepted.get(source_key)
                for forecast_key, source_key in (
                    ("position", "position"), ("gap", "gap"),
                    ("modelPosition", "modelPosition"), ("modelGap", "modelGap"),
                )
            ):
                raise ValueError("actual forecast differs from accepted qualifying values")

    if prediction.get("prediction_id") != digest(prediction, semantic_prediction=True):
        raise ValueError("prediction_id does not match semantic content")


def write_immutable(path: str | Path, payload: Any) -> None:
    """Create canonical JSON exclusively; identical existing bytes are a no-op."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_bytes(payload) + b"\n"
    try:
        with target.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError as exc:
        if target.read_bytes() == encoded:
            return
        raise ArtifactCollisionError(f"immutable collision at {target}") from exc


def archive_prediction(
    root: str | Path, event: Mapping[str, Any], prediction: Mapping[str, Any]
) -> Path:
    """Store one immutable version and create the initial forecast at most once."""

    validate_prediction(prediction, event)
    season, round_number = _event_identity(event)
    event_dir = Path(root) / "prediction_snapshots" / f"{season}-{round_number}"
    event_path = event_dir / "event.json"
    event_dir.mkdir(parents=True, exist_ok=True)
    event_bytes = canonical_bytes(_json_safe(event, missing_as_null=True)) + b"\n"
    if not event_path.exists() or event_path.read_bytes() != event_bytes:
        descriptor, temp_name = tempfile.mkstemp(
            dir=event_dir, prefix=".event-", suffix=".json"
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(event_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, event_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    write_immutable(
        event_dir / "versions" / f"{prediction['prediction_id']}.json", prediction
    )
    initial_path = event_dir / "initial.json"
    if prediction["mode"] == "predicted_qualifying" and not initial_path.exists():
        write_immutable(initial_path, prediction)
    return event_dir


def load_prediction_for_input(
    root: str | Path, event: Mapping[str, Any], input_hash: str
) -> dict[str, Any] | None:
    """Find a validated durable candidate for pre-model crash/restart reuse."""

    _require_digest(input_hash, "input_hash")
    season, round_number = _event_identity(event)
    versions = (
        Path(root) / "prediction_snapshots" / f"{season}-{round_number}" / "versions"
    )
    matches = []
    for path in sorted(versions.glob("*.json")) if versions.exists() else ():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"stored prediction is unreadable: {path}") from exc
        if candidate.get("input_hash") != input_hash:
            continue
        validate_prediction(candidate, event)
        matches.append(candidate)
    if len(matches) > 1:
        raise ArtifactCollisionError(
            "multiple immutable prediction versions share the same input_hash"
        )
    return matches[0] if matches else None
