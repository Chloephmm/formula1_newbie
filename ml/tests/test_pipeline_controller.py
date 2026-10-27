"""Narrow generation-seam tests; scheduling and publication belong to later tasks."""
from __future__ import annotations

import pandas as pd
import pytest

from test_forecast import CaptureClassifier, _accepted, _entries, _event, _history

pytestmark = pytest.mark.filterwarnings("error::FutureWarning")


def test_actual_candidate_trains_stage_two_on_filtered_history_after_hash_change(monkeypatch):
    from src.pipeline import controller

    trained = []
    podium = CaptureClassifier()

    def train(cutoff, **kwargs):
        trained.append((cutoff, kwargs))
        return podium

    monkeypatch.setattr(controller, "train_podium_live", train)
    candidate = controller.generate_actual_candidate(
        _event(), history=_history(), entries=_entries(), qualifying=_accepted(),
        input_hash="semantic-input-v1",
    )

    assert candidate["status"] == "success"
    assert candidate["mode"] == "actual_qualifying"
    assert candidate["input_hash"] == "semantic-input-v1"
    assert len(trained) == 1
    cutoff, kwargs = trained[0]
    assert cutoff == pd.Timestamp("2026-02-01T00:00:00Z")
    assert set(zip(kwargs["results"]["season"], kwargs["results"]["round"])) == {(2026, 1)}
    assert set(zip(kwargs["qualifying"]["season"], kwargs["qualifying"]["round"])) == {(2026, 1)}
    assert kwargs["target_season"] == 2026
    assert kwargs["target_round"] == 2


def test_actual_candidate_reuses_only_same_successful_context_without_fitting(monkeypatch):
    from src.pipeline import controller

    previous = {
        "status": "success", "mode": "actual_qualifying",
        "event": {"season": 2026, "round": 2},
        "training_cutoff": "2026-02-01T00:00:00+00:00",
        "qualifying_source_version": "a" * 64,
        "input_hash": "semantic-input-v1",
        "forecast": {"saved": "initial candidate stays immutable"},
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("unchanged successful candidate must not refit")

    monkeypatch.setattr(controller, "train_podium_live", forbidden)
    reused = controller.generate_actual_candidate(
        _event(), history=_history(), entries=_entries(), qualifying=_accepted(),
        input_hash="semantic-input-v1", previous_candidate=previous,
    )

    assert reused is previous
    assert reused["forecast"] == {"saved": "initial candidate stays immutable"}


def test_same_hash_in_wrong_context_does_not_reuse(monkeypatch):
    from src.pipeline import controller

    calls = []
    monkeypatch.setattr(
        controller, "train_podium_live",
        lambda *args, **kwargs: calls.append((args, kwargs)) or CaptureClassifier(),
    )
    wrong_event_candidate = {
        "status": "success", "mode": "actual_qualifying",
        "event": {"season": 2026, "round": 1},
        "training_cutoff": "2026-02-01T00:00:00+00:00",
        "qualifying_source_version": "a" * 64,
        "input_hash": "semantic-input-v1", "forecast": {"wrong": "event"},
    }

    result = controller.generate_actual_candidate(
        _event(), history=_history(), entries=_entries(), qualifying=_accepted(),
        input_hash="semantic-input-v1", previous_candidate=wrong_event_candidate,
    )

    assert len(calls) == 1
    assert result is not wrong_event_candidate
    assert result["event"] == {"season": 2026, "round": 2}


def test_invalid_actual_inputs_never_train(monkeypatch):
    from src.pipeline import controller

    incomplete = _accepted(rows=[_accepted().rows.iloc[0].to_dict()])

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid inputs must be rejected before training")

    monkeypatch.setattr(controller, "train_podium_live", forbidden)
    try:
        controller.generate_actual_candidate(
            _event(), history=_history(), entries=_entries(), qualifying=incomplete,
            input_hash="semantic-input-v1",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete qualifying was accepted")


def test_train_podium_live_builds_only_from_filtered_raw_history(monkeypatch):
    from src.model import retrain

    fitted = []

    class FakeCalibrator:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self, frame, target):
            fitted.append((frame.copy(deep=True), target.copy(deep=True)))
            return self

    monkeypatch.setattr(retrain, "CalibratedClassifierCV", FakeCalibrator)
    history = _history()
    retrain.train_podium_live(
        pd.Timestamp("2026-02-01T00:00:00Z"),
        results=history["results"], qualifying=history["qualifying"],
        target_season=2026, target_round=2,
    )

    assert len(fitted) == 1
    frame, target = fitted[0]
    assert frame["grid_position"].tolist() == [5.0, 5.0]
    assert len(target) == 2


def test_retrain_live_uses_one_recorded_cutoff_snapshot_for_both_stages(monkeypatch):
    from src.model import retrain

    podium_fits, qualifying_fits = [], []

    class FakeCalibrator:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self, frame, target):
            podium_fits.append((frame.copy(deep=True), target.copy(deep=True)))
            return self

    class FakeRegressor:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self, frame, target):
            qualifying_fits.append((frame.copy(deep=True), target.copy(deep=True)))
            return self

    monkeypatch.setattr(retrain, "CalibratedClassifierCV", FakeCalibrator)
    monkeypatch.setattr(retrain.lgb, "LGBMRegressor", FakeRegressor)

    retrain.retrain_live("2026-02-01", 2026, 2, history=_history())

    assert len(podium_fits[0][1]) == 2
    assert len(qualifying_fits[0][1]) == 2


def test_stage_one_accepts_mixed_legacy_and_task3_enriched_qualifying(monkeypatch):
    from src.model import retrain
    from src.pipeline.qualifying import (
        fetch_target_qualifying,
        replace_target_rows,
        validate_qualifying,
    )
    from test_qualifying_validation import (
        _event as qualifying_event,
        _payload,
        _result as qualifying_result,
        _roster_record,
    )

    canonical = qualifying_event(
        roster=[
            _roster_record("driver_a", "team_a"),
            _roster_record("driver_b", "team_b"),
        ],
        round=2,
        circuit_id="target_ring",
    )
    payload = _payload(
        [
            qualifying_result("driver_a", "1", constructor_id="team_a", q1="1:19.000"),
            qualifying_result("driver_b", "2", constructor_id="team_b", q1="1:19.750"),
        ],
        round_number=2,
        circuit_id="target_ring",
    )
    fetched = fetch_target_qualifying(2026, 2, lambda path, params: payload)
    accepted = validate_qualifying(canonical, fetched.rows, fetched.page_evidence)
    history = _history()
    mixed_qualifying = replace_target_rows(
        history["qualifying"], accepted.rows, 2026, 2
    )
    original_results = history["results"].copy(deep=True)
    original_qualifying = mixed_qualifying.copy(deep=True)
    fits = []

    class FakeRegressor:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self, frame, target):
            fits.append((frame.copy(deep=True), target.copy(deep=True)))
            return self

    monkeypatch.setattr(retrain.lgb, "LGBMRegressor", FakeRegressor)
    retrain.train_quali_live(
        2026,
        3,
        results=history["results"],
        qualifying=mixed_qualifying,
        cutoff_date="2026-03-01T00:00:00Z",
    )

    assert mixed_qualifying.loc[mixed_qualifying["round"] == 1, "circuit_id"].isna().all()
    assert set(mixed_qualifying.loc[mixed_qualifying["round"] == 2, "circuit_id"]) == {
        "target_ring"
    }
    assert len(fits) == 1
    assert len(fits[0][1]) == 4
    pd.testing.assert_frame_equal(history["results"], original_results)
    pd.testing.assert_frame_equal(mixed_qualifying, original_qualifying)
