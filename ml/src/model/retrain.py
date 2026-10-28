"""Live (production) retraining used by `forecast()` and the Streamlit RUN button.

Both stages fit on EVERY race strictly *before* the target Grand Prix (expanding
window, leakage-safe) so predictions reflect the latest racing. Models live in
memory; nothing is pickled. The offline trainers (`train.py`, `quali.train_quali`)
still exist so the metrics page can report honest held-out evaluation numbers.

Backtests (frozen ≤2022 split vs this) showed gains that grow with recency: podium
hit rate up (biggest on 2026), quali pole accuracy 22%→31% and gap MAE 0.67s→0.58s
over 2024–26. See `scripts/backtest_live.py`.
"""
from __future__ import annotations

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from src.features.build_features import FEATURES, build_feature_table
from src.model.quali import QTARGET, QUALI_FEATURES, build_quali_features

# Same conservative hyperparameters as the offline trainers (train.py / quali.py): a small
# dataset (~5k rows, few features) overfits easily, so favor shallow trees + regularization.
_LGBM_KW = dict(
    n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
    min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=1.0, random_state=42, verbosity=-1,
)


def train_podium_live(cutoff_date):
    """Stage-2 podium model fit on every race strictly before ``cutoff_date``.

    Probabilities are calibrated with 5-fold CV sigmoid instead of a held-out season,
    so the most recent races are used for fitting too. Returns a fitted
    ``CalibratedClassifierCV`` with the standard scikit-learn ``predict_proba`` interface.
    """
    cutoff = pd.Timestamp(cutoff_date).normalize()
    df = build_feature_table()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    train = df[df["date"] < cutoff].dropna(subset=["podium"])
    model = CalibratedClassifierCV(lgb.LGBMClassifier(**_LGBM_KW), method="sigmoid", cv=5)
    model.fit(train[FEATURES], train["podium"])
    return model


def train_quali_live(season, rnd):
    """Stage-1 quali model fit on every qualifying strictly before race ``(season, rnd)``.

    Returns a fitted ``LGBMRegressor`` with the standard scikit-learn ``predict`` interface.
    """
    target = int(season) * 100 + int(rnd)
    q = build_quali_features().dropna(subset=[QTARGET])
    q = q[(q["season"] * 100 + q["round"]) < target]
    model = lgb.LGBMRegressor(**_LGBM_KW)
    model.fit(q[QUALI_FEATURES], q[QTARGET])
    return model


def retrain_live(target_date, season, rnd) -> dict:
    """Retrain both stages for the target race. Returns ``{"podium": …, "quali": …}``."""
    return {
        "podium": train_podium_live(target_date),
        "quali": train_quali_live(season, rnd),
    }
