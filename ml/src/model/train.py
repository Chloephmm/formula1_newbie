"""Train the podium models and calibrate (Approach A: prefit + FrozenEstimator).

- Baseline: logistic regression (the benchmark LightGBM must beat).
- Main: LightGBM, fit on train-fit (<=2022), then calibrated on 2023 with the
  **sigmoid** method (robust for the small 2023 calibration set, ~66 positives).

Saves an artifact dict to ml/models/podium_model.pkl with the calibrated model,
the baseline, the feature list, and LightGBM feature importances.
"""
from __future__ import annotations

import joblib
import lightgbm as lgb
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.model.data import FEATURES, ML_DIR, TARGET, load_features, split_by_season


def train():
    df = load_features()
    train_fit, calib, _test = split_by_season(df)
    Xtr, ytr = train_fit[FEATURES], train_fit[TARGET]

    # --- baseline: logistic regression (scaled, class-balanced) ---
    baseline = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )
    baseline.fit(Xtr, ytr)

    # --- main model: LightGBM ---
    # Conservative config: small dataset (~3.7k rows, 7 features) overfits easily,
    # so favor shallow trees + regularization. Probabilities are fixed by calibration,
    # so we don't force class weighting (which mainly distorts the probability scale).
    base = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        max_depth=4,
        min_child_samples=40,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
        verbosity=-1,
    )
    base.fit(Xtr, ytr)

    # --- benchmark model: XGBoost (same train/calibrate recipe for a fair compare) ---
    xgb_base = xgb.XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    xgb_base.fit(Xtr, ytr)

    # --- calibrate on 2023 (sigmoid; do NOT retrain base -> FrozenEstimator) ---
    calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
    calibrated.fit(calib[FEATURES], calib[TARGET])
    calibrated_xgb = CalibratedClassifierCV(FrozenEstimator(xgb_base), method="sigmoid")
    calibrated_xgb.fit(calib[FEATURES], calib[TARGET])

    # Shipped artifact (saved to disk) — LightGBM + baseline only, so the app can load
    # it WITHOUT needing xgboost installed.
    saved = {
        "model": calibrated,            # shipped model = calibrated LightGBM
        "baseline": baseline,           # logistic-regression baseline
        "features": FEATURES,
        "feature_importances": dict(
            zip(FEATURES, [float(x) for x in base.feature_importances_])),
    }
    models_dir = ML_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(saved, models_dir / "podium_model.pkl")

    # Full artifact (incl. XGBoost benchmark) returned for in-process evaluation only —
    # NOT pickled, to keep the app decoupled from xgboost.
    return {**saved, "xgboost": calibrated_xgb}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ML_DIR))
    train()
    print("trained -> ml/models/podium_model.pkl")
