"""Unit tests for the feature table — integrity and the no-leakage guarantee."""
import pandas as pd
import pytest

from src.model.data import ML_DIR

FEAT = ML_DIR / "data" / "processed" / "features.parquet"
RAW = ML_DIR / "data" / "raw"
FEATURES = ["grid_position", "quali_time_gap_to_pole", "recent_form", "recent_points",
            "team_strength", "track_history", "dnf_rate"]

pytestmark = pytest.mark.skipif(
    not FEAT.exists(), reason="features.parquet not built (run scripts/build_features.py)")


def test_features_integrity():
    feat = pd.read_parquet(FEAT)
    # no missing feature values
    assert feat[FEATURES].isna().sum().sum() == 0
    # target is binary
    assert set(feat["podium"].dropna().unique()) <= {0, 1}
    # exactly one row per driver per race
    assert not feat.duplicated(["season", "round", "driver_id"]).any()


def test_no_leakage_recent_form():
    """recent_form must use ONLY prior races (the shift(1) leakage guard)."""
    feat = pd.read_parquet(FEAT)
    res = pd.concat([pd.read_parquet(f) for f in sorted(RAW.glob("results_*.parquet"))],
                    ignore_index=True).sort_values(["season", "round"])

    drv, season, rnd = "max_verstappen", 2023, 10
    sub = feat[(feat.driver_id == drv) & (feat.season == season) & (feat["round"] == rnd)]
    if sub.empty:
        pytest.skip("sample driver-race not present in features")

    got = float(sub.iloc[0]["recent_form"])
    hist = res[res.driver_id == drv]
    prior = hist[(hist.season < season) | ((hist.season == season) & (hist["round"] < rnd))]
    expected = prior.tail(5)["position"].mean()      # last 5 races BEFORE the target
    assert got == pytest.approx(expected, abs=1e-6)
