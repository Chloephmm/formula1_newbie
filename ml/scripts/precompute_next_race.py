"""Prepare and confirm the next event's saved initial forecast.

This is the Monday rollover step. It materializes the prior event's deterministic
final selection when due, then creates the next event metadata and at most one
pre-qualifying initial. Missing the pre-qualifying deadline is recorded as
``missing_initial``; it never fabricates or backdates an initial forecast.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys
import tempfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ML_DIR = ROOT / "ml"
SCRIPTS = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "web" / "public" / "data"
sys.path.insert(0, str(ML_DIR))
sys.path.insert(0, str(SCRIPTS))

from check_qualifying import (  # noqa: E402
    _load_history,
    _read_json,
    _remote_reader,
    model_manifest,
)
from src.features.build_features import FEATURES  # noqa: E402
from src.model.forecast import (  # noqa: E402
    _forecast_prepared,
    _prepare_forecast_inputs,
    next_race,
)
from src.model.quali import QUALI_FEATURES  # noqa: E402
from src.model.retrain import retrain_live  # noqa: E402
from src.pipeline.artifacts import (  # noqa: E402
    build_prediction,
    build_provenance,
    load_prediction_for_input,
)
from src.pipeline.events import (  # noqa: E402
    apply_event_override,
    build_event_metadata,
    event_windows,
    parse_utc,
    provisional_roster_from_results,
    write_event_json,
)
from src.pipeline.publish import (  # noqa: E402
    GitPublisher,
    publish_candidate,
    select_final,
    stage_candidate,
    write_final,
)
from src.pipeline.state import write_status_json  # noqa: E402


def _json_row(row: pd.Series) -> dict:
    return row.where(pd.notna(row), None).to_dict()


def build_next_event(asof: str, *, observed_at: datetime) -> dict:
    """Build exact event metadata from cached schedule and prior-race entries."""

    target = next_race(asof)
    if target is None:
        raise RuntimeError(f"No race on/after {asof} in cached schedule")
    schedule = _json_row(target)
    season, round_number = int(schedule["season"]), int(schedule["round"])
    history = _load_history()["results"]
    identities = history[["season", "round"]].drop_duplicates()
    prior = identities.loc[
        (pd.to_numeric(identities["season"]) < season)
        | (
            (pd.to_numeric(identities["season"]) == season)
            & (pd.to_numeric(identities["round"]) < round_number)
        )
    ]
    if prior.empty:
        raise RuntimeError("No completed prior race exists for provisional entries")
    prior_identity = max(
        (int(row.season), int(row["round"])) for _, row in prior.iterrows()
    )
    prior_rows = history.loc[
        (pd.to_numeric(history["season"]) == prior_identity[0])
        & (pd.to_numeric(history["round"]) == prior_identity[1])
    ].to_dict("records")
    source_url = (
        f"https://api.jolpi.ca/ergast/f1/{prior_identity[0]}/"
        f"{prior_identity[1]}/results/"
    )
    roster, source = provisional_roster_from_results(
        prior_rows,
        season=prior_identity[0],
        round_number=prior_identity[1],
        source_url=source_url,
        observed_at=observed_at,
    )
    event = build_event_metadata(schedule, roster, source)
    event["country"] = schedule.get("country")
    overrides = _read_json(ML_DIR / "config" / "event_overrides.json", {})
    return apply_event_override(event, overrides)


def build_initial_prediction(event: dict, *, generated_at: datetime) -> dict:
    """Fit both stages on the exact pre-event snapshot and build schema 2."""

    history = _load_history()
    model_event = dict(event, training_cutoff=generated_at)
    prepared, features, _ = _prepare_forecast_inputs(
        model_event,
        mode="predicted_qualifying",
        history=history,
        entries=event["roster"],
    )
    input_columns = [
        "driver_id",
        *dict.fromkeys([*FEATURES, *QUALI_FEATURES]),
    ]
    input_columns = [column for column in input_columns if column in features.columns]
    provenance = build_provenance(
        event,
        mode="predicted_qualifying",
        training_cutoff=generated_at,
        training_snapshot=prepared,
        model_manifest=model_manifest(stages=("stage1", "stage2")),
        feature_inputs=features[input_columns],
    )
    existing = load_prediction_for_input(DATA_ROOT, event, provenance["input_hash"])
    if existing is not None:
        return existing
    models = retrain_live(
        generated_at,
        int(event["season"]),
        int(event["round"]),
        history=history,
    )
    forecast = _forecast_prepared(
        event,
        mode="predicted_qualifying",
        features=features,
        models=models,
    )
    return build_prediction(
        event,
        forecast=forecast,
        generated_at=generated_at,
        provenance=provenance,
    )


def materialize_previous_final(now: datetime) -> dict | None:
    """Write a due prior final from confirmed receipts without recomputation."""

    feed = _read_json(DATA_ROOT / "prediction_feed.json")
    if not feed or not isinstance(feed.get("event"), dict):
        return None
    event = feed["event"]
    if parse_utc(now) < event_windows(event)["cutoff_at"]:
        return None
    directory = (
        DATA_ROOT
        / "prediction_snapshots"
        / f"{int(event['season'])}-{int(event['round'])}"
    )
    receipts = [
        value
        for path in sorted(directory.glob("publications/*.json"))
        if (value := _read_json(path)) is not None
    ]
    selection = select_final(
        receipts, event_windows(event)["cutoff_at"], event=event
    )
    return write_final(event, selection, root=DATA_ROOT)


def publish_initial(event: dict, prediction: dict) -> dict:
    feed = _read_json(DATA_ROOT / "prediction_feed.json") or {}
    target_id = f"{event['season']}-{event['round']}"
    same_event = feed.get("current_event_id") == target_id
    current = (feed.get("current") or {}).get("prediction") or {}
    status = dict(feed.get("status") or {})
    candidate = stage_candidate(
        Path(tempfile.gettempdir()) / "f1-publication-staging",
        event,
        prediction,
        expected_current_id=current.get("prediction_id") if same_event else None,
        expected_source_version=(
            status.get("qualifying_source_version") if same_event else None
        ),
        expected_feed_event_id=feed.get(
            "current_event_id", target_id
        ),
    )
    publisher = GitPublisher(
        ROOT,
        remote="origin",
        branch=os.environ.get("PREDICTION_BRANCH", "main"),
        remote_reader=_remote_reader,
    )
    return publish_candidate(candidate, publisher=publisher)


def main(asof: str, *, now: datetime | None = None) -> dict:
    generated_at = now or datetime.now(timezone.utc)
    materialize_previous_final(generated_at)
    event = build_next_event(asof, observed_at=generated_at)
    directory = (
        DATA_ROOT
        / "prediction_snapshots"
        / f"{event['season']}-{event['round']}"
    )
    initial_path = directory / "initial.json"
    print(
        f"Next race: {event['race_name']} "
        f"(round {event['round']}, race {event['race_start_at']})"
    )
    if initial_path.exists():
        print("Initial forecast already exists; preserving the immutable archive.")
        return {"outcome": "initial_preserved", "event": event}
    if parse_utc(generated_at) >= parse_utc(event["qualifying_start_at"]):
        write_event_json(directory / "event.json", event)
        write_status_json(
            directory / "status.json",
            {
                "validation_reason": "missing_initial",
                "last_error": "initial_deadline_missed",
            },
        )
        print("Initial deadline was missed; event saved for actual qualifying only.")
        return {"outcome": "missing_initial", "event": event}

    print("Retraining both stages on pre-event history …")
    prediction = build_initial_prediction(event, generated_at=generated_at)
    print("Confirming the saved initial through the publication origin …")
    receipt = publish_initial(event, prediction)
    print(f"Confirmed initial {prediction['prediction_id']}.")
    return {
        "outcome": "initial_published",
        "event": event,
        "prediction": prediction,
        "receipt": receipt,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asof",
        default=date.today().isoformat(),
        help="as-of date (YYYY-MM-DD); defaults to today",
    )
    args = parser.parse_args()
    main(args.asof)
