"""Event identity, timing, roster, and override contracts (no network I/O)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest


def _schedule(**updates):
    event = {
        "season": 2026,
        "round": 20,
        "race_name": "Example Grand Prix",
        "circuit_id": "example_ring",
        "qualifying_start_at": "2026-10-23T15:00:00Z",
        "qualifying_end_observed_at": None,
        "race_start_at": "2026-10-25T17:00:00Z",
        "schedule_updated_at": "2026-01-15T12:00:00Z",
        "schedule_source": "jolpica",
    }
    event.update(updates)
    return event


def _roster_record(driver_id="driver_one", **updates):
    record = {
        "driver_id": driver_id,
        "code": "ONE",
        "driver_name": "Driver One",
        "constructor_id": "example",
        "constructor_name": "Example Racing",
        "number": "11",
        "eligible": True,
        "expected": True,
        "participation": "provisional",
        "exception": None,
        "provenance": {
            "source": "previous_completed_race",
            "season": 2026,
            "round": 19,
            "source_url": "https://example.test/results/2026/19",
            "observed_at": "2026-10-20T12:00:00Z",
        },
    }
    record.update(updates)
    return record


def _roster_source():
    return {
        "source": "previous_completed_race",
        "season": 2026,
        "round": 19,
        "source_url": "https://example.test/results/2026/19",
        "observed_at": "2026-10-20T12:00:00Z",
        "provisional": True,
    }


def test_parse_utc_normalizes_offsets_and_rejects_naive_values():
    from src.pipeline.events import EventContractError, parse_utc

    assert parse_utc("2026-10-23T11:00:00-04:00") == datetime(
        2026, 10, 23, 15, tzinfo=timezone.utc
    )
    assert parse_utc(datetime(2026, 10, 23, 15, tzinfo=timezone.utc)) == datetime(
        2026, 10, 23, 15, tzinfo=timezone.utc
    )
    with pytest.raises(EventContractError, match="timezone"):
        parse_utc("2026-10-23T15:00:00")
    with pytest.raises(EventContractError, match="timezone"):
        parse_utc(datetime(2026, 10, 23, 15))


def test_event_windows_supports_friday_qualifying_and_sunday_race():
    from src.pipeline.events import event_windows

    windows = event_windows(_schedule())

    assert windows == {
        "qualifying_end_at": datetime(2026, 10, 23, 16, 30, tzinfo=timezone.utc),
        "end_time_estimated": True,
        "first_check_at": datetime(2026, 10, 23, 21, 30, tzinfo=timezone.utc),
        "cutoff_at": datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc),
        "final_check_at": datetime(2026, 10, 25, 14, 15, tzinfo=timezone.utc),
        "latest_generation_start_at": datetime(
            2026, 10, 25, 14, 45, tzinfo=timezone.utc
        ),
    }


def test_event_windows_supports_saturday_race_without_weekday_guesses():
    from src.pipeline.events import event_windows

    windows = event_windows(
        _schedule(
            qualifying_start_at="2026-11-19T18:00:00Z",
            race_start_at="2026-11-21T17:00:00Z",
        )
    )

    assert windows["qualifying_end_at"] == datetime(
        2026, 11, 19, 19, 30, tzinfo=timezone.utc
    )
    assert windows["cutoff_at"] == datetime(
        2026, 11, 21, 15, 0, tzinfo=timezone.utc
    )


def test_observed_qualifying_end_replaces_estimate():
    from src.pipeline.events import event_windows

    windows = event_windows(
        _schedule(qualifying_end_observed_at="2026-10-23T16:47:00Z")
    )

    assert windows["qualifying_end_at"] == datetime(
        2026, 10, 23, 16, 47, tzinfo=timezone.utc
    )
    assert windows["end_time_estimated"] is False
    assert windows["first_check_at"] == datetime(
        2026, 10, 23, 21, 47, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"qualifying_start_at": None}, "missing_schedule_evidence"),
        ({"race_start_at": None}, "missing_schedule_evidence"),
        (
            {"qualifying_start_at": "2026-10-26T15:00:00Z"},
            "inconsistent_event_times",
        ),
        (
            {"qualifying_end_observed_at": "2026-10-23T14:59:00Z"},
            "inconsistent_event_times",
        ),
    ],
)
def test_event_windows_fails_closed_for_missing_or_inconsistent_times(
    updates, reason_code
):
    from src.pipeline.events import EventContractError, event_windows

    with pytest.raises(EventContractError) as exc_info:
        event_windows(_schedule(**updates))
    assert exc_info.value.code == reason_code


def test_schedule_hash_ignores_retrieval_time_but_detects_schedule_changes():
    from src.pipeline.events import schedule_hash

    original = _schedule(schedule_updated_at="2026-01-01T00:00:00Z")
    fetched_later = _schedule(schedule_updated_at="2026-10-01T00:00:00Z")
    rescheduled = _schedule(qualifying_start_at="2026-10-23T16:00:00Z")

    assert schedule_hash(original) == schedule_hash(fetched_later)
    assert schedule_hash(original) != schedule_hash(rescheduled)


def test_roster_version_is_order_independent_and_not_tied_to_field_size():
    from src.pipeline.events import roster_version

    driver_two = _roster_record(
        "driver_two", code="TWO", driver_name="Driver Two", number=None
    )
    two_driver_version = roster_version([_roster_record(), driver_two])

    assert two_driver_version == roster_version([driver_two, _roster_record()])
    assert two_driver_version != roster_version(
        [driver_two, _roster_record(), _roster_record("driver_three")]
    )


def test_roster_version_ignores_audit_observation_time():
    from src.pipeline.events import roster_version

    original = _roster_record()
    observed_later = _roster_record(
        provenance={
            **original["provenance"],
            "observed_at": "2026-10-21T12:00:00Z",
        }
    )

    assert roster_version([original]) == roster_version([observed_later])


def test_build_event_metadata_is_json_native_and_preserves_provenance():
    from src.pipeline.events import build_event_metadata

    event = build_event_metadata(_schedule(), [_roster_record()], _roster_source())

    assert event["qualifying_end_at"] == "2026-10-23T16:30:00Z"
    assert event["end_time_estimated"] is True
    assert event["schedule_hash"]
    assert event["roster_version"]
    assert event["roster_source"]["source"] == "previous_completed_race"
    assert event["roster"][0]["provenance"]["round"] == 19
    json.dumps(event)


def test_write_event_json_atomically_replaces_metadata_file(tmp_path):
    from src.pipeline.events import build_event_metadata, write_event_json

    destination = tmp_path / "event.json"
    destination.write_text('{"stale": true}', encoding="utf-8")
    event = build_event_metadata(_schedule(), [_roster_record()], _roster_source())

    write_event_json(destination, event)

    assert json.loads(destination.read_text(encoding="utf-8")) == event
    assert list(tmp_path.iterdir()) == [destination]


def test_previous_race_roster_is_explicitly_provisional():
    from src.pipeline.events import provisional_roster_from_results

    rows = [
        {
            "driver_id": "driver_one",
            "code": "ONE",
            "driver_name": "Driver One",
            "constructor_id": "example",
            "constructor_name": "Example Racing",
            "number": "11",
        }
    ]

    roster, source = provisional_roster_from_results(
        rows,
        season=2026,
        round_number=19,
        source_url="https://example.test/results/2026/19",
        observed_at="2026-10-20T12:00:00Z",
    )

    assert roster[0]["eligible"] is True
    assert roster[0]["expected"] is True
    assert roster[0]["participation"] == "provisional"
    assert roster[0]["provenance"]["source"] == "previous_completed_race"
    assert source["provisional"] is True


def test_roster_requires_entry_evidence_instead_of_guessing():
    from src.pipeline.events import EventContractError, build_event_metadata

    unsupported = _roster_record(provenance={})
    with pytest.raises(EventContractError) as exc_info:
        build_event_metadata(_schedule(), [unsupported], _roster_source())
    assert exc_info.value.code == "missing_entry_evidence"


def test_exact_event_override_preserves_provenance_and_participant_exception():
    from src.pipeline.events import apply_event_override, build_event_metadata

    event = build_event_metadata(_schedule(), [_roster_record()], _roster_source())
    overrides = {
        "2026-20": {
            "reason": "Confirmed substitute after the entry list changed",
            "source_url": "https://example.test/official-entry-list",
            "observed_at": "2026-10-22T15:00:00Z",
            "participants": {
                "driver_one": {
                    "participation": "confirmed_substitute",
                    "exception": {
                        "kind": "confirmed_substitute",
                        "reason": "Official substitution",
                        "source_url": "https://example.test/official-entry-list",
                        "observed_at": "2026-10-22T15:00:00Z",
                        "replaces_driver_id": "original_driver",
                        "allow_model_position": False,
                    },
                }
            },
        },
        "2026-21": {
            "reason": "Different event",
            "source_url": "https://example.test/other",
            "observed_at": "2026-10-22T15:00:00Z",
            "schedule": {"race_start_at": "2026-11-01T17:00:00Z"},
        },
    }

    updated = apply_event_override(event, overrides)

    assert updated["race_start_at"] == event["race_start_at"]
    assert updated["roster"][0]["participation"] == "confirmed_substitute"
    assert updated["roster"][0]["exception"]["replaces_driver_id"] == "original_driver"
    assert updated["overrides"][0]["reason"].startswith("Confirmed substitute")


@pytest.mark.parametrize(
    "override",
    [
        {"schedule": {"race_start_at": "2026-10-25T18:00:00Z"}},
        {
            "reason": "Changed",
            "source_url": "https://example.test/source",
            "observed_at": "2026-10-22T15:00:00Z",
            "schedule": {"date": "2026-10-25"},
        },
        {
            "reason": "Changed",
            "source_url": "not-a-source",
            "observed_at": "2026-10-22T15:00:00Z",
            "participants": {"driver_one": {"expected": False}},
        },
    ],
)
def test_override_rejects_missing_evidence_and_unsupported_changes(override):
    from src.pipeline.events import EventContractError, apply_event_override

    event = {
        **_schedule(),
        "qualifying_end_at": "2026-10-23T16:30:00Z",
        "end_time_estimated": True,
        "schedule_hash": "placeholder",
        "roster": [_roster_record()],
        "roster_source": _roster_source(),
        "roster_version": "placeholder",
    }
    with pytest.raises(EventContractError) as exc_info:
        apply_event_override(event, {"2026-20": override})
    assert exc_info.value.code == "unsupported_override"


def test_participant_override_rejects_contradictory_flags():
    from src.pipeline.events import EventContractError, apply_event_override

    event = {
        **_schedule(),
        "qualifying_end_at": "2026-10-23T16:30:00Z",
        "end_time_estimated": True,
        "schedule_hash": "placeholder",
        "roster": [_roster_record()],
        "roster_source": _roster_source(),
        "roster_version": "placeholder",
    }
    override = {
        "reason": "Driver withdrew",
        "source_url": "https://example.test/official-entry-list",
        "observed_at": "2026-10-22T15:00:00Z",
        "participants": {
            "driver_one": {
                "participation": "withdrawn",
                "expected": True,
                "eligible": False,
            }
        },
    }

    with pytest.raises(EventContractError) as exc_info:
        apply_event_override(event, {"2026-20": override})
    assert exc_info.value.code == "invalid_roster"


def test_no_lap_exception_schema_can_authorize_model_position_later():
    from src.pipeline.events import validate_roster_record

    record = _roster_record(
        participation="confirmed",
        exception={
            "kind": "no_qualifying_lap",
            "reason": "Official timing shows no lap",
            "source_url": "https://example.test/official-timing",
            "observed_at": "2026-10-23T17:00:00Z",
            "replaces_driver_id": None,
            "allow_model_position": True,
        },
    )

    assert validate_roster_record(record)["exception"]["allow_model_position"] is True


def test_jolpica_schedule_uses_only_grand_prix_qualifying_timestamp(monkeypatch):
    from src.data import jolpica

    payload = {
        "RaceTable": {
            "Races": [
                {
                    "season": "2026",
                    "round": "20",
                    "raceName": "Example Grand Prix",
                    "Circuit": {
                        "circuitId": "example_ring",
                        "circuitName": "Example Ring",
                        "Location": {"country": "Example", "locality": "Town"},
                    },
                    "date": "2026-10-25",
                    "time": "17:00:00Z",
                    "Qualifying": {"date": "2026-10-23", "time": "15:00:00Z"},
                    "SprintQualifying": {
                        "date": "2026-10-24",
                        "time": "10:00:00Z",
                    },
                }
            ]
        }
    }
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter([payload]))

    schedule = jolpica.get_schedule(
        2026, fetched_at="2026-01-15T12:00:00Z"
    ).iloc[0]

    assert schedule["qualifying_start_at"] == "2026-10-23T15:00:00Z"
    assert schedule["race_start_at"] == "2026-10-25T17:00:00Z"
    assert schedule["schedule_updated_at"] == "2026-01-15T12:00:00Z"
    assert schedule["schedule_source"] == "jolpica"
    assert schedule["date"] == "2026-10-25"


def test_jolpica_schedule_leaves_missing_optional_times_as_none(monkeypatch):
    from src.data import jolpica

    payload = {
        "RaceTable": {
            "Races": [
                {
                    "season": "2026",
                    "round": "20",
                    "raceName": "Example Grand Prix",
                    "Circuit": {
                        "circuitId": "example_ring",
                        "circuitName": "Example Ring",
                    },
                    "date": "2026-10-25",
                }
            ]
        }
    }
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter([payload]))

    schedule = jolpica.get_schedule(
        2026, fetched_at="2026-01-15T12:00:00Z"
    ).iloc[0]

    assert schedule["qualifying_start_at"] is None
    assert schedule["race_start_at"] is None
