"""Contract tests for fetching and validating one qualifying event."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pandas as pd
import pytest
import requests


def _roster_record(
    driver_id: str,
    constructor_id: str = "team",
    *,
    expected: bool = True,
    eligible: bool = True,
    participation: str = "confirmed",
    exception: dict | None = None,
) -> dict:
    return {
        "driver_id": driver_id,
        "code": driver_id[:3].upper(),
        "driver_name": driver_id.replace("_", " ").title(),
        "constructor_id": constructor_id,
        "constructor_name": constructor_id.title(),
        "number": "1",
        "expected": expected,
        "eligible": eligible,
        "participation": participation,
        "exception": exception,
        "provenance": {
            "source": "previous_completed_race",
            "source_url": "https://example.test/race-19",
            "observed_at": "2026-10-20T12:00:00Z",
            "season": 2026,
            "round": 19,
        },
    }


def _event(roster: list[dict] | None = None, **updates) -> dict:
    event = {
        "season": 2026,
        "round": 20,
        "race_name": "Example Grand Prix",
        "circuit_id": "example_ring",
        "roster": roster
        or [_roster_record("driver_one"), _roster_record("driver_two")],
    }
    event.update(updates)
    return event


def _result(
    driver_id: str,
    position: str | None,
    *,
    constructor_id: str = "team",
    q1: str | None = "1:20.000",
    q2: str | None = None,
    q3: str | None = None,
) -> dict:
    result = {
        "number": "1",
        "Driver": {
            "driverId": driver_id,
            "code": driver_id[:3].upper(),
            "givenName": driver_id,
            "familyName": "Driver",
        },
        "Constructor": {"constructorId": constructor_id, "name": constructor_id.title()},
    }
    if position is not None:
        result["position"] = position
    if q1 is not None:
        result["Q1"] = q1
    if q2 is not None:
        result["Q2"] = q2
    if q3 is not None:
        result["Q3"] = q3
    return result


def _payload(
    results: list[dict],
    *,
    total: int | None = None,
    limit: int = 100,
    offset: int = 0,
    season: int = 2026,
    round_number: int = 20,
    circuit_id: str = "example_ring",
    series: str = "f1",
    include_session: bool = True,
) -> dict:
    race = {
        "season": str(season),
        "round": str(round_number),
        "raceName": "Example Grand Prix",
        "Circuit": {"circuitId": circuit_id, "circuitName": "Example Ring"},
    }
    if include_session:
        race["QualifyingResults"] = results
    return {
        "MRData": {
            "series": series,
            "url": (
                f"https://api.jolpi.ca/ergast/f1/{season}/{round_number}/qualifying/"
            ),
            "limit": str(limit),
            "offset": str(offset),
            "total": str(len(results) if total is None else total),
            "RaceTable": {
                "season": str(season),
                "round": str(round_number),
                "Races": [race],
            },
        }
    }


def _fetch(pages: list[dict]):
    from src.pipeline.qualifying import fetch_target_qualifying

    calls = []

    def get_page(path, params):
        calls.append((path, dict(params)))
        return copy.deepcopy(pages[len(calls) - 1])

    fetched = fetch_target_qualifying(2026, 20, get_page)
    return fetched, calls


def _valid_results() -> list[dict]:
    return [
        _result("driver_one", "1", q1="1:20.100", q2="1:19.900", q3="1:19.800"),
        _result("driver_two", "2", q1="1:20.500", q2=None, q3=None),
    ]


def _validated(event=None, payload=None):
    from src.pipeline.qualifying import validate_qualifying

    fetched, _ = _fetch([payload or _payload(_valid_results())])
    return validate_qualifying(event or _event(), fetched.rows, fetched.page_evidence)


def test_fetch_uses_exact_endpoint_and_provider_page_limit():
    first = _payload([_valid_results()[0]], total=2, limit=1, offset=0)
    second = _payload([_valid_results()[1]], total=2, limit=1, offset=1)

    fetched, calls = _fetch([first, second])

    assert calls == [
        ("2026/20/qualifying", {"limit": 100, "offset": 0}),
        ("2026/20/qualifying", {"limit": 1, "offset": 1}),
    ]
    assert fetched.rows["driver_id"].tolist() == ["driver_one", "driver_two"]
    assert len(fetched.source_pages) == 2
    assert fetched.retrieval_metadata[0]["requested_offset"] == 0


def test_fetch_preserves_timeout_and_does_not_accept_zero_results():
    from src.pipeline.qualifying import QualifyingValidationError, fetch_target_qualifying

    def timeout(path, params):
        raise requests.Timeout("late")

    with pytest.raises(requests.Timeout):
        fetch_target_qualifying(2026, 20, timeout)

    fetched, _ = _fetch([_payload([], total=0)])
    with pytest.raises(QualifyingValidationError, match="no qualifying results") as exc_info:
        from src.pipeline.qualifying import validate_qualifying

        validate_qualifying(_event(), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == "qualifying_unavailable"


@pytest.mark.parametrize(
    ("season", "round_number"),
    [("last", 20), (2026, "next"), (True, 20), (2026, False), (2026.0, 20), (2026, 20.5)],
)
def test_fetch_rejects_non_explicit_target_before_http(season, round_number):
    from src.pipeline.qualifying import QualifyingValidationError, fetch_target_qualifying

    called = False

    def get_page(path, params):
        nonlocal called
        called = True
        return _payload(_valid_results())

    with pytest.raises(QualifyingValidationError) as exc_info:
        fetch_target_qualifying(season, round_number, get_page)
    assert exc_info.value.code == "invalid_target"
    assert called is False


@pytest.mark.parametrize("invalid", [True, 1.9, float("inf"), "1.9"])
def test_fetch_strictly_rejects_malformed_numeric_pagination(invalid):
    from src.pipeline.qualifying import QualifyingValidationError

    payload = _payload(_valid_results())
    payload["MRData"]["limit"] = invalid

    with pytest.raises(QualifyingValidationError) as exc_info:
        _fetch([payload])
    assert exc_info.value.code == "malformed_pagination"


@pytest.mark.parametrize(
    ("payload_updates", "event_updates", "code"),
    [
        ({"season": 2025}, {}, "wrong_event"),
        ({"round_number": 19}, {}, "wrong_event"),
        ({"circuit_id": "other"}, {}, "wrong_event"),
        ({"series": "other"}, {}, "wrong_series"),
        ({"include_session": False}, {}, "wrong_session"),
        ({}, {"circuit_id": "other"}, "wrong_event"),
    ],
)
def test_rejects_wrong_series_event_circuit_or_session(payload_updates, event_updates, code):
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    payload = _payload(_valid_results(), **payload_updates)
    fetched, _ = _fetch([payload])
    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(**event_updates), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == code


@pytest.mark.parametrize("location", ["table", "race"])
@pytest.mark.parametrize("field", ["season", "round"])
@pytest.mark.parametrize("kind", ["fractional", "whole_float", "infinite", "nan", "boolean"])
def test_raw_event_identity_rejects_coerced_values(location, field, kind):
    from src.pipeline.qualifying import (
        QualifyingValidationError,
        fetch_target_qualifying,
        validate_qualifying,
    )

    identity = {"season": 2026, "round": 20}
    if kind == "boolean":
        identity[field] = 1
    value = {
        "fractional": identity[field] + 0.9,
        "whole_float": float(identity[field]),
        "infinite": float("inf"),
        "nan": float("nan"),
        "boolean": True,
    }[kind]
    payload = _payload(
        _valid_results(), season=identity["season"], round_number=identity["round"]
    )
    table = payload["MRData"]["RaceTable"]
    target = table if location == "table" else table["Races"][0]
    target[field] = value
    fetched = fetch_target_qualifying(
        identity["season"], identity["round"], lambda path, params: payload
    )

    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(**identity), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == "wrong_event"


@pytest.mark.parametrize("location", ["table", "race"])
def test_raw_event_identity_accepts_integer_values(location):
    payload = _payload(_valid_results())
    table = payload["MRData"]["RaceTable"]
    target = table if location == "table" else table["Races"][0]
    target.update(season=2026, round=20)

    assert len(_validated(payload=payload).rows) == 2


@pytest.mark.parametrize(
    ("pages", "code"),
    [
        (
            [
                _payload(_valid_results(), total=3, limit=2, offset=0),
                _payload([], total=3, limit=2, offset=2),
            ],
            "incomplete_pagination",
        ),
        (
            [
                _payload([_valid_results()[0]], total=2, limit=1, offset=0),
                _payload([_valid_results()[1]], total=3, limit=1, offset=1),
                _payload([], total=3, limit=1, offset=2),
            ],
            "changing_pagination",
        ),
    ],
)
def test_rejects_partial_or_changing_pagination(pages, code):
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    fetched, calls = _fetch(pages)
    if code == "changing_pagination":
        assert len(calls) == 2
    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == code


def test_rejects_malformed_page_counts_even_when_total_count_adds_up():
    from src.pipeline.qualifying import (
        PageEvidence,
        QualifyingValidationError,
        validate_qualifying,
    )

    pages = [
        _payload([], total=2, limit=1, offset=0),
        _payload(_valid_results(), total=2, limit=1, offset=1),
    ]
    fetched, _ = _fetch([_payload(_valid_results())])
    evidence = PageEvidence(
        source_pages=tuple(pages),
        retrieval_metadata=[
            {
                **fetched.retrieval_metadata[0],
                "requested_limit": 100 if offset == 0 else 1,
                "requested_offset": offset,
                "returned_offset": offset,
            }
            for offset in (0, 1)
        ],
    )

    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(), fetched.rows, evidence)
    assert exc_info.value.code == "malformed_page_count"


@pytest.mark.parametrize("first_results", [[], _valid_results()])
def test_fetch_stops_at_bad_page_count_and_preserves_evidence(first_results):
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    first = _payload(first_results, total=2, limit=1, offset=0)
    second = _payload([_valid_results()[1]], total=2, limit=1, offset=1)

    fetched, calls = _fetch([first, second])

    assert calls == [("2026/20/qualifying", {"limit": 100, "offset": 0})]
    assert fetched.source_pages == (first,)
    assert len(fetched.retrieval_metadata) == 1
    assert len(fetched.rows) == len(first_results)
    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == "noncontiguous_pagination"


def test_validation_rejects_page_evidence_from_a_different_endpoint():
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    fetched, _ = _fetch([_payload(_valid_results())])
    fetched.retrieval_metadata[0]["requested_path"] = "2026/20/sprint"

    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(), fetched.rows, fetched.page_evidence)
    assert exc_info.value.code == "wrong_endpoint"


def test_validation_rejects_non_object_qualifying_result_entries():
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    payload = _payload([_result("driver_one", "1"), "malformed"])
    fetched, _ = _fetch([payload])

    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(
            _event([_roster_record("driver_one")]),
            fetched.rows,
            fetched.page_evidence,
        )
    assert exc_info.value.code == "malformed_response"


@pytest.mark.parametrize(
    ("results", "code"),
    [
        ([_result("driver_one", "1"), _result("driver_one", "2")], "duplicate_driver"),
        ([_result("driver_one", "1"), _result("driver_two", "1")], "duplicate_position"),
        ([_result("driver_one", "1")], "missing_expected_driver"),
        (_valid_results() + [_result("unknown", "3")], "unknown_driver"),
        (
            [_result("driver_one", "1", constructor_id="other"), _result("driver_two", "2")],
            "constructor_mismatch",
        ),
    ],
)
def test_rejects_duplicate_or_roster_inconsistent_results(results, code):
    from src.pipeline.qualifying import QualifyingValidationError

    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(payload=_payload(results))
    assert exc_info.value.code == code


def test_missing_q2_q3_is_valid_and_best_lap_sets_event_gap():
    accepted = _validated()
    rows = accepted.rows.set_index("driver_id")

    assert pd.isna(rows.loc["driver_two", "q2"])
    assert rows.loc["driver_one", "quali_time_gap_to_pole"] == pytest.approx(0.0)
    assert rows.loc["driver_two", "quali_time_gap_to_pole"] == pytest.approx(0.7)
    assert accepted.imputation_policy["no_lap_model_gap"] == "largest_valid_event_gap"


@pytest.mark.parametrize("bad_time", ["bad", "0", "-1", "NaN", "inf"])
def test_present_timing_must_be_finite_and_positive(bad_time):
    from src.pipeline.qualifying import QualifyingValidationError

    results = _valid_results()
    results[1]["Q1"] = bad_time
    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(payload=_payload(results))
    assert exc_info.value.code == "invalid_lap_time"


@pytest.mark.parametrize(
    "bad_time",
    ["1:-1", "-1:80", "1:99.000", "1:60", "+80.000", "1.5:20", "1e2", "1:+20", "1:2e1"],
)
def test_present_timing_requires_unsigned_decimal_components(bad_time):
    from src.pipeline.qualifying import QualifyingValidationError

    results = _valid_results()
    results[1]["Q1"] = bad_time

    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(payload=_payload(results))
    assert exc_info.value.code == "invalid_lap_time"


@pytest.mark.parametrize("bad_time", [80.0, float("nan"), float("inf")])
def test_present_raw_timing_must_be_a_string(bad_time):
    from src.pipeline.qualifying import QualifyingValidationError

    results = _valid_results()
    results[1]["Q1"] = bad_time
    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(payload=_payload(results))
    assert exc_info.value.code == "invalid_lap_time"


def test_classified_no_lap_keeps_actuals_missing_and_imputes_only_model_gap():
    results = _valid_results()
    results[1].pop("Q1")

    accepted = _validated(payload=_payload(results))
    row = accepted.rows.set_index("driver_id").loc["driver_two"]

    assert pd.isna(row["best_qualifying_time_seconds"])
    assert pd.isna(row["quali_time_gap_to_pole"])
    assert row["model_quali_time_gap_to_pole"] == pytest.approx(0.0)
    assert row["model_position"] == 2


def test_all_no_lap_results_are_rejected():
    from src.pipeline.qualifying import QualifyingValidationError

    results = [_result("driver_one", "1", q1=None), _result("driver_two", "2", q1=None)]
    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(payload=_payload(results))
    assert exc_info.value.code == "no_valid_lap_times"


def _no_lap_exception(model_position=None, *, allow=True):
    exception = {
        "kind": "no_qualifying_lap",
        "reason": "Official timing shows no classification",
        "source_url": "https://example.test/official-timing",
        "observed_at": "2026-10-23T17:00:00Z",
        "allow_model_position": allow,
    }
    if model_position is not None:
        exception["model_position"] = model_position
    return exception


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (None, "unclassified_driver"),
        (_no_lap_exception(), "missing_model_position"),
        (_no_lap_exception(2, allow=False), "invalid_roster"),
    ],
)
def test_unclassified_driver_requires_explicit_model_position_policy(exception, code):
    from src.pipeline.qualifying import QualifyingValidationError

    roster = [
        _roster_record("driver_one"),
        _roster_record("driver_two", exception=exception),
    ]
    results = [_result("driver_one", "1"), _result("driver_two", None, q1=None)]
    with pytest.raises((QualifyingValidationError, ValueError)) as exc_info:
        _validated(event=_event(roster), payload=_payload(results))
    assert getattr(exc_info.value, "code", None) == code


def test_unclassified_model_position_must_not_conflict_with_modeled_entrant():
    from src.pipeline.qualifying import QualifyingValidationError

    roster = [
        _roster_record("driver_one"),
        _roster_record("driver_two", exception=_no_lap_exception(1)),
    ]
    results = [_result("driver_one", "1"), _result("driver_two", None, q1=None)]
    with pytest.raises(QualifyingValidationError) as exc_info:
        _validated(event=_event(roster), payload=_payload(results))
    assert exc_info.value.code == "duplicate_model_position"


def test_confirmed_substitution_and_withdrawal_are_respected():
    withdrawn = _roster_record(
        "driver_two",
        expected=False,
        eligible=False,
        participation="withdrawn",
        exception={
            "kind": "withdrawn",
            "reason": "Official withdrawal",
            "source_url": "https://example.test/entry-list",
            "observed_at": "2026-10-23T12:00:00Z",
        },
    )
    substitute = _roster_record(
        "substitute",
        participation="confirmed_substitute",
        exception={
            "kind": "confirmed_substitute",
            "reason": "Official substitution",
            "source_url": "https://example.test/entry-list",
            "observed_at": "2026-10-23T12:00:00Z",
            "replaces_driver_id": "driver_two",
        },
    )
    results = [_result("driver_one", "1"), _result("substitute", "2")]

    accepted = _validated(event=_event([_roster_record("driver_one"), withdrawn, substitute]), payload=_payload(results))

    assert set(accepted.rows["driver_id"]) == {"driver_one", "substitute"}
    assert set(accepted.roster.loc[accepted.roster["eligible"], "driver_id"]) == {
        "driver_one",
        "substitute",
    }


def test_inactive_known_result_is_retained_but_not_modeled():
    withdrawn = _roster_record(
        "driver_two",
        expected=False,
        eligible=False,
        participation="withdrawn",
        exception={
            "kind": "withdrawn",
            "reason": "Official withdrawal",
            "source_url": "https://example.test/entry-list",
            "observed_at": "2026-10-23T12:00:00Z",
        },
    )
    accepted = _validated(
        event=_event([_roster_record("driver_one"), withdrawn]),
        payload=_payload([_result("driver_one", "1"), _result("driver_two", "2")]),
    )
    row = accepted.rows.set_index("driver_id").loc["driver_two"]
    assert bool(row["eligible"]) is False


def test_source_version_ignores_order_fetch_time_and_page_layout_but_tracks_semantics():
    from src.pipeline.qualifying import validate_qualifying

    results = _valid_results()
    one_page, _ = _fetch([_payload(results)])
    split, _ = _fetch(
        [
            _payload([results[1]], total=2, limit=1, offset=0),
            _payload([results[0]], total=2, limit=1, offset=1),
        ]
    )
    split.page_evidence.retrieval_metadata[0]["retrieved_at"] = "2099-01-01T00:00:00Z"
    version_one = validate_qualifying(_event(), one_page.rows, one_page.page_evidence).source_version
    version_split = validate_qualifying(_event(), split.rows, split.page_evidence).source_version

    changed = copy.deepcopy(results)
    changed[1]["Q1"] = "1:20.600"
    changed_fetch, _ = _fetch([_payload(changed)])
    version_changed = validate_qualifying(
        _event(), changed_fetch.rows, changed_fetch.page_evidence
    ).source_version

    assert version_one == version_split
    assert version_changed != version_one


def test_source_version_normalizes_equivalent_timing_text():
    from src.pipeline.qualifying import validate_qualifying

    colon_results = _valid_results()
    seconds_results = copy.deepcopy(colon_results)
    seconds_results[0]["Q1"] = "80.1000"
    seconds_results[0]["Q2"] = "79.900"
    seconds_results[0]["Q3"] = "79.8000"
    seconds_results[1]["Q1"] = "80.500"
    colon_fetch, _ = _fetch([_payload(colon_results)])
    seconds_fetch, _ = _fetch([_payload(seconds_results)])

    colon_version = validate_qualifying(
        _event(), colon_fetch.rows, colon_fetch.page_evidence
    ).source_version
    seconds_version = validate_qualifying(
        _event(), seconds_fetch.rows, seconds_fetch.page_evidence
    ).source_version

    assert colon_version == seconds_version


@pytest.mark.parametrize(
    ("colon_time", "seconds_time"),
    [("1:01.029", "61.029"), ("1:00.009", "60.009"), ("2:03.001", "123.001")],
)
def test_millisecond_timing_formats_have_identical_times_gaps_and_version(
    colon_time, seconds_time
):
    colon_results = [
        _result("driver_one", "1", q1=colon_time),
        _result("driver_two", "2", q1="180.000"),
    ]
    seconds_results = copy.deepcopy(colon_results)
    seconds_results[0]["Q1"] = seconds_time

    colon = _validated(payload=_payload(colon_results))
    seconds = _validated(payload=_payload(seconds_results))

    derived_columns = [
        "driver_id",
        "best_qualifying_time_seconds",
        "quali_time_gap_to_pole",
        "model_quali_time_gap_to_pole",
    ]
    pd.testing.assert_frame_equal(
        colon.rows[derived_columns], seconds.rows[derived_columns], check_exact=True
    )
    assert colon.source_version == seconds.source_version


def test_validation_rejects_rows_tampered_after_fetch():
    from src.pipeline.qualifying import QualifyingValidationError, validate_qualifying

    fetched, _ = _fetch([_payload(_valid_results())])
    tampered = fetched.rows.copy()
    tampered.loc[tampered.driver_id == "driver_two", "q1"] = "1:10.000"

    with pytest.raises(QualifyingValidationError) as exc_info:
        validate_qualifying(_event(), tampered, fetched.page_evidence)
    assert exc_info.value.code == "rows_do_not_match_evidence"


def test_replace_target_rows_is_pure_and_preserves_other_events():
    from src.pipeline.qualifying import replace_target_rows

    existing = pd.DataFrame(
        [
            {"season": 2026, "round": 19, "driver_id": "old", "quali_position": 1},
            {"season": 2026, "round": 20, "driver_id": "stale", "quali_position": 1},
        ]
    )
    accepted = pd.DataFrame(
        [{"season": 2026, "round": 20, "driver_id": "new", "quali_position": 2}]
    )
    before = existing.copy(deep=True)

    merged = replace_target_rows(existing, accepted, 2026, 20)

    pd.testing.assert_frame_equal(existing, before)
    assert merged[["round", "driver_id"]].to_records(index=False).tolist() == [
        (19, "old"),
        (20, "new"),
    ]


@pytest.mark.parametrize(
    ("accepted", "code"),
    [
        (pd.DataFrame(), "empty_accepted_rows"),
        (
            pd.DataFrame(
                [
                    {"season": 2026, "round": 20, "driver_id": "one"},
                    {"season": 2026, "round": 19, "driver_id": "two"},
                ]
            ),
            "mixed_event_rows",
        ),
        (
            pd.DataFrame(
                [
                    {"season": 2026, "round": 20, "driver_id": "one"},
                    {"season": 2026, "round": 20, "driver_id": "one"},
                ]
            ),
            "duplicate_accepted_rows",
        ),
    ],
)
def test_replace_target_rows_rejects_invalid_input(accepted, code):
    from src.pipeline.qualifying import QualifyingValidationError, replace_target_rows

    with pytest.raises(QualifyingValidationError) as exc_info:
        replace_target_rows(pd.DataFrame(), accepted, 2026, 20)
    assert exc_info.value.code == code


@pytest.mark.parametrize("missing_field", ["season", "round"])
def test_replace_target_rows_rejects_nullable_missing_identity_without_mutation(missing_field):
    from src.pipeline.qualifying import QualifyingValidationError, replace_target_rows

    existing = pd.DataFrame(
        [{"season": 2026, "round": 19, "driver_id": "other_event"}]
    )
    accepted = pd.DataFrame(
        {
            "season": pd.array([2026, 2026], dtype="Int64"),
            "round": pd.array([20, 20], dtype="Int64"),
            "driver_id": ["one", "two"],
        }
    )
    accepted.loc[1, missing_field] = pd.NA
    existing_before = existing.copy(deep=True)
    accepted_before = accepted.copy(deep=True)

    with pytest.raises(QualifyingValidationError) as exc_info:
        replace_target_rows(existing, accepted, 2026, 20)
    assert exc_info.value.code == "mixed_event_rows"
    pd.testing.assert_frame_equal(existing, existing_before)
    pd.testing.assert_frame_equal(accepted, accepted_before)


@pytest.mark.parametrize("driver_id", [None, pd.NA, float("nan"), "", " \t", 23, False])
def test_replace_target_rows_rejects_invalid_driver_id_without_mutation(driver_id):
    from src.pipeline.qualifying import QualifyingValidationError, replace_target_rows

    existing = pd.DataFrame(
        [{"season": 2026, "round": 19, "driver_id": "other_event"}]
    )
    accepted = pd.DataFrame(
        [
            {"season": 2026, "round": 20, "driver_id": "valid"},
            {"season": 2026, "round": 20, "driver_id": driver_id},
        ]
    )
    existing_before = existing.copy(deep=True)
    accepted_before = accepted.copy(deep=True)

    with pytest.raises(QualifyingValidationError) as exc_info:
        replace_target_rows(existing, accepted, 2026, 20)
    assert exc_info.value.code == "invalid_accepted_driver"
    pd.testing.assert_frame_equal(existing, existing_before)
    pd.testing.assert_frame_equal(accepted, accepted_before)
