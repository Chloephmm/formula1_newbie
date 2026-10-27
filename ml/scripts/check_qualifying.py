"""Plan or run one automatic qualifying-monitor tick.

``--plan`` is deliberately standard-library-only and is used before dependency
installation in GitHub Actions.  ``--run`` loads the model stack only after that
gate says work is due.  ``--dry-run`` reports the same decision without network,
tracked-file writes, Git commits, or pushes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
ML_DIR = ROOT / "ml"
DATA_ROOT = ROOT / "web" / "public" / "data"
FEED_PATH = DATA_ROOT / "prediction_feed.json"
SNAPSHOT_ROOT = DATA_ROOT / "prediction_snapshots"
DEFAULT_REPOSITORY = "Chloephmm/formula1_newbie"


def _utc(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, default=None):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _event_dir(event: Mapping[str, Any]) -> Path:
    return SNAPSHOT_ROOT / f"{int(event['season'])}-{int(event['round'])}"


def _feed_event(root: Path = ROOT) -> tuple[dict, dict] | None:
    data_root = root / "web" / "public" / "data"
    feed = _read_json(data_root / "prediction_feed.json")
    if feed and isinstance(feed.get("event"), dict):
        return dict(feed["event"]), dict(feed.get("status") or {})
    snapshots = data_root / "prediction_snapshots"
    candidates = []
    for path in snapshots.glob("*-*/event.json") if snapshots.exists() else ():
        event = _read_json(path)
        if event:
            candidates.append((int(event["season"]), int(event["round"]), path, event))
    if not candidates:
        return None
    _, _, path, event = max(candidates)
    return dict(event), dict(_read_json(path.with_name("status.json"), {}) or {})


def plan_needs_work(root: Path, now: datetime) -> tuple[bool, str]:
    """Evaluate the cheap due gate using only JSON and the standard library."""

    loaded = _feed_event(root)
    if loaded is None:
        return True, "event_bootstrap_required"
    event, status = loaded
    try:
        evaluated = _utc(now)
        qualifying_start = _utc(event["qualifying_start_at"])
        qualifying_end = _utc(
            event.get("qualifying_end_observed_at")
            or event.get("qualifying_end_at")
            or qualifying_start + timedelta(minutes=90)
        )
        cutoff = _utc(event["race_start_at"]) - timedelta(hours=2)
        first_check = qualifying_end + timedelta(hours=5)
        final_check = cutoff - timedelta(minutes=45)
        latest_start = cutoff - timedelta(minutes=15)
    except (KeyError, TypeError, ValueError):
        return True, "invalid_event_metadata"
    if status.get("frozen_at") or status.get("final_state") in {"frozen", "unavailable"}:
        return False, "already_frozen"

    last_refresh = status.get("last_schedule_refresh_at")
    if last_refresh is None:
        return True, "schedule_refresh_due"
    try:
        refresh_interval = (
            timedelta(hours=1)
            if qualifying_start - timedelta(hours=72) <= evaluated < cutoff
            else timedelta(days=1)
        )
        if evaluated >= _utc(last_refresh) + refresh_interval:
            return True, "schedule_refresh_due"
    except (TypeError, ValueError):
        return True, "invalid_schedule_refresh_state"

    if evaluated >= cutoff:
        return True, "freeze_due"
    if first_check >= cutoff:
        return False, "wait_exceeds_cutoff"
    if evaluated < first_check:
        return False, "before_first_check"
    if status.get("final_check_attempted_at"):
        return False, "final_check_already_attempted"
    if evaluated >= latest_start:
        return False, "insufficient_publication_window"
    if evaluated >= final_check:
        return True, "final_check_due"
    if status.get("actual_publication_confirmed") is True:
        return False, "actual_publication_confirmed"
    last_started = status.get("last_qualifying_check_started_at")
    if last_started is None:
        return True, "ordinary_check_due"
    try:
        due = evaluated >= _utc(last_started) + timedelta(hours=1)
    except (TypeError, ValueError):
        return True, "invalid_check_state"
    return (due, "ordinary_check_due" if due else "ordinary_check_not_due")


def _write_github_output(path: str | None, *, needs_work: bool, reason: str) -> None:
    if path is None:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"needs_work={'true' if needs_work else 'false'}\n")
        handle.write(f"reason={reason}\n")


def _load_active_event(now: datetime) -> tuple[dict, dict, dict | None]:
    loaded = _feed_event(ROOT)
    if loaded is None:
        raise RuntimeError(
            "No saved event metadata exists. Run the Monday refresh to prepare an initial forecast."
        )
    event, status = loaded
    feed = _read_json(FEED_PATH)
    return event, status, feed


def _load_history():
    import pandas as pd

    raw = ML_DIR / "data" / "raw"

    def load(name: str):
        paths = sorted(raw.glob(f"{name}_*.parquet"))
        if not paths:
            raise FileNotFoundError(f"No cached {name} history is available")
        return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)

    return {"results": load("results"), "qualifying": load("qualifying")}


def _code_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def model_manifest(*, stages: tuple[str, ...]) -> dict[str, Any]:
    """Return deterministic model/code/dependency evidence for an artifact."""

    from importlib.metadata import version
    from src.features.build_features import FEATURES
    from src.model.quali import QUALI_FEATURES
    from src.model.retrain import _LGBM_KW

    files = [
        ML_DIR / "src" / "model" / "forecast.py",
        ML_DIR / "src" / "model" / "retrain.py",
        ML_DIR / "src" / "features" / "build_features.py",
        ML_DIR / "src" / "model" / "quali.py",
    ]
    columns = list(FEATURES)
    if "stage1" in stages:
        columns += [column for column in QUALI_FEATURES if column not in columns]
    return {
        "code_hash": _code_hash(files),
        "parameters": {stage: dict(_LGBM_KW) for stage in stages},
        "feature_columns": columns,
        "library_versions": {
            package: version(package)
            for package in ("lightgbm", "numpy", "pandas", "scikit-learn")
        },
        "stages": list(stages),
    }


def build_actual_prediction(event, accepted, generated_at: datetime):
    """Create a schema-2 actual prediction from the exact validated input."""

    from src.features.build_features import FEATURES
    from src.model.forecast import _prepare_forecast_inputs
    from src.pipeline.artifacts import (
        build_prediction,
        build_provenance,
        load_prediction_for_input,
    )
    from src.pipeline.controller import generate_actual_candidate

    history = _load_history()
    prepared, features, actual_rows = _prepare_forecast_inputs(
        event,
        mode="actual_qualifying",
        history=history,
        entries=event["roster"],
        qualifying=accepted,
    )
    by_driver = actual_rows.set_index("driver_id")
    feature_inputs = features.copy(deep=True)
    feature_inputs["grid_position"] = feature_inputs["driver_id"].map(
        by_driver["model_position"]
    )
    feature_inputs["quali_time_gap_to_pole"] = feature_inputs["driver_id"].map(
        by_driver["model_quali_time_gap_to_pole"]
    )
    feature_inputs = feature_inputs[["driver_id", *FEATURES]]
    provenance = build_provenance(
        event,
        mode="actual_qualifying",
        training_cutoff=event["race_start_at"],
        training_snapshot=prepared,
        model_manifest=model_manifest(stages=("stage2",)),
        feature_inputs=feature_inputs,
        qualifying=accepted,
    )
    prior = load_prediction_for_input(
        DATA_ROOT, event, provenance["input_hash"]
    )
    if prior is not None:
        return prior
    generated = generate_actual_candidate(
        event,
        history=history,
        entries=event["roster"],
        qualifying=accepted,
        input_hash=provenance["input_hash"],
    )
    return build_prediction(
        event,
        forecast=generated["forecast"],
        generated_at=generated_at,
        provenance=provenance,
    )


def _remote_reader(commit: str, repository_path: str, *, timeout: float) -> bytes:
    import requests

    repository = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    url = f"https://raw.githubusercontent.com/{repository}/{commit}/{repository_path}"
    response = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-cache"})
    response.raise_for_status()
    return response.content


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = ""
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _run(now: datetime):
    import pandas as pd

    from src.data import jolpica
    from src.pipeline.artifacts import canonical_bytes, digest, validate_prediction
    from src.pipeline.controller import PipelineDependencies, run_due_work
    from src.pipeline.events import (
        apply_event_override,
        build_event_metadata,
        write_event_json,
    )
    from src.pipeline.publish import (
        GitPublisher,
        build_feed,
        publish_candidate,
        select_final,
        stage_candidate,
        write_final,
    )
    from src.pipeline.qualifying import (
        fetch_target_qualifying,
        replace_target_rows,
        validate_qualifying,
    )
    from src.pipeline.state import read_status_json, write_status_json

    event, status, initial_feed = _load_active_event(now)
    event_directory = _event_dir(event)
    status_path = event_directory / "status.json"
    if status_path.exists():
        status = read_status_json(status_path)
    runtime: dict[str, Any] = {"fetched": None, "latest_status": dict(status)}

    def refresh_schedule(current):
        schedule = jolpica.get_schedule(int(current["season"]), fetched_at=now)
        row = schedule.loc[
            (schedule["season"] == int(current["season"]))
            & (schedule["round"] == int(current["round"]))
        ]
        if len(row) != 1:
            raise ValueError("schedule refresh did not return the exact active event")
        record = row.iloc[0].where(pd.notna(row.iloc[0]), None).to_dict()
        if current.get("qualifying_end_observed_at"):
            record["qualifying_end_observed_at"] = current[
                "qualifying_end_observed_at"
            ]
        refreshed = build_event_metadata(
            record, current["roster"], current["roster_source"]
        )
        refreshed["country"] = record.get("country")
        overrides = _read_json(ML_DIR / "config" / "event_overrides.json", {})
        return apply_event_override(refreshed, overrides)

    def fetch(current):
        fetched = fetch_target_qualifying(
            int(current["season"]), int(current["round"])
        )
        runtime["fetched"] = fetched
        return fetched

    def validate(current, fetched):
        return validate_qualifying(current, fetched.rows, fetched.page_evidence)

    def generate(current, accepted, _source_version):
        return build_actual_prediction(current, accepted, _utc(datetime.now(timezone.utc)))

    def stage(current, prediction, accepted, current_status):
        fetched = runtime["fetched"]
        if fetched is None:
            raise RuntimeError("qualifying source evidence is unavailable")
        season = int(current["season"])
        raw_path = ML_DIR / "data" / "raw" / f"qualifying_{season}.parquet"
        old_bytes = raw_path.read_bytes() if raw_path.exists() else None
        existing = pd.read_parquet(raw_path) if raw_path.exists() else pd.DataFrame()
        merged = replace_target_rows(existing, accepted.rows, season, int(current["round"]))
        parquet = tempfile.SpooledTemporaryFile()
        merged.to_parquet(parquet, index=False)
        parquet.seek(0)
        raw_bytes = parquet.read()
        source = {
            "schema_version": 1,
            "season": season,
            "round": int(current["round"]),
            "source_version": accepted.source_version,
            "pages": list(fetched.page_evidence.source_pages),
            "retrieval_metadata": list(fetched.page_evidence.retrieval_metadata),
        }
        checked_at = _now_text(datetime.now(timezone.utc))
        check = {
            "schema_version": 1,
            "season": season,
            "round": int(current["round"]),
            "checked_at": checked_at,
            "outcome": "accepted",
            "source_version": accepted.source_version,
        }
        check_id = digest(check)
        base = (
            f"web/public/data/prediction_snapshots/{season}-{int(current['round'])}"
        )
        raw_repo_path = f"ml/data/raw/qualifying_{season}.parquet"
        files = {
            raw_repo_path: raw_bytes,
            f"{base}/sources/{accepted.source_version}.json": canonical_bytes(source) + b"\n",
            f"{base}/checks/{check_id}.json": canonical_bytes(check) + b"\n",
        }
        current_selection = (initial_feed or {}).get("current") or {}
        current_prediction = current_selection.get("prediction") or {}
        feed_event_id = (initial_feed or {}).get(
            "current_event_id", f"{season}-{int(current['round'])}"
        )
        staging = Path(tempfile.gettempdir()) / "f1-publication-staging"
        return stage_candidate(
            staging,
            current,
            prediction,
            expected_current_id=current_prediction.get("prediction_id"),
            expected_source_version=current_status.get("qualifying_source_version"),
            expected_feed_event_id=feed_event_id,
            expected_file_checksums={
                raw_repo_path: (
                    hashlib.sha256(old_bytes).hexdigest()
                    if old_bytes is not None
                    else None
                )
            },
            files=files,
        )

    publisher = GitPublisher(
        ROOT,
        remote="origin",
        branch=os.environ.get("PREDICTION_BRANCH", "main"),
        remote_reader=_remote_reader,
    )

    def publish(candidate):
        return publish_candidate(candidate, publisher=publisher)

    def freeze(current, current_status, _evaluated):
        receipts = []
        for path in sorted(_event_dir(current).glob("publications/*.json")):
            value = _read_json(path)
            if value:
                receipts.append(value)
        selection = select_final(
            receipts,
            _utc(current["race_start_at"]) - timedelta(hours=2),
            event=current,
        )
        write_final(current, selection, root=DATA_ROOT)
        return selection

    def capture_status(value):
        runtime["latest_status"] = dict(value)

    dependencies = PipelineDependencies(
        fetch_qualifying=fetch,
        validate_qualifying=validate,
        generate_prediction=generate,
        validate_prediction=lambda prediction, current: validate_prediction(
            prediction, current
        ),
        stage_prediction=stage,
        publish_prediction=publish,
        refresh_schedule=refresh_schedule,
        freeze=freeze,
        persist_status=capture_status,
    )
    result = run_due_work(
        event,
        status,
        clock=lambda: datetime.now(timezone.utc),
        dependencies=dependencies,
    )
    if result.outcome != "published":
        directory = _event_dir(result.event)
        write_event_json(directory / "event.json", result.event)
        write_status_json(directory / "status.json", result.status)
        feed = initial_feed
        if feed and feed.get("current_event_id") == (
            f"{result.event['season']}-{result.event['round']}"
        ):
            updated = build_feed(
                result.event,
                result.status,
                current=feed.get("current"),
                previous=feed.get("previous"),
                initial=feed.get("initial"),
                updated_at=datetime.now(timezone.utc),
            )
            encoded = canonical_bytes(updated) + b"\n"
            _atomic_bytes(FEED_PATH, encoded)
            _atomic_bytes(directory / "feed.json", encoded)
        check = {
            "schema_version": 1,
            "season": int(result.event["season"]),
            "round": int(result.event["round"]),
            "checked_at": _now_text(datetime.now(timezone.utc)),
            "outcome": result.outcome,
            "reason": result.status.get("validation_reason"),
        }
        check_path = directory / "checks" / f"{digest(check)}.json"
        _atomic_bytes(check_path, canonical_bytes(check) + b"\n")
        from publish_refresh import publish_paths

        publish_paths("monitor")
    print(json.dumps({"outcome": result.outcome, "status": result.status}, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--github-output")
    parser.add_argument("--now", help="UTC ISO timestamp; allowed only for plan/dry-run")
    args = parser.parse_args()
    if args.run and args.now:
        parser.error("--run always uses real UTC and rejects --now")
    evaluated = _utc(args.now) if args.now else datetime.now(timezone.utc)
    needs_work, reason = plan_needs_work(ROOT, evaluated)
    if args.plan:
        _write_github_output(
            args.github_output, needs_work=needs_work, reason=reason
        )
        print(json.dumps({"needs_work": needs_work, "reason": reason}))
        return
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "needs_work": needs_work,
                    "reason": reason,
                    "evaluated_at": _now_text(evaluated),
                },
                sort_keys=True,
            )
        )
        return
    if not needs_work:
        print(json.dumps({"outcome": "not_due", "reason": reason}))
        return
    _run(evaluated)


if __name__ == "__main__":
    main()
