"""Round-scoped qualifying validation and normalization."""
import importlib
from pathlib import Path

import pandas as pd
import pytest

from src.data.jolpica import PaginationMetadata, QualifyingFetchResult


EXPECTED_EVENT = {
    "season": 2026,
    "round": 4,
    "race_name": "Miami Grand Prix",
    "circuit_id": "miami",
}
EMPTY_EXCEPTIONS = {"version": 1, "events": {}}


def _validation_module():
    return importlib.import_module("src.publication.qualifying")


def _row(driver_id, position, *, q1="1:20.000", q2=None, q3=None, **overrides):
    row = {
        **EXPECTED_EVENT,
        "driver_id": driver_id,
        "code": driver_id[:3].upper(),
        "constructor_id": f"team_{driver_id}",
        "quali_position": position,
        "q1": q1,
        "q2": q2,
        "q3": q3,
    }
    row.update(overrides)
    return row


def _fetch(rows, *, reported_total=None, fetched_count=None, complete=None):
    count = len(rows)
    reported_total = count if reported_total is None else reported_total
    fetched_count = count if fetched_count is None else fetched_count
    complete = fetched_count == reported_total if complete is None else complete
    return QualifyingFetchResult(
        data=pd.DataFrame(rows),
        pagination=PaginationMetadata(
            reported_total=reported_total,
            fetched_count=fetched_count,
            pages_fetched=1,
            offsets=(0,),
            limits=(100,),
            complete=complete,
        ),
    )


def _validate(rows, expected_participants, exceptions=EMPTY_EXCEPTIONS, **fetch_kwargs):
    validation = _validation_module()
    return validation.validate_qualifying(
        _fetch(rows, **fetch_kwargs),
        expected_event=EXPECTED_EVENT,
        expected_participants=expected_participants,
        exceptions=exceptions,
    )


def test_normalizes_gaps_accepts_missing_later_sessions_and_fills_no_lap_gap():
    rows = [
        _row("driver_a", 1, q1="1:20.000", q2="1:19.500"),
        _row("driver_b", 2, q1="1:20.500"),
        _row("driver_c", 3, q1=None),
    ]

    result = _validate(rows, ["driver_a", "driver_b", "driver_c"])

    by_driver = {row["driver_id"]: row for row in result.rows}
    assert by_driver["driver_a"]["best_lap_seconds"] == pytest.approx(79.5)
    assert by_driver["driver_a"]["qualifying_gap_seconds"] == pytest.approx(0.0)
    assert by_driver["driver_b"]["qualifying_gap_seconds"] == pytest.approx(1.0)
    assert by_driver["driver_c"]["best_lap_seconds"] is None
    assert by_driver["driver_c"]["qualifying_gap_seconds"] == pytest.approx(1.0)
    assert len(result.input_hash) == 64

    reversed_result = _validate(list(reversed(rows)), ["driver_c", "driver_b", "driver_a"])
    assert reversed_result.rows == result.rows
    assert reversed_result.input_hash == result.input_hash


def test_rejects_incomplete_pagination():
    validation = _validation_module()
    with pytest.raises(validation.QualifyingValidationError, match="pagination"):
        _validate(
            [_row("driver_a", 1), _row("driver_b", 2)],
            ["driver_a", "driver_b"],
            reported_total=3,
            fetched_count=2,
            complete=False,
        )


def test_rejects_pagination_metadata_with_a_repeated_offset():
    validation = _validation_module()
    rows = [_row("driver_a", 1), _row("driver_b", 2)]
    fetched = QualifyingFetchResult(
        data=pd.DataFrame(rows),
        pagination=PaginationMetadata(
            reported_total=2,
            fetched_count=2,
            pages_fetched=2,
            offsets=(0, 0),
            limits=(1, 1),
            complete=True,
        ),
    )

    with pytest.raises(validation.QualifyingValidationError, match="pagination"):
        validation.validate_qualifying(
            fetched,
            expected_event=EXPECTED_EVENT,
            expected_participants=["driver_a", "driver_b"],
            exceptions=EMPTY_EXCEPTIONS,
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"season": 2025}, "season"),
        ({"round": 5}, "round"),
        ({"race_name": "Not Miami"}, "race_name"),
        ({"circuit_id": "not_miami"}, "circuit_id"),
    ],
)
def test_rejects_wrong_event_identity(override, message):
    validation = _validation_module()
    with pytest.raises(validation.QualifyingValidationError, match=message):
        _validate([_row("driver_a", 1, **override)], ["driver_a"])


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_row("driver_a", 1), _row("driver_a", 2)], "driver"),
        ([_row("driver_a", 1), _row("driver_b", 1)], "position"),
        ([_row("driver_a", 0)], "positive integer"),
        ([_row("driver_a", "not-a-position")], "positive integer"),
    ],
)
def test_rejects_duplicate_or_invalid_classification(rows, message):
    validation = _validation_module()
    expected = sorted({row["driver_id"] for row in rows})
    with pytest.raises(validation.QualifyingValidationError, match=message):
        _validate(rows, expected)


def test_applies_withdrawn_and_excluded_coverage_exceptions():
    exceptions = {
        "version": 1,
        "events": {
            "2026-4": {
                "withdrawn": [{"driver_id": "driver_c", "reason": "injury"}],
                "excluded": [{"driver_id": "driver_d", "reason": "not entered"}],
                "substitutions": [],
            }
        },
    }

    result = _validate(
        [_row("driver_a", 1), _row("driver_b", 2)],
        ["driver_a", "driver_b", "driver_c", "driver_d"],
        exceptions,
    )

    assert [row["driver_id"] for row in result.rows] == ["driver_a", "driver_b"]


def test_applies_substitution_coverage_exception():
    exceptions = {
        "version": 1,
        "events": {
            "2026-4": {
                "withdrawn": [],
                "excluded": [],
                "substitutions": [
                    {
                        "out_driver_id": "driver_out",
                        "in_driver_id": "driver_in",
                        "reason": "reserve driver",
                    }
                ],
            }
        },
    }

    result = _validate(
        [_row("driver_a", 1), _row("driver_in", 2)],
        ["driver_a", "driver_out"],
        exceptions,
    )

    assert {row["driver_id"] for row in result.rows} == {"driver_a", "driver_in"}


@pytest.mark.parametrize(
    "rows",
    [
        [_row("driver_a", 1)],
        [_row("driver_a", 1), _row("driver_b", 2), _row("driver_extra", 3)],
    ],
)
def test_rejects_unexpected_missing_or_extra_drivers(rows):
    validation = _validation_module()
    with pytest.raises(validation.QualifyingValidationError, match="coverage"):
        _validate(rows, ["driver_a", "driver_b"])


@pytest.mark.parametrize("lap_time", ["malformed", "1:60.000", ""])
def test_rejects_malformed_supplied_lap_time(lap_time):
    validation = _validation_module()
    with pytest.raises(validation.QualifyingValidationError, match="lap time"):
        _validate([_row("driver_a", 1, q1=lap_time)], ["driver_a"])


def test_rejects_a_classification_with_no_valid_laps_at_all():
    validation = _validation_module()
    with pytest.raises(validation.QualifyingValidationError, match="at least one valid lap"):
        _validate([_row("driver_a", 1, q1=None)], ["driver_a"])


def test_versioned_exception_config_contract_and_initial_config():
    validation = _validation_module()
    config_path = Path(__file__).parents[1] / "config" / "qualifying_exceptions.v1.json"

    config = validation.load_exceptions_config(config_path)

    assert config == {"version": 1, "events": {}}
    with pytest.raises(validation.QualifyingValidationError, match="reason"):
        validation.validate_exceptions_config(
            {
                "version": 1,
                "events": {
                    "2026-4": {
                        "withdrawn": [{"driver_id": "driver_a"}],
                        "excluded": [],
                        "substitutions": [],
                    }
                },
            }
        )
