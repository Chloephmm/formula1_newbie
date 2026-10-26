"""Canonical event timing and roster metadata.

This module deliberately uses only the Python standard library so a controller can
validate an event during a cheap planning step, before importing pandas or any model
dependencies.

Roster semantics are intentionally small and explicit:

``expected``
    A qualifying result row is required for this driver.
``eligible``
    The driver may be included in the podium forecast.
``participation``
    One of ``provisional``, ``confirmed``, ``confirmed_substitute``, ``withdrawn``,
    or ``excluded``. Withdrawn/excluded records must be neither expected nor eligible.
``exception``
    Optional evidence-backed metadata for a ``confirmed_substitute`` or a
    ``no_qualifying_lap``. The latter can explicitly allow a later validator to use a
    model position; this module does not implement that validator.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


UTC = timezone.utc
PARTICIPATION_STATES = frozenset(
    {"provisional", "confirmed", "confirmed_substitute", "withdrawn", "excluded"}
)
EXCEPTION_KINDS = frozenset({"confirmed_substitute", "no_qualifying_lap"})
SCHEDULE_OVERRIDE_FIELDS = frozenset(
    {"qualifying_start_at", "qualifying_end_observed_at", "race_start_at"}
)
PARTICIPANT_OVERRIDE_FIELDS = frozenset(
    {
        "code",
        "driver_name",
        "constructor_id",
        "constructor_name",
        "number",
        "eligible",
        "expected",
        "participation",
        "exception",
    }
)


class EventContractError(ValueError):
    """An event cannot be planned without guessing.

    ``code`` is stable for controller branching; the message is for operators.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        # Compatibility for callers that prefer a more verbose attribute name.
        self.reason_code = code


def parse_utc(value: str | datetime) -> datetime:
    """Parse an aware timestamp and normalize it to UTC.

    Naive timestamps are rejected because assuming a circuit or host timezone could
    silently move an event window.
    """

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise EventContractError("invalid_timestamp", "timestamp cannot be empty")
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EventContractError(
                "invalid_timestamp", f"invalid ISO timestamp: {value!r}"
            ) from exc
    else:
        raise EventContractError(
            "invalid_timestamp", f"timestamp must be text or datetime, got {type(value).__name__}"
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventContractError(
            "invalid_timestamp", f"timestamp must include a timezone: {value!r}"
        )
    return parsed.astimezone(UTC)


def _format_utc(value: str | datetime) -> str:
    return parse_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _required_text(mapping: Mapping[str, Any], key: str, code: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EventContractError(code, f"{key} requires non-empty evidence")
    return value.strip()


def _evidence_url(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise EventContractError(code, "source_url must be an http(s) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EventContractError(code, "source_url must be an http(s) URL")
    return value


def event_windows(event: Mapping[str, Any]) -> dict[str, Any]:
    """Compute UTC timing gates from explicit target-event timestamps."""

    if not event.get("qualifying_start_at") or not event.get("race_start_at"):
        raise EventContractError(
            "missing_schedule_evidence",
            "target event requires qualifying_start_at and race_start_at",
        )
    qualifying_start = parse_utc(event["qualifying_start_at"])
    race_start = parse_utc(event["race_start_at"])
    observed = event.get("qualifying_end_observed_at")
    if observed:
        qualifying_end = parse_utc(observed)
        estimated = False
    else:
        qualifying_end = qualifying_start + timedelta(minutes=90)
        estimated = True

    cutoff = race_start - timedelta(hours=2)
    first_check = qualifying_end + timedelta(hours=5)
    if not qualifying_start < qualifying_end < race_start or first_check >= cutoff:
        raise EventContractError(
            "inconsistent_event_times",
            "qualifying and race timestamps do not form a viable event window",
        )

    return {
        "qualifying_end_at": qualifying_end,
        "end_time_estimated": estimated,
        "first_check_at": first_check,
        "cutoff_at": cutoff,
        "final_check_at": cutoff - timedelta(minutes=45),
        "latest_generation_start_at": cutoff - timedelta(minutes=15),
    }


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def schedule_hash(event: Mapping[str, Any]) -> str:
    """Hash semantic schedule values, excluding retrieval/audit timestamps."""

    windows = event_windows(event)
    payload = {
        "season": event.get("season"),
        "round": event.get("round"),
        "race_name": event.get("race_name"),
        "circuit_id": event.get("circuit_id"),
        "qualifying_start_at": _format_utc(event["qualifying_start_at"]),
        "qualifying_end_at": _format_utc(windows["qualifying_end_at"]),
        "qualifying_end_observed_at": (
            _format_utc(event["qualifying_end_observed_at"])
            if event.get("qualifying_end_observed_at")
            else None
        ),
        "race_start_at": _format_utc(event["race_start_at"]),
    }
    return _digest(payload)


def _validate_exception(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise EventContractError("invalid_roster", "exception must be an object")
    allowed = {
        "kind",
        "reason",
        "source_url",
        "observed_at",
        "replaces_driver_id",
        "allow_model_position",
    }
    if set(value) - allowed:
        raise EventContractError("invalid_roster", "exception has unsupported fields")
    kind = value.get("kind")
    if kind not in EXCEPTION_KINDS:
        raise EventContractError("invalid_roster", "unsupported roster exception kind")
    reason = _required_text(value, "reason", "missing_entry_evidence")
    source_url = _evidence_url(value.get("source_url"), "missing_entry_evidence")
    observed_at = _format_utc(value.get("observed_at"))
    allow_model_position = value.get("allow_model_position")
    if not isinstance(allow_model_position, bool):
        raise EventContractError(
            "invalid_roster", "exception allow_model_position must be boolean"
        )
    replaces_driver_id = value.get("replaces_driver_id")
    if replaces_driver_id is not None and (
        not isinstance(replaces_driver_id, str) or not replaces_driver_id.strip()
    ):
        raise EventContractError("invalid_roster", "invalid replaces_driver_id")
    if kind == "confirmed_substitute" and not replaces_driver_id:
        raise EventContractError(
            "invalid_roster", "confirmed substitute must identify the replaced driver"
        )
    if kind == "no_qualifying_lap" and not allow_model_position:
        raise EventContractError(
            "invalid_roster", "no-lap exception must explicitly allow model position"
        )
    return {
        "kind": kind,
        "reason": reason,
        "source_url": source_url,
        "observed_at": observed_at,
        "replaces_driver_id": replaces_driver_id,
        "allow_model_position": allow_model_position,
    }


def _validate_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EventContractError(
            "missing_entry_evidence", "roster record requires provenance"
        )
    source = _required_text(value, "source", "missing_entry_evidence")
    source_url = _evidence_url(value.get("source_url"), "missing_entry_evidence")
    if value.get("observed_at") is None:
        raise EventContractError(
            "missing_entry_evidence", "provenance requires observed_at"
        )
    observed_at = _format_utc(value["observed_at"])
    season = value.get("season")
    round_number = value.get("round")
    if source == "previous_completed_race" and (
        not isinstance(season, int) or not isinstance(round_number, int)
    ):
        raise EventContractError(
            "missing_entry_evidence",
            "previous_completed_race provenance requires season and round",
        )
    result = {
        "source": source,
        "source_url": source_url,
        "observed_at": observed_at,
    }
    if season is not None:
        result["season"] = season
    if round_number is not None:
        result["round"] = round_number
    return result

def validate_roster_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one canonical roster record."""

    if not isinstance(record, Mapping):
        raise EventContractError("invalid_roster", "roster record must be an object")
    driver_id = _required_text(record, "driver_id", "invalid_roster")
    driver_name = _required_text(record, "driver_name", "invalid_roster")
    constructor_id = _required_text(record, "constructor_id", "invalid_roster")
    constructor_name = _required_text(record, "constructor_name", "invalid_roster")
    code = record.get("code")
    number = record.get("number")
    if code is not None and not isinstance(code, str):
        raise EventContractError("invalid_roster", "code must be text or null")
    if number is not None and not isinstance(number, (str, int)):
        raise EventContractError("invalid_roster", "number must be text, integer, or null")
    expected = record.get("expected")
    eligible = record.get("eligible")
    if not isinstance(expected, bool) or not isinstance(eligible, bool):
        raise EventContractError(
            "invalid_roster", "expected and eligible must be explicit booleans"
        )
    participation = record.get("participation")
    if participation not in PARTICIPATION_STATES:
        raise EventContractError("invalid_roster", "unsupported participation state")
    if participation in {"withdrawn", "excluded"}:
        coherent = not expected and not eligible
    else:
        coherent = expected and eligible
    if not coherent:
        raise EventContractError(
            "invalid_roster",
            f"{participation} participation contradicts expected/eligible flags",
        )
    exception = _validate_exception(record.get("exception"))
    if participation == "confirmed_substitute" and (
        not exception or exception["kind"] != "confirmed_substitute"
    ):
        raise EventContractError(
            "invalid_roster", "confirmed_substitute requires its matching exception"
        )
    provenance = _validate_provenance(record.get("provenance"))
    normalized = {
        "driver_id": driver_id,
        "code": code,
        "driver_name": driver_name,
        "constructor_id": constructor_id,
        "constructor_name": constructor_name,
        "number": str(number) if number is not None else None,
        "eligible": eligible,
        "expected": expected,
        "participation": participation,
        "exception": exception,
        "provenance": provenance,
    }
    if record.get("override_provenance") is not None:
        normalized["override_provenance"] = _validate_provenance(
            record["override_provenance"]
        )
    return normalized


def roster_version(roster: Iterable[Mapping[str, Any]]) -> str:
    """Hash roster semantics independent of ordering and audit-only timestamps."""

    normalized = [validate_roster_record(record) for record in roster]
    driver_ids = [record["driver_id"] for record in normalized]
    if len(driver_ids) != len(set(driver_ids)):
        raise EventContractError("invalid_roster", "duplicate driver_id in roster")
    semantic = []
    for record in normalized:
        exception = record["exception"]
        semantic.append(
            {
                key: record[key]
                for key in (
                    "driver_id",
                    "code",
                    "driver_name",
                    "constructor_id",
                    "constructor_name",
                    "number",
                    "eligible",
                    "expected",
                    "participation",
                )
            }
            | {
                "exception": (
                    {
                        "kind": exception["kind"],
                        "replaces_driver_id": exception["replaces_driver_id"],
                        "allow_model_position": exception["allow_model_position"],
                    }
                    if exception
                    else None
                )
            }
        )
    semantic.sort(key=lambda item: item["driver_id"])
    return _digest(semantic)


def _normalize_roster_source(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _validate_provenance(value)
    provisional = value.get("provisional")
    if not isinstance(provisional, bool):
        raise EventContractError(
            "missing_entry_evidence", "roster_source requires provisional boolean"
        )
    normalized["provisional"] = provisional
    return normalized


def provisional_roster_from_results(
    rows: Iterable[Mapping[str, Any]],
    *,
    season: int,
    round_number: int,
    source_url: str,
    observed_at: str | datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a provisional baseline from caller-supplied previous-race results."""

    source = {
        "source": "previous_completed_race",
        "season": season,
        "round": round_number,
        "source_url": source_url,
        "observed_at": _format_utc(observed_at),
        "provisional": True,
    }
    normalized_source = _normalize_roster_source(source)
    roster = []
    for row in rows:
        roster.append(
            validate_roster_record(
                {
                    "driver_id": row.get("driver_id"),
                    "code": row.get("code"),
                    "driver_name": row.get("driver_name"),
                    "constructor_id": row.get("constructor_id"),
                    "constructor_name": row.get("constructor_name"),
                    "number": row.get("number"),
                    "eligible": True,
                    "expected": True,
                    "participation": "provisional",
                    "exception": None,
                    "provenance": normalized_source,
                }
            )
        )
    if not roster:
        raise EventContractError(
            "missing_entry_evidence", "previous completed race supplied no roster rows"
        )
    roster_version(roster)
    return sorted(roster, key=lambda item: item["driver_id"]), normalized_source


def build_event_metadata(
    schedule: Mapping[str, Any],
    roster: Iterable[Mapping[str, Any]],
    roster_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the JSON-native ``event.json`` contract from explicit evidence."""

    season = schedule.get("season")
    round_number = schedule.get("round")
    if not isinstance(season, int) or not isinstance(round_number, int):
        raise EventContractError(
            "missing_schedule_evidence", "schedule requires integer season and round"
        )
    race_name = _required_text(schedule, "race_name", "missing_schedule_evidence")
    circuit_id = _required_text(schedule, "circuit_id", "missing_schedule_evidence")
    schedule_source = _required_text(
        schedule, "schedule_source", "missing_schedule_evidence"
    )
    if schedule.get("schedule_updated_at") is None:
        raise EventContractError(
            "missing_schedule_evidence", "schedule requires schedule_updated_at"
        )
    windows = event_windows(schedule)
    normalized_roster = [validate_roster_record(record) for record in roster]
    if not normalized_roster:
        raise EventContractError("missing_entry_evidence", "roster cannot be empty")
    normalized_roster.sort(key=lambda item: item["driver_id"])
    version = roster_version(normalized_roster)
    normalized_roster_source = _normalize_roster_source(roster_source)
    event = {
        "season": season,
        "round": round_number,
        "race_name": race_name,
        "circuit_id": circuit_id,
        "qualifying_start_at": _format_utc(schedule["qualifying_start_at"]),
        "qualifying_end_at": _format_utc(windows["qualifying_end_at"]),
        "qualifying_end_observed_at": (
            _format_utc(schedule["qualifying_end_observed_at"])
            if schedule.get("qualifying_end_observed_at")
            else None
        ),
        "end_time_estimated": windows["end_time_estimated"],
        "race_start_at": _format_utc(schedule["race_start_at"]),
        "schedule_updated_at": _format_utc(schedule["schedule_updated_at"]),
        "schedule_source": schedule_source,
        "schedule_hash": schedule_hash(schedule),
        "roster": normalized_roster,
        "roster_source": normalized_roster_source,
        "roster_version": version,
    }
    return event


def write_event_json(path: str | os.PathLike[str], event: Mapping[str, Any]) -> None:
    """Atomically replace an event metadata file in its destination directory."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(event, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _override_evidence(override: Mapping[str, Any]) -> dict[str, Any]:
    if set(override) - {
        "reason",
        "source_url",
        "observed_at",
        "schedule",
        "participants",
    }:
        raise EventContractError("unsupported_override", "override has unsupported fields")
    reason = _required_text(override, "reason", "unsupported_override")
    if len(reason) < 10:
        raise EventContractError("unsupported_override", "override reason is too vague")
    source_url = _evidence_url(override.get("source_url"), "unsupported_override")
    if override.get("observed_at") is None:
        raise EventContractError("unsupported_override", "override requires observed_at")
    observed_at = _format_utc(override["observed_at"])
    if not override.get("schedule") and not override.get("participants"):
        raise EventContractError("unsupported_override", "override changes nothing")
    return {
        "source": "event_override",
        "reason": reason,
        "source_url": source_url,
        "observed_at": observed_at,
    }


def apply_event_override(
    event: Mapping[str, Any], overrides: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply only the exact ``season-round`` override and preserve its evidence."""

    result = copy.deepcopy(dict(event))
    key = f"{event.get('season')}-{event.get('round')}"
    override = overrides.get(key)
    if override is None:
        return result
    if not isinstance(override, Mapping):
        raise EventContractError("unsupported_override", "event override must be an object")
    evidence = _override_evidence(override)

    schedule_changes = override.get("schedule", {})
    if not isinstance(schedule_changes, Mapping) or (
        set(schedule_changes) - SCHEDULE_OVERRIDE_FIELDS
    ):
        raise EventContractError(
            "unsupported_override", "schedule override has unsupported fields"
        )
    for field, value in schedule_changes.items():
        if value is None:
            raise EventContractError(
                "unsupported_override", "schedule override cannot remove evidence"
            )
        result[field] = _format_utc(value)

    participant_changes = override.get("participants", {})
    if not isinstance(participant_changes, Mapping):
        raise EventContractError("unsupported_override", "participants must be an object")
    roster_by_id = {record["driver_id"]: record for record in result.get("roster", [])}
    override_provenance = {
        "source": "event_override",
        "source_url": evidence["source_url"],
        "observed_at": evidence["observed_at"],
    }
    for driver_id, patch in participant_changes.items():
        if not isinstance(driver_id, str) or not driver_id or not isinstance(patch, Mapping):
            raise EventContractError("unsupported_override", "invalid participant override")
        if set(patch) - PARTICIPANT_OVERRIDE_FIELDS:
            raise EventContractError(
                "unsupported_override", "participant override has unsupported fields"
            )
        current = copy.deepcopy(roster_by_id.get(driver_id, {"driver_id": driver_id}))
        current.update(patch)
        if "provenance" not in current:
            current["provenance"] = override_provenance
        current["override_provenance"] = override_provenance
        roster_by_id[driver_id] = validate_roster_record(current)

    result["roster"] = sorted(roster_by_id.values(), key=lambda item: item["driver_id"])
    result["roster_version"] = roster_version(result["roster"])
    if schedule_changes:
        windows = event_windows(result)
        result["qualifying_end_at"] = _format_utc(windows["qualifying_end_at"])
        result["end_time_estimated"] = windows["end_time_estimated"]
        result["schedule_hash"] = schedule_hash(result)
    result.setdefault("overrides", []).append(
        {
            "event_key": key,
            "reason": evidence["reason"],
            "source_url": evidence["source_url"],
            "observed_at": evidence["observed_at"],
            "schedule_fields": sorted(schedule_changes),
            "participant_ids": sorted(participant_changes),
        }
    )
    return result
