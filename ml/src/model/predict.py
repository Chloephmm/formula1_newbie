"""Generate per-race podium predictions for the website.

For each race: score every driver, normalize so the probabilities sum to 3 (three
podium spots), and sort descending. Index 0 = predicted winner; top 3 = predicted podium.
"""
from __future__ import annotations

import pandas as pd

from src.model.data import FEATURES


def predict_per_race(model, df: pd.DataFrame) -> dict:
    """Return {"<season>-<round>": [ {driver, team, podiumProbability}, ... ]}."""
    out: dict[str, list] = {}
    proba = model.predict_proba(df[FEATURES])[:, 1]
    df = df.assign(_p=proba)
    for (season, rnd), g in df.groupby(["season", "round"]):
        s = g["_p"].clip(lower=1e-6)
        norm = s * 3.0 / s.sum()                      # sum to 3 podium spots
        g = g.assign(podiumProbability=norm).sort_values("podiumProbability", ascending=False)
        out[f"{int(season)}-{int(rnd)}"] = [
            {
                "driver": row.code if isinstance(row.code, str) else row.driver_id,
                "driverName": row.driver_name,
                "team": row.constructor_name,
                "podiumProbability": round(float(row.podiumProbability), 4),
            }
            for row in g.itertuples()
        ]
    return out
