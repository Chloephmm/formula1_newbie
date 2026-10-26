"""Pure timing policy and small JSON persistence helpers for qualifying polling.

The controller owns I/O, feeds, and prediction generation. This module only
decides the next action and records JSON-native status. Canonical persisted fields
are ``last_schedule_refresh_at``, check start/completion/success timestamps,
``next_qualifying_check_at``, ``last_error``, ``actual_publication_confirmed``,
``final_check_attempted_at``, and the terminal ``frozen_at``/``freeze_selection``.
Controllers may also retain ``validation_reason`` and ``current_prediction_id`` in
the same object; this module preserves unknown JSON-compatible fields.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .events import EventContractError, event_windows, parse_utc


ACTION_WAIT = "wait"
ACTION_CHECK_QUALIFYING = "check_qualifying"
ACTION_FINAL_CHECK = "final_check"
ACTION_FREEZE = "freeze"
ACTION_UNAVAILABLE = "unavailable"
_ACTIONS = frozenset(
    {
        ACTION_WAIT,
        ACTION_CHECK_QUALIFYING,
        ACTION_FINAL_CHECK,
        ACTION_FREEZE,
        ACTION_UNAVAILABLE,
    }
)


@dataclass(frozen=True)
class ActionDecision:
    """A controller-facing policy result, including a stable optional reason."""

    action: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError(f"unsupported action: {self.action}")


def _utc_timestamp(value: Any, field: str) -> datetime:
    try:
        return parse_utc(value)
    except EventContractError as exc:
        raise EventContractError(exc.code, f"invalid {field}: {exc}") from exc


def _status_timestamp(status: Mapping[str, Any], field: str) -> datetime | None:
    value = status.get(field)
    if value is None:
        return None
    return _utc_timestamp(value, field)


def _format_timestamp(value: str | datetime) -> str:
    return _utc_timestamp(value, "timestamp").isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _is_frozen(status: Mapping[str, Any]) -> bool:
    """Recognize both current and deliberately explicit older freeze markers."""

    return bool(
        status.get("frozen_at")
        or status.get("freeze_marker")
        or status.get("final_state") in {"frozen", "unavailable"}
        or "frozen_prediction_id" in status
    )


def _policy_windows(event: Mapping[str, Any]) -> dict[str, Any]:
    """Use canonical windows, retaining the meaningful short-window wait state."""

    try:
        return event_windows(event)
    except EventContractError as exc:
        if exc.code != "inconsistent_event_times":
            raise
        qualifying_start = _utc_timestamp(
            event.get("qualifying_start_at"), "qualifying_start_at"
        )
        race_start = _utc_timestamp(event.get("race_start_at"), "race_start_at")
        observed_end = event.get("qualifying_end_observed_at")
        qualifying_end = (
            _utc_timestamp(observed_end, "qualifying_end_observed_at")
            if observed_end is not None
            else qualifying_start + timedelta(minutes=90)
        )
        if not qualifying_start < qualifying_end < race_start:
            raise exc
        cutoff = race_start - timedelta(hours=2)
        return {
            "qualifying_end_at": qualifying_end,
            "first_check_at": qualifying_end + timedelta(hours=5),
            "cutoff_at": cutoff,
            "final_check_at": cutoff - timedelta(minutes=45),
            "latest_generation_start_at": cutoff - timedelta(minutes=15),
        }


def action_decision(
    event: Mapping[str, Any], status: Mapping[str, Any], now: str | datetime
) -> ActionDecision:
    """Return the next qualifying-polling action without mutating inputs.

    Invalid schedule, status, or evaluation timestamps fail closed.  The caller can
    store/display ``reason`` without parsing exception text.
    """

    try:
        evaluated_at = _utc_timestamp(now, "now")
        if _is_frozen(status):
            return ActionDecision(ACTION_FREEZE, "already_frozen")
        windows = _policy_windows(event)
        if evaluated_at >= windows["cutoff_at"]:
            return ActionDecision(ACTION_FREEZE, "cutoff_reached")
        if windows["first_check_at"] >= windows["cutoff_at"]:
            return ActionDecision(ACTION_WAIT, "wait_exceeds_cutoff")
        if evaluated_at < windows["first_check_at"]:
            return ActionDecision(ACTION_WAIT, "before_first_check")
        final_attempt = _status_timestamp(status, "final_check_attempted_at")
        last_started = _status_timestamp(status, "last_qualifying_check_started_at")
        if final_attempt is not None:
            return ActionDecision(ACTION_WAIT, "final_check_already_attempted")
        if evaluated_at >= windows["latest_generation_start_at"]:
            return ActionDecision(ACTION_WAIT, "insufficient_publication_window")
        if evaluated_at >= windows["final_check_at"]:
            return ActionDecision(ACTION_FINAL_CHECK, "final_check_due")
        if status.get("actual_publication_confirmed") is True:
            return ActionDecision(ACTION_WAIT, "actual_publication_confirmed")

        if last_started is None or evaluated_at >= last_started + timedelta(hours=1):
            return ActionDecision(ACTION_CHECK_QUALIFYING, "ordinary_check_due")
        return ActionDecision(ACTION_WAIT, "ordinary_check_not_due")
    except EventContractError as exc:
        return ActionDecision(ACTION_UNAVAILABLE, exc.code)


def decide_action(
    event: Mapping[str, Any], status: Mapping[str, Any], now: str | datetime
) -> str:
    """Return only the canonical action for simple controller dispatch."""

    return action_decision(event, status, now).action


def schedule_refresh_due(
    event: Mapping[str, Any], status: Mapping[str, Any], now: str | datetime
) -> bool:
    """Decide schedule refresh cadence independently from qualifying availability.

    Refresh once per hour from 72 hours before qualifying until the cutoff, and
    daily outside that interval.  Bad timestamps fail closed rather than guessing.
    """

    try:
        evaluated_at = _utc_timestamp(now, "now")
        windows = _policy_windows(event)
        last_refresh = _status_timestamp(status, "last_schedule_refresh_at")
    except EventContractError:
        return False
    if last_refresh is None:
        return True
    qualifying_refresh_start = _utc_timestamp(
        event["qualifying_start_at"], "qualifying_start_at"
    ) - timedelta(hours=72)
    interval = (
        timedelta(hours=1)
        if qualifying_refresh_start <= evaluated_at < windows["cutoff_at"]
        else timedelta(days=1)
    )
    return evaluated_at >= last_refresh + interval


def reconcile_schedule(
    status: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    """Record a new schedule hash before freeze; flag it for review after freeze.

    Windows are always recalculated from the supplied current event, so this function
    intentionally never stores deadline snapshots that could become stale.
    """

    result = copy.deepcopy(dict(status))
    current_hash = event.get("schedule_hash")
    if not isinstance(current_hash, str) or not current_hash:
        return result
    prior_hash = result.get("schedule_hash")
    if prior_hash == current_hash:
        return result
    if _is_frozen(result):
        result["schedule_changed_after_freeze"] = True
        return result
    result["schedule_hash"] = current_hash
    if event.get("schedule_updated_at") is not None:
        result["schedule_updated_at"] = _format_timestamp(event["schedule_updated_at"])
    result.pop("schedule_changed_after_freeze", None)
    return result


def start_qualifying_check(
    status: Mapping[str, Any], started_at: str | datetime
) -> dict[str, Any]:
    """Record a check start. The controller must reevaluate before confirmation."""

    result = copy.deepcopy(dict(status))
    result["last_qualifying_check_started_at"] = _format_timestamp(started_at)
    return result


def complete_qualifying_check(
    status: Mapping[str, Any],
    completed_at: str | datetime,
    *,
    success: bool,
    error: str | None = None,
    event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record completion and an ordinary retry when it remains safe to advertise.

    Supplying the current event prevents a retry timestamp at or after the cutoff.
    """

    result = copy.deepcopy(dict(status))
    completed = _utc_timestamp(completed_at, "completed_at")
    result["last_qualifying_check_completed_at"] = _format_timestamp(completed)
    if success:
        result["last_successful_qualifying_check_at"] = _format_timestamp(completed)
        result["last_error"] = None
    else:
        result["last_error"] = error or "qualifying_check_failed"
    if (
        _is_frozen(result)
        or result.get("actual_publication_confirmed") is True
        or result.get("final_check_attempted_at") is not None
    ):
        result.pop("next_qualifying_check_at", None)
        return result
    last_started = _status_timestamp(result, "last_qualifying_check_started_at")
    next_check = (last_started or completed) + timedelta(hours=1)
    if event is not None and next_check >= _policy_windows(event)["cutoff_at"]:
        result.pop("next_qualifying_check_at", None)
        return result
    result["next_qualifying_check_at"] = _format_timestamp(next_check)
    return result


def mark_actual_publication_confirmed(
    status: Mapping[str, Any], confirmed_at: str | datetime
) -> dict[str, Any]:
    """Persist confirmed availability; the final-check policy still runs once."""

    result = copy.deepcopy(dict(status))
    result["actual_publication_confirmed"] = True
    result["actual_publication_confirmed_at"] = _format_timestamp(confirmed_at)
    result.pop("next_qualifying_check_at", None)
    return result


def mark_final_check_attempted(
    status: Mapping[str, Any], attempted_at: str | datetime
) -> dict[str, Any]:
    """Persist the once-only final-check marker."""

    result = copy.deepcopy(dict(status))
    result["final_check_attempted_at"] = _format_timestamp(attempted_at)
    result.pop("next_qualifying_check_at", None)
    return result


def freeze_status(
    status: Mapping[str, Any],
    frozen_at: str | datetime,
    *,
    reason: str,
    selection: Any = None,
) -> dict[str, Any]:
    """Create an explicit terminal marker, including an unavailable null selection."""

    result = copy.deepcopy(dict(status))
    if _is_frozen(result):
        result.pop("next_qualifying_check_at", None)
        return result
    result["frozen_at"] = _format_timestamp(frozen_at)
    result["freeze_reason"] = reason
    result["final_state"] = "frozen"
    result["freeze_selection"] = copy.deepcopy(selection)
    result.pop("next_qualifying_check_at", None)
    return result


def record_schedule_refresh(
    status: Mapping[str, Any], refreshed_at: str | datetime
) -> dict[str, Any]:
    """Record schedule polling separately from qualifying checks."""

    result = copy.deepcopy(dict(status))
    result["last_schedule_refresh_at"] = _format_timestamp(refreshed_at)
    return result


def read_status_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load an absent status file as the initial empty JSON object."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("status JSON must contain an object")
    return value


def write_status_json(
    path: str | os.PathLike[str], status: Mapping[str, Any]
) -> bool:
    """Atomically write changed JSON only, preserving bytes and mtime for idle ticks."""

    destination = Path(path)
    normalized = dict(status)
    encoded = json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        existing = json.loads(destination.read_text(encoding="utf-8"))
        existing_encoded = (
            json.dumps(existing, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        )
        if existing_encoded == encoded:
            return False
    except FileNotFoundError:
        pass
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
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        return True
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
