"""Explicit two-stage event forecasting plus a legacy offline wrapper.

``forecast_event`` never decides whether qualifying is available.  Its caller selects
one explicit mode and supplies either a validated qualifying object or no qualifying
data.  ``forecast`` remains an offline cache-reconstruction helper for the legacy CLI
and app; it always reconstructs the predicted-qualifying mode.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from numbers import Integral
import re
from typing import Any

import numpy as np
import pandas as pd

from src.data.jolpica import laptime_to_seconds
from src.model.data import FEATURES, ML_DIR
from src.model.quali import QUALI_FEATURES
from src.model.retrain import retrain_live
from src.pipeline.qualifying import AcceptedQualifying, QualifyingValidationError

RAW = ML_DIR / "data" / "raw"
WINDOW = 5
PODIUM_PROBABILITY_POLICY = "capped-sum-to-three-v1"


def _load(table):
    return pd.concat(
        [pd.read_parquet(path) for path in sorted(RAW.glob(f"{table}_*.parquet"))],
        ignore_index=True,
    )


def _load_schedule():
    schedule = _load("schedule")
    schedule["date"] = pd.to_datetime(schedule["date"], errors="coerce")
    return schedule.dropna(subset=["date"]).sort_values("date")


def next_race(asof):
    """Return the next cached schedule row on/after an offline as-of date."""

    asof = pd.Timestamp(asof).normalize()
    upcoming = _load_schedule()[lambda rows: rows["date"] >= asof]
    return None if upcoming.empty else upcoming.iloc[0]


def _event_identity(event: Mapping[str, Any]) -> tuple[int, int]:
    def positive_integer(value):
        if isinstance(value, bool):
            raise ValueError("event requires integer season and round")
        if isinstance(value, Integral):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise ValueError("event requires integer season and round")

    try:
        season = positive_integer(event["season"])
        round_number = positive_integer(event["round"])
    except KeyError as exc:
        raise ValueError("event requires integer season and round") from exc
    if season <= 0 or round_number <= 0:
        raise ValueError("event season and round must be positive")
    return season, round_number


def _event_cutoff(event: Mapping[str, Any]) -> pd.Timestamp:
    """Recorded training cutoff, falling back to the event start/date offline."""

    value = event.get("training_cutoff", event.get("race_start_at", event.get("date")))
    if value is None:
        raise ValueError("event requires training_cutoff, race_start_at, or date")
    cutoff = pd.Timestamp(value)
    if pd.isna(cutoff):
        raise ValueError("event training cutoff is invalid")
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    if "training_cutoff" in event:
        known_value = event.get("race_start_at", event.get("date"))
        if known_value is not None:
            known_event = pd.Timestamp(known_value)
            if pd.isna(known_event):
                raise ValueError("known event time is invalid")
            if known_event.tzinfo is None:
                known_event = known_event.tz_localize("UTC")
            else:
                known_event = known_event.tz_convert("UTC")
            if cutoff > known_event:
                raise ValueError("training cutoff cannot be later than the known event time")
    return cutoff


def _before_event(frame: pd.DataFrame, season: int, round_number: int) -> pd.Series:
    seasons = pd.to_numeric(frame["season"], errors="coerce")
    rounds = pd.to_numeric(frame["round"], errors="coerce")
    return (seasons < season) | ((seasons == season) & (rounds < round_number))


def _prepare_history(event: Mapping[str, Any], history: Mapping[str, pd.DataFrame]) -> dict:
    """Copy and filter raw history before any feature calculation.

    Results must pass both target-identity and recorded-date guards. Qualifying has no
    recorded date in the legacy cache, so it must also belong to an event present in
    the already-filtered completed results.
    """

    if not isinstance(history, Mapping):
        raise TypeError("history must map 'results' and 'qualifying' to DataFrames")
    results = history.get("results")
    qualifying = history.get("qualifying")
    if not isinstance(results, pd.DataFrame) or not isinstance(qualifying, pd.DataFrame):
        raise TypeError("history results and qualifying must be DataFrames")
    required_result = {"season", "round", "date", "driver_id"}
    required_quali = {"season", "round", "driver_id"}
    if not required_result.issubset(results.columns):
        raise ValueError("results history is missing event identity/date columns")
    if not required_quali.issubset(qualifying.columns):
        raise ValueError("qualifying history is missing event identity columns")

    season, round_number = _event_identity(event)
    cutoff = _event_cutoff(event)
    result_copy = results.copy(deep=True)
    dates = pd.to_datetime(result_copy["date"], errors="coerce", utc=True)
    result_copy = result_copy.loc[
        _before_event(result_copy, season, round_number) & (dates < cutoff)
    ].copy()
    result_copy["date"] = dates.loc[result_copy.index]

    completed_keys = result_copy[["season", "round"]].drop_duplicates()
    quali_copy = qualifying.copy(deep=True)
    quali_copy = quali_copy.loc[
        _before_event(quali_copy, season, round_number)
    ].copy()
    quali_copy = quali_copy.merge(completed_keys, on=["season", "round"], how="inner")
    return {
        "results": result_copy.reset_index(drop=True),
        "qualifying": quali_copy.reset_index(drop=True),
    }


def _entries_frame(entries: Sequence[Mapping[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """Normalize canonical roster records supplied as a list or DataFrame."""

    if isinstance(entries, pd.DataFrame):
        frame = entries.copy(deep=True)
    elif isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
        frame = pd.DataFrame([dict(record) for record in entries])
    else:
        raise TypeError("entries must be canonical roster records or a DataFrame")
    required = {
        "driver_id", "code", "driver_name", "constructor_id", "constructor_name",
        "eligible",
    }
    if not required.issubset(frame.columns):
        raise ValueError("entries are missing canonical roster columns")
    if frame.empty or frame["driver_id"].isna().any() or frame["driver_id"].duplicated().any():
        raise ValueError("entries require unique non-empty driver IDs")
    if not frame["eligible"].map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError("entry eligibility must be explicit booleans")
    frame = frame.loc[frame["eligible"].astype(bool)].copy()
    if frame.empty:
        raise ValueError("entries contain no eligible drivers")
    return frame.sort_values("driver_id", kind="stable").reset_index(drop=True)


def _history_with_quali_gaps(prepared: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    results = prepared["results"].copy(deep=True)
    qualifying = prepared["qualifying"].copy(deep=True)
    for column in ("q1", "q2", "q3"):
        if column not in qualifying:
            qualifying[column] = None
        qualifying[f"{column}_s"] = qualifying[column].map(laptime_to_seconds)
    qualifying["best_s"] = qualifying[["q1_s", "q2_s", "q3_s"]].min(axis=1)
    qualifying["quali_gap"] = qualifying["best_s"] - qualifying.groupby(
        ["season", "round"]
    )["best_s"].transform("min")
    columns = ["season", "round", "driver_id", "quali_gap", "quali_position"]
    merged = results.merge(qualifying[columns], on=["season", "round", "driver_id"], how="left")
    merged["is_dnf"] = (~(
        (merged["status"] == "Finished")
        | merged["status"].astype(str).str.startswith("+")
    )).astype(int)
    return merged.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)


def _build_event_features_from_prepared(
    event: Mapping[str, Any], prepared: Mapping[str, pd.DataFrame], entries
) -> pd.DataFrame:
    roster = _entries_frame(entries)
    history = _history_with_quali_gaps(prepared)
    circuit_id = event.get("circuit_id")

    team_finish = (
        history.groupby(["constructor_id", "season", "round"])["position"]
        .mean().reset_index(name="team_finish")
        .sort_values(["constructor_id", "season", "round"])
    )
    team_quali = (
        history.groupby(["constructor_id", "season", "round"])["quali_gap"]
        .mean().reset_index(name="team_quali")
        .sort_values(["constructor_id", "season", "round"])
    )

    rows = []
    for entry in roster.itertuples(index=False):
        driver_history = history.loc[history["driver_id"] == entry.driver_id]
        recent = driver_history.tail(WINDOW)
        track = driver_history.loc[driver_history["circuit_id"] == circuit_id]
        constructor = entry.constructor_id
        rows.append({
            "driver_id": entry.driver_id,
            "code": entry.code,
            "name": entry.driver_name,
            "team": entry.constructor_name,
            "team_id": constructor,
            "recent_form": recent["position"].mean(),
            "recent_points": recent["points"].mean(),
            "team_strength": team_finish.loc[
                team_finish["constructor_id"] == constructor, "team_finish"
            ].tail(WINDOW).mean(),
            "track_history": track["position"].mean(),
            "dnf_rate": recent["is_dnf"].mean(),
            "recent_quali_gap": recent["quali_gap"].mean(),
            "recent_quali_pos": recent["quali_position"].mean(),
            "quali_track_hist": track["quali_gap"].mean(),
            "team_quali_strength": team_quali.loc[
                team_quali["constructor_id"] == constructor, "team_quali"
            ].tail(WINDOW).mean(),
        })
    features = pd.DataFrame(rows)
    for column, fill in [
        ("recent_form", 11.0), ("recent_points", 0.0), ("team_strength", 11.0),
        ("dnf_rate", 0.1), ("recent_quali_gap", 1.0), ("recent_quali_pos", 11.0),
        ("team_quali_strength", 1.0),
    ]:
        features[column] = features[column].fillna(fill)
    features["track_history"] = features["track_history"].fillna(features["recent_form"])
    features["quali_track_hist"] = features["quali_track_hist"].fillna(
        features["recent_quali_gap"]
    )
    return features


def build_event_features(event, history, entries) -> pd.DataFrame:
    """Build target-event features from copied raw history and an explicit roster.

    ``entries`` accepts either canonical roster-record mappings or a DataFrame with
    the same fields. Only explicitly eligible entries are returned.
    """

    prepared = _prepare_history(event, history)
    return _build_event_features_from_prepared(event, prepared, entries)


def _qualifying_error(code: str, message: str):
    raise QualifyingValidationError(code, message)


def _validated_actual_rows(event, entries, qualifying) -> pd.DataFrame:
    if not isinstance(qualifying, AcceptedQualifying):
        _qualifying_error("unvalidated_qualifying", "actual mode requires AcceptedQualifying")
    if not isinstance(qualifying.source_version, str) or not re.fullmatch(
        r"[0-9a-f]{64}", qualifying.source_version
    ):
        _qualifying_error("invalid_source_version", "accepted qualifying source version is invalid")
    rows = qualifying.rows.copy(deep=True)
    accepted_roster = qualifying.roster.copy(deep=True)
    roster = _entries_frame(entries)
    required = {
        "season", "round", "driver_id", "constructor_id", "eligible",
        "quali_position", "quali_time_gap_to_pole",
        "model_position", "model_quali_time_gap_to_pole",
    }
    if not required.issubset(rows.columns):
        _qualifying_error("incomplete_qualifying", "accepted qualifying is missing model inputs")
    season, round_number = _event_identity(event)
    if rows.empty or not (
        (pd.to_numeric(rows["season"], errors="coerce") == season)
        & (pd.to_numeric(rows["round"], errors="coerce") == round_number)
    ).all():
        _qualifying_error("wrong_event", "accepted qualifying is not the exact target event")
    for field in ("race_name", "circuit_id"):
        if field in rows and event.get(field) is not None:
            if not rows[field].map(lambda value: value == event[field]).all():
                _qualifying_error("wrong_event", f"accepted qualifying has the wrong {field}")

    expected = roster[["driver_id", "constructor_id"]].sort_values("driver_id").reset_index(drop=True)
    eligible_rows = rows.loc[rows["eligible"].map(lambda value: value is True or value == True)].copy()
    actual = eligible_rows[["driver_id", "constructor_id"]].sort_values("driver_id").reset_index(drop=True)
    if expected.to_dict("records") != actual.to_dict("records"):
        _qualifying_error("incomplete_qualifying", "qualifying does not cover the eligible roster")
    if not {"driver_id", "constructor_id", "eligible"}.issubset(accepted_roster.columns):
        _qualifying_error("invalid_roster", "accepted qualifying roster is incomplete")
    accepted_eligible = accepted_roster.loc[
        accepted_roster["eligible"].map(lambda value: value is True or value == True),
        ["driver_id", "constructor_id"],
    ].sort_values("driver_id").reset_index(drop=True)
    if expected.to_dict("records") != accepted_eligible.to_dict("records"):
        _qualifying_error("invalid_roster", "accepted qualifying roster changed")

    model_positions = pd.to_numeric(eligible_rows["model_position"], errors="coerce")
    model_gaps = pd.to_numeric(
        eligible_rows["model_quali_time_gap_to_pole"], errors="coerce"
    )
    if (
        model_positions.isna().any()
        or not np.equal(model_positions, np.floor(model_positions)).all()
        or (model_positions <= 0).any()
        or model_positions.duplicated().any()
    ):
        _qualifying_error("invalid_model_position", "model positions must be unique positive integers")
    if not np.isfinite(model_gaps).all() or (model_gaps < 0).any():
        _qualifying_error("invalid_model_gap", "model gaps must be finite non-negative values")
    official = pd.to_numeric(eligible_rows["quali_position"], errors="coerce")
    present_official = official.dropna()
    if (
        present_official.duplicated().any()
        or (present_official <= 0).any()
        or not np.equal(present_official, np.floor(present_official)).all()
    ):
        _qualifying_error(
            "invalid_position", "official positions must be unique positive integers"
        )
    actual_gaps = pd.to_numeric(eligible_rows["quali_time_gap_to_pole"], errors="coerce")
    if not np.isfinite(actual_gaps.dropna()).all() or (actual_gaps.dropna() < 0).any():
        _qualifying_error("invalid_gap", "official gaps must be non-negative when present")
    eligible_rows["model_position"] = model_positions.astype(int)
    eligible_rows["model_quali_time_gap_to_pole"] = model_gaps.astype(float)
    return eligible_rows.sort_values("driver_id", kind="stable").reset_index(drop=True)


def _prepare_forecast_inputs(event, *, mode, history, entries, qualifying=None):
    prepared = _prepare_history(event, history)
    features = _build_event_features_from_prepared(event, prepared, entries)
    actual_rows = None
    if mode == "actual_qualifying":
        actual_rows = _validated_actual_rows(event, entries, qualifying)
    return prepared, features, actual_rows


def _podium_scores(model, frame):
    """Return raw scores and capped normalized podium estimates.

    At least three positive scores are required because ``min(1, scale * score)``
    cannot otherwise reach a total of three without inventing mass for zero scores.
    """

    raw = np.asarray(model.predict_proba(frame[FEATURES]), dtype=float)
    if raw.ndim != 2 or raw.shape != (len(frame), 2):
        raise ValueError("podium model returned invalid probability shape")
    scores = raw[:, 1]
    if len(scores) < 3:
        raise ValueError("podium normalization requires at least three entrants")
    if not np.isfinite(scores).all() or (scores < 0).any():
        raise ValueError("podium scores must be finite non-negative values")
    active = scores > 0
    if active.sum() < 3:
        raise ValueError("podium normalization requires at least three positive scores")

    normalized = np.zeros(len(scores), dtype=float)
    remaining = 3.0
    while active.any():
        active_scores = scores[active]
        relative_scores = active_scores / active_scores.max()
        candidates = relative_scores * (remaining / relative_scores.sum())
        active_indices = np.flatnonzero(active)
        capped = candidates >= 1.0
        if not capped.any():
            normalized[active] = candidates
            remaining = 0.0
            break
        capped_indices = active_indices[capped]
        normalized[capped_indices] = 1.0
        active[capped_indices] = False
        remaining -= float(len(capped_indices))
        if remaining < -1e-12:
            raise ValueError("podium normalization exceeded its total")
    if remaining > 1e-9 or not math.isclose(
        float(normalized.sum()), 3.0, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError("podium scores cannot be normalized to a capped total of three")
    return scores, normalized


def _podium(model, frame):
    return _podium_scores(model, frame)[1]


def _pod(row, probability, rank):
    return {
        "driver_id": row.driver_id, "code": row.code,
        "driverName": row.name, "team": row.team,
        "teamId": row.team_id, "podiumProbability": float(probability),
        "rank": rank,
    }


def _optional_int(value):
    return None if pd.isna(value) else int(value)


def _optional_float(value):
    return None if pd.isna(value) else float(value)


def _race_payload(event):
    season, round_number = _event_identity(event)
    date_value = event.get("date", event.get("race_start_at"))
    date_text = None if date_value is None else str(pd.Timestamp(date_value).date())
    qualifying_date = event.get("qualifying_date", event.get("qualifyingDate"))
    qualifying_estimated = event.get("qualifying_date_estimated")
    qualifying_source = event.get("qualifying_date_source")
    if qualifying_date is None and event.get("qualifying_start_at") is not None:
        qualifying_date = str(pd.Timestamp(event["qualifying_start_at"]).date())
        qualifying_estimated = False
        qualifying_source = "event-qualifying-start"
    payload = {
        "name": event.get("race_name"), "season": season, "round": round_number,
        "country": event.get("country"), "date": date_text,
        "qualifyingDate": qualifying_date,
    }
    if qualifying_estimated is not None:
        payload["qualifyingDateEstimated"] = bool(qualifying_estimated)
    if qualifying_source is not None:
        payload["qualifyingDateSource"] = qualifying_source
    return payload


def _forecast_prepared(event, *, mode, features, models, actual_rows=None) -> dict:
    if not isinstance(models, Mapping) or "podium" not in models:
        raise ValueError("models must contain a podium classifier")
    frame = features.copy(deep=True)
    predicted_qualifying = []
    pre_podium = []
    real_qualifying = None
    real_podium = None

    if mode == "predicted_qualifying":
        if "quali" not in models:
            raise ValueError("predicted_qualifying mode requires a quali regressor")
        estimates = np.asarray(models["quali"].predict(frame[QUALI_FEATURES]), dtype=float)
        if len(estimates) != len(frame) or not np.isfinite(estimates).all():
            raise ValueError("quali model returned invalid estimates")
        frame["predicted_gap"] = np.clip(estimates - estimates.min(), 0, None)
        frame["predicted_position"] = frame["predicted_gap"].rank(method="first")
        stage_two = frame.assign(
            grid_position=frame["predicted_position"],
            quali_time_gap_to_pole=frame["predicted_gap"],
        )
        frame["podium_raw_score"], frame["podium"] = _podium_scores(
            models["podium"], stage_two
        )
        predicted_qualifying = [
            {"driver_id": row.driver_id, "position": int(row.predicted_position),
             "code": row.code,
             "driverName": row.name, "team": row.team, "teamId": row.team_id,
             "gap": float(row.predicted_gap)}
            for row in frame.sort_values("predicted_position").itertuples()
        ]
        podium_order = frame.sort_values(
                ["podium", "podium_raw_score", "driver_id"],
                ascending=[False, False, True], kind="stable",
            )
        pre_podium = [
            _pod(row, row.podium, rank)
            for rank, row in enumerate(podium_order.itertuples(), start=1)
        ]
    elif mode == "actual_qualifying":
        if actual_rows is None:
            _qualifying_error("unvalidated_qualifying", "actual qualifying was not prepared")
        by_driver = actual_rows.set_index("driver_id")
        frame["actual_model_position"] = frame["driver_id"].map(by_driver["model_position"])
        frame["actual_model_gap"] = frame["driver_id"].map(
            by_driver["model_quali_time_gap_to_pole"]
        )
        stage_two = frame.assign(
            grid_position=frame["actual_model_position"],
            quali_time_gap_to_pole=frame["actual_model_gap"],
        )
        frame["podium_raw_score"], frame["podium"] = _podium_scores(
            models["podium"], stage_two
        )
        podium_order = frame.sort_values(
                ["podium", "podium_raw_score", "driver_id"],
                ascending=[False, False, True], kind="stable",
            )
        real_podium = [
            _pod(row, row.podium, rank)
            for rank, row in enumerate(podium_order.itertuples(), start=1)
        ]
        display = frame[["driver_id", "code", "name", "team", "team_id"]].merge(
            actual_rows[[
                "driver_id", "quali_position", "quali_time_gap_to_pole",
                "model_position", "model_quali_time_gap_to_pole",
            ]],
            on="driver_id", how="inner",
        ).sort_values("model_position")
        real_qualifying = [
            {"driver_id": row.driver_id,
             "position": _optional_int(row.quali_position), "code": row.code,
             "driverName": row.name, "team": row.team, "teamId": row.team_id,
             "gap": _optional_float(row.quali_time_gap_to_pole),
             "modelPosition": int(row.model_position),
             "modelGap": float(row.model_quali_time_gap_to_pole)}
            for row in display.itertuples()
        ]
    else:
        raise ValueError(f"unsupported forecast mode: {mode!r}")

    return {
        "error": None, "mode": mode, "race": _race_payload(event),
        "probabilityPolicyVersion": PODIUM_PROBABILITY_POLICY,
        "podiumEstimateSemantics": "normalized_podium_estimate",
        "predictedQualifying": predicted_qualifying,
        "preQualifyingPodium": pre_podium,
        "hasRealGrid": mode == "actual_qualifying",
        "realGridPodium": real_podium, "realQualifying": real_qualifying,
    }


def forecast_event(event, *, mode, history, entries, models, qualifying=None) -> dict:
    """Forecast one explicit event in predicted- or actual-qualifying mode."""

    if mode not in {"predicted_qualifying", "actual_qualifying"}:
        raise ValueError(f"unsupported forecast mode: {mode!r}")
    if mode == "predicted_qualifying" and qualifying is not None:
        raise ValueError("qualifying must be None in predicted_qualifying mode")
    _, features, actual_rows = _prepare_forecast_inputs(
        event, mode=mode, history=history, entries=entries, qualifying=qualifying
    )
    return _forecast_prepared(
        event, mode=mode, features=features, models=models, actual_rows=actual_rows
    )


def forecast(asof, models=None) -> dict:
    """Offline compatibility wrapper reconstructing a predicted-qualifying forecast.

    Cached target qualifying and the as-of date are never treated as proof that actual
    qualifying was available. The date-minus-one value retained in ``qualifyingDate``
    is a legacy display estimate only, not a production availability signal.
    """

    asof = pd.Timestamp(asof).normalize()
    target = next_race(asof)
    if target is None:
        latest = _load_schedule()["date"].max().date()
        return {"error": f"No race on/after {asof.date()} in cached data (latest: {latest}). "
                         "Fetch newer data first."}
    season, round_number = int(target.season), int(target["round"])
    target_date = pd.Timestamp(target["date"])
    history = {"results": _load("results"), "qualifying": _load("qualifying")}
    scheduled_quali = next(
        (
            value
            for value in (
                target.get("qualifying_date"),
                target.get("qualifyingDate"),
            )
            if value is not None and not pd.isna(value)
        ),
        None,
    )
    qualifying_start = target.get("qualifying_start_at")
    if scheduled_quali is not None:
        qualifying_date = str(pd.Timestamp(scheduled_quali).date())
        qualifying_date_estimated = False
        qualifying_date_source = "cached-schedule-field"
    elif qualifying_start is not None and not pd.isna(qualifying_start):
        qualifying_date = str(pd.Timestamp(qualifying_start).date())
        qualifying_date_estimated = False
        qualifying_date_source = "cached-schedule-qualifying-start"
    else:
        qualifying_date = str((target_date - pd.Timedelta(days=1)).date())
        qualifying_date_estimated = True
        qualifying_date_source = "legacy-race-date-minus-one-display-only"
    event = {
        "season": season, "round": round_number, "race_name": target.race_name,
        "circuit_id": target.circuit_id, "country": getattr(target, "country", None),
        "date": str(target_date.date()), "training_cutoff": str(target_date.date()),
        "qualifying_date": qualifying_date,
        "qualifying_date_estimated": qualifying_date_estimated,
        "qualifying_date_source": qualifying_date_source,
    }
    prepared = _prepare_history(event, history)
    completed = prepared["results"]
    if completed.empty:
        return {"error": "No completed-race data before the target date."}
    last = completed.sort_values(["date", "season", "round"]).iloc[-1]
    entries = (
        completed.loc[
            (completed["season"] == last.season) & (completed["round"] == last["round"]),
            ["driver_id", "code", "driver_name", "constructor_id", "constructor_name"],
        ].drop_duplicates("driver_id").assign(eligible=True, expected=True)
    )
    if models is None:
        models = retrain_live(
            target_date.date().isoformat(), season, round_number, history=history
        )
    result = forecast_event(
        event, mode="predicted_qualifying", history=history, entries=entries,
        models=models, qualifying=None,
    )
    result["asof"] = str(asof.date())
    result["executionContext"] = "offline-reconstruction"
    return result
