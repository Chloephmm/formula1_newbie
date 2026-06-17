"""Offline hyperparameter tuning for the Stage-2 podium LightGBM (Optuna).

Discipline (matches the model itself — no leakage, time-aware):
  • Objective = mean ROC-AUC over an EXPANDING season CV. For each validation season
    in {2022, 2023, 2024} we fit on every prior season and score that season. AUC is a
    smooth surrogate for ranking quality (podium hit rate is too coarse to optimise on).
  • Seasons 2025–2026 are NEVER touched during tuning, so the acceptance backtest's
    2025-2026 / 2026 columns are an honest out-of-sample check.
  • Search space is regularisation-focused — the dataset is small (~5k rows, 7 feats),
    so aggressive trees overfit.

After the search, runs a walk-forward podium backtest (train on all prior races, score)
with the CURRENT params vs the TUNED params and prints both, so you can decide whether the
gain is real before adopting. Writes the best params to ml/models/podium_hparams.json.

Run:
    # macOS: LightGBM needs libomp (see ml/scripts/fix_libomp_macos.sh)
    python ml/scripts/tune_hyperparams.py --trials 60
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR))

from src.features.build_features import FEATURES, build_feature_table  # noqa: E402
from src.model.data import TARGET  # "podium"  # noqa: E402
from src.model.retrain import _LGBM_KW  # current hand-set params  # noqa: E402

VAL_SEASONS = [2022, 2023, 2024]   # tuning CV; 2025-2026 held out from tuning
BACKTEST_WINDOWS = [("2024-2026", 2024), ("2025-2026", 2025), ("2026 only", 2026)]
FIXED = dict(random_state=42, verbosity=-1, n_jobs=-1)


# ----------------------------- objective -----------------------------
def _cv_auc(df: pd.DataFrame, params: dict) -> float:
    aucs = []
    for vs in VAL_SEASONS:
        tr, va = df[df.season < vs], df[df.season == vs]
        if va[TARGET].nunique() < 2:
            continue
        m = lgb.LGBMClassifier(**params, **FIXED).fit(tr[FEATURES], tr[TARGET])
        aucs.append(roc_auc_score(va[TARGET], m.predict_proba(va[FEATURES])[:, 1]))
    return float(np.mean(aucs)) if aucs else 0.0


def _make_objective(df):
    def objective(trial):
        params = dict(
            n_estimators=trial.suggest_int("n_estimators", 100, 400, step=50),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            num_leaves=trial.suggest_int("num_leaves", 7, 63),
            max_depth=trial.suggest_int("max_depth", 3, 8),
            min_child_samples=trial.suggest_int("min_child_samples", 10, 80),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
            reg_lambda=trial.suggest_float("reg_lambda", 0.0, 5.0),
        )
        return _cv_auc(df, params)
    return objective


# --------------------- walk-forward podium backtest ---------------------
def _podium_backtest(df: pd.DataFrame, params: dict) -> dict:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    out = {}
    for label, y0 in BACKTEST_WINDOWS:
        races = df[df.season >= y0][["season", "round", "date"]].drop_duplicates()
        hit = win = n = 0
        for _, tr in races.iterrows():
            race = df[(df.season == tr.season) & (df["round"] == tr["round"])]
            actual3 = set(race[race.position <= 3]["code"])
            aw = race[race.position == 1]["code"]
            if len(actual3) < 3 or aw.empty:
                continue
            train = df[df["date"] < tr.date]
            m = lgb.LGBMClassifier(**params, **FIXED).fit(train[FEATURES], train[TARGET])
            r = race.assign(p=m.predict_proba(race[FEATURES])[:, 1]).sort_values("p", ascending=False)
            hit += len(set(r["code"].head(3)) & actual3) / 3
            win += int(r.iloc[0]["code"] == aw.iloc[0])
            n += 1
        out[label] = dict(races=n, podium=hit / n, winner=win / n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--adopt", action="store_true",
                    help="write best params to ml/models/podium_hparams.json")
    args = ap.parse_args()

    df = build_feature_table()
    current = {k: v for k, v in _LGBM_KW.items() if k not in ("random_state", "verbosity")}

    base_auc = _cv_auc(df, current)
    print(f"Current params — CV AUC: {base_auc:.4f}")

    print(f"\nTuning ({args.trials} trials, expanding CV on {VAL_SEASONS}) …")
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(_make_objective(df), n_trials=args.trials, show_progress_bar=False)
    best = study.best_params
    print(f"Best CV AUC: {study.best_value:.4f}  (current {base_auc:.4f}, "
          f"Δ {study.best_value - base_auc:+.4f})")
    print("Best params:", json.dumps(best, indent=2))

    print("\nWalk-forward podium backtest — CURRENT vs TUNED:")
    cur_bt, tun_bt = _podium_backtest(df, current), _podium_backtest(df, best)
    print(f"{'window':<14}{'metric':<10}{'CURRENT':>10}{'TUNED':>10}{'Δ':>8}")
    for label, _ in BACKTEST_WINDOWS:
        c, t = cur_bt[label], tun_bt[label]
        for key in ("podium", "winner"):
            d = t[key] - c[key]
            print(f"{label:<14}{key:<10}{c[key]:>9.1%}{t[key]:>10.1%}{d:>+8.1%}")

    if args.adopt:
        path = ML_DIR / "models" / "podium_hparams.json"
        path.write_text(json.dumps(best, indent=2))
        print(f"\nWrote {path.relative_to(ML_DIR.parent)}")
    else:
        print("\n(dry run — re-run with --adopt to write podium_hparams.json)")


if __name__ == "__main__":
    main()
