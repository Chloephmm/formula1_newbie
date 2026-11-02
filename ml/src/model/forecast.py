"""Shared forecasting logic: given an as-of date, predict the next race.

Returns a structured dict (no printing) so it can be reused by:
  - the CLI (scripts/predict_dual.py)
  - the Streamlit app (streamlit_app/app.py)

Pipeline: date -> next race -> data before it -> Stage-1 qualifying model -> Stage-2 race
model. This entry point always produces an estimated-qualifying forecast. Actual
qualifying is handled only by the validated publication pipeline.

Both models are trained live (expanding window, every race strictly before the target GP).
Callers may pass pre-trained models via `models=` to skip the retrain — the Streamlit app
uses this to cache the retrain across renders. With `models=None`, `forecast()` retrains
internally via `retrain_live()`.
"""
from __future__ import annotations

import copy
import numpy as np
import pandas as pd

from src.data.jolpica import laptime_to_seconds
from src.features.common import is_finished, sort_race_rows
from src.model.data import FEATURES, ML_DIR
from src.model.quali import QUALI_FEATURES
from src.model.retrain import retrain_live

RAW = ML_DIR / "data" / "raw"
WINDOW = 5


def _load(t):
    return sort_race_rows(pd.concat([pd.read_parquet(f) for f in sorted(RAW.glob(f"{t}_*.parquet"))],
                                   ignore_index=True))


def _load_schedule():
    sched = _load("schedule")
    sched["date"] = pd.to_datetime(sched["date"], errors="coerce")
    return sched.dropna(subset=["date"]).sort_values(["date", "season", "round"], kind="stable")


def next_race(asof):
    """The next Grand Prix on/after `asof` as a schedule row, or None if none remain.

    Shared by `forecast()` and the Streamlit app so both agree on the target race
    (and the app can key the live-retrain cache on it) without duplicating the lookup.
    """
    asof = pd.Timestamp(asof).normalize()
    upcoming = _load_schedule()[lambda s: s["date"] >= asof]
    return None if upcoming.empty else upcoming.iloc[0]


def _podium(model, X):
    p = model.predict_proba(X[FEATURES])[:, 1]
    return p * 3.0 / p.sum()


def _pod(row, prob):
    """One podium entry from a DataFrame row + a probability value."""
    return {"code": row.code, "driverName": row.name, "team": row.team,
            "teamId": row.team_id, "podiumProbability": round(float(prob), 4)}


def _historical_driver_table(target_date) -> pd.DataFrame:
    """Build the leakage-safe history table used to feature actual entrants."""
    target_date = pd.Timestamp(target_date).normalize()
    res, qua = _load("results"), _load("qualifying")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    for column in ("q1", "q2", "q3"):
        qua[f"{column}_s"] = qua[column].map(laptime_to_seconds)
    qua["best_s"] = qua[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    qua["quali_gap"] = (
        qua["best_s"]
        - qua.groupby(["season", "round"])["best_s"].transform("min")
    )
    history = res.merge(
        qua[["season", "round", "driver_id", "quali_gap", "quali_position"]],
        on=["season", "round", "driver_id"],
        how="left",
    )
    history["is_dnf"] = (~is_finished(history["status"])).astype(int)
    history["grid"] = history["grid"].replace(0, np.nan)
    return sort_race_rows(history[history["date"] < target_date])


def _actual_entry_features(
    history: pd.DataFrame,
    actual_qualifying,
    circuit_id: str,
) -> pd.DataFrame:
    """Feature validated entrants, including substitutions with no driver history."""
    history = sort_race_rows(history)
    if "is_dnf" not in history:
        history["is_dnf"] = (~is_finished(history["status"])).astype(int)
    team_position = (
        history.groupby(["constructor_id", "season", "round"])["position"]
        .mean().reset_index(name="team_position")
    )
    team_gap = (
        history.groupby(["constructor_id", "season", "round"])["quali_gap"]
        .mean().reset_index(name="team_gap")
    )
    rows = []
    for entrant in sorted(actual_qualifying, key=lambda row: row["driver_id"]):
        driver_id = entrant["driver_id"]
        constructor_id = entrant.get("constructor_id")
        driver_history = history[history.driver_id == driver_id]
        recent = driver_history.tail(WINDOW)
        at_circuit = driver_history[driver_history.circuit_id == circuit_id]
        rows.append({
            "driver_id": driver_id,
            "code": entrant.get("code") or driver_id[:3].upper(),
            "name": entrant.get("driver_name") or driver_id,
            "team": entrant.get("constructor_name") or constructor_id or "Unknown",
            "team_id": constructor_id,
            "recent_form": recent["position"].mean(),
            "recent_points": recent["points"].mean(),
            "team_strength": team_position[
                team_position.constructor_id == constructor_id
            ].tail(WINDOW)["team_position"].mean(),
            "track_history": at_circuit["position"].mean(),
            "dnf_rate": recent["is_dnf"].mean(),
            "recent_quali_gap": recent["quali_gap"].mean(),
            "recent_quali_pos": recent["quali_position"].mean(),
            "quali_track_hist": at_circuit["quali_gap"].mean(),
            "team_quali_strength": team_gap[
                team_gap.constructor_id == constructor_id
            ].tail(WINDOW)["team_gap"].mean(),
            "grid_position": int(entrant["qualifying_position"]),
            "quali_time_gap_to_pole": float(entrant["qualifying_gap_seconds"]),
        })
    features = pd.DataFrame(rows)
    for column, fill in [
        ("recent_form", 11.0),
        ("recent_points", 0.0),
        ("team_strength", 11.0),
        ("dnf_rate", 0.1),
        ("recent_quali_gap", 1.0),
        ("recent_quali_pos", 11.0),
        ("team_quali_strength", 1.0),
    ]:
        features[column] = features[column].fillna(fill)
    features["track_history"] = features["track_history"].fillna(features["recent_form"])
    features["quali_track_hist"] = features["quali_track_hist"].fillna(
        features["recent_quali_gap"]
    )
    return features


def forecast_actual_qualifying(
    *,
    base_forecast: dict,
    actual_qualifying,
    podium_model,
    target_date,
) -> dict:
    """Run Stage 2 with a fully validated actual qualifying classification."""
    rows = tuple(actual_qualifying)
    if not rows:
        raise ValueError("actual qualifying results are empty")
    race = base_forecast.get("race", {})
    expected = (int(race.get("season", -1)), int(race.get("round", -1)), race.get("name"))
    actual = (int(rows[0]["season"]), int(rows[0]["round"]), rows[0]["race_name"])
    if actual != expected or any(
        (int(row["season"]), int(row["round"]), row["race_name"]) != actual
        for row in rows
    ):
        raise ValueError("actual qualifying event does not match the forecast race")

    history = _historical_driver_table(target_date)
    features = _actual_entry_features(history, rows, rows[0]["circuit_id"])
    probabilities = _podium(podium_model, features)
    features["actual_podium"] = probabilities

    result = copy.deepcopy(base_forecast)
    # Stage 2 was just replaced: only its new model can attest to its training.
    if isinstance(result.get("training_metadata"), dict):
        result["training_metadata"].pop("stage2", None)
    metadata = getattr(podium_model, "training_metadata_", None)
    stage2 = metadata.get("stage2") if isinstance(metadata, dict) else None
    if isinstance(stage2, dict) and stage2:
        result.setdefault("training_metadata", {})["stage2"] = copy.deepcopy(stage2)
    result["inputMode"] = "actual_qualifying"
    result["hasActualQualifying"] = True
    result["actualQualifying"] = [
        {
            "position": int(row.grid_position),
            "code": row.code,
            "driverName": row.name,
            "team": row.team,
            "teamId": row.team_id,
            "gap": round(float(row.quali_time_gap_to_pole), 3),
        }
        for row in features.sort_values("grid_position", kind="stable").itertuples()
    ]
    result["actualQualifyingPodium"] = [
        _pod(row, row.actual_podium)
        for row in features.sort_values("actual_podium", ascending=False, kind="stable").itertuples()
    ]
    return result


def forecast(asof, models=None) -> dict:
    """Predict qualifying + podium for the next race on/after `asof` (date or 'YYYY-MM-DD').

    `models`: optional ``{"podium": clf, "quali": reg}`` already trained for this race.
    When omitted, both stages are retrained inline on every race before the target GP.
    """
    asof = pd.Timestamp(asof).normalize()

    tgt = next_race(asof)
    if tgt is None:
        latest = _load_schedule()["date"].max().date()
        return {"error": f"No race on/after {asof.date()} in cached data "
                         f"(latest: {latest}). Fetch newer data first."}

    tseason, tround = int(tgt.season), int(tgt["round"])
    tcircuit, tdate = tgt.circuit_id, tgt["date"]
    qualifying_start_at = getattr(tgt, "qualifying_start_at", None)
    if pd.isna(qualifying_start_at):
        qualifying_start_at = None
    race_start_at = getattr(tgt, "race_start_at", None)
    if pd.isna(race_start_at):
        race_start_at = None

    res, qua = _load("results"), _load("qualifying")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    for c in ["q1", "q2", "q3"]:
        qua[f"{c}_s"] = qua[c].map(laptime_to_seconds)
    qua["best_s"] = qua[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    qua["quali_gap"] = qua["best_s"] - qua.groupby(["season", "round"])["best_s"].transform("min")

    t = res.merge(qua[["season", "round", "driver_id", "quali_gap", "quali_position"]],
                  on=["season", "round", "driver_id"], how="left")
    t["is_dnf"] = (~is_finished(t["status"])).astype(int)
    t["grid"] = t["grid"].replace(0, np.nan)
    t = sort_race_rows(t[t["date"] < tdate])
    if t.empty:
        return {"error": "No completed-race data before the target date."}

    last = t.sort_values("date", kind="stable").iloc[-1]
    entry = (t[(t.season == last.season) & (t["round"] == last["round"])]
             [["driver_id", "code", "driver_name", "constructor_id", "constructor_name"]]
             .drop_duplicates("driver_id"))

    tr_pos = t.groupby(["constructor_id", "season", "round"])["position"].mean().reset_index(name="tp")
    tr_gap = t.groupby(["constructor_id", "season", "round"])["quali_gap"].mean().reset_index(name="tq")

    rows = []
    for r in entry.itertuples():
        h = t[t.driver_id == r.driver_id]
        last5 = h.tail(WINDOW)
        mon = h[h.circuit_id == tcircuit]
        rows.append({
            "driver_id": r.driver_id, "code": r.code, "name": r.driver_name,
            "team": r.constructor_name, "team_id": r.constructor_id,
            "recent_form": last5["position"].mean(),
            "recent_points": last5["points"].mean(),
            "team_strength": tr_pos[tr_pos.constructor_id == r.constructor_id].tail(WINDOW)["tp"].mean(),
            "track_history": mon["position"].mean(),
            "dnf_rate": last5["is_dnf"].mean(),
            "recent_quali_gap": last5["quali_gap"].mean(),
            "recent_quali_pos": last5["quali_position"].mean(),
            "quali_track_hist": mon["quali_gap"].mean(),
            "team_quali_strength": tr_gap[tr_gap.constructor_id == r.constructor_id].tail(WINDOW)["tq"].mean(),
        })
    X = pd.DataFrame(rows)
    for col, fill in [("recent_form", 11.0), ("recent_points", 0.0), ("team_strength", 11.0),
                      ("dnf_rate", 0.1), ("recent_quali_gap", 1.0), ("recent_quali_pos", 11.0),
                      ("team_quali_strength", 1.0)]:
        X[col] = X[col].fillna(fill)
    X["track_history"] = X["track_history"].fillna(X["recent_form"])
    X["quali_track_hist"] = X["quali_track_hist"].fillna(X["recent_quali_gap"])

    if models is None:
        models = retrain_live(tdate.date().isoformat(), tseason, tround)
    race_model, quali_model = models["podium"], models["quali"]

    # Estimated qualifying (Stage 1 -> Stage 2)
    g = quali_model.predict(X[QUALI_FEATURES])
    X["m1_gap"] = np.clip(g - g.min(), 0, None)
    X["m1_grid"] = X["m1_gap"].rank(method="first")
    X["mode1"] = _podium(race_model, X.assign(grid_position=X["m1_grid"],
                                              quali_time_gap_to_pole=X["m1_gap"]))

    q = X.sort_values("m1_grid", kind="stable")
    a = X.sort_values("mode1", ascending=False, kind="stable")
    result = {
        "error": None,
        "asof": str(asof.date()),
        "race": {"name": tgt.race_name, "season": tseason, "round": tround,
                 "country": getattr(tgt, "country", None),
                 "date": str(tdate.date()), "raceStartAt": race_start_at,
                 "qualifyingStartAt": qualifying_start_at},
        "predictedQualifying": [
            {"position": i + 1, "code": r.code, "driverName": r.name, "team": r.team,
             "teamId": r.team_id, "gap": round(float(r.m1_gap), 3)}
            for i, r in enumerate(q.itertuples())],
        "preQualifyingPodium": [_pod(r, r.mode1) for r in a.itertuples()],
        "inputMode": "estimated_qualifying",
        "hasActualQualifying": False,
        "actualQualifyingPodium": None,
        "actualQualifying": None,
    }
    if models.get("training_metadata") is not None:
        result["training_metadata"] = copy.deepcopy(models["training_metadata"])
    return result
