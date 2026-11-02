"""Small, real CPU fits verify chronology, ordering and live provenance."""
import copy
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from src.features import build_features
from src.model import forecast, quali, retrain, provenance
from src.model.predict import predict_per_race


@pytest.fixture
def tables(monkeypatch):
    results, qualifying = [], []
    for rnd in range(1, 13):
        for driver in range(20):
            position = (driver + rnd) % 20 + 1
            common = dict(season=2026, round=rnd, driver_id=f"d{driver:02}", constructor_id=f"t{driver // 2}")
            results.append(dict(**common, race_name=f"Race {rnd}", circuit_id=f"c{rnd % 3}",
                                date=f"2026-{rnd:02}-01", code=f"D{driver:02}", driver_name=f"Driver {driver}",
                                constructor_name=f"Team {driver // 2}", position=position, grid=position,
                                points=max(0, 11-position), status="Lapped" if driver % 2 else "Finished"))
            qualifying.append(dict(**common, quali_position=position, q1=f"1:{20+position:02}.000",
                                   q2=f"1:{21+position:02}.000", q3=f"1:{22+position:02}.000"))
    data = {"results": pd.DataFrame(results), "qualifying": pd.DataFrame(qualifying)}
    for module in (build_features, quali, forecast):
        monkeypatch.setattr(module, "_load", lambda name: data[name].copy())
    return data


def test_feature_rows_are_canonical_and_leakage_safe(tables):
    initial = build_features.build_feature_table()
    initial_q = quali.build_quali_features()
    for key in tables:
        tables[key] = tables[key].sample(frac=1, random_state=7).reset_index(drop=True)
    pd.testing.assert_frame_equal(initial, build_features.build_feature_table())
    pd.testing.assert_frame_equal(initial_q, quali.build_quali_features())
    # Changing the target race outcomes cannot affect its pre-race features.
    tables["results"].loc[tables["results"]["round"] == 6, ["position", "points", "status"]] = [19, 0, "Retired"]
    changed = build_features.build_feature_table()
    pd.testing.assert_frame_equal(initial.loc[initial["round"] == 6, build_features.FEATURES],
                                  changed.loc[changed["round"] == 6, build_features.FEATURES])
    assert (initial.loc[initial["round"] > 1, "dnf_rate"] == 0).all()


def test_repeat_and_shuffled_live_training(tables):
    a = retrain.retrain_live("2026-10-01", 2026, 10)
    b = retrain.retrain_live("2026-10-01", 2026, 10)
    for key in tables:
        tables[key] = tables[key].sample(frac=1, random_state=91).reset_index(drop=True)
    c = retrain.retrain_live("2026-10-01", 2026, 10)
    features = build_features.build_feature_table()
    q = quali.build_quali_features()
    for model in (b, c):
        np.testing.assert_array_equal(a["podium"].predict_proba(features[build_features.FEATURES]),
                                      model["podium"].predict_proba(features[build_features.FEATURES]))
        np.testing.assert_array_equal(a["quali"].predict(q[quali.QUALI_FEATURES]),
                                      model["quali"].predict(q[quali.QUALI_FEATURES]))
    assert "training_metadata" in a
    metadata = a["training_metadata"]
    assert metadata["stage1"]["row_count"] == metadata["stage2"]["row_count"] == 180
    assert metadata["stage2"]["race_count"] == 9
    assert metadata["stage2"]["model_params"]["deterministic"] is True
    assert metadata["stage2"]["model_params"]["n_jobs"] == 1
    assert metadata["stage1"]["training_data_sha256"] == c["training_metadata"]["stage1"]["training_data_sha256"]
    assert metadata["stage2"] == a["podium"].training_metadata_["stage2"]
    json.dumps(metadata, allow_nan=False)
    assert np.unique(a["podium"].predict_proba(features[build_features.FEATURES])[:, 1]).size > 1
    assert np.unique(a["quali"].predict(q[quali.QUALI_FEATURES])).size > 1


def test_cutoffs_exclude_target_and_future_labels(tables):
    tables["results"].loc[(tables["results"]["round"] == 2) & (tables["results"].driver_id == "d00"), "grid"] = 0
    before = retrain.retrain_live("2026-10-01", 2026, 10)
    tables["results"].loc[tables["results"]["round"] >= 10, ["position", "points", "status"]] = [20, 0, "Retired"]
    tables["results"].loc[tables["results"]["round"] >= 10, "grid"] = 99
    tables["qualifying"].loc[tables["qualifying"]["round"] >= 10, ["q1", "q2", "q3"]] = "1:50.000"
    after = retrain.retrain_live("2026-10-01", 2026, 10)
    for stage in ("stage1", "stage2"):
        assert before["training_metadata"][stage]["training_data_sha256"] == after["training_metadata"][stage]["training_data_sha256"]


def test_pit_lane_fallback_uses_only_same_race_grid(tables):
    results = tables["results"]
    results.loc[(results["round"] == 2) & (results.driver_id == "d00"), "grid"] = 0
    before = build_features.build_feature_table()
    pit_lane = before[(before["round"] == 2) & (before.driver_id == "d00")].iloc[0]
    assert pit_lane.grid_position == results.loc[results["round"] == 2, "grid"].max()
    results.loc[results["round"] >= 10, "grid"] = 99
    after = build_features.build_feature_table()
    pd.testing.assert_frame_equal(before[before["round"] < 10], after[after["round"] < 10])


def test_offline_inference_ties_have_canonical_driver_order(tables):
    class TiedModel:
        def predict_proba(self, frame):
            return np.tile([0.5, 0.5], (len(frame), 1))

    frame = build_features.build_feature_table()
    expected = predict_per_race(TiedModel(), frame)
    assert predict_per_race(TiedModel(), frame.sample(frac=1, random_state=42)) == expected


def test_provenance_hashes_inputs_and_code_but_not_artifacts(monkeypatch, tmp_path, tables):
    ml_dir = tmp_path / "ml"
    raw = ml_dir / "data" / "raw"
    raw.mkdir(parents=True)
    for name, frame in tables.items():
        frame.to_parquet(raw / f"{name}_2026.parquet", index=False)
    (ml_dir / "src").mkdir()
    source = ml_dir / "src" / "training.py"
    source.write_text("# training code\n")
    lock = ml_dir / "requirements-lock.txt"
    lock.write_text("lightgbm==4.6.0\n")
    monkeypatch.setattr(provenance, "ML_DIR", ml_dir)
    frame = build_features.build_feature_table()
    kwargs = dict(cutoff={"date_exclusive": "2027-01-01"}, features=build_features.FEATURES,
                  target="podium", model_params=retrain._LGBM_KW)
    before = provenance.training_metadata(frame, **kwargs)
    assert before["dependency_lock_sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert before["input_data_sha256"]["results"]["results_2026.parquet"] == hashlib.sha256((raw / "results_2026.parquet").read_bytes()).hexdigest()
    (ml_dir / "models").mkdir()
    (ml_dir / "models" / "artifact.pkl").write_bytes(b"generated model")
    assert provenance.training_metadata(frame, **kwargs)["code_sha256"] == before["code_sha256"]
    source.write_text("# modified training code\n")
    assert provenance.training_metadata(frame, **kwargs)["code_sha256"] != before["code_sha256"]


def test_forecast_metadata_optional_and_actual_stage_merge(monkeypatch, tables):
    models = retrain.retrain_live("2026-10-01", 2026, 10)
    target = pd.Series(dict(season=2026, round=10, circuit_id="c1", date=pd.Timestamp("2026-10-01"), race_name="Race 10"))
    monkeypatch.setattr(forecast, "next_race", lambda asof: target)
    base = forecast.forecast("2026-10-01", models=models)
    assert base["training_metadata"] == models["training_metadata"]
    for key in tables:
        tables[key] = tables[key].sample(frac=1, random_state=33).reset_index(drop=True)
    assert forecast.forecast("2026-10-01", models=models) == base
    legacy = forecast.forecast("2026-10-01", models={"quali": models["quali"], "podium": models["podium"]})
    assert "training_metadata" not in legacy
    actual = [dict(season=2026, round=10, race_name="Race 10", circuit_id="c1", driver_id=f"d{i:02}",
                   constructor_id=f"t{i // 2}", qualifying_position=i+1, qualifying_gap_seconds=i*0.1) for i in range(10)]
    podium = retrain.train_podium_live("2026-10-01")
    podium.training_metadata_["stage2"]["generated_at"] = "new-stage-two"
    original = copy.deepcopy(base)
    result = forecast.forecast_actual_qualifying(base_forecast=base, actual_qualifying=actual,
                                                podium_model=podium, target_date="2026-10-01")
    assert result["training_metadata"]["stage1"] == original["training_metadata"]["stage1"]
    assert result["training_metadata"]["stage2"] == podium.training_metadata_["stage2"]
    assert base == original
    reversed_result = forecast.forecast_actual_qualifying(base_forecast=base, actual_qualifying=list(reversed(actual)),
                                                         podium_model=podium, target_date="2026-10-01")
    assert reversed_result == result


@pytest.mark.parametrize("replacement_metadata", [None, {}, {"stage2": None}, {"stage2": {}}])
def test_actual_replacement_without_provenance_removes_old_stage_two(tables, replacement_metadata):
    class ReplacementModel:
        def predict_proba(self, frame):
            return np.tile([0.5, 0.5], (len(frame), 1))

    model = ReplacementModel()
    if replacement_metadata is not None:
        model.training_metadata_ = replacement_metadata
    base = {
        "race": {"name": "Race 10", "season": 2026, "round": 10},
        "training_metadata": {"stage1": {"generated_at": "original-stage-one"},
                              "stage2": {"generated_at": "stale-stage-two"}},
    }
    original = copy.deepcopy(base)
    actual = [dict(season=2026, round=10, race_name="Race 10", circuit_id="c1", driver_id=f"d{i:02}",
                   constructor_id=f"t{i // 2}", qualifying_position=i+1, qualifying_gap_seconds=i*0.1) for i in range(10)]
    result = forecast.forecast_actual_qualifying(base_forecast=base, actual_qualifying=actual,
                                                podium_model=model, target_date="2026-10-01")
    assert result["training_metadata"] == {"stage1": original["training_metadata"]["stage1"]}
    assert base == original
