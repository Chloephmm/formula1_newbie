"""Export the website's static JSON from the trained model + cached standings.

Run from ml/ (after train_model.py):
    python scripts/export_json.py

Writes into <repo>/web/public/data/:
    predictions.json  - per-race podium probabilities (test seasons >=2024)
    races.json        - race list for the Predict dropdown
    teams.json        - latest-season constructor standings (+ their drivers)
    drivers.json      - latest-season driver standings (+ stats)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # add ml/ to sys.path

from src.model.data import ML_DIR, load_features  # noqa: E402
from src.model.predict import predict_per_race  # noqa: E402

RAW = ML_DIR / "data" / "raw"
WEB = ML_DIR.parent / "web" / "public" / "data"

# Brand colors aren't in any F1 API — small hardcoded lookup for the Teams page.
TEAM_COLORS = {
    "red_bull": "#3671C6", "ferrari": "#E8002D", "mercedes": "#27F4D2",
    "mclaren": "#FF8000", "aston_martin": "#229971", "alpine": "#0093CC",
    "williams": "#64C4FF", "rb": "#6692FF", "alphatauri": "#5E8FAA",
    "sauber": "#52E252", "kick_sauber": "#52E252", "haas": "#B6BABD",
    "alfa": "#C92D4B", "racing_point": "#F596C8", "renault": "#FFF500",
    "toro_rosso": "#469BFF", "force_india": "#F596C8", "lotus_f1": "#FFB800",
}


def _load(table: str) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(f) for f in sorted(RAW.glob(f"{table}_*.parquet"))],
                     ignore_index=True)


def build_races(race_keys: set[tuple[int, int]]) -> list:
    """Only races that actually have a prediction (i.e. have been run)."""
    s = _load("schedule")
    s = s[s.apply(lambda r: (int(r.season), int(r["round"])) in race_keys, axis=1)]
    s = s.sort_values(["season", "round"])
    return [{"season": int(getattr(r, "season")), "round": int(getattr(r, "round")),
             "name": r.race_name, "circuit": r.circuit_name, "date": r.date}
            for r in s.itertuples()]


def build_standings(season: int):
    ds = _load("driver_standings")
    cs = _load("constructor_standings")
    res = _load("results")
    ds, cs, rs = ds[ds.season == season], cs[cs.season == season], res[res.season == season]

    info = rs.groupby("driver_id").agg(
        driver_name=("driver_name", "first"), nationality=("nationality", "first")).reset_index()
    pod = (rs.assign(pod=(rs.position <= 3).astype(int))
             .groupby("driver_id")["pod"].sum().rename("podiums").reset_index())
    d = ds.merge(info, on="driver_id", how="left").merge(pod, on="driver_id", how="left")

    drivers = [{"id": r.driver_id, "name": r.driver_name, "code": r.code,
                "team": r.constructor_id, "nationality": r.nationality,
                "wins": int(r.wins), "podiums": int(r.podiums or 0), "points": float(r.points)}
               for r in d.sort_values("position").itertuples()]

    team_drivers = d.groupby("constructor_id")["code"].apply(list).to_dict()
    teams = [{"id": r.constructor_id, "name": r.constructor_name,
              "color": TEAM_COLORS.get(r.constructor_id, "#888888"),
              "points": float(r.points), "wins": int(r.wins),
              "drivers": team_drivers.get(r.constructor_id, [])}
             for r in cs.sort_values("position").itertuples()]
    return teams, drivers


def main() -> None:
    artifact = joblib.load(ML_DIR / "models" / "podium_model.pkl")
    model = artifact["model"]

    feats = load_features()
    pred_df = feats[feats.season >= 2024]                 # honest: test seasons only
    predictions = predict_per_race(model, pred_df)

    race_keys = {tuple(int(x) for x in k.split("-")) for k in predictions}
    races = build_races(race_keys)
    teams, drivers = build_standings(int(feats.season.max()))

    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "predictions.json").write_text(json.dumps(predictions))
    (WEB / "races.json").write_text(json.dumps(races, indent=2))
    (WEB / "teams.json").write_text(json.dumps(teams, indent=2))
    (WEB / "drivers.json").write_text(json.dumps(drivers, indent=2))

    print(f"wrote JSON to {WEB}")
    print(f"  predictions: {len(predictions)} races | races.json: {len(races)} | "
          f"teams: {len(teams)} | drivers: {len(drivers)}")


if __name__ == "__main__":
    main()
