"""Shared dataset helpers for the model layer: features, target, season split."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ML_DIR = Path(__file__).resolve().parents[2]
PROCESSED = ML_DIR / "data" / "processed" / "features.parquet"

FEATURES = [
    "grid_position",
    "quali_time_gap_to_pole",
    "recent_form",
    "recent_points",
    "team_strength",
    "track_history",
    "dnf_rate",
]
TARGET = "podium"


def load_features() -> pd.DataFrame:
    if not PROCESSED.exists():
        raise FileNotFoundError(
            f"{PROCESSED} not found. Run scripts/build_features.py first.")
    return pd.read_parquet(PROCESSED)


def split_by_season(df: pd.DataFrame):
    """LOCKED three-way chronological split."""
    train_fit = df[df.season <= 2022].reset_index(drop=True)
    calib = df[df.season == 2023].reset_index(drop=True)
    test = df[df.season >= 2024].reset_index(drop=True)
    return train_fit, calib, test
