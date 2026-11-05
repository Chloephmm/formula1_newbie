"""Live production retraining used by the scheduled publication jobs.

Both stages fit on EVERY race strictly *before* the target Grand Prix (expanding
window, leakage-safe) so predictions reflect the latest racing. Models live in
memory; nothing is pickled. The offline trainers (`train.py`, `quali.train_quali`)
still exist so the metrics page can report honest held-out evaluation numbers.

See `scripts/backtest_live.py` for the separately reported walk-forward metrics.
Its podium evaluation uses actual qualifying and an uncalibrated base model;
it is not the estimated-qualifying production pipeline's accuracy.
"""
from __future__ import annotations

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from src.features.build_features import FEATURES, build_feature_table
from src.model.quali import QTARGET, QUALI_FEATURES, build_quali_features
from src.features.common import sort_race_rows
from src.model.config import LGBM_PARAMS
from src.model.provenance import training_metadata
from src.features.build_features import _load as _load_race_raw
from src.model.quali import _load as _load_quali_raw

# Same conservative hyperparameters as the offline trainers (train.py / quali.py): a small
# dataset (~5k rows, few features) overfits easily, so favor shallow trees + regularization.
_LGBM_KW = LGBM_PARAMS


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


def train_podium_live(cutoff_date, *, results=None, qualifying=None, target_season=None, target_round=None):
    """Stage-2 podium model fit on every race strictly before ``cutoff_date``.

    Probabilities are calibrated with 5-fold CV sigmoid instead of a held-out season,
    so the most recent races are used for fitting too. Returns a fitted
    ``CalibratedClassifierCV`` with the standard scikit-learn ``predict_proba`` interface.
    """
    cutoff = pd.Timestamp(cutoff_date).normalize()
    if results is not None or qualifying is not None:
        results, qualifying, cutoff = _filtered_raw(
            cutoff_date, results=results, qualifying=qualifying,
            target_season=target_season, target_round=target_round)
        df = build_feature_table(results=results, qualifying=qualifying)
    else:
        df = build_feature_table()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=cutoff.tzinfo is not None)
    train = sort_race_rows(df[df["date"] < cutoff].dropna(subset=["podium"]))
    model = CalibratedClassifierCV(lgb.LGBMClassifier(**_LGBM_KW), method="sigmoid", cv=5)
    model.fit(train[FEATURES], train["podium"])
    model.training_metadata_ = {"stage2": training_metadata(
        train, cutoff={"date_exclusive": cutoff.date().isoformat()}, features=FEATURES,
        target="podium", model_params=model.estimator.get_params(),
        calibration={"method": "sigmoid", "cv": 5},
    )}
    return model


def train_quali_live(season, rnd, *, results=None, qualifying=None, cutoff_date=None):
    """Stage-1 quali model fit on every qualifying strictly before race ``(season, rnd)``.

    Returns a fitted ``LGBMRegressor`` with the standard scikit-learn ``predict`` interface.
    """
    target = int(season) * 100 + int(rnd)
    if results is not None or qualifying is not None:
        cutoff = pd.Timestamp.max.tz_localize("UTC") if cutoff_date is None else cutoff_date
        results, qualifying, _ = _filtered_raw(cutoff, results=results, qualifying=qualifying,
                                              target_season=season, target_round=rnd)
        q = build_quali_features(results=results, qualifying=qualifying).dropna(subset=[QTARGET])
    else:
        q = build_quali_features().dropna(subset=[QTARGET])
    q = sort_race_rows(q[(q["season"] * 100 + q["round"]) < target])
    model = lgb.LGBMRegressor(**_LGBM_KW)
    model.fit(q[QUALI_FEATURES], q[QTARGET])
    model.training_metadata_ = {"stage1": training_metadata(
        q, cutoff={"season": int(season), "round_exclusive": int(rnd)},
        features=QUALI_FEATURES, target=QTARGET, model_params=model.get_params(),
    )}
    return model


def retrain_live(target_date, season, rnd, *, history=None) -> dict:
    """Return both fitted models and optional-consumer ``training_metadata`` provenance."""
    if history is None:
        podium = train_podium_live(target_date)
        quali = train_quali_live(season, rnd)
    else:
        results, qualifying, cutoff = _filtered_raw(target_date, **history,
                                                   target_season=season, target_round=rnd)
        podium = train_podium_live(cutoff, results=results, qualifying=qualifying,
                                  target_season=season, target_round=rnd)
        quali = train_quali_live(season, rnd, results=results, qualifying=qualifying, cutoff_date=cutoff)
    return {
        "podium": podium,
        "quali": quali,
        "training_metadata": {**quali.training_metadata_, **podium.training_metadata_},
    }
