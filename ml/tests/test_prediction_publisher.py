"""State-machine tests for automated qualifying prediction publication."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd

from src.data.jolpica import PaginationMetadata, QualifyingFetchResult
from src.publication.publisher import run_publication


UTC = timezone.utc
SCHEDULE = {
    "season": 2026,
    "round": 4,
    "race_name": "Miami Grand Prix",
    "circuit_id": "miami",
    "qualifying_start_at": "2026-05-02T17:00:00Z",
    "qualifying_end_at": "2026-05-02T20:00:00Z",
    "end_time_estimated": True,
    "race_start_at": "2026-05-03T20:00:00Z",
    "schedule_updated_at": "2026-05-01T00:00:00Z",
}
BASE_FORECAST = {
    "error": None,
    "race": {
        "name": "Miami Grand Prix",
        "season": 2026,
        "round": 4,
        "country": "USA",
        "date": "2026-05-03",
        "qualifyingDate": "2026-05-02",
    },
    "predictedQualifying": [
        {"position": 1, "code": "AAA", "driverName": "Driver A", "team": "A", "teamId": "a", "gap": 0.0},
        {"position": 2, "code": "BBB", "driverName": "Driver B", "team": "B", "teamId": "b", "gap": 0.4},
        {"position": 3, "code": "CCC", "driverName": "Driver C", "team": "C", "teamId": "c", "gap": 0.8},
    ],
    "preQualifyingPodium": [
        {"code": "AAA", "driverName": "Driver A", "team": "A", "teamId": "a", "podiumProbability": 1.0},
        {"code": "BBB", "driverName": "Driver B", "team": "B", "teamId": "b", "podiumProbability": 1.0},
        {"code": "CCC", "driverName": "Driver C", "team": "C", "teamId": "c", "podiumProbability": 1.0},
    ],
}
EXCEPTIONS = {"version": 1, "events": {}}


def _qualifying(q1_b="1:20.500"):
    rows = pd.DataFrame(
        [
            {
                "season": 2026, "round": 4, "race_name": "Miami Grand Prix", "circuit_id": "miami",
                "driver_id": "driver_a", "code": "AAA", "driver_name": "Driver A",
                "constructor_id": "a", "constructor_name": "A", "quali_position": 1,
                "q1": "1:20.000", "q2": None, "q3": None,
            },
            {
                "season": 2026, "round": 4, "race_name": "Miami Grand Prix", "circuit_id": "miami",
                "driver_id": "driver_b", "code": "BBB", "driver_name": "Driver B",
                "constructor_id": "b", "constructor_name": "B", "quali_position": 2,
                "q1": q1_b, "q2": None, "q3": None,
            },
            {
                "season": 2026, "round": 4, "race_name": "Miami Grand Prix", "circuit_id": "miami",
                "driver_id": "driver_c", "code": "CCC", "driver_name": "Driver C",
                "constructor_id": "c", "constructor_name": "C", "quali_position": 3,
                "q1": "1:21.000", "q2": None, "q3": None,
            },
        ]
    )
    return QualifyingFetchResult(
        data=rows,
        pagination=PaginationMetadata(
            reported_total=3,
            fetched_count=3,
            pages_fetched=1,
            offsets=(0,),
            limits=(100,),
            complete=True,
        ),
    )


def _actual_forecast(validated):
    result = dict(BASE_FORECAST)
    result.update(
        inputMode="actual_qualifying",
        hasActualQualifying=True,
        actualQualifying=[
            {
                "position": row["qualifying_position"],
                "code": row["code"],
                "driverName": row["driver_name"],
                "team": row["constructor_name"],
                "teamId": row["constructor_id"],
                "gap": row["qualifying_gap_seconds"],
            }
            for row in validated.rows
        ],
        actualQualifyingPodium=[
            {"code": "AAA", "driverName": "Driver A", "team": "A", "teamId": "a", "podiumProbability": 1.0},
            {"code": "BBB", "driverName": "Driver B", "team": "B", "teamId": "b", "podiumProbability": 1.0},
            {"code": "CCC", "driverName": "Driver C", "team": "C", "teamId": "c", "podiumProbability": 1.0},
        ],
    )
    return result


def test_before_first_check_publishes_waiting_status_without_fetching():
    calls = []
    update = run_publication(
        now=datetime(2026, 5, 2, 23, 0, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: calls.append("fetch"),
        build_actual_forecast=_actual_forecast,
    )

    assert calls == []
    assert update.status["state"] == "estimated_waiting"
    assert update.status["next_scheduled_check_at"] == "2026-05-03T01:17:00Z"
    assert update.snapshot["forecast"] == BASE_FORECAST
    assert update.model_ran is False


def test_status_only_poll_keeps_optional_provenance():
    metadata = {"stage1": {"source": "genuine-stage1"}, "stage2": {"source": "genuine-stage2"}}
    update = run_publication(
        now=datetime(2026, 5, 2, 23, 0, tzinfo=UTC), schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST,
                         "training_metadata": metadata},
        status=None, archive_index=None, expected_participants=[], exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: None, build_actual_forecast=_actual_forecast,
    )
    assert update.snapshot["training_metadata"] == metadata


def test_invalid_check_updates_status_without_running_model_or_replacing_forecast():
    calls = []
    qualifying = _qualifying()
    invalid = replace(qualifying, data=qualifying.data.iloc[:1])
    update = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: invalid,
        build_actual_forecast=lambda validated: calls.append("model"),
    )

    assert calls == []
    assert update.status["state"] == "estimated_waiting"
    assert update.status["last_data_check_at"] == "2026-05-03T01:17:00Z"
    assert update.status["next_scheduled_check_at"] == "2026-05-03T02:17:00Z"
    assert update.snapshot["forecast"] == BASE_FORECAST


def test_fetch_failure_is_recorded_without_running_model_or_replacing_forecast():
    calls = []
    update = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(ValueError("bad response")),
        build_actual_forecast=lambda validated: calls.append("model"),
    )

    assert calls == []
    assert update.status["state"] == "estimated_waiting"
    assert "bad response" in update.status["status_reason"]
    assert update.snapshot["forecast"] == BASE_FORECAST


def test_valid_results_publish_actual_and_pause_until_final_check():
    calls = []

    def build(validated):
        calls.append(validated.input_hash)
        return _actual_forecast(validated)

    update = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=_qualifying,
        build_actual_forecast=build,
    )

    assert len(calls) == 1
    assert update.model_ran is True
    assert update.snapshot["input_mode"] == "actual_qualifying"
    assert update.snapshot["qualifying_input_hash"] == calls[0]
    assert update.status["state"] == "actual_published"
    assert update.status["next_scheduled_check_at"] == "2026-05-03T17:17:00Z"
    assert update.archive_index["active_race_id"] == "2026-4"

    paused_calls = []
    paused = run_publication(
        now=datetime(2026, 5, 3, 5, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot=update.snapshot,
        status=update.status,
        archive_index=update.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: paused_calls.append("fetch"),
        build_actual_forecast=_actual_forecast,
    )
    assert paused_calls == []
    assert paused.model_ran is False


def test_unchanged_final_check_skips_model_then_cutoff_freezes_artifact():
    first = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=_qualifying,
        build_actual_forecast=_actual_forecast,
    )
    model_calls = []
    final = run_publication(
        now=datetime(2026, 5, 3, 17, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot=first.snapshot,
        status=first.status,
        archive_index=first.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=_qualifying,
        build_actual_forecast=lambda validated: model_calls.append("model"),
    )
    assert model_calls == []
    assert final.status["final_verification_completed_at"] == "2026-05-03T17:17:00Z"
    assert final.status["next_scheduled_check_at"] is None

    frozen_calls = []
    frozen = run_publication(
        now=datetime(2026, 5, 3, 18, 1, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot=final.snapshot,
        status=final.status,
        archive_index=final.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: frozen_calls.append("fetch"),
        build_actual_forecast=_actual_forecast,
    )
    assert frozen_calls == []
    assert frozen.status["state"] == "frozen_actual"
    assert frozen.snapshot["frozen_at"] == "2026-05-03T18:00:00Z"
    assert frozen.archive_index["races"][0]["frozen"] is True


def test_corrected_results_trigger_one_validated_republish_at_final_check():
    first = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=_qualifying,
        build_actual_forecast=_actual_forecast,
    )
    model_calls = []

    corrected = run_publication(
        now=datetime(2026, 5, 3, 17, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot=first.snapshot,
        status=first.status,
        archive_index=first.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: _qualifying("1:20.400"),
        build_actual_forecast=lambda validated: (
            model_calls.append(validated.input_hash) or _actual_forecast(validated)
        ),
    )

    assert len(model_calls) == 1
    assert corrected.model_ran is True
    assert corrected.forecast_changed is True
    assert corrected.snapshot["qualifying_input_hash"] != first.snapshot["qualifying_input_hash"]
    assert corrected.snapshot["prediction_updated_at"] == "2026-05-03T17:17:00Z"


def test_monday_roll_forward_preserves_archived_races_and_changes_active_id():
    old_index = {
        "schema_version": 2,
        "active_race_id": "2026-3",
        "races": [{
            "race_id": "2026-3", "season": 2026, "round": 3,
            "race_name": "Japanese Grand Prix", "race_start_at": "2026-03-29T05:00:00Z",
            "artifact_url": "predictions/2026-3.json", "input_mode": "actual_qualifying",
            "frozen": True,
        }],
    }
    update = run_publication(
        now=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=old_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(AssertionError("must not fetch")),
        build_actual_forecast=_actual_forecast,
    )

    assert update.archive_index["active_race_id"] == "2026-4"
    assert {entry["race_id"] for entry in update.archive_index["races"]} == {
        "2026-3", "2026-4"
    }


def test_too_late_schedule_retains_estimated_prediction_with_reason():
    late_schedule = dict(SCHEDULE, qualifying_end_at="2026-05-03T15:30:00Z")
    update = run_publication(
        now=datetime(2026, 5, 3, 16, 0, tzinfo=UTC),
        schedule=late_schedule,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(AssertionError("must not fetch")),
        build_actual_forecast=_actual_forecast,
    )
    assert update.snapshot["input_mode"] == "estimated_qualifying"
    assert update.status["status_reason"] == "five_hour_wait_exceeds_cutoff"
    assert update.status["next_scheduled_check_at"] is None


def test_postponement_recalculates_checks_from_refreshed_schedule():
    original = run_publication(
        now=datetime(2026, 5, 2, 23, 0, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(AssertionError("must not fetch")),
        build_actual_forecast=_actual_forecast,
    )
    postponed_schedule = dict(
        SCHEDULE,
        qualifying_start_at="2026-05-02T18:00:00Z",
        qualifying_end_at="2026-05-02T21:00:00Z",
        schedule_updated_at="2026-05-02T23:30:00Z",
    )

    postponed = run_publication(
        now=datetime(2026, 5, 2, 23, 30, tzinfo=UTC),
        schedule=postponed_schedule,
        active_snapshot=original.snapshot,
        status=original.status,
        archive_index=original.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(AssertionError("must not fetch")),
        build_actual_forecast=_actual_forecast,
    )

    assert postponed.status["schedule_updated_at"] == "2026-05-02T23:30:00Z"
    assert postponed.status["next_scheduled_check_at"] == "2026-05-03T02:17:00Z"


def test_repeated_run_after_failed_final_check_remains_estimated():
    invalid = replace(_qualifying(), data=_qualifying().data.iloc[:1])
    final = run_publication(
        now=datetime(2026, 5, 3, 17, 17, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST},
        status=None,
        archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: invalid,
        build_actual_forecast=_actual_forecast,
    )

    repeated = run_publication(
        now=datetime(2026, 5, 3, 17, 25, tzinfo=UTC),
        schedule=SCHEDULE,
        active_snapshot=final.snapshot,
        status=final.status,
        archive_index=final.archive_index,
        expected_participants=["driver_a", "driver_b", "driver_c"],
        exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: (_ for _ in ()).throw(AssertionError("must not fetch")),
        build_actual_forecast=_actual_forecast,
    )

    assert repeated.snapshot["input_mode"] == "estimated_qualifying"
    assert repeated.status["input_mode"] == "estimated_qualifying"
    assert repeated.status["state"] == "estimated_waiting"


def test_already_frozen_prediction_never_fetches_even_before_revised_cutoff():
    from copy import deepcopy
    frozen = {
        "schema_version": 2, "race_id": "2026-4", "race": BASE_FORECAST["race"],
        "forecast": BASE_FORECAST, "input_mode": "estimated_qualifying",
        "prediction_updated_at": "2026-05-01T00:00:00Z",
        "publication_cutoff_at": "2026-05-02T18:00:00Z",
        "frozen_at": "2026-05-02T18:00:00Z", "qualifying_input_hash": None,
        "status_reason": None,
    }
    original = deepcopy(frozen)
    calls = []
    result = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC), schedule=SCHEDULE,
        active_snapshot=frozen, status=None, archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"], exceptions=EXCEPTIONS,
        fetch_qualifying=lambda: calls.append("fetch") or _qualifying(),
        build_actual_forecast=lambda v: calls.append("model") or _actual_forecast(v),
    )
    assert calls == []
    assert result.snapshot == original
    assert result.status["state"] == "frozen_estimated"


def test_metadata_free_actual_replacement_does_not_keep_old_envelope_provenance():
    result = run_publication(
        now=datetime(2026, 5, 3, 1, 17, tzinfo=UTC), schedule=SCHEDULE,
        active_snapshot={"race": BASE_FORECAST["race"], "forecast": BASE_FORECAST,
                         "training_metadata": {"stage2": {"source": "old-model"}}},
        status=None, archive_index=None,
        expected_participants=["driver_a", "driver_b", "driver_c"], exceptions=EXCEPTIONS,
        fetch_qualifying=_qualifying, build_actual_forecast=_actual_forecast,
    )
    assert "training_metadata" not in result.snapshot
