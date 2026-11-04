"""Training and both inference paths must agree on classified finishes."""
import pandas as pd
import pytest

from src.features.build_features import _is_finished
from src.model.forecast import _actual_entry_features


@pytest.mark.parametrize("status", ["Finished", " finished ", "FINISHED", "Lapped", " lAPPED ", "+1 Lap", " +2  LAPS "])
def test_classified_finish(status):
    assert bool(_is_finished(pd.Series([status])).iloc[0])


@pytest.mark.parametrize("status", ["Retired", "DNS", "Disqualified", "Unknown", None, "+unknown", ""])
def test_nonfinish(status):
    assert not bool(_is_finished(pd.Series([status])).iloc[0])


def test_actual_entry_fallback_uses_same_finish_rule():
    history = pd.DataFrame([dict(season=2026, round=1, driver_id="a", constructor_id="t",
                                circuit_id="c", position=8, points=4, status=" lapped ",
                                quali_gap=1.0, quali_position=8)])
    actual = [dict(driver_id="a", constructor_id="t", qualifying_position=8, qualifying_gap_seconds=1.0)]
    assert _actual_entry_features(history, actual, "c").iloc[0].dnf_rate == 0.0
