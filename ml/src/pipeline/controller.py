"""Compose the qualifying state machine without hiding external side effects.

The production adapter lives in :mod:`ml.scripts.check_qualifying`; this module keeps
the order of operations testable with injected callables.  In particular, no model
call is reachable until a due fetch has passed exact-event validation, changed its
semantic source version, and left enough publication time.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from src.model.forecast import (
    _event_cutoff,
    _event_identity,
    _forecast_prepared,
    _prepare_forecast_inputs,
)
from src.model.retrain import train_podium_live
from src.pipeline.events import event_windows, parse_utc
from src.pipeline.state import (
    ACTION_CHECK_QUALIFYING,
    ACTION_FINAL_CHECK,
    ACTION_FREEZE,
    action_decision,
    complete_qualifying_check,
    freeze_status,
    mark_actual_publication_confirmed,
    mark_final_check_attempted,
    record_schedule_refresh,
    reconcile_schedule,
    schedule_refresh_due,
    start_qualifying_check,
)


def _noop_status(_status: Mapping[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class PipelineDependencies:
    """Every impure controller operation, supplied by the caller.

    The signatures are intentionally small so the GitHub job, dry-run adapter, and
    fixture tests all exercise the same state transitions.
    """

    fetch_qualifying: Callable[[Mapping[str, Any]], Any]
    validate_qualifying: Callable[[Mapping[str, Any], Any], Any]
    generate_prediction: Callable[[Mapping[str, Any], Any, str], Mapping[str, Any]]
    validate_prediction: Callable[[Mapping[str, Any], Mapping[str, Any]], None]
    stage_prediction: Callable[
        [Mapping[str, Any], Mapping[str, Any], Any, Mapping[str, Any]], Any
    ]
    publish_prediction: Callable[[Any], Mapping[str, Any]]
    refresh_schedule: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None
    freeze: Callable[
        [Mapping[str, Any], Mapping[str, Any], datetime], Any
    ] | None = None
    persist_status: Callable[[Mapping[str, Any]], None] = _noop_status


@dataclass(frozen=True)
class ControllerResult:
    outcome: str
    event: dict[str, Any]
    status: dict[str, Any]
    receipt: dict[str, Any] | None = None


def _reason(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return str(code) if isinstance(code, str) and code else type(exc).__name__


def _finish(
    outcome: str,
    event: Mapping[str, Any],
    status: Mapping[str, Any],
    dependencies: PipelineDependencies,
    *,
    receipt: Mapping[str, Any] | None = None,
) -> ControllerResult:
    saved = dict(status)
    dependencies.persist_status(saved)
    return ControllerResult(
        outcome=outcome,
        event=dict(event),
        status=saved,
        receipt=None if receipt is None else dict(receipt),
    )


def run_due_work(
    event: Mapping[str, Any],
    status: Mapping[str, Any],
    *,
    clock: Callable[[], datetime],
    dependencies: PipelineDependencies,
) -> ControllerResult:
    """Run at most one due qualifying operation and return its persisted outcome.

    Schedule refresh remains independent of qualifying polling.  Fetch/validation
    failures are recoverable state, while publication and freeze adapters may raise
    so an Actions job cannot report success for uncertain delivery.
    """

    current_event = dict(event)
    current_status = dict(status)
    evaluated_at = parse_utc(clock())

    if (
        dependencies.refresh_schedule is not None
        and schedule_refresh_due(current_event, current_status, evaluated_at)
    ):
        try:
            current_event = dict(dependencies.refresh_schedule(current_event))
            current_status = reconcile_schedule(current_status, current_event)
            current_status = record_schedule_refresh(current_status, evaluated_at)
        except Exception as exc:
            current_status["last_error"] = f"schedule_refresh:{_reason(exc)}"
            return _finish(
                "schedule_refresh_failed", current_event, current_status, dependencies
            )

    decision = action_decision(current_event, current_status, evaluated_at)
    if decision.action == ACTION_FREEZE:
        selection = (
            dependencies.freeze(current_event, current_status, evaluated_at)
            if dependencies.freeze is not None
            else current_status.get("freeze_selection")
        )
        frozen = freeze_status(
            current_status,
            evaluated_at,
            reason=decision.reason or "cutoff_reached",
            selection=selection,
        )
        return _finish("frozen", current_event, frozen, dependencies)
    if decision.action not in {ACTION_CHECK_QUALIFYING, ACTION_FINAL_CHECK}:
        current_status["validation_reason"] = decision.reason
        return _finish(decision.action, current_event, current_status, dependencies)

    started_at = parse_utc(clock())
    current_status = start_qualifying_check(current_status, started_at)
    if decision.action == ACTION_FINAL_CHECK:
        current_status = mark_final_check_attempted(current_status, started_at)
    # Persist the start marker before network/model work so a crashed job does not
    # immediately retry and final verification remains once-only.
    dependencies.persist_status(dict(current_status))

    try:
        fetched = dependencies.fetch_qualifying(current_event)
        accepted = dependencies.validate_qualifying(current_event, fetched)
        source_version = getattr(accepted, "source_version", None)
        if not isinstance(source_version, str) or not source_version:
            raise ValueError("validated qualifying requires a semantic source version")
    except Exception as exc:
        completed_at = parse_utc(clock())
        failed = complete_qualifying_check(
            current_status,
            completed_at,
            success=False,
            error=_reason(exc),
            event=current_event,
        )
        failed["validation_reason"] = _reason(exc)
        return _finish("qualifying_unavailable", current_event, failed, dependencies)

    if (
        current_status.get("qualifying_source_version") == source_version
        and current_status.get("actual_publication_confirmed") is True
    ):
        unchanged = complete_qualifying_check(
            current_status,
            parse_utc(clock()),
            success=True,
            event=current_event,
        )
        unchanged["validation_reason"] = "unchanged_qualifying"
        return _finish("unchanged", current_event, unchanged, dependencies)

    before_generation = parse_utc(clock())
    if before_generation >= event_windows(current_event)["latest_generation_start_at"]:
        late = complete_qualifying_check(
            current_status,
            before_generation,
            success=False,
            error="insufficient_publication_window",
            event=current_event,
        )
        late["validation_reason"] = "insufficient_publication_window"
        return _finish("too_late", current_event, late, dependencies)

    prediction = dependencies.generate_prediction(
        current_event, accepted, source_version
    )
    dependencies.validate_prediction(prediction, current_event)

    before_publication = parse_utc(clock())
    if before_publication >= event_windows(current_event)["cutoff_at"]:
        late = complete_qualifying_check(
            current_status,
            before_publication,
            success=False,
            error="publication_deadline_reached",
            event=current_event,
        )
        late["validation_reason"] = "publication_deadline_reached"
        return _finish("too_late", current_event, late, dependencies)

    candidate = dependencies.stage_prediction(
        current_event, prediction, accepted, current_status
    )
    receipt = dependencies.publish_prediction(candidate)
    confirmed_at = parse_utc(receipt["published_at"])
    published = complete_qualifying_check(
        current_status,
        confirmed_at,
        success=True,
        event=current_event,
    )
    published = mark_actual_publication_confirmed(published, confirmed_at)
    published["qualifying_source_version"] = source_version
    published["current_prediction_id"] = prediction.get("prediction_id")
    published["validation_reason"] = "actual_qualifying_published"
    return _finish(
        "published", current_event, published, dependencies, receipt=receipt
    )


def _same_successful_context(previous, *, event, cutoff, qualifying, input_hash):
    if not isinstance(previous, Mapping):
        return False
    season, round_number = _event_identity(event)
    return (
        previous.get("status") == "success"
        and previous.get("mode") == "actual_qualifying"
        and previous.get("event") == {"season": season, "round": round_number}
        and previous.get("training_cutoff") == cutoff.isoformat()
        and previous.get("qualifying_source_version") == qualifying.source_version
        and previous.get("input_hash") == input_hash
        and isinstance(previous.get("forecast"), Mapping)
    )


def generate_actual_candidate(
    event, *, history, entries, qualifying, input_hash, previous_candidate=None
):
    """Validate inputs, reuse an unchanged success, or fit Stage 2 once.

    The supplied hash is intentionally not generated or interpreted here. Task 5 owns
    canonical hashing and immutable artifact metadata.
    """

    if not isinstance(input_hash, str) or not input_hash:
        raise ValueError("input_hash must be a non-empty caller-supplied value")
    prepared, features, actual_rows = _prepare_forecast_inputs(
        event, mode="actual_qualifying", history=history, entries=entries,
        qualifying=qualifying,
    )
    cutoff = _event_cutoff(event)
    if _same_successful_context(
        previous_candidate, event=event, cutoff=cutoff,
        qualifying=qualifying, input_hash=input_hash,
    ):
        return previous_candidate

    season, round_number = _event_identity(event)
    podium_model = train_podium_live(
        cutoff,
        results=prepared["results"], qualifying=prepared["qualifying"],
        target_season=season, target_round=round_number,
    )
    result = _forecast_prepared(
        event, mode="actual_qualifying", features=features,
        models={"podium": podium_model}, actual_rows=actual_rows,
    )
    return {
        "status": "success",
        "mode": "actual_qualifying",
        "event": {"season": season, "round": round_number},
        "training_cutoff": cutoff.isoformat(),
        "qualifying_source_version": qualifying.source_version,
        "input_hash": input_hash,
        "forecast": result,
    }
