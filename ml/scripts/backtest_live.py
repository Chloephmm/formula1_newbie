"""Walk-forward backtest: frozen ≤2022 split vs live retrain (all races before target).

Reproduces the comparison that justified the live retrain. For each race in a recent test
window it trains two models — FROZEN (seasons ≤2022) and LIVE (every race strictly before
that race) — predicts, and scores. Leakage-safe throughout. Podium ranking is invariant
to calibration, so the base LightGBM is compared directly.

Run:
    # macOS: LightGBM needs libomp on the dyld path (see ml/scripts/fix_libomp_macos.sh)
    python ml/scripts/backtest_live.py
    python ml/scripts/backtest_live.py --write    # also dump ml/models/live_metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import lightgbm as lgb
import pandas as pd

warnings.filterwarnings("ignore")
ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR))

from src.features.build_features import FEATURES, build_feature_table  # noqa: E402
from src.model.quali import QTARGET, QUALI_FEATURES, build_quali_features  # noqa: E402

_KW = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
           min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
           reg_lambda=1.0, random_state=42, verbosity=-1)
WINDOWS = [("2024-2026", 2024), ("2025-2026", 2025), ("2026 only", 2026)]


def _podium_backtest(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    out = {}
    for label, y0 in WINDOWS:
        races = df[df.season >= y0][["season", "round", "date"]].drop_duplicates().sort_values("date")
        old_hit = c_hit = old_win = c_win = n = 0
        for _, tr in races.iterrows():
            race = df[(df.season == tr.season) & (df["round"] == tr["round"])]
            actual3 = set(race[race.position <= 3]["code"])
            aw = race[race.position == 1]["code"]
            if len(actual3) < 3 or aw.empty:
                continue
            aw = aw.iloc[0]
            for tag, train in (("old", df[df.season <= 2022]), ("c", df[df["date"] < tr.date])):
                m = lgb.LGBMClassifier(**_KW).fit(train[FEATURES], train["podium"])
                r = race.assign(p=m.predict_proba(race[FEATURES])[:, 1]).sort_values("p", ascending=False)
                hit = len(set(r["code"].head(3)) & actual3) / 3
                win = int(r.iloc[0]["code"] == aw)
                if tag == "old":
                    old_hit += hit; old_win += win
                else:
                    c_hit += hit; c_win += win
            n += 1
        out[label] = dict(races=n, old_podium=old_hit / n, c_podium=c_hit / n,
                          old_winner=old_win / n, c_winner=c_win / n)
    return out


def _quali_backtest():
    q = build_quali_features().dropna(subset=[QTARGET, "quali_position"]).copy()
    q["ord"] = q.season * 100 + q["round"]
    out = {}
    for label, y0 in WINDOWS:
        races = q[q.season >= y0][["season", "round", "ord"]].drop_duplicates().sort_values("ord")
        o_ge = c_ge = o_pole = c_pole = o_mae = c_mae = n = 0
        for _, tr in races.iterrows():
            race = q[(q.season == tr.season) & (q["round"] == tr["round"])]
            if race["quali_position"].nunique() < 3:
                continue
            for tag, train in (("old", q[q.season <= 2022]), ("c", q[q["ord"] < tr.ord])):
                m = lgb.LGBMRegressor(**_KW).fit(train[QUALI_FEATURES], train[QTARGET])
                g = race.assign(pred=m.predict(race[QUALI_FEATURES]))
                g = g.assign(pred_grid=g["pred"].rank(method="first"))
                ge = (g["pred_grid"] - g["quali_position"]).abs().mean()
                pole = int(g.sort_values("pred").iloc[0]["quali_position"] == 1)
                mae = float((g["pred"] - g[QTARGET]).abs().median())
                if tag == "old":
                    o_ge += ge; o_pole += pole; o_mae += mae
                else:
                    c_ge += ge; c_pole += pole; c_mae += mae
            n += 1
        out[label] = dict(races=n, old_grid_err=o_ge / n, c_grid_err=c_ge / n,
                          old_pole=o_pole / n, c_pole=c_pole / n,
                          old_gap_mae=o_mae / n, c_gap_mae=c_mae / n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="dump ml/models/live_metrics.json")
    args = ap.parse_args()

    podium = _podium_backtest(build_feature_table())
    quali = _quali_backtest()

    for label, _ in WINDOWS:
        p, q = podium[label], quali[label]
        print(f"\n=== {label}  ({p['races']} races) ===")
        print(f"{'metric':<26}{'FROZEN (<=2022)':>15}{'LIVE (all-before)':>19}")
        print(f"{'podium hit rate':<26}{p['old_podium']:>13.1%}{p['c_podium']:>16.1%}")
        print(f"{'winner correct':<26}{p['old_winner']:>13.1%}{p['c_winner']:>16.1%}")
        print(f"{'quali pole accuracy':<26}{q['old_pole']:>13.1%}{q['c_pole']:>16.1%}")
        print(f"{'quali mean grid error':<26}{q['old_grid_err']:>14.2f}{q['c_grid_err']:>16.2f}")
        print(f"{'quali median gap MAE':<26}{q['old_gap_mae']:>14.3f}{q['c_gap_mae']:>16.3f}")

    if args.write:
        path = ML_DIR / "models" / "live_metrics.json"
        path.write_text(json.dumps({"podium": podium, "quali": quali}, indent=2))
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
