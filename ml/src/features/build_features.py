"""Phase 2 — feature engineering.

Turn the cached raw tables (results, qualifying) into one model-ready table:
**one row per driver per race**, the ``podium`` label, and 7 leakage-safe features.

The golden rule: every feature uses ONLY data available BEFORE the race. For any
backward-looking stat we ``shift(1)`` so the current race is never included.

Output: ``ml/data/processed/features.parquet``.
Run via ``scripts/build_features.py`` (or ``python -m src.features.build_features``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.jolpica import laptime_to_seconds

ML_DIR = Path(__file__).resolve().parents[2]
RAW = ML_DIR / "data" / "raw"
PROCESSED = ML_DIR / "data" / "processed"

RECENT_WINDOW = 5          # races for driver recent-form / points / dnf
TEAM_WINDOW = 5            # races for constructor strength

FEATURES = [
    "grid_position",
    "quali_time_gap_to_pole",
    "recent_form",
    "recent_points",
    "team_strength",
    "track_history",
    "dnf_rate",
]


def _load(table: str) -> pd.DataFrame:
    files = sorted(RAW.glob(f"{table}_*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No cached {table}_*.parquet in {RAW}. Run scripts/fetch_data.py first."
        )
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _is_finished(status: pd.Series) -> pd.Series:
    """A driver is classified as finished if 'Finished' or lapped ('+N Lap(s)')."""
    s = status.astype(str)
    return (s == "Finished") | s.str.startswith("+")


def _quali_gap(qua: pd.DataFrame) -> pd.DataFrame:
    """Per driver-race gap (seconds) from their best qualifying lap to the pole time."""
    q = qua.copy()
    for c in ["q1", "q2", "q3"]:
        q[f"{c}_s"] = q[c].map(laptime_to_seconds)
    q["best_s"] = q[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    pole = q.groupby(["season", "round"])["best_s"].transform("min")
    q["quali_time_gap_to_pole"] = q["best_s"] - pole
    return q[["season", "round", "driver_id", "quali_time_gap_to_pole"]]


def build_feature_table() -> pd.DataFrame:
    res = _load("results")
    qua = _load("qualifying")

    # Chronological order is the backbone of every leakage-safe feature.
    df = res.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)

    # --- target ---
    df["podium"] = (df["position"] <= 3).astype(int)

    # --- finished / DNF flag ---
    df["is_dnf"] = (~_is_finished(df["status"])).astype(int)

    # --- grid: 0 means pit-lane start -> treat as back of the grid ---
    df["grid_position"] = df["grid"].replace(0, np.nan)
    df["grid_position"] = df["grid_position"].fillna(df["grid_position"].max())

    # --- driver rolling features (one row per driver per race; shift(1) = exclude current) ---
    by_driver = df.groupby("driver_id")
    df["recent_form"] = by_driver["position"].transform(
        lambda s: s.shift(1).rolling(RECENT_WINDOW, min_periods=1).mean())
    df["recent_points"] = by_driver["points"].transform(
        lambda s: s.shift(1).rolling(RECENT_WINDOW, min_periods=1).mean())
    df["dnf_rate"] = by_driver["is_dnf"].transform(
        lambda s: s.shift(1).rolling(RECENT_WINDOW, min_periods=1).mean())

    # --- track history: driver's avg finish at THIS circuit, prior visits only ---
    df["track_history"] = df.groupby(["driver_id", "circuit_id"])["position"].transform(
        lambda s: s.shift(1).expanding().mean())

    # --- team strength: computed at RACE level to avoid teammate same-race leakage ---
    team_race = (df.groupby(["constructor_id", "season", "round"])["position"]
                   .mean().reset_index(name="team_race_finish")
                   .sort_values(["constructor_id", "season", "round"]))
    team_race["team_strength"] = team_race.groupby("constructor_id")["team_race_finish"].transform(
        lambda s: s.shift(1).rolling(TEAM_WINDOW, min_periods=1).mean())
    df = df.merge(team_race[["constructor_id", "season", "round", "team_strength"]],
                  on=["constructor_id", "season", "round"], how="left")

    # --- qualifying gap (same-race qualifying happens BEFORE the race -> not leakage) ---
    df = df.merge(_quali_gap(qua), on=["season", "round", "driver_id"], how="left")

    # --- cold-start NaN fills (documented; neutral / mid-field defaults) ---
    MIDFIELD = 11.0
    df["recent_form"] = df["recent_form"].fillna(MIDFIELD)
    df["recent_points"] = df["recent_points"].fillna(0.0)
    df["dnf_rate"] = df["dnf_rate"].fillna(0.1)
    df["team_strength"] = df["team_strength"].fillna(MIDFIELD)
    df["track_history"] = df["track_history"].fillna(df["recent_form"])
    race_max_gap = df.groupby(["season", "round"])["quali_time_gap_to_pole"].transform("max")
    df["quali_time_gap_to_pole"] = df["quali_time_gap_to_pole"].fillna(race_max_gap).fillna(3.0)

    keep = ["season", "round", "race_name", "circuit_id", "date", "driver_id", "code",
            "driver_name", "constructor_id", "constructor_name", "position", "podium"] + FEATURES
    return df[keep].copy()


def main() -> None:
    df = build_feature_table()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED / "features.parquet"
    df.to_parquet(out_path, index=False)

    print(f"wrote {out_path}  shape={df.shape}")
    print(f"features ({len(FEATURES)}): {FEATURES}")
    print(f"podium positives: {int(df.podium.sum())} ({df.podium.mean():.1%})")
    print("NaNs in features:", int(df[FEATURES].isna().sum().sum()))
    print("\nper-split rows:")
    for name, m in [("train-fit <=2022", df.season <= 2022),
                    ("calibration 2023", df.season == 2023),
                    ("test >=2024", df.season >= 2024)]:
        print(f"  {name:20s} rows={int(m.sum()):5d}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ML_DIR))
    main()
