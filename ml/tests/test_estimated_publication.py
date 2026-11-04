"""Safety checks for correcting an estimated forecast without rewriting history."""
import copy
from datetime import datetime, timezone

import pytest

from src.publication import publisher
from src.publication.service import PublicationPaths, _atomic_json, read_json


SCHEDULE = {
    "season": 2026, "round": 19, "race_name": "Mexico City Grand Prix",
    "circuit_id": "rodriguez", "qualifying_start_at": "2026-10-31T21:00:00Z",
    "qualifying_end_at": "2026-11-01T00:00:00Z", "end_time_estimated": True,
    "race_start_at": "2026-11-01T20:00:00Z",
    "schedule_updated_at": "2026-10-30T00:00:00Z",
}
NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def forecast():
    return {
        "error": None,
        "race": {"name": SCHEDULE["race_name"], "season": 2026, "round": 19,
                 "raceStartAt": SCHEDULE["race_start_at"],
                 "qualifyingStartAt": SCHEDULE["qualifying_start_at"]},
        "predictedQualifying": [{"position": i + 1, "code": c, "gap": i / 10}
                                for i, c in enumerate("ABCD")],
        "preQualifyingPodium": [{"code": c, "podiumProbability": .75} for c in "ABCD"],
        "training_metadata": {"stage1": {"rows": 10}, "stage2": {"rows": 12}},
    }


def candidate():
    from src.publication.estimated import make_candidate
    return make_candidate(forecast(), SCHEDULE, set("ABCD"), NOW)


def test_estimated_validator_rejects_out_of_range_even_when_sum_is_three():
    value = forecast()
    value["preQualifyingPodium"][0]["podiumProbability"] = 1.5
    value["preQualifyingPodium"][1]["podiumProbability"] = 0
    with pytest.raises(ValueError, match="between zero and one"):
        publisher.validate_forecast_artifact(value, SCHEDULE, set("ABCD"), input_mode="estimated_qualifying")


def test_candidate_carries_provenance_and_correct_cutoff():
    value = candidate()
    assert value["training_metadata"] == forecast()["training_metadata"]
    assert value["publication_cutoff_at"] == "2026-11-01T18:00:00Z"
    assert value["frozen_at"] is None


@pytest.mark.parametrize("field", ["qualifying_start_at", "race_start_at", "schedule_updated_at"])
def test_missing_schedule_values_fail_preflight(field):
    from src.publication.estimated import validate_schedule
    schedule = dict(SCHEDULE, **{field: None})
    with pytest.raises(ValueError):
        validate_schedule(schedule)


@pytest.mark.parametrize("mutation", ["wrong_event", "missing_driver", "duplicate_driver", "nan", "bad_time"])
def test_bad_candidates_rejected(mutation):
    from src.publication.estimated import make_candidate
    value = forecast()
    if mutation == "wrong_event": value["race"]["round"] = 18
    if mutation == "missing_driver": value["predictedQualifying"].pop()
    if mutation == "duplicate_driver": value["preQualifyingPodium"][0]["code"] = "B"
    if mutation == "nan": value["preQualifyingPodium"][0]["podiumProbability"] = float("nan")
    if mutation == "bad_time": value["race"]["raceStartAt"] = "bad"
    with pytest.raises(ValueError):
        make_candidate(value, SCHEDULE, set("ABCD"), NOW)


@pytest.mark.parametrize("protection", ["frozen", "actual", "cutoff", "buffer", "rolled_forward"])
def test_protected_publication_changes_no_files(tmp_path, protection):
    from src.publication.estimated import publish_candidate
    paths = PublicationPaths(tmp_path)
    original = candidate()
    now = NOW
    if protection == "frozen": original["frozen_at"] = "2026-10-29T18:00:00Z"
    if protection == "actual": original["input_mode"] = "actual_qualifying"
    if protection == "cutoff": now = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
    if protection == "buffer": now = datetime(2026, 11, 1, 17, 31, tzinfo=timezone.utc)
    if protection == "rolled_forward": original["race_id"] = "2026-20"
    _atomic_json(paths.active, original)
    _atomic_json(paths.archive(original["race_id"]), original)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(ValueError):
        publish_candidate(paths, candidate(), SCHEDULE, set("ABCD"), clock=lambda: now)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.json")} == before


def test_publish_keeps_four_interfaces_consistent_and_history_unchanged(tmp_path):
    from src.publication.estimated import publish_candidate
    paths = PublicationPaths(tmp_path)
    original = candidate()
    _atomic_json(paths.active, original)
    _atomic_json(paths.archive("2026-18"), {"frozen_at": "2026-10-25T18:00:00Z"})
    old = paths.archive("2026-18").read_bytes()
    publish_candidate(paths, candidate(), SCHEDULE, set("ABCD"), clock=lambda: NOW)
    assert read_json(paths.active) == read_json(paths.archive("2026-19"))
    assert read_json(paths.status)["prediction_updated_at"] == original["prediction_updated_at"]
    assert read_json(paths.index)["active_race_id"] == "2026-19"
    assert paths.archive("2026-18").read_bytes() == old


def test_deadline_rechecked_immediately_before_write(tmp_path):
    from src.publication.estimated import publish_candidate
    paths = PublicationPaths(tmp_path)
    _atomic_json(paths.active, candidate())
    times = iter([NOW, datetime(2026, 11, 1, 18, tzinfo=timezone.utc)])
    before = paths.active.read_bytes()
    with pytest.raises(ValueError, match="cutoff"):
        publish_candidate(paths, candidate(), SCHEDULE, set("ABCD"), clock=lambda: next(times))
    assert paths.active.read_bytes() == before
