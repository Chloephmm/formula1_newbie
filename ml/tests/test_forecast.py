"""Unit tests for the forecast pipeline — output contract, normalization, mode logic."""
import pytest

from src.model.data import ML_DIR
from src.model.forecast import forecast

MODELS_OK = ((ML_DIR / "models" / "podium_model.pkl").exists()
             and (ML_DIR / "models" / "quali_model.pkl").exists())
pytestmark = pytest.mark.skipif(not MODELS_OK, reason="models not trained")

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
