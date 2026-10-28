"""Contracts for canonical, immutable prediction artifacts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

import src.pipeline.artifacts as artifacts
from src.pipeline.artifacts import (
    ArtifactCollisionError,
    archive_prediction,
    build_provenance,
    build_prediction,
    canonical_bytes,
    digest,
    _input_payload,
    load_prediction_for_input,
    training_snapshot_hash,
    validate_prediction,
    write_immutable,
)
from src.pipeline.qualifying import AcceptedQualifying


def _roster_record(driver_id: str, position: int) -> dict:
    suffix = driver_id[-1].upper()
    return {
        "driver_id": driver_id,
        "code": f"{suffix * 3}",
        "driver_name": f"Driver {suffix}",
        "constructor_id": f"team_{suffix.lower()}",
        "constructor_name": f"Team {suffix}",
        "number": str(position),
        "eligible": True,
        "expected": True,
        "participation": "confirmed",
        "exception": None,
        "provenance": {
            "source": "previous_completed_race",
            "source_url": "https://example.test/previous",
            "observed_at": "2026-10-20T10:00:00Z",
            "season": 2026,
            "round": 19,
        },
    }


def _event(**updates) -> dict:
    event = {
        "season": 2026,
        "round": 20,
        "race_name": "Artifact Grand Prix",
        "circuit_id": "artifact_ring",
        "qualifying_start_at": "2026-10-31T18:00:00Z",
        "qualifying_end_observed_at": "2026-10-31T19:02:00Z",
        "race_start_at": "2026-11-01T18:00:00Z",
        "roster": [
            _roster_record("driver_a", 1),
            _roster_record("driver_b", 2),
            _roster_record("driver_c", 3),
            _roster_record("driver_d", 4),
        ],
    }
    event.update(updates)
    return event


def _training_snapshot() -> dict:
    return {
        "results": [
            {"season": 2026, "round": 19, "date": "2026-10-25T18:00:00Z",
             "driver_id": "driver_a", "position": 1},
            {"season": 2026, "round": 19, "date": "2026-10-25T18:00:00Z",
             "driver_id": "driver_b", "position": 2},
        ],
        "qualifying": [
            {"season": 2026, "round": 19, "driver_id": "driver_a", "q1": "1:20.100"},
            {"season": 2026, "round": 19, "driver_id": "driver_b", "q1": "1:20.500"},
        ],
    }


def _model_manifest(**updates) -> dict:
    manifest = {
        "code_hash": "c" * 64,
        "parameters": {"num_leaves": 31, "random_state": 42},
        "feature_columns": ["grid_position", "quali_time_gap_to_pole"],
        "library_versions": {"lightgbm": "4.6.0", "scikit-learn": "1.7.2"},
    }
    manifest.update(updates)
    return manifest


def _feature_inputs() -> list[dict]:
    return [
        {"driver_id": f"driver_{letter}", "grid_position": index,
         "quali_time_gap_to_pole": float(index - 1) / 10}
        for index, letter in enumerate("abcd", start=1)
    ]


def _accepted(source_version: str) -> AcceptedQualifying:
    rows = pd.DataFrame([
        {"season": 2026, "round": 20, "driver_id": f"driver_{letter}",
         "constructor_id": f"team_{letter}", "eligible": True,
         "quali_position": index, "quali_time_gap_to_pole": float(index - 1) / 10,
         "model_position": index,
         "model_quali_time_gap_to_pole": float(index - 1) / 10}
        for index, letter in enumerate("abcd", start=1)
    ])
    return AcceptedQualifying(
        rows=rows, roster=pd.DataFrame(_event()["roster"]),
        source_version=source_version, notes=("accepted",),
        imputation_policy={"no_lap_model_gap": "largest_valid_event_gap"},
    )


def _forecast() -> dict:
    podium = [
        {"driver_id": "driver_a", "code": "AAA", "driverName": "Driver A",
         "team": "Team A", "teamId": "team_a", "podiumProbability": 1.0, "rank": 1},
        {"driver_id": "driver_b", "code": "BBB", "driverName": "Driver B",
         "team": "Team B", "teamId": "team_b", "podiumProbability": 0.8, "rank": 2},
        {"driver_id": "driver_c", "code": "CCC", "driverName": "Driver C",
         "team": "Team C", "teamId": "team_c", "podiumProbability": 0.7, "rank": 3},
        {"driver_id": "driver_d", "code": "DDD", "driverName": "Driver D",
         "team": "Team D", "teamId": "team_d", "podiumProbability": 0.5, "rank": 4},
    ]
    return {
        "error": None,
        "mode": "predicted_qualifying",
        "probabilityPolicyVersion": "capped-sum-to-three-v1",
        "podiumEstimateSemantics": "normalized_podium_estimate",
        "race": {"name": "Artifact Grand Prix", "season": 2026, "round": 20},
        "predictedQualifying": [
            {"driver_id": f"driver_{letter}", "position": index,
             "code": letter.upper() * 3, "driverName": f"Driver {letter.upper()}",
             "team": f"Team {letter.upper()}", "teamId": f"team_{letter}",
             "gap": float(index - 1) / 10}
            for index, letter in enumerate("abcd", start=1)
        ],
        "preQualifyingPodium": podium,
        "hasRealGrid": False,
        "realGridPodium": None,
        "realQualifying": None,
    }


def _prediction(**updates) -> dict:
    target_event = updates.pop("event", _event())
    kwargs = {
        "mode": "predicted_qualifying",
        "training_cutoff": "2026-10-30T00:00:00Z",
        "training_snapshot": _training_snapshot(),
        "model_manifest": _model_manifest(),
        "feature_inputs": _feature_inputs(),
        "qualifying": None,
    }
    forecast = updates.pop("forecast", _forecast())
    generated_at = updates.pop("generated_at", "2026-10-30T12:00:00Z")
    previous_candidate = updates.pop("previous_candidate", None)
    kwargs.update(updates)
    provenance = build_provenance(target_event, **kwargs)
    return build_prediction(
        target_event, forecast=forecast, generated_at=generated_at,
        provenance=provenance, previous_candidate=previous_candidate,
    )


def _rehash_tampered_prediction(prediction: dict) -> dict:
    prediction["input_hash"] = digest(_input_payload(prediction))
    prediction["prediction_id"] = digest(prediction, semantic_prediction=True)
    return prediction


def test_canonical_hash_is_stable_under_mapping_and_driver_row_ordering():
    first = _prediction()
    reordered_training = {
        "qualifying": list(reversed(_training_snapshot()["qualifying"])),
        "results": list(reversed(_training_snapshot()["results"])),
    }
    second = _prediction(
        training_snapshot=reordered_training,
    )
    reordered_prediction = copy.deepcopy(second)
    reordered_prediction["forecast"]["predictedQualifying"].reverse()
    reordered_prediction["forecast"]["preQualifyingPodium"].reverse()

    assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert first["training_data_hash"] == second["training_data_hash"]
    assert first["training_manifest"] == second["training_manifest"]
    assert first["input_hash"] == second["input_hash"]
    assert first["prediction_id"] == second["prediction_id"]
    assert digest(reordered_prediction, semantic_prediction=True) == first["prediction_id"]


def test_podium_rank_identity_is_semantic_even_when_capped_values_tie():
    prediction = _prediction()
    changed = copy.deepcopy(prediction)
    first, second = changed["forecast"]["preQualifyingPodium"][:2]
    first["rank"], second["rank"] = second["rank"], first["rank"]

    assert digest(changed, semantic_prediction=True) != prediction["prediction_id"]
    with pytest.raises(ValueError, match="rank"):
        validate_prediction(changed, _event())


def test_changed_accepted_timing_versions_actual_prediction_but_poll_metadata_does_not():
    forecast = _forecast() | {
        "mode": "actual_qualifying",
        "predictedQualifying": [],
        "preQualifyingPodium": [],
        "hasRealGrid": True,
        "realQualifying": [
            {"driver_id": f"driver_{letter}", "position": index,
             "modelPosition": index, "code": letter.upper() * 3,
             "driverName": f"Driver {letter.upper()}", "team": f"Team {letter.upper()}",
             "teamId": f"team_{letter}", "gap": float(index - 1) / 10,
             "modelGap": float(index - 1) / 10}
            for index, letter in enumerate("abcd", start=1)
        ],
        "realGridPodium": copy.deepcopy(_forecast()["preQualifyingPodium"]),
    }
    first = _prediction(
        mode="actual_qualifying", forecast=forecast,
        qualifying=_accepted("a" * 64),
    )
    timing_changed = _prediction(
        mode="actual_qualifying", forecast=forecast,
        qualifying=_accepted("b" * 64),
    )
    metadata_changed = copy.deepcopy(first)
    metadata_changed["generated_at"] = "2026-10-30T12:05:00Z"
    metadata_changed["status"] = "saved-locally"
    metadata_changed["poll_attempt"] = 9

    assert timing_changed["prediction_id"] != first["prediction_id"]
    assert digest(metadata_changed, semantic_prediction=True) == first["prediction_id"]


def test_same_input_reuses_valid_candidate_and_preserves_generation_time():
    first = _prediction()
    reused = _prediction(
        generated_at="2026-10-30T12:30:00Z",
        previous_candidate=first,
    )

    assert reused == first
    assert reused["generated_at"] == "2026-10-30T12:00:00Z"


def test_write_immutable_is_idempotent_and_rejects_collisions(tmp_path):
    path = tmp_path / "nested" / "artifact.json"
    write_immutable(path, {"answer": 42})
    first = path.read_bytes()
    write_immutable(path, {"answer": 42})

    assert first == b'{"answer":42}\n'
    with pytest.raises(ArtifactCollisionError, match="immutable collision"):
        write_immutable(path, {"answer": 43})


class _InterruptedBinaryWriter:
    def __init__(self, stream):
        self._stream = stream

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._stream.close()

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def write(self, value):
        self._stream.write(value[: max(1, len(value) // 2)])
        self._stream.flush()
        raise OSError("injected partial write")


def _inject_partial_binary_write(monkeypatch):
    original_path_open = Path.open
    original_fdopen = artifacts.os.fdopen

    def interrupted_path_open(path, mode="r", *args, **kwargs):
        stream = original_path_open(path, mode, *args, **kwargs)
        return _InterruptedBinaryWriter(stream) if mode == "xb" else stream

    def interrupted_fdopen(fd, mode="r", *args, **kwargs):
        stream = original_fdopen(fd, mode, *args, **kwargs)
        return _InterruptedBinaryWriter(stream) if mode == "wb" else stream

    monkeypatch.setattr(Path, "open", interrupted_path_open)
    monkeypatch.setattr(artifacts.os, "fdopen", interrupted_fdopen)


def test_write_immutable_never_exposes_partial_final_and_retry_succeeds(tmp_path, monkeypatch):
    path = tmp_path / "artifact.json"
    with monkeypatch.context() as faults:
        _inject_partial_binary_write(faults)
        with pytest.raises(OSError, match="partial write"):
            write_immutable(path, {"answer": 42})

    assert not path.exists()
    write_immutable(path, {"answer": 42})
    assert path.read_bytes() == b'{"answer":42}\n'


def test_archive_preserves_first_initial_and_appends_versions(tmp_path):
    first = _prediction()
    changed = _prediction(model_manifest=_model_manifest(code_hash="d" * 64))
    event_dir = archive_prediction(tmp_path, _event(), first)
    archive_prediction(tmp_path, _event(), changed)

    assert json.loads((event_dir / "initial.json").read_text()) == first
    assert json.loads((event_dir / "versions" / f"{first['prediction_id']}.json").read_text()) == first
    assert json.loads((event_dir / "versions" / f"{changed['prediction_id']}.json").read_text()) == changed


def test_archive_version_partial_write_is_retryable(tmp_path, monkeypatch):
    first = _prediction()
    event_dir = archive_prediction(tmp_path, _event(), first)
    changed = _prediction(model_manifest=_model_manifest(code_hash="d" * 64))
    changed_path = event_dir / "versions" / f"{changed['prediction_id']}.json"

    with monkeypatch.context() as faults:
        _inject_partial_binary_write(faults)
        with pytest.raises(OSError, match="partial write"):
            archive_prediction(tmp_path, _event(), changed)

    assert not changed_path.exists()
    archive_prediction(tmp_path, _event(), changed)
    assert json.loads(changed_path.read_text()) == changed


def test_archive_initial_partial_write_is_retryable(tmp_path, monkeypatch):
    prediction = _prediction()
    event_dir = archive_prediction(tmp_path, _event(), prediction)
    initial_path = event_dir / "initial.json"
    initial_path.unlink()

    with monkeypatch.context() as faults:
        _inject_partial_binary_write(faults)
        with pytest.raises(OSError, match="partial write"):
            archive_prediction(tmp_path, _event(), prediction)

    assert not initial_path.exists()
    archive_prediction(tmp_path, _event(), prediction)
    assert json.loads(initial_path.read_text()) == prediction


@pytest.mark.parametrize("corrupt", [b'{"truncated":\n', b'[]\n', b'null\n'])
def test_archive_rejects_corrupt_existing_initial_without_overwrite(tmp_path, corrupt):
    prediction = _prediction()
    event_dir = archive_prediction(tmp_path, _event(), prediction)
    initial_path = event_dir / "initial.json"
    initial_path.write_bytes(corrupt)

    with pytest.raises(ArtifactCollisionError, match="existing initial"):
        archive_prediction(tmp_path, _event(), prediction)

    assert initial_path.read_bytes() == corrupt


def test_archive_rejects_malformed_initial_forecast_with_artifact_error(tmp_path):
    prediction = _prediction()
    event_dir = archive_prediction(tmp_path, _event(), prediction)
    initial_path = event_dir / "initial.json"
    malformed = copy.deepcopy(prediction)
    malformed["forecast"] = []
    encoded = canonical_bytes(malformed) + b"\n"
    initial_path.write_bytes(encoded)

    with pytest.raises(ArtifactCollisionError, match="existing initial"):
        archive_prediction(tmp_path, _event(), prediction)

    assert initial_path.read_bytes() == encoded


def test_archive_rejects_initial_that_differs_from_its_immutable_version(tmp_path):
    prediction = _prediction()
    event_dir = archive_prediction(tmp_path, _event(), prediction)
    version_path = event_dir / "versions" / f"{prediction['prediction_id']}.json"
    version_path.write_bytes(b'{"different":true}\n')

    with pytest.raises(ArtifactCollisionError, match="existing initial"):
        archive_prediction(tmp_path, _event(), prediction)


def test_changed_schedule_builds_new_version_and_refreshes_event_metadata(tmp_path):
    first = _prediction()
    archive_prediction(tmp_path, _event(), first)
    changed_event = _event(qualifying_end_observed_at="2026-10-31T19:05:00Z")
    changed = _prediction(event=changed_event, previous_candidate=first)
    archive_prediction(tmp_path, changed_event, changed)

    event_dir = tmp_path / "prediction_snapshots" / "2026-20"
    assert changed["prediction_id"] != first["prediction_id"]
    assert json.loads((event_dir / "event.json").read_text())[
        "qualifying_end_observed_at"
    ] == "2026-10-31T19:05:00Z"
    assert json.loads((event_dir / "initial.json").read_text()) == first


def test_restart_reuses_durable_candidate_and_original_generation_time(tmp_path):
    first = _prediction()
    archive_prediction(tmp_path, _event(), first)

    durable = load_prediction_for_input(tmp_path, _event(), first["input_hash"])
    rebuilt = _prediction(
        generated_at="2026-10-30T13:00:00Z", previous_candidate=durable
    )
    archive_prediction(tmp_path, _event(), rebuilt)

    assert rebuilt == first
    assert rebuilt["generated_at"] == "2026-10-30T12:00:00Z"


def test_durable_lookup_skips_versions_from_an_unrelated_event_revision(tmp_path):
    first = _prediction()
    archive_prediction(tmp_path, _event(), first)
    changed_event = _event(race_start_at="2026-11-01T19:00:00Z")

    assert load_prediction_for_input(tmp_path, changed_event, "e" * 64) is None


@pytest.mark.parametrize("probabilities", [
    [1.1, 0.8, 0.6, 0.5],
    [float("nan"), 1.0, 1.0, 1.0],
    [0.9, 0.8, 0.7, 0.5],
])
def test_validate_prediction_rejects_invalid_podium_estimates(probabilities):
    prediction = _prediction()
    for row, probability in zip(
        prediction["forecast"]["preQualifyingPodium"], probabilities
    ):
        row["podiumProbability"] = probability

    with pytest.raises(ValueError, match="podium"):
        validate_prediction(prediction, _event())


def test_validate_prediction_rejects_wrong_event_identity_and_actual_without_source():
    prediction = _prediction()
    with pytest.raises(ValueError, match="event identity"):
        validate_prediction(prediction, _event(round=21))

    actual = copy.deepcopy(prediction)
    actual["mode"] = "actual_qualifying"
    actual["qualifying_source_version"] = None
    with pytest.raises(ValueError, match="source version"):
        validate_prediction(actual, _event())


@pytest.mark.parametrize(
    "field,value",
    [
        ("probabilityPolicyVersion", None),
        ("probabilityPolicyVersion", "legacy-scale-v0"),
        ("podiumEstimateSemantics", None),
        ("podiumEstimateSemantics", "calibrated_probability"),
    ],
)
def test_validate_prediction_requires_supported_nested_probability_semantics(field, value):
    prediction = _prediction()
    if value is None:
        del prediction["forecast"][field]
    else:
        prediction["forecast"][field] = value
    prediction["prediction_id"] = digest(prediction, semantic_prediction=True)

    with pytest.raises(ValueError, match="probability|estimate semantics"):
        validate_prediction(prediction, _event())


def test_training_hash_rejects_target_or_later_rows():
    snapshot = _training_snapshot()
    snapshot["results"].append(
        {"season": 2026, "round": 20, "date": "2026-11-01T18:00:00Z",
         "driver_id": "driver_c", "position": 1}
    )

    with pytest.raises(ValueError, match="target or later"):
        training_snapshot_hash(
            snapshot, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
        )


def test_training_snapshot_requires_dated_results_and_linked_qualifying():
    undated = _training_snapshot()
    del undated["results"][0]["date"]
    with pytest.raises(ValueError, match="result.*date"):
        training_snapshot_hash(
            undated, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
        )

    orphaned = _training_snapshot()
    orphaned["qualifying"][0]["round"] = 18
    with pytest.raises(ValueError, match="orphan"):
        training_snapshot_hash(
            orphaned, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "arbitrary_table", "missing_dates", "orphan", "reversed_dates",
        "partial_qualifying_dates", "reversed_qualifying_dates",
    ],
)
def test_serialized_training_manifest_rejects_incomplete_or_incoherent_evidence(mutation):
    prediction = _prediction()
    manifest = prediction["training_manifest"]
    if mutation == "arbitrary_table":
        manifest["tables"] = {
            "unrecognized": {
                "row_count": 1,
                "events": [{"season": 2026, "round": 19, "row_count": 1}],
            }
        }
        manifest["row_count"] = 1
    elif mutation == "missing_dates":
        result_event = manifest["tables"]["results"]["events"][0]
        del result_event["min_date"]
        del result_event["max_date"]
    elif mutation == "orphan":
        manifest["tables"]["qualifying"]["events"][0]["round"] = 18
    elif mutation == "reversed_dates":
        result_event = manifest["tables"]["results"]["events"][0]
        result_event["min_date"], result_event["max_date"] = (
            result_event["max_date"], "2026-10-24T00:00:00Z"
        )
    elif mutation == "partial_qualifying_dates":
        manifest["tables"]["qualifying"]["events"][0]["min_date"] = (
            "2026-10-25T00:00:00Z"
        )
    else:
        qualifying_event = manifest["tables"]["qualifying"]["events"][0]
        qualifying_event["min_date"] = "2026-10-26T00:00:00Z"
        qualifying_event["max_date"] = "2026-10-25T00:00:00Z"
    _rehash_tampered_prediction(prediction)

    with pytest.raises(ValueError, match="training manifest"):
        validate_prediction(prediction, _event())


@pytest.mark.parametrize("nonfinite", [float("inf"), float("-inf")])
def test_training_hash_rejects_infinite_historical_values(nonfinite):
    snapshot = _training_snapshot()
    snapshot["results"][0]["points"] = nonfinite

    with pytest.raises(ValueError, match="infinite"):
        training_snapshot_hash(
            snapshot, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
        )


def test_training_hash_canonicalizes_legitimate_missing_values_to_null():
    missing_nan = _training_snapshot()
    missing_none = _training_snapshot()
    missing_nan["results"][0]["optional"] = float("nan")
    missing_none["results"][0]["optional"] = None

    assert training_snapshot_hash(
        missing_nan, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
    ) == training_snapshot_hash(
        missing_none, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
    )


def test_training_snapshot_rejects_unrecognized_tables():
    snapshot = _training_snapshot()
    snapshot["telemetry"] = [
        {"season": 2026, "round": 19, "driver_id": "driver_a", "speed": 300}
    ]

    with pytest.raises(ValueError, match="results and qualifying tables only"):
        training_snapshot_hash(
            snapshot, event=_event(), training_cutoff="2026-10-30T00:00:00Z"
        )


def test_canonical_serialization_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        canonical_bytes({"not_json": float("nan")})


def test_model_manifest_and_feature_inputs_version_pre_model_inputs():
    baseline = build_provenance(
        _event(), mode="predicted_qualifying",
        training_cutoff="2026-10-30T00:00:00Z",
        training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
        feature_inputs=_feature_inputs(), qualifying=None,
    )
    parameter_changed = build_provenance(
        _event(), mode="predicted_qualifying",
        training_cutoff="2026-10-30T00:00:00Z",
        training_snapshot=_training_snapshot(),
        model_manifest=_model_manifest(parameters={"num_leaves": 63, "random_state": 42}),
        feature_inputs=_feature_inputs(), qualifying=None,
    )
    features = _feature_inputs()
    features[0]["quali_time_gap_to_pole"] = 0.001
    feature_changed = build_provenance(
        _event(), mode="predicted_qualifying",
        training_cutoff="2026-10-30T00:00:00Z",
        training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
        feature_inputs=features, qualifying=None,
    )

    assert parameter_changed["model_version"] != baseline["model_version"]
    assert parameter_changed["input_hash"] != baseline["input_hash"]
    assert feature_changed["feature_input_hash"] != baseline["feature_input_hash"]
    assert feature_changed["input_hash"] != baseline["input_hash"]


def test_build_provenance_recomputes_schedule_and_roster_versions():
    event = _event(event_schedule_hash="stale", roster_version="stale")
    provenance = build_provenance(
        event, mode="predicted_qualifying",
        training_cutoff="2026-10-30T00:00:00Z",
        training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
        feature_inputs=_feature_inputs(), qualifying=None,
    )

    assert provenance["event_schedule_hash"] != "stale"
    assert provenance["roster_version"] != "stale"


def test_actual_provenance_requires_accepted_qualifying_not_free_form_digest():
    with pytest.raises(TypeError, match="AcceptedQualifying"):
        build_provenance(
            _event(), mode="actual_qualifying",
            training_cutoff="2026-10-30T00:00:00Z",
            training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
            feature_inputs=_feature_inputs(), qualifying="a" * 64,
        )


@pytest.mark.parametrize("mismatch", ["rows", "roster", "both"])
def test_actual_provenance_rejects_constructor_mismatch_with_event_roster(mismatch):
    accepted = _accepted("a" * 64)
    if mismatch in {"rows", "both"}:
        accepted.rows.loc[accepted.rows["driver_id"] == "driver_a", "constructor_id"] = (
            "wrong_team"
        )
    if mismatch in {"roster", "both"}:
        accepted.roster.loc[
            accepted.roster["driver_id"] == "driver_a", "constructor_id"
        ] = "wrong_team"

    with pytest.raises(ValueError, match="constructor|roster"):
        build_provenance(
            _event(), mode="actual_qualifying",
            training_cutoff="2026-10-30T00:00:00Z",
            training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
            feature_inputs=_feature_inputs(), qualifying=accepted,
        )


def test_actual_provenance_rejects_lossy_event_identity_conversion():
    accepted = _accepted("a" * 64)
    accepted.rows["season"] = accepted.rows["season"].astype(float)
    accepted.rows.loc[0, "season"] = 2026.5

    with pytest.raises(ValueError, match="identity"):
        build_provenance(
            _event(), mode="actual_qualifying",
            training_cutoff="2026-10-30T00:00:00Z",
            training_snapshot=_training_snapshot(), model_manifest=_model_manifest(),
            feature_inputs=_feature_inputs(), qualifying=accepted,
        )


def test_initial_prediction_must_be_generated_before_qualifying():
    with pytest.raises(ValueError, match="before qualifying"):
        _prediction(generated_at="2026-10-31T18:00:00Z")


def test_provenance_composes_with_prepared_history_and_feature_frames():
    from src.model.forecast import _prepare_history, build_event_features
    from test_forecast import _entries as forecast_entries
    from test_forecast import _event as forecast_event
    from test_forecast import _history

    target = forecast_event(
        race_name="Artifact Grand Prix", circuit_id="artifact_ring",
        training_cutoff="2026-01-31T00:00:00Z",
        qualifying_start_at="2026-01-31T18:00:00Z",
        qualifying_end_observed_at="2026-01-31T19:02:00Z",
        race_start_at="2026-02-01T18:00:00Z",
        roster=_event()["roster"],
    )
    history = _history()
    history["results"]["optional_note"] = pd.NA
    prepared = _prepare_history(target, history)
    features = build_event_features(target, history, forecast_entries())

    provenance = build_provenance(
        target, mode="predicted_qualifying",
        training_cutoff="2026-01-31T00:00:00Z",
        training_snapshot=prepared, model_manifest=_model_manifest(),
        feature_inputs=features, qualifying=None,
    )

    assert provenance["training_manifest"]["tables"] == {
        "qualifying": {"row_count": 4, "events": [{"season": 2026, "round": 1, "row_count": 4}]},
        "results": {
            "row_count": 4,
            "events": [{
                "season": 2026, "round": 1, "row_count": 4,
                "min_date": "2026-01-01T00:00:00Z",
                "max_date": "2026-01-01T00:00:00Z",
            }],
        },
    }
    assert len(provenance["feature_input_hash"]) == 64
