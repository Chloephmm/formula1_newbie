"""Stage-2 forecasting from validated actual qualifying results."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model import forecast as forecast_module


class _PodiumModel:
    def predict_proba(self, X):
        probability = 1.0 / (pd.to_numeric(X["grid_position"]) + 1.0)
        probability = np.asarray(probability, dtype=float)
        return np.column_stack([1.0 - probability, probability])


def _history():
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "date": "2026-03-08",
                "circuit_id": "old_track",
                "driver_id": "known",
                "code": "KNO",
                "driver_name": "Known Driver",
                "constructor_id": "team_a",
                "constructor_name": "Team A",
                "position": 4,
                "points": 12,
                "status": "Finished",
                "grid": 3,
                "quali_gap": 0.2,
                "quali_position": 3,
            }
        ]
    )


def _actual_rows():
    return (
        {
            "season": 2026,
            "round": 2,
            "race_name": "Test Grand Prix",
            "circuit_id": "test_track",
            "driver_id": "known",
            "code": "KNO",
            "driver_name": "Known Driver",
            "constructor_id": "team_a",
            "constructor_name": "Team A",
            "qualifying_position": 1,
            "qualifying_gap_seconds": 0.0,
        },
        {
            "season": 2026,
            "round": 2,
            "race_name": "Test Grand Prix",
            "circuit_id": "test_track",
            "driver_id": "reserve",
            "code": "RES",
            "driver_name": "Reserve Driver",
            "constructor_id": "team_b",
            "constructor_name": "Team B",
            "qualifying_position": 2,
            "qualifying_gap_seconds": 0.7,
        },
    )


def test_actual_stage_two_includes_substitute_and_uses_neutral_history(monkeypatch):
    monkeypatch.setattr(forecast_module, "_historical_driver_table", lambda target_date: _history())
    base = {
        "error": None,
        "race": {
            "name": "Test Grand Prix",
            "season": 2026,
            "round": 2,
            "country": "Testland",
            "date": "2026-03-15",
            "qualifyingDate": "2026-03-14",
        },
        "predictedQualifying": [],
        "preQualifyingPodium": [],
    }

    result = forecast_module.forecast_actual_qualifying(
        base_forecast=base,
        actual_qualifying=_actual_rows(),
        podium_model=_PodiumModel(),
        target_date="2026-03-15",
    )

    assert result["inputMode"] == "actual_qualifying"
    assert [row["code"] for row in result["actualQualifying"]] == ["KNO", "RES"]
    assert {row["driverName"] for row in result["actualQualifyingPodium"]} == {
        "Known Driver",
        "Reserve Driver",
    }
    assert sum(row["podiumProbability"] for row in result["actualQualifyingPodium"]) == pytest.approx(3.0)


def test_actual_stage_two_rejects_event_mismatch():
    base = {
        "error": None,
        "race": {"name": "Other", "season": 2026, "round": 3, "date": "2026-03-15"},
    }

    with pytest.raises(ValueError, match="does not match"):
        forecast_module.forecast_actual_qualifying(
            base_forecast=base,
            actual_qualifying=_actual_rows(),
            podium_model=_PodiumModel(),
            target_date="2026-03-15",
        )
