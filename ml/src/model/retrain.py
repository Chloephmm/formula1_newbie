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

# Same conservative hyperparameters as the offline trainers (train.py / quali.py): a small
# dataset (~5k rows, few features) overfits easily, so favor shallow trees + regularization.
_LGBM_KW = LGBM_PARAMS


def train_podium_live(cutoff_date):
    """Stage-2 podium model fit on every race strictly before ``cutoff_date``.

    Probabilities are calibrated with 5-fold CV sigmoid instead of a held-out season,
    so the most recent races are used for fitting too. Returns a fitted
    ``CalibratedClassifierCV`` with the standard scikit-learn ``predict_proba`` interface.
    """
    cutoff = pd.Timestamp(cutoff_date).normalize()
    df = build_feature_table()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    train = sort_race_rows(df[df["date"] < cutoff].dropna(subset=["podium"]))
    model = CalibratedClassifierCV(lgb.LGBMClassifier(**_LGBM_KW), method="sigmoid", cv=5)
    model.fit(train[FEATURES], train["podium"])
    model.training_metadata_ = {"stage2": training_metadata(
        train, cutoff={"date_exclusive": cutoff.date().isoformat()}, features=FEATURES,
        target="podium", model_params=model.estimator.get_params(),
        calibration={"method": "sigmoid", "cv": 5},
    )}
    return model


def train_quali_live(season, rnd):
    """Stage-1 quali model fit on every qualifying strictly before race ``(season, rnd)``.

    Returns a fitted ``LGBMRegressor`` with the standard scikit-learn ``predict`` interface.
    """
    target = int(season) * 100 + int(rnd)
    q = build_quali_features().dropna(subset=[QTARGET])
    q = sort_race_rows(q[(q["season"] * 100 + q["round"]) < target])
    model = lgb.LGBMRegressor(**_LGBM_KW)
    model.fit(q[QUALI_FEATURES], q[QTARGET])
    model.training_metadata_ = {"stage1": training_metadata(
        q, cutoff={"season": int(season), "round_exclusive": int(rnd)},
        features=QUALI_FEATURES, target=QTARGET, model_params=model.get_params(),
    )}
    return model


def retrain_live(target_date, season, rnd) -> dict:
    """Return both fitted models and optional-consumer ``training_metadata`` provenance."""
    podium = train_podium_live(target_date)
    quali = train_quali_live(season, rnd)
    return {
        "podium": podium,
        "quali": quali,
        "training_metadata": {**quali.training_metadata_, **podium.training_metadata_},
    }
