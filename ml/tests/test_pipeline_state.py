"""Persistent qualifying-polling state and time-gate policy."""
from __future__ import annotations

import time
from datetime import datetime, timezone


UTC = timezone.utc


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 23, hour, minute, tzinfo=UTC)


def _event(**updates):
    event = {
        "qualifying_start_at": "2026-10-23T10:00:00Z",
        "race_start_at": "2026-10-24T18:00:00Z",
        "schedule_hash": "schedule-a",
        "schedule_updated_at": "2026-10-01T00:00:00Z",
    }
    event.update(updates)
    return event


def test_waits_until_five_hours_after_qualifying_end():
    from src.pipeline.state import decide_action

    assert decide_action(_event(), {}, _at(16, 29)) == "wait"


def test_ordinary_qualifying_checks_retry_hourly_until_success():
    from src.pipeline.state import decide_action

    status = {"last_qualifying_check_started_at": "2026-10-23T16:30:00Z"}

    assert decide_action(_event(), {}, _at(16, 30)) == "check_qualifying"
    assert decide_action(_event(), status, _at(17, 29)) == "wait"
    assert decide_action(_event(), status, _at(17, 30)) == "check_qualifying"


def test_actual_publication_pauses_ordinary_retries_but_keeps_final_check():
    from src.pipeline.state import decide_action

    status = {"actual_publication_confirmed": True}

    assert decide_action(_event(), status, _at(17)) == "wait"
    assert decide_action(
        _event(), status, datetime(2026, 10, 24, 15, 15, tzinfo=UTC)
    ) == "final_check"


def test_final_check_runs_once_and_then_never_reverts_to_ordinary_polling():
    from src.pipeline.state import decide_action

    attempted = {"final_check_attempted_at": "2026-10-24T15:15:00Z"}

    assert (
        decide_action(_event(), {}, datetime(2026, 10, 24, 15, 15, tzinfo=UTC))
        == "final_check"
    )
    assert (
        decide_action(_event(), attempted, datetime(2026, 10, 24, 15, 16, tzinfo=UTC))
        == "wait"
    )


def test_short_window_waits_without_guessing_and_invalid_timestamp_fails_closed():
    from src.pipeline.state import action_decision, decide_action

    short_window = _event(race_start_at="2026-10-23T17:00:00Z")
    decision = action_decision(short_window, {}, _at(14))

    assert decide_action(short_window, {}, _at(14)) == "wait"
    assert decision.reason == "wait_exceeds_cutoff"
    assert decide_action(_event(race_start_at="bad"), {}, _at(16)) == "unavailable"


def test_cutoff_and_frozen_marker_freeze_even_without_prediction_id():
    from src.pipeline.state import decide_action

    cutoff = datetime(2026, 10, 24, 16, tzinfo=UTC)

    assert decide_action(_event(), {}, cutoff) == "freeze"
    assert (
        decide_action(
            _event(),
            {"frozen_at": "2026-10-24T15:00:00Z", "current_prediction_id": None},
            _at(17),
        )
        == "freeze"
    )


def test_latest_generation_window_waits_and_check_completion_must_reevaluate_cutoff():
    from src.pipeline.state import decide_action

    before_cutoff = datetime(2026, 10, 24, 15, 50, tzinfo=UTC)
    after_cutoff = datetime(2026, 10, 24, 16, 1, tzinfo=UTC)
    started = {"last_qualifying_check_started_at": before_cutoff.isoformat()}

    assert decide_action(_event(), {}, before_cutoff) == "wait"
    assert decide_action(_event(), started, after_cutoff) == "freeze"


def test_schedule_refresh_frequency_is_separate_from_qualifying_success():
    from src.pipeline.state import schedule_refresh_due

    status = {
        "actual_publication_confirmed": True,
        "last_schedule_refresh_at": "2026-10-20T10:00:00Z",
    }
    qualifying_window = datetime(2026, 10, 22, 10, tzinfo=UTC)
    outside_window = datetime(2026, 10, 19, 10, tzinfo=UTC)

    assert schedule_refresh_due(_event(), status, qualifying_window) is True
    assert schedule_refresh_due(
        _event(),
        {**status, "last_schedule_refresh_at": "2026-10-22T09:30:00Z"},
        qualifying_window,
    ) is False
    assert schedule_refresh_due(
        _event(), {"last_schedule_refresh_at": "2026-10-18T10:00:00Z"}, outside_window
    ) is True
    assert schedule_refresh_due(
        _event(), {"last_schedule_refresh_at": "2026-10-19T01:00:00Z"}, outside_window
    ) is False
    assert schedule_refresh_due(_event(), {}, outside_window) is True


def test_schedule_change_recomputes_before_freeze_and_is_only_flagged_after_freeze():
    from src.pipeline.state import decide_action, reconcile_schedule

    changed = _event(race_start_at="2026-10-24T20:00:00Z", schedule_hash="schedule-b")

    before = reconcile_schedule({"schedule_hash": "schedule-a"}, changed)
    after = reconcile_schedule(
        {
            "schedule_hash": "schedule-a",
            "frozen_at": "2026-10-24T15:00:00Z",
            "current_prediction_id": None,
        },
        changed,
    )

    assert before["schedule_hash"] == "schedule-b"
    assert "schedule_changed_after_freeze" not in before
    assert (
        decide_action(changed, before, datetime(2026, 10, 24, 16, 30, tzinfo=UTC))
        == "check_qualifying"
    )
    assert after["schedule_hash"] == "schedule-a"
    assert after["schedule_changed_after_freeze"] is True


def test_invalid_status_timestamps_fail_closed_and_status_write_is_noop_when_unchanged(tmp_path):
    from src.pipeline.state import decide_action, write_status_json

    status = {"last_qualifying_check_started_at": "not-a-timestamp"}
    assert decide_action(_event(), status, _at(17)) == "unavailable"

    destination = tmp_path / "status.json"
    assert write_status_json(destination, {"actual_publication_confirmed": False}) is True
    initial_bytes = destination.read_bytes()
    initial_mtime = destination.stat().st_mtime_ns
    time.sleep(0.01)
    assert write_status_json(destination, {"actual_publication_confirmed": False}) is False
    assert destination.read_bytes() == initial_bytes
    assert destination.stat().st_mtime_ns == initial_mtime


def test_status_transition_helpers_preserve_canonical_timestamps_and_next_check():
    from src.pipeline.state import complete_qualifying_check, start_qualifying_check

    started = start_qualifying_check({}, _at(16, 30))
    completed = complete_qualifying_check(
        started, _at(16, 31), success=False, error="feed unavailable"
    )

    assert started["last_qualifying_check_started_at"] == "2026-10-23T16:30:00Z"
    assert completed["last_qualifying_check_completed_at"] == "2026-10-23T16:31:00Z"
    assert completed["last_error"] == "feed unavailable"
    assert completed["next_qualifying_check_at"] == "2026-10-23T17:30:00Z"


def test_unavailable_final_freeze_with_null_selection_is_sticky():
    from src.pipeline.state import decide_action, freeze_status

    status = freeze_status(
        {}, datetime(2026, 10, 24, 16, tzinfo=UTC), reason="actual_unavailable"
    )

    assert status["freeze_selection"] is None
    assert (
        decide_action(_event(), status, datetime(2026, 10, 24, 14, tzinfo=UTC))
        == "freeze"
    )


def test_final_attempt_never_resumes_ordinary_polling_after_schedule_postponement():
    from src.pipeline.state import (
        decide_action,
        mark_final_check_attempted,
        reconcile_schedule,
    )

    attempted = mark_final_check_attempted(
        {}, datetime(2026, 10, 24, 15, 15, tzinfo=UTC)
    )
    postponed = _event(
        race_start_at="2026-10-24T20:00:00Z", schedule_hash="schedule-b"
    )
    status = reconcile_schedule(
        {**attempted, "schedule_hash": "schedule-a"}, postponed
    )

    assert (
        decide_action(postponed, status, datetime(2026, 10, 24, 16, 30, tzinfo=UTC))
        == "wait"
    )


def test_repeated_freeze_preserves_original_outcome_and_invalid_schedule_cannot_reopen_it():
    from src.pipeline.state import decide_action, freeze_status

    frozen = freeze_status(
        {},
        datetime(2026, 10, 24, 15, tzinfo=UTC),
        reason="actual_unavailable",
        selection={"podium": ["A", "B", "C"]},
    )
    repeated = freeze_status(
        frozen,
        datetime(2026, 10, 24, 16, tzinfo=UTC),
        reason="replacement_attempt",
        selection=None,
    )

    assert repeated == frozen
    assert decide_action(
        _event(race_start_at="invalid"),
        repeated,
        datetime(2026, 10, 24, 16, tzinfo=UTC),
    ) == "freeze"
    assert decide_action(
        _event(race_start_at="invalid"),
        {"frozen_prediction_id": None},
        datetime(2026, 10, 24, 16, tzinfo=UTC),
    ) == "freeze"


def test_invalid_existing_policy_timestamps_fail_closed_before_check_actions():
    from src.pipeline.state import action_decision, decide_action

    ordinary = action_decision(
        _event(), {"final_check_attempted_at": "bad"}, _at(17)
    )
    final_window = action_decision(
        _event(),
        {"last_qualifying_check_started_at": "bad"},
        datetime(2026, 10, 24, 15, 15, tzinfo=UTC),
    )

    assert (
        decide_action(_event(), {"final_check_attempted_at": "bad"}, _at(17))
        == "unavailable"
    )
    assert ordinary.reason == "invalid_timestamp"
    assert decide_action(
        _event(),
        {"last_qualifying_check_started_at": "bad"},
        datetime(2026, 10, 24, 15, 15, tzinfo=UTC),
    ) == "unavailable"
    assert final_window.reason == "invalid_timestamp"
