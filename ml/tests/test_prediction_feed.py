"""Published-feed validation and selector behavior."""
from __future__ import annotations

import json

import pytest

from streamlit_app.prediction_feed import FeedError, choose_race, load_bundle, load_index


def _artifact():
    return {
        "schema_version": 2,
        "race_id": "2026-4",
        "race": {"name": "Miami Grand Prix", "season": 2026, "round": 4},
        "forecast": {
            "error": None,
            "race": {"name": "Miami Grand Prix", "season": 2026, "round": 4},
            "predictedQualifying": [{"position": 1, "code": "AAA", "gap": 0}],
            "preQualifyingPodium": [{"code": "AAA", "podiumProbability": 3.0}],
        },
        "input_mode": "estimated_qualifying",
        "prediction_updated_at": "2026-05-01T00:00:00Z",
        "qualifying_input_hash": None,
        "publication_cutoff_at": "2026-05-03T18:00:00Z",
        "frozen_at": None,
        "status_reason": "actual_qualifying_not_checked_yet",
    }


def test_loads_local_archive_and_active_status(tmp_path):
    (tmp_path / "predictions").mkdir()
    artifact = _artifact()
    index = {
        "schema_version": 2,
        "active_race_id": "2026-4",
        "races": [{"race_id": "2026-4", "race_name": "Miami Grand Prix", "artifact_url": "predictions/2026-4.json"}],
    }
    status = {"schema_version": 2, "race_id": "2026-4", "state": "estimated_waiting"}
    (tmp_path / "predictions" / "index.json").write_text(json.dumps(index))
    (tmp_path / "predictions" / "2026-4.json").write_text(json.dumps(artifact))
    (tmp_path / "prediction_status.json").write_text(json.dumps(status))

    bundle = load_bundle(tmp_path, base_url=None, race_id="2026-4")

    assert bundle.artifact["race_id"] == "2026-4"
    assert bundle.status["state"] == "estimated_waiting"


def test_rejects_malformed_or_incompatible_artifact(tmp_path):
    (tmp_path / "predictions").mkdir()
    index = {
        "schema_version": 2,
        "active_race_id": "2026-4",
        "races": [{"race_id": "2026-4", "race_name": "Miami", "artifact_url": "predictions/2026-4.json"}],
    }
    (tmp_path / "predictions" / "index.json").write_text(json.dumps(index))
    (tmp_path / "predictions" / "2026-4.json").write_text("{}")
    (tmp_path / "prediction_status.json").write_text("{}")

    with pytest.raises(FeedError, match="schema_version"):
        load_bundle(tmp_path, base_url=None, race_id="2026-4")


def test_selector_defaults_active_but_retains_valid_historical_selection():
    available = ["2026-4", "2026-3", "2026-2"]
    assert choose_race("2026-4", available, None) == "2026-4"
    assert choose_race("2026-4", available, "2026-3") == "2026-3"
    assert choose_race("2026-4", available, "2025-1") == "2026-4"
    assert choose_race("2026-4", available, "2026-3", "2026-3") == "2026-4"
    assert choose_race("2026-4", available, "2026-2", "2026-3") == "2026-2"


def test_monday_active_snapshot_rolls_forward_before_archive_index_catches_up(tmp_path):
    (tmp_path / "predictions").mkdir()
    old_index = {
        "schema_version": 2,
        "active_race_id": "2026-3",
        "races": [{
            "race_id": "2026-3", "season": 2026, "round": 3,
            "race_name": "Japanese Grand Prix", "artifact_url": "predictions/2026-3.json",
        }],
    }
    active = _artifact()
    (tmp_path / "predictions" / "index.json").write_text(json.dumps(old_index))
    (tmp_path / "next_race_prediction.json").write_text(json.dumps(active))
    (tmp_path / "prediction_status.json").write_text(json.dumps({
        "schema_version": 2, "race_id": "2026-3", "state": "frozen_actual"
    }))

    index = load_index(tmp_path, base_url=None)
    bundle = load_bundle(tmp_path, base_url=None, race_id="2026-4", index=index)

    assert index["active_race_id"] == "2026-4"
    assert bundle.artifact["race_id"] == "2026-4"
    assert bundle.status is None


def test_next_poll_switches_from_estimated_to_actual_without_user_action(tmp_path):
    (tmp_path / "predictions").mkdir()
    index = {
        "schema_version": 2,
        "active_race_id": "2026-4",
        "races": [{
            "race_id": "2026-4", "season": 2026, "round": 4,
            "race_name": "Miami Grand Prix", "artifact_url": "predictions/2026-4.json",
        }],
    }
    estimated = _artifact()
    (tmp_path / "predictions" / "index.json").write_text(json.dumps(index))
    (tmp_path / "next_race_prediction.json").write_text(json.dumps(estimated))
    (tmp_path / "prediction_status.json").write_text(json.dumps({
        "schema_version": 2, "race_id": "2026-4", "state": "estimated_waiting"
    }))

    first_poll = load_bundle(
        tmp_path, base_url=None, race_id="2026-4", index=load_index(tmp_path, base_url=None)
    )
    actual = _artifact()
    actual["input_mode"] = "actual_qualifying"
    actual["forecast"]["actualQualifying"] = actual["forecast"]["predictedQualifying"]
    actual["forecast"]["actualQualifyingPodium"] = actual["forecast"]["preQualifyingPodium"]
    (tmp_path / "next_race_prediction.json").write_text(json.dumps(actual))
    (tmp_path / "prediction_status.json").write_text(json.dumps({
        "schema_version": 2, "race_id": "2026-4", "state": "actual_published"
    }))

    second_poll = load_bundle(
        tmp_path, base_url=None, race_id="2026-4", index=load_index(tmp_path, base_url=None)
    )

    assert first_poll.artifact["input_mode"] == "estimated_qualifying"
    assert second_poll.artifact["input_mode"] == "actual_qualifying"
    assert second_poll.status["state"] == "actual_published"
