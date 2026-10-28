"""Task-level integration fixtures for the scheduled controller and Monday job."""
from __future__ import annotations

from datetime import datetime, timezone
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "ml" / "scripts"


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plan_gate_bootstraps_without_importing_model_stack(tmp_path):
    before = set(sys.modules)
    check = _load_script("check_qualifying")

    assert check.plan_needs_work(tmp_path, datetime(2026, 10, 23, tzinfo=UTC)) == (
        True,
        "event_bootstrap_required",
    )
    assert not {
        name
        for name in set(sys.modules) - before
        if name.startswith("src.model") or name.startswith("pandas")
    }


def test_direct_monitor_script_makes_ml_package_importable_without_pythonpath():
    script = SCRIPTS / "check_qualifying.py"
    probe = (
        "import importlib.util, pathlib; "
        f"path = pathlib.Path({str(script)!r}); "
        "spec = importlib.util.spec_from_file_location('monitor_probe', path); "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "import src.pipeline.state; "
        "assert pathlib.Path(src.pipeline.state.__file__).resolve().is_relative_to(path.parents[1])"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


def test_run_mode_executes_bootstrap_when_event_metadata_is_missing(monkeypatch):
    check = _load_script("check_qualifying")
    calls = []
    monkeypatch.setattr(
        check,
        "plan_needs_work",
        lambda _root, _now: (True, "event_bootstrap_required"),
    )
    monkeypatch.setattr(
        check,
        "_bootstrap_missing_event",
        lambda _now: calls.append("bootstrap") or {"outcome": "initial_published"},
        raising=False,
    )
    monkeypatch.setattr(check, "_run", lambda _now: calls.append("run"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPTS / "check_qualifying.py"), "--run"])

    check.main()

    assert calls == ["bootstrap"]


def test_late_bootstrap_continues_to_actual_qualifying_monitor(monkeypatch):
    check = _load_script("check_qualifying")
    calls = []
    monkeypatch.setattr(
        check,
        "plan_needs_work",
        lambda _root, _now: (True, "event_bootstrap_required"),
    )
    monkeypatch.setattr(
        check,
        "_bootstrap_missing_event",
        lambda _now: calls.append("bootstrap") or {"outcome": "missing_initial"},
    )
    monkeypatch.setattr(check, "_run", lambda _now: calls.append("run"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPTS / "check_qualifying.py"), "--run"])

    check.main()

    assert calls == ["bootstrap", "run"]


def test_monitor_publisher_allows_event_metadata_for_bootstrap_and_schedule_refresh():
    publisher = _load_script("publish_refresh")

    assert publisher._allowed(
        "monitor",
        "web/public/data/prediction_snapshots/2026-20/event.json",
    )


def test_plan_gate_dry_run_against_saved_event_fixture(tmp_path):
    check = _load_script("check_qualifying")
    directory = (
        tmp_path
        / "web"
        / "public"
        / "data"
        / "prediction_snapshots"
        / "2026-18"
    )
    directory.mkdir(parents=True)
    event = {
        "season": 2026,
        "round": 18,
        "qualifying_start_at": "2026-10-23T10:00:00Z",
        "race_start_at": "2026-10-24T18:00:00Z",
    }
    status = {"last_schedule_refresh_at": "2026-10-23T16:00:00Z"}
    (directory / "event.json").write_text(json.dumps(event), encoding="utf-8")
    (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")

    assert check.plan_needs_work(
        tmp_path, datetime(2026, 10, 23, 16, 30, tzinfo=UTC)
    ) == (True, "ordinary_check_due")
    assert json.loads((directory / "event.json").read_text()) == event
    assert json.loads((directory / "status.json").read_text()) == status


def test_monday_fetch_still_calls_every_original_endpoint(monkeypatch):
    refresh = _load_script("refresh_for_next_race")
    calls = []

    class Frame:
        def __len__(self):
            return 1

    monkeypatch.setattr(
        refresh,
        "_ENDPOINTS",
        {
            name: (lambda season, name=name: calls.append((name, season)) or Frame())
            for name in (
                "results",
                "qualifying",
                "driver_standings",
                "constructor_standings",
                "schedule",
            )
        },
    )
    monkeypatch.setattr(
        refresh.cache,
        "cached",
        lambda _name, builder, refresh: builder(),
    )

    refresh._fetch([2026])

    assert [name for name, _ in calls] == list(refresh._ENDPOINTS)


def test_monday_runs_backtest_even_if_next_event_generation_fails():
    refresh = _load_script("refresh_for_next_race")
    calls = []

    def fail_snapshot(_asof):
        calls.append("snapshot")
        raise ValueError("model failed")

    with pytest.raises(RuntimeError, match="snapshot: model failed"):
        refresh.run_refresh(
            asof="2026-10-26",
            seasons=[2026],
            no_fetch=False,
            no_snapshot=False,
            backtest=True,
            fetch_step=lambda seasons: calls.append(("fetch", tuple(seasons))),
            precompute_step=fail_snapshot,
            backtest_step=lambda: calls.append("backtest"),
        )

    assert calls == [("fetch", (2026,)), "snapshot", "backtest"]


def test_monday_rollover_publishes_next_event_without_mutating_old_archives(
    tmp_path, monkeypatch
):
    precompute = _load_script("precompute_next_race")
    data = tmp_path / "data"
    old = data / "prediction_snapshots" / "2026-18"
    old.mkdir(parents=True)
    initial = old / "initial.json"
    final = old / "final.json"
    initial.write_bytes(b"old-initial\n")
    final.write_bytes(b"old-final\n")
    event = {
        "season": 2026,
        "round": 19,
        "race_name": "Next Grand Prix",
        "qualifying_start_at": "2026-10-30T18:00:00Z",
        "race_start_at": "2026-11-01T18:00:00Z",
    }
    prediction = {"prediction_id": "a" * 64}
    calls = []
    monkeypatch.setattr(precompute, "DATA_ROOT", data)
    monkeypatch.setattr(
        precompute, "materialize_previous_final", lambda now: calls.append("finalize")
    )
    monkeypatch.setattr(
        precompute, "build_next_event", lambda asof, observed_at: dict(event)
    )
    monkeypatch.setattr(
        precompute,
        "build_initial_prediction",
        lambda current, generated_at: dict(prediction),
    )
    monkeypatch.setattr(
        precompute,
        "publish_initial",
        lambda current, candidate: calls.append(
            ("publish", current["round"], candidate["prediction_id"])
        )
        or {"publication_id": "b" * 64},
    )

    result = precompute.main(
        "2026-10-26", now=datetime(2026, 10, 26, 10, tzinfo=UTC)
    )

    assert result["outcome"] == "initial_published"
    assert calls == ["finalize", ("publish", 19, "a" * 64)]
    assert initial.read_bytes() == b"old-initial\n"
    assert final.read_bytes() == b"old-final\n"


def test_missed_initial_records_status_without_calling_model(tmp_path, monkeypatch):
    precompute = _load_script("precompute_next_race")
    data = tmp_path / "data"
    event = {
        "season": 2026,
        "round": 19,
        "race_name": "Next Grand Prix",
        "qualifying_start_at": "2026-10-30T18:00:00Z",
        "race_start_at": "2026-11-01T18:00:00Z",
    }
    monkeypatch.setattr(precompute, "DATA_ROOT", data)
    monkeypatch.setattr(precompute, "materialize_previous_final", lambda now: None)
    monkeypatch.setattr(
        precompute, "build_next_event", lambda asof, observed_at: dict(event)
    )
    monkeypatch.setattr(
        precompute,
        "build_initial_prediction",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("late Monday must not train")
        ),
    )

    result = precompute.main(
        "2026-10-31", now=datetime(2026, 10, 31, 10, tzinfo=UTC)
    )

    status = (
        data / "prediction_snapshots" / "2026-19" / "status.json"
    ).read_text(encoding="utf-8")
    assert result["outcome"] == "missing_initial"
    assert "missing_initial" in status


def test_saved_lifecycle_keeps_initial_through_failures_updates_and_freezes_latest():
    from src.pipeline.controller import PipelineDependencies, run_due_work

    event = {
        "season": 2026,
        "round": 18,
        "race_name": "Lifecycle Grand Prix",
        "circuit_id": "lifecycle_ring",
        "qualifying_start_at": "2026-10-23T10:00:00Z",
        "race_start_at": "2026-10-24T18:00:00Z",
        "schedule_hash": "schedule-a",
        "schedule_updated_at": "2026-10-22T00:00:00Z",
    }
    initial = {"prediction_id": "initial", "mode": "predicted_qualifying"}
    initial_before = copy.deepcopy(initial)
    served = [initial]
    responses = iter(["empty", "incomplete", "a" * 64, "b" * 64])
    runtime = {"now": datetime(2026, 10, 23, 16, 30, tzinfo=UTC), "source": None}
    fits = []
    receipts = []

    class Missing(ValueError):
        code = "qualifying_unavailable"

    class Incomplete(ValueError):
        code = "missing_expected_driver"

    def validate(_event, raw):
        if raw == "empty":
            raise Missing()
        if raw == "incomplete":
            raise Incomplete()
        runtime["source"] = raw
        return SimpleNamespace(source_version=raw)

    def generate(_event, accepted, source):
        fits.append(source)
        return {"prediction_id": f"actual-{source[0]}", "mode": "actual_qualifying"}

    def publish(prediction):
        receipt = {
            "prediction_id": prediction["prediction_id"],
            "published_at": runtime["now"].isoformat(),
        }
        receipts.append(receipt)
        served[0] = prediction
        return receipt

    dependencies = PipelineDependencies(
        fetch_qualifying=lambda _event: next(responses),
        validate_qualifying=validate,
        generate_prediction=generate,
        validate_prediction=lambda prediction, _event: None,
        stage_prediction=lambda _event, prediction, accepted, status: prediction,
        publish_prediction=publish,
        freeze=lambda _event, _status, _now: receipts[-1],
    )
    status = {}
    for at, expected in (
        (datetime(2026, 10, 23, 16, 30, tzinfo=UTC), "qualifying_unavailable"),
        (datetime(2026, 10, 23, 17, 30, tzinfo=UTC), "qualifying_unavailable"),
        (datetime(2026, 10, 23, 18, 30, tzinfo=UTC), "published"),
        (datetime(2026, 10, 24, 15, 15, tzinfo=UTC), "published"),
    ):
        runtime["now"] = at
        result = run_due_work(
            event, status, clock=lambda: runtime["now"], dependencies=dependencies
        )
        status = result.status
        assert result.outcome == expected
        if expected == "qualifying_unavailable":
            assert served[0] is initial

    runtime["now"] = datetime(2026, 10, 24, 16, 0, tzinfo=UTC)
    frozen = run_due_work(
        event, status, clock=lambda: runtime["now"], dependencies=dependencies
    )

    assert initial == initial_before
    assert fits == ["a" * 64, "b" * 64]
    assert served[0]["prediction_id"] == "actual-b"
    assert frozen.outcome == "frozen"
    assert frozen.status["freeze_selection"]["prediction_id"] == "actual-b"


def test_workflows_preserve_original_schedules_and_share_one_writer_queue():
    workflows = ROOT / ".github" / "workflows"
    weekly = (workflows / "refresh-predictions.yml").read_text(encoding="utf-8")
    stats = (workflows / "sync-stats.yml").read_text(encoding="utf-8")
    monitor = (workflows / "qualifying-monitor.yml").read_text(encoding="utf-8")

    assert 'cron: "0 6 * * 1"' in weekly
    assert "python ml/scripts/refresh_for_next_race.py --backtest" in weekly
    assert 'cron: "0 6 * 3-12 1"' in stats
    assert "npm run sync-stats" in stats
    assert 'cron: "7,22,37,52 * * * *"' in monitor
    assert "timeout-minutes: 30" in monitor
    assert "cache-dependency-path: ml/requirements.txt" in monitor
    for source in (weekly, stats, monitor):
        assert "group: f1-data-writes" in source
        assert "queue: max" in source
        assert "ref: main" in source
        assert "fetch-depth: 0" in source


def test_austin_legacy_reference_resolves_exact_original_git_blob():
    path = (
        ROOT
        / "web"
        / "public"
        / "data"
        / "prediction_snapshots"
        / "2026-18"
        / "legacy_initial_reference.json"
    )
    reference = json.loads(path.read_text(encoding="utf-8"))
    source = reference["source"]
    resolved = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "rev-parse",
            f"{source['commit']}:{source['path']}",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    ).stdout.strip()

    assert resolved == source["git_blob"]
    assert reference["generated_at"] == "2026-10-19"
    assert reference["generated_at_precision"] == "date"
    assert set(reference["provenance"].values()) == {"unknown"}
    assert reference["contract"]["schema_2_validated"] is False
    assert reference["contract"]["eligible_for_frozen_evaluation"] is False
