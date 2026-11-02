"""Filesystem and participant selection tests for the publication service."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.publication.publisher import PublicationUpdate
from src.publication.service import PublicationPaths, latest_completed_participants, write_update


def _snapshot(*, frozen=False):
    return {
        "schema_version": 2,
        "race_id": "2026-4",
        "race": {"name": "Miami Grand Prix", "season": 2026, "round": 4},
        "forecast": {"race": {"name": "Miami Grand Prix", "season": 2026, "round": 4}},
        "input_mode": "estimated_qualifying",
        "prediction_updated_at": "2026-05-01T00:00:00Z",
        "qualifying_input_hash": None,
        "publication_cutoff_at": "2026-05-03T18:00:00Z",
        "frozen_at": "2026-05-03T18:00:00Z" if frozen else None,
        "status_reason": None,
    }


def _update(*, frozen=False):
    snapshot = _snapshot(frozen=frozen)
    return PublicationUpdate(
        snapshot=snapshot,
        status={"schema_version": 2, "race_id": "2026-4", "state": "frozen_estimated" if frozen else "estimated_waiting"},
        archive_index={"schema_version": 2, "active_race_id": "2026-4", "races": []},
        model_ran=False,
        forecast_changed=False,
    )


def test_dry_run_writes_nothing_and_normal_run_writes_all_artifacts(tmp_path):
    paths = PublicationPaths(tmp_path)

    write_update(paths, _update(), dry_run=True)
    assert list(tmp_path.rglob("*.json")) == []

    write_update(paths, _update(), dry_run=False)
    assert json.loads(paths.active.read_text())["race_id"] == "2026-4"
    assert json.loads(paths.status.read_text())["state"] == "estimated_waiting"
    assert json.loads(paths.index.read_text())["active_race_id"] == "2026-4"
    assert json.loads(paths.archive("2026-4").read_text())["race_id"] == "2026-4"


def test_frozen_archive_is_never_overwritten(tmp_path):
    paths = PublicationPaths(tmp_path)
    write_update(paths, _update(frozen=True), dry_run=False)
    original = paths.archive("2026-4").read_text()

    changed = _update(frozen=True)
    changed.snapshot["status_reason"] = "should-not-replace-frozen-artifact"
    write_update(paths, changed, dry_run=False)

    assert paths.archive("2026-4").read_text() == original


def test_expected_participants_come_from_latest_completed_race(tmp_path):
    pd.DataFrame([
        {"season": 2025, "round": 24, "date": "2025-12-07", "driver_id": "old"},
        {"season": 2026, "round": 2, "date": "2026-03-15", "driver_id": "a"},
        {"season": 2026, "round": 2, "date": "2026-03-15", "driver_id": "b"},
        {"season": 2026, "round": 4, "date": "2026-05-03", "driver_id": "future"},
    ]).to_parquet(tmp_path / "results_2026.parquet")

    participants = latest_completed_participants(
        tmp_path,
        race_start_at="2026-05-03T20:00:00Z",
    )

    assert participants == {"a", "b"}


@pytest.mark.parametrize("change", ["actual", "race", "newer_estimate"])
def test_status_only_update_cannot_replace_newer_active_forecast(tmp_path, change):
    from src.publication.service import _atomic_json
    paths = PublicationPaths(tmp_path)
    current = _snapshot()
    if change == "actual": current["input_mode"] = "actual_qualifying"
    if change == "race": current["race_id"] = "2026-5"
    if change == "newer_estimate": current["prediction_updated_at"] = "2026-05-02T00:00:00Z"
    _atomic_json(paths.active, current)
    before = paths.active.read_bytes()
    with pytest.raises(ValueError):
        write_update(paths, _update(), dry_run=False)
    assert paths.active.read_bytes() == before
