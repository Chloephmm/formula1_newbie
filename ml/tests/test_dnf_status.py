"""Race-status semantics stay identical in training, forecasts, and backtests."""
import pandas as pd
import pytest

from scripts.backtest_live import build_feature_table as build_backtest_features
from src.features.build_features import _is_finished, build_feature_table
from src.model.forecast import forecast_event
from test_forecast import (
    CaptureClassifier,
    CaptureRegressor,
    _accepted,
    _entries,
    _event,
    _history,
    _quali,
    _result,
)


@pytest.mark.parametrize(
    "status, expected",
    [
        ("Finished", True), (" finished \t", True), ("FINISHED", True),
        ("Lapped", True), (" lApPeD\n", True),
        ("+1 Lap", True), ("+2 Laps", True), (" +12  lApS\t", True),
        ("Retired", False), ("Accident", False), ("Engine", False),
        ("Did not start", False), ("Disqualified", False),
        ("Not classified", False), ("Unknown", False), ("", False),
        (None, False), (float("nan"), False), (pd.NA, False),
        ("+unknown", False), ("+1 Lap retired", False),
    ],
)
def test_finished_status_recognizes_only_finished_and_lapped_results(status, expected):
    statuses = pd.Series([status], index=[17], name="status", dtype=object)

    actual = _is_finished(statuses)

    assert actual.index.equals(statuses.index)
    assert actual.tolist() == [expected]


@pytest.mark.parametrize("builder", [build_feature_table, build_backtest_features],
                         ids=["training", "backtest"])
def test_training_and_backtest_dnf_rate_uses_only_previous_five_races(builder):
    statuses = ["Retired", " Finished ", "Lapped", " +1 lap ", "+2 Laps", "Engine",
                "Disqualified"]
    results = pd.DataFrame([
        _result(2026, rnd, f"2026-01-{rnd:02d}", "driver_a", 4) | {"status": status}
        for rnd, status in enumerate(statuses, start=1)
    ])
    qualifying = pd.DataFrame([
        _quali(2026, rnd, "driver_a", 4, "1:20.000")
        for rnd in range(1, len(statuses) + 1)
    ])

    features = builder(results=results, qualifying=qualifying)

    assert features["dnf_rate"].tolist() == pytest.approx(
        [0.1, 1.0, 0.5, 1 / 3, 0.25, 0.2, 0.2]
    )


@pytest.mark.parametrize("mode", ["predicted_qualifying", "actual_qualifying"])
def test_forecast_modes_share_training_dnf_status_semantics(mode):
    history = _history()
    prior = history["results"]["round"].eq(1) & history["results"]["season"].eq(2026)
    history["results"].loc[prior, "status"] = [" LAPPED ", " finished ", "+2 laps", "Retired"]
    podium = CaptureClassifier()

    forecast_event(
        _event(), mode=mode, history=history, entries=_entries(),
        models={"quali": CaptureRegressor(), "podium": podium},
        qualifying=_accepted() if mode == "actual_qualifying" else None,
    )
    training = build_feature_table(**history)
    target = training.loc[
        training["season"].eq(2026) & training["round"].eq(2)
    ].sort_values("driver_id")

    assert podium.calls[0]["dnf_rate"].tolist() == [0.0, 0.0, 0.0, 1.0]
    assert target["dnf_rate"].tolist() == podium.calls[0]["dnf_rate"].tolist()
