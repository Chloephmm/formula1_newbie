"""Deterministic contract tests for explicit event forecasting."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model.data import FEATURES
from src.model.forecast import build_event_features, forecast_event
from src.model.quali import QUALI_FEATURES
from src.pipeline.qualifying import AcceptedQualifying, QualifyingValidationError


def _event(**updates):
    event = {
        "season": 2026,
        "round": 2,
        "race_name": "Target Grand Prix",
        "circuit_id": "target_ring",
        "date": "2026-02-01",
        "training_cutoff": "2026-02-01T00:00:00Z",
    }
    event.update(updates)
    return event


def _entries():
    return [
        {"driver_id": "driver_a", "code": "AAA", "driver_name": "Driver A",
         "constructor_id": "team_a", "constructor_name": "Team A",
         "eligible": True, "expected": True},
        {"driver_id": "driver_b", "code": "BBB", "driver_name": "Driver B",
         "constructor_id": "team_b", "constructor_name": "Team B",
         "eligible": True, "expected": True},
    ]


def _result(season, round_number, date, driver_id, position, *, circuit="old_ring", grid=None):
    suffix = driver_id[-1]
    return {
        "season": season, "round": round_number, "race_name": f"Race {round_number}",
        "circuit_id": circuit, "date": date, "driver_id": driver_id,
        "code": f"{suffix.upper()}AA", "driver_name": f"Historical {suffix.upper()}",
        "constructor_id": f"team_{suffix}",
        "constructor_name": f"Historical Team {suffix.upper()}",
        "position": position, "points": max(0, 10 - position),
        "status": "Finished", "grid": position if grid is None else grid,
    }


def _quali(season, round_number, driver_id, position, q1):
    suffix = driver_id[-1]
    return {
        "season": season, "round": round_number, "driver_id": driver_id,
        "code": f"{suffix.upper()}AA", "constructor_id": f"team_{suffix}",
        "quali_position": position, "q1": q1, "q2": None, "q3": None,
    }


def _history():
    results = pd.DataFrame([
        _result(2026, 1, "2026-01-01", "driver_a", 2, grid=0),
        _result(2026, 1, "2026-01-01", "driver_b", 5),
        _result(2026, 2, "2026-02-01", "driver_a", 19, circuit="target_ring"),
        _result(2026, 2, "2026-02-01", "driver_b", 20, circuit="target_ring"),
        _result(2026, 3, "2026-03-01", "driver_a", 18),
        _result(2026, 3, "2026-03-01", "driver_b", 17),
        # Each half of the identity/date guard is independently hostile.
        _result(2025, 99, "2026-04-01", "driver_a", 1, grid=999),
        _result(2027, 1, "2025-01-01", "driver_b", 1, grid=999),
    ])
    qualifying = pd.DataFrame([
        _quali(2026, 1, "driver_a", 2, "1:20.000"),
        _quali(2026, 1, "driver_b", 5, "1:21.500"),
        _quali(2026, 2, "driver_a", 20, "1:40.000"),
        _quali(2026, 2, "driver_b", 19, "1:39.000"),
        _quali(2025, 99, "driver_a", 1, "1:00.000"),
    ])
    return {"results": results, "qualifying": qualifying}


class CaptureRegressor:
    def __init__(self, values=(1.2, 0.2)):
        self.values = np.asarray(values, dtype=float)
        self.calls = []

    def predict(self, frame):
        self.calls.append(frame.copy(deep=True))
        return self.values.copy()


class CaptureClassifier:
    def __init__(self, probabilities=(0.2, 0.7)):
        self.probabilities = np.asarray(probabilities, dtype=float)
        self.calls = []

    def predict_proba(self, frame):
        self.calls.append(frame.copy(deep=True))
        return np.column_stack([1.0 - self.probabilities, self.probabilities])


def _accepted(rows=None, roster=None):
    accepted_rows = pd.DataFrame(rows or [
        {"season": 2026, "round": 2, "race_name": "Target Grand Prix",
         "circuit_id": "target_ring", "driver_id": "driver_a", "code": "AAA",
         "constructor_id": "team_a", "quali_position": 1, "q1": "1:19.000",
         "q2": None, "q3": None, "best_qualifying_time_seconds": 79.0,
         "quali_time_gap_to_pole": 0.0, "model_quali_time_gap_to_pole": 0.0,
         "model_position": 1, "eligible": True},
        {"season": 2026, "round": 2, "race_name": "Target Grand Prix",
         "circuit_id": "target_ring", "driver_id": "driver_b", "code": "BBB",
         "constructor_id": "team_b", "quali_position": 2, "q1": None,
         "q2": None, "q3": None, "best_qualifying_time_seconds": None,
         "quali_time_gap_to_pole": None, "model_quali_time_gap_to_pole": 0.75,
         "model_position": 2, "eligible": True},
    ])
    return AcceptedQualifying(
        rows=accepted_rows, roster=pd.DataFrame(roster or _entries()),
        source_version="a" * 64, notes=("fixture",),
        imputation_policy={"no_lap_model_gap": "largest_valid_event_gap"},
    )


def test_build_event_features_filters_raw_history_before_feature_building():
    history = _history()
    original = {name: frame.copy(deep=True) for name, frame in history.items()}

    features = build_event_features(_event(), history, _entries())

    by_driver = features.set_index("driver_id")
    assert by_driver.loc["driver_a", "recent_form"] == 2
    assert by_driver.loc["driver_b", "recent_form"] == 5
    assert by_driver.loc["driver_a", "recent_quali_gap"] == 0
    assert by_driver.loc["driver_b", "recent_quali_gap"] == pytest.approx(1.5)
    assert by_driver.loc["driver_a", "name"] == "Driver A"
    assert by_driver.loc["driver_a", "team"] == "Team A"
    for name in history:
        pd.testing.assert_frame_equal(history[name], original[name])


def test_predicted_mode_sends_stage_one_estimates_to_stage_two_exactly():
    quali, podium = CaptureRegressor(), CaptureClassifier()
    result = forecast_event(
        _event(), mode="predicted_qualifying", history=_history(), entries=_entries(),
        models={"quali": quali, "podium": podium},
    )

    assert len(quali.calls) == 1
    assert list(quali.calls[0].columns) == QUALI_FEATURES
    assert len(podium.calls) == 1
    assert list(podium.calls[0].columns) == FEATURES
    assert podium.calls[0]["grid_position"].tolist() == [2.0, 1.0]
    assert podium.calls[0]["quali_time_gap_to_pole"].tolist() == [1.0, 0.0]
    assert [row["position"] for row in result["predictedQualifying"]] == [1, 2]
    assert result["mode"] == "predicted_qualifying"
    assert result["hasRealGrid"] is False
    assert result["realGridPodium"] is None


def test_tied_stage_one_predictions_use_canonical_driver_order():
    first = forecast_event(
        _event(), mode="predicted_qualifying", history=_history(), entries=_entries(),
        models={"quali": CaptureRegressor((0.5, 0.5)), "podium": CaptureClassifier()},
    )
    second = forecast_event(
        _event(), mode="predicted_qualifying", history=_history(),
        entries=list(reversed(_entries())),
        models={"quali": CaptureRegressor((0.5, 0.5)), "podium": CaptureClassifier()},
    )

    assert first["predictedQualifying"] == second["predictedQualifying"]
    assert [row["code"] for row in first["predictedQualifying"]] == ["AAA", "BBB"]


def test_actual_mode_skips_stage_one_and_preserves_official_values():
    podium = CaptureClassifier()
    result = forecast_event(
        _event(), mode="actual_qualifying", history=_history(), entries=_entries(),
        models={"podium": podium}, qualifying=_accepted(),
    )

    assert len(podium.calls) == 1
    assert podium.calls[0]["grid_position"].tolist() == [1.0, 2.0]
    assert podium.calls[0]["quali_time_gap_to_pole"].tolist() == [0.0, 0.75]
    assert result["predictedQualifying"] == []
    assert result["preQualifyingPodium"] == []
    assert result["mode"] == "actual_qualifying"
    assert result["hasRealGrid"] is True
    assert [row["position"] for row in result["realQualifying"]] == [1, 2]
    assert [row["gap"] for row in result["realQualifying"]] == [0.0, None]


@pytest.mark.parametrize("qualifying", [None, _accepted(rows=[_accepted().rows.iloc[0].to_dict()])])
def test_actual_mode_rejects_missing_or_incomplete_qualifying_before_model(qualifying):
    podium = CaptureClassifier()
    with pytest.raises(QualifyingValidationError):
        forecast_event(
            _event(), mode="actual_qualifying", history=_history(), entries=_entries(),
            models={"podium": podium}, qualifying=qualifying,
        )
    assert podium.calls == []


def test_actual_mode_rechecks_exact_event_and_unique_finite_model_inputs():
    podium = CaptureClassifier()
    invalid = []
    wrong_event = _accepted()
    wrong_event.rows.loc[0, "round"] = 1
    invalid.append(wrong_event)
    duplicate_position = _accepted()
    duplicate_position.rows["model_position"] = [1, 1]
    invalid.append(duplicate_position)
    non_finite_gap = _accepted()
    non_finite_gap.rows.loc[1, "model_quali_time_gap_to_pole"] = np.inf
    invalid.append(non_finite_gap)
    fractional_official = _accepted()
    fractional_official.rows["quali_position"] = [1.0, 2.5]
    invalid.append(fractional_official)
    missing_source_version = _accepted()
    missing_source_version.source_version = ""
    invalid.append(missing_source_version)
    for qualifying in invalid:
        with pytest.raises(QualifyingValidationError):
            forecast_event(
                _event(), mode="actual_qualifying", history=_history(), entries=_entries(),
                models={"podium": podium}, qualifying=qualifying,
            )
    assert podium.calls == []


def test_predicted_mode_rejects_supplied_qualifying():
    with pytest.raises(ValueError, match="must be None"):
        forecast_event(
            _event(), mode="predicted_qualifying", history=_history(), entries=_entries(),
            models={"quali": CaptureRegressor(), "podium": CaptureClassifier()},
            qualifying=_accepted(),
        )


@pytest.mark.parametrize("invalid", [True, 2026.5])
def test_event_identity_rejects_lossy_integer_coercion_before_models(invalid):
    event = _event(season=invalid)
    with pytest.raises(ValueError, match="integer season and round"):
        forecast_event(
            event, mode="predicted_qualifying", history=_history(), entries=_entries(),
            models={"quali": CaptureRegressor(), "podium": CaptureClassifier()},
        )


def test_training_cutoff_cannot_be_later_than_known_event_time():
    event = _event(training_cutoff="2026-02-02T00:00:00Z")
    with pytest.raises(ValueError, match="later than the known event"):
        build_event_features(event, _history(), _entries())


def test_canonical_qualifying_start_supplies_display_date_without_estimation():
    result = forecast_event(
        _event(qualifying_start_at="2026-01-31T18:00:00Z"),
        mode="predicted_qualifying", history=_history(), entries=_entries(),
        models={"quali": CaptureRegressor(), "podium": CaptureClassifier()},
    )

    assert result["race"]["qualifyingDate"] == "2026-01-31"
    assert result["race"]["qualifyingDateEstimated"] is False
    assert result["race"]["qualifyingDateSource"] == "event-qualifying-start"


def test_real_qualifying_validation_composes_with_actual_forecast():
    from test_qualifying_validation import (
        _event as qualifying_event,
        _payload,
        _result as qualifying_result,
        _roster_record,
        _validated,
    )

    substitute = _roster_record(
        "driver_three", "team_c", participation="confirmed_substitute",
        exception={
            "kind": "confirmed_substitute", "reason": "documented replacement",
            "source_url": "https://example.test/replacement",
            "observed_at": "2026-10-20T13:00:00Z",
            "replaces_driver_id": "driver_four", "allow_model_position": False,
        },
    )
    withdrawn = _roster_record(
        "driver_four", "team_c", expected=False, eligible=False,
        participation="withdrawn",
        exception={
            "kind": "withdrawn", "reason": "documented withdrawal",
            "source_url": "https://example.test/withdrawal",
            "observed_at": "2026-10-20T12:30:00Z",
            "allow_model_position": False,
        },
    )
    unclassified = _roster_record(
        "driver_five", "team_d",
        exception={
            "kind": "no_qualifying_lap", "reason": "documented no-lap exception",
            "source_url": "https://example.test/no-lap",
            "observed_at": "2026-10-20T13:15:00Z",
            "allow_model_position": True, "model_position": 7,
        },
    )
    canonical = qualifying_event(
        roster=[
            _roster_record("driver_one", "team_a"),
            _roster_record("driver_two", "team_b"),
            substitute,
            withdrawn,
            unclassified,
        ]
    )
    accepted = _validated(
        event=canonical,
        payload=_payload([
            qualifying_result("driver_one", "1", constructor_id="team_a", q1="1:19.800"),
            qualifying_result("driver_two", "3", constructor_id="team_b", q1="1:20.550"),
            qualifying_result("driver_three", "5", constructor_id="team_c", q1=None),
            qualifying_result("driver_five", None, constructor_id="team_d", q1=None),
        ]),
    )
    event = canonical | {
        "date": "2026-11-01", "training_cutoff": "2026-11-01T00:00:00Z"
    }
    podium = CaptureClassifier((0.1, 0.2, 0.4, 0.3))

    result = forecast_event(
        event, mode="actual_qualifying", history=_history(), entries=canonical["roster"],
        models={"podium": podium}, qualifying=accepted,
    )

    assert podium.calls[0]["grid_position"].tolist() == [7.0, 1.0, 5.0, 3.0]
    assert podium.calls[0]["quali_time_gap_to_pole"].tolist() == [0.75, 0.0, 0.75, 0.75]
    assert [row["position"] for row in result["realQualifying"]] == [1, 3, 5, None]
    assert [row["gap"] for row in result["realQualifying"]] == [0.0, 0.75, None, None]
    substitute_row = next(
        row for row in result["realQualifying"] if row["teamId"] == "team_c"
    )
    assert substitute_row["driverName"] == "Driver Three"
    assert substitute_row["team"] == "Team_C"


def test_offline_wrapper_never_inferrs_actual_mode_from_cached_target_qualifying(monkeypatch):
    import importlib

    forecast_module = importlib.import_module("src.model.forecast")
    history = _history()
    target = pd.Series({
        "season": 2026, "round": 2, "race_name": "Target Grand Prix",
        "circuit_id": "target_ring", "country": "Example", "date": pd.Timestamp("2026-02-01"),
    })
    monkeypatch.setattr(forecast_module, "next_race", lambda asof: target)
    monkeypatch.setattr(forecast_module, "_load", lambda table: history[table].copy(deep=True))

    result = forecast_module.forecast(
        "2026-02-01", models={"quali": CaptureRegressor(), "podium": CaptureClassifier()}
    )

    assert result["hasRealGrid"] is False
    assert result["realQualifying"] is None
    assert result["executionContext"] == "offline-reconstruction"
    assert result["race"]["qualifyingDate"] == "2026-01-31"
    assert result["race"]["qualifyingDateEstimated"] is True
    assert result["race"]["qualifyingDateSource"] == "legacy-race-date-minus-one-display-only"
