"""Shared forecasting logic: given an as-of date, predict the next race.

Returns a structured dict (no printing) so it can be reused by:
  - the CLI (scripts/predict_dual.py)
  - the Streamlit app (streamlit_app/app.py)

Pipeline: date -> next race -> data before it -> Stage-1 quali model -> Stage-2 race
model. MODE 1 (pre-qualifying) always; MODE 2 (real grid) when qualifying exists by then.

Both models are trained live (expanding window, every race strictly before the target GP).
Callers may pass pre-trained models via `models=` to skip the retrain — the Streamlit app
uses this to cache the retrain across renders. With `models=None`, `forecast()` retrains
internally via `retrain_live()`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.jolpica import laptime_to_seconds
from src.model.data import FEATURES, ML_DIR
from src.model.quali import QUALI_FEATURES
from src.model.retrain import retrain_live

RAW = ML_DIR / "data" / "raw"
WINDOW = 5


def _load(t):
    return pd.concat([pd.read_parquet(f) for f in sorted(RAW.glob(f"{t}_*.parquet"))],
                     ignore_index=True)


def _load_schedule():
    sched = _load("schedule")
    sched["date"] = pd.to_datetime(sched["date"], errors="coerce")
    return sched.dropna(subset=["date"]).sort_values("date")


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
    quali_date = tdate - pd.Timedelta(days=1)

    res, qua = _load("results"), _load("qualifying")
    res["date"] = pd.to_datetime(res["date"], errors="coerce")
    for c in ["q1", "q2", "q3"]:
        qua[f"{c}_s"] = qua[c].map(laptime_to_seconds)
    qua["best_s"] = qua[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    qua["quali_gap"] = qua["best_s"] - qua.groupby(["season", "round"])["best_s"].transform("min")

    t = res.merge(qua[["season", "round", "driver_id", "quali_gap", "quali_position"]],
                  on=["season", "round", "driver_id"], how="left")
    t["is_dnf"] = (~((t.status == "Finished") | t.status.astype(str).str.startswith("+"))).astype(int)
    t["grid"] = t["grid"].replace(0, np.nan)
    t = t[t["date"] < tdate].sort_values(["season", "round"]).reset_index(drop=True)
    if t.empty:
        return {"error": "No completed-race data before the target date."}

    last = t.sort_values("date").iloc[-1]
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

    # MODE 1 — pre-qualifying (Stage 1 -> Stage 2)
    g = quali_model.predict(X[QUALI_FEATURES])
    X["m1_gap"] = np.clip(g - g.min(), 0, None)
    X["m1_grid"] = X["m1_gap"].rank(method="first")
    X["mode1"] = _podium(race_model, X.assign(grid_position=X["m1_grid"],
                                              quali_time_gap_to_pole=X["m1_gap"]))

    # MODE 2 — real grid (only if qualifying happened by `asof` and exists)
    real_q = qua[(qua.season == tseason) & (qua["round"] == tround)].set_index("driver_id")
    # real-grid mode only AFTER qualifying day (on/before quali day -> 2-stage predict)
    has_real = (len(real_q) > 0) and (asof > quali_date)
    real_podium = None
    real_quali = None
    if has_real:
        X["r_grid"] = X["driver_id"].map(lambda d: real_q.loc[d, "quali_position"] if d in real_q.index else np.nan)
        X["r_gap"] = X["driver_id"].map(lambda d: real_q.loc[d, "quali_gap"] if d in real_q.index else np.nan)
        X["mode2"] = _podium(race_model, X.assign(grid_position=X["r_grid"].fillna(X["r_grid"].max()),
                                                  quali_time_gap_to_pole=X["r_gap"].fillna(X["r_gap"].max())))
        b = X.sort_values("mode2", ascending=False)
        real_podium = [_pod(r, r.mode2) for r in b.itertuples()]
        rqd = X.assign(r_gap_f=X["r_gap"].fillna(X["r_gap"].max())).sort_values("r_grid", na_position="last")
        real_quali = [
            {"position": i + 1, "code": r.code, "driverName": r.name, "team": r.team,
             "teamId": r.team_id, "gap": round(float(r.r_gap_f), 3)}
            for i, r in enumerate(rqd.itertuples())]

    q = X.sort_values("m1_grid")
    a = X.sort_values("mode1", ascending=False)
    return {
        "error": None,
        "asof": str(asof.date()),
        "race": {"name": tgt.race_name, "season": tseason, "round": tround,
                 "country": getattr(tgt, "country", None),
                 "date": str(tdate.date()), "qualifyingDate": str(quali_date.date())},
        "predictedQualifying": [
            {"position": i + 1, "code": r.code, "driverName": r.name, "team": r.team,
             "teamId": r.team_id, "gap": round(float(r.m1_gap), 3)}
            for i, r in enumerate(q.itertuples())],
        "preQualifyingPodium": [_pod(r, r.mode1) for r in a.itertuples()],
        "hasRealGrid": bool(has_real),
        "realGridPodium": real_podium,
        "realQualifying": real_quali,
    }
