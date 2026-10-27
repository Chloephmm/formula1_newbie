"""Leakage-safe in-memory retraining for explicit target events."""
from __future__ import annotations

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from src.features.build_features import FEATURES, _load as _load_race_raw, build_feature_table
from src.model.quali import (
    QTARGET,
    QUALI_FEATURES,
    _load as _load_quali_raw,
    build_quali_features,
)

_LGBM_KW = dict(
    n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
    min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=1.0, random_state=42, verbosity=-1,
)


def _before_identity(frame, season, round_number):
    if season is None or round_number is None:
        return pd.Series(True, index=frame.index)
    seasons = pd.to_numeric(frame["season"], errors="coerce")
    rounds = pd.to_numeric(frame["round"], errors="coerce")
    return (seasons < int(season)) | (
        (seasons == int(season)) & (rounds < int(round_number))
    )


def _filtered_raw(
    cutoff_date, *, results=None, qualifying=None, target_season=None, target_round=None
):
    if (results is None) != (qualifying is None):
        raise ValueError("results and qualifying must be supplied together")
    if results is None:
        results = _load_race_raw("results")
        qualifying = _load_quali_raw("qualifying")
    result_copy = results.copy(deep=True)
    quali_copy = qualifying.copy(deep=True)
    cutoff = pd.Timestamp(cutoff_date)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    dates = pd.to_datetime(result_copy["date"], errors="coerce", utc=True)
    result_copy = result_copy.loc[
        _before_identity(result_copy, target_season, target_round) & (dates < cutoff)
    ].copy()
    result_copy["date"] = dates.loc[result_copy.index]
    completed = result_copy[["season", "round"]].drop_duplicates()
    quali_copy = quali_copy.loc[
        _before_identity(quali_copy, target_season, target_round)
    ].merge(completed, on=["season", "round"], how="inner")
    return result_copy.reset_index(drop=True), quali_copy.reset_index(drop=True), cutoff


def train_podium_live(
    cutoff_date, *, results=None, qualifying=None, target_season=None, target_round=None
):
    """Fit Stage 2 only on raw events before both target identity and cutoff."""

    result_rows, qualifying_rows, cutoff = _filtered_raw(
        cutoff_date, results=results, qualifying=qualifying,
        target_season=target_season, target_round=target_round,
    )
    frame = build_feature_table(results=result_rows, qualifying=qualifying_rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True)
    train = frame.loc[frame["date"] < cutoff].dropna(subset=["podium"])
    model = CalibratedClassifierCV(
        lgb.LGBMClassifier(**_LGBM_KW), method="sigmoid", cv=5
    )
    model.fit(train[FEATURES], train["podium"])
    return model


def train_quali_live(
    season, rnd, *, results=None, qualifying=None, cutoff_date=None
):
    """Fit Stage 1 only on qualifying before target identity."""

    cutoff = pd.Timestamp.max.tz_localize("UTC") if cutoff_date is None else cutoff_date
    result_rows, qualifying_rows, _ = _filtered_raw(
        cutoff, results=results, qualifying=qualifying,
        target_season=season, target_round=rnd,
    )
    frame = build_quali_features(
        results=result_rows, qualifying=qualifying_rows
    ).dropna(subset=[QTARGET])
    model = lgb.LGBMRegressor(**_LGBM_KW)
    model.fit(frame[QUALI_FEATURES], frame[QTARGET])
    return model


def retrain_live(target_date, season, rnd, *, history=None) -> dict:
    """Retrain both legacy stages; explicit actual generation must not call this."""

    supplied = {} if history is None else {
        "results": history["results"], "qualifying": history["qualifying"]
    }
    result_rows, qualifying_rows, cutoff = _filtered_raw(
        target_date, **supplied, target_season=season, target_round=rnd
    )
    raw = {"results": result_rows, "qualifying": qualifying_rows}
    return {
        "podium": train_podium_live(
            cutoff, **raw, target_season=season, target_round=rnd
        ),
        "quali": train_quali_live(season, rnd, **raw, cutoff_date=cutoff),
    }
