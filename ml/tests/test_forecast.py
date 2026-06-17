"""Unit tests for the forecast pipeline — output contract, normalization, mode logic."""
import pytest

from src.model.data import ML_DIR
from src.model.forecast import forecast, next_race

RAW = ML_DIR / "data" / "raw"
DATA_OK = (RAW / "results_2026.parquet").exists() and (RAW / "qualifying_2026.parquet").exists()
pytestmark = pytest.mark.skipif(not DATA_OK, reason="raw 2026 data not cached")

PRE_DATE = "2026-06-12"    # Barcelona — before its qualifying (June 13) -> pre-qualifying
REAL_DATE = "2026-06-07"   # targets Monaco — after its qualifying (June 6) -> real grid


def test_forecast_contract():
    r = forecast(PRE_DATE)
    assert r.get("error") is None
    for key in ("race", "predictedQualifying", "preQualifyingPodium", "hasRealGrid"):
        assert key in r
    assert len(r["preQualifyingPodium"]) >= 3
    # podium is sorted by probability (descending)
    probs = [d["podiumProbability"] for d in r["preQualifyingPodium"]]
    assert probs == sorted(probs, reverse=True)


def test_podium_probs_normalized_to_three():
    """Per race the podium probabilities are normalized to sum to 3 (three spots)."""
    r = forecast(PRE_DATE)
    total = sum(d["podiumProbability"] for d in r["preQualifyingPodium"])
    assert total == pytest.approx(3.0, abs=0.05)


def test_mode_selection_by_date():
    # before qualifying -> predicted grid (no real grid)
    assert forecast(PRE_DATE)["hasRealGrid"] is False
    # after the race's qualifying (and cached) -> real grid
    assert forecast(REAL_DATE)["hasRealGrid"] is True


def test_next_race_matches_forecast_target():
    tgt = next_race(PRE_DATE)
    assert tgt is not None
    assert int(tgt["round"]) == int(forecast(PRE_DATE)["race"]["round"])


def test_injected_models_match_internal_retrain():
    """Pre-retraining once and injecting via `models=` matches an internal retrain — used
    by the app to cache the retrain across renders."""
    from src.model.retrain import retrain_live

    tgt = next_race(PRE_DATE)
    models = retrain_live(tgt["date"].date().isoformat(),
                          int(tgt.season), int(tgt["round"]))
    a = forecast(PRE_DATE)
    b = forecast(PRE_DATE, models=models)
    assert [d["code"] for d in a["preQualifyingPodium"]] == \
           [d["code"] for d in b["preQualifyingPodium"]]
    assert [d["podiumProbability"] for d in a["preQualifyingPodium"]] == \
           [d["podiumProbability"] for d in b["preQualifyingPodium"]]
