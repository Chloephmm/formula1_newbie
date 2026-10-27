"""Task-level integration fixtures for the scheduled controller and Monday job."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

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
