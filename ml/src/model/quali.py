"""Stage-1 QUALIFYING model: predict each driver's qualifying gap-to-pole from history.

This lets us estimate a race's grid *before* qualifying happens, feeding it into the
Stage-2 race (podium) model. Same leakage discipline: features use only pre-event data.

Target  : quali_time_gap_to_pole (seconds; pole = 0)
Features: recent qualifying form + qualifying track history + team qualifying pace
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from src.data.jolpica import laptime_to_seconds
from src.model.data import ML_DIR

RAW = ML_DIR / "data" / "raw"
QUALI_FEATURES = [
    "recent_quali_gap",      # avg gap-to-pole over last 5 races
    "recent_quali_pos",      # avg qualifying position over last 5 races
    "quali_track_hist",      # avg gap-to-pole at THIS circuit, prior years
    "team_quali_strength",   # constructor recent avg gap-to-pole
]
QTARGET = "quali_gap"
WINDOW = 5


def _load(t):
    return pd.concat([pd.read_parquet(f) for f in sorted(RAW.glob(f"{t}_*.parquet"))],
                     ignore_index=True)


def build_quali_features() -> pd.DataFrame:
    res, qua = _load("results"), _load("qualifying")
    cmap = res[["season", "round", "circuit_id"]].drop_duplicates()
    q = qua.merge(cmap, on=["season", "round"], how="left")

    for c in ["q1", "q2", "q3"]:
        q[f"{c}_s"] = q[c].map(laptime_to_seconds)
    q["best_s"] = q[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    q["quali_gap"] = q["best_s"] - q.groupby(["season", "round"])["best_s"].transform("min")
    q = q.sort_values(["season", "round"]).reset_index(drop=True)

    byd = q.groupby("driver_id")
    q["recent_quali_gap"] = byd["quali_gap"].transform(
        lambda s: s.shift(1).rolling(WINDOW, min_periods=1).mean())
    q["recent_quali_pos"] = byd["quali_position"].transform(
        lambda s: s.shift(1).rolling(WINDOW, min_periods=1).mean())
    q["quali_track_hist"] = q.groupby(["driver_id", "circuit_id"])["quali_gap"].transform(
        lambda s: s.shift(1).expanding().mean())

    tr = (q.groupby(["constructor_id", "season", "round"])["quali_gap"].mean()
            .reset_index(name="tg").sort_values(["constructor_id", "season", "round"]))
    tr["team_quali_strength"] = tr.groupby("constructor_id")["tg"].transform(
        lambda s: s.shift(1).rolling(WINDOW, min_periods=1).mean())
    q = q.merge(tr[["constructor_id", "season", "round", "team_quali_strength"]],
                on=["constructor_id", "season", "round"], how="left")

    # cold-start fills
    q["recent_quali_gap"] = q["recent_quali_gap"].fillna(1.0)
    q["recent_quali_pos"] = q["recent_quali_pos"].fillna(11.0)
    q["quali_track_hist"] = q["quali_track_hist"].fillna(q["recent_quali_gap"])
    q["team_quali_strength"] = q["team_quali_strength"].fillna(1.0)
    return q


def train_quali():
    q = build_quali_features().dropna(subset=[QTARGET])
    train = q[q.season <= 2022]
    model = lgb.LGBMRegressor(
        n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
        min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
        reg_lambda=1.0, random_state=42, verbosity=-1)
    model.fit(train[QUALI_FEATURES], train[QTARGET])

    artifact = {"model": model, "features": QUALI_FEATURES}
    joblib.dump(artifact, ML_DIR / "models" / "quali_model.pkl")

    # quick eval on test (>=2024): rank by predicted gap, compare to actual quali pos
    test = q[q.season >= 2024].copy()
    test["pred"] = model.predict(test[QUALI_FEATURES])
    median_gap_mae = float((test["pred"] - test[QTARGET]).abs().median())
    grid_err, pole_hits, n = [], 0, 0
    for _, g in test.groupby(["season", "round"]):
        g = g.copy()
        g["pred_grid"] = g["pred"].rank(method="first")
        grid_err.append((g["pred_grid"] - g["quali_position"]).abs().mean())
        n += 1
        if g.sort_values("pred").iloc[0]["quali_position"] == 1:
            pole_hits += 1
    metrics = {
        "mean_grid_error": round(float(np.mean(grid_err)), 2),
        "pole_accuracy": round(pole_hits / n, 3),
        "median_gap_mae": round(median_gap_mae, 3),
        "train_races": int(train[["season", "round"]].drop_duplicates().shape[0]),
        "test_races": n,
    }
    (ML_DIR / "models" / "quali_metrics.json").write_text(json.dumps(metrics, indent=2))
    return artifact, metrics
