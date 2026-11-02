"""Exercise the CLI boundaries without network access or an expensive fit."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from test_estimated_publication import SCHEDULE, NOW, candidate, forecast
from src.publication.service import _atomic_json, PublicationPaths


@pytest.fixture
def script(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts/precompute_next_race.py"
    spec = importlib.util.spec_from_file_location("precompute_safety", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DATA_ROOT", tmp_path / "feed")
    monkeypatch.setattr(module, "RAW_ROOT", tmp_path / "raw")
    module.RAW_ROOT.mkdir()
    pd.DataFrame([dict(season=2026, round=18, date="2026-10-25", driver_id=c, code=c)
                  for c in "ABCD"]).to_parquet(module.RAW_ROOT / "results_2026.parquet")
    schedule = dict(SCHEDULE, date=pd.Timestamp("2026-11-01"))
    monkeypatch.setattr(module, "next_race", lambda asof: pd.Series(schedule))
    return module, schedule


def test_preflight_rejects_missing_schedule_before_model_work(script, monkeypatch):
    module, schedule = script
    schedule["race_start_at"] = None
    calls = []
    monkeypatch.setattr(module, "retrain_live", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="race_start_at"):
        module.main("2026-10-30", clock=lambda: NOW)
    assert calls == []
    assert not module.DATA_ROOT.exists()


def test_candidate_mode_leaves_feed_untouched(script, tmp_path, monkeypatch):
    module, _ = script
    paths = PublicationPaths(module.DATA_ROOT)
    _atomic_json(paths.active, candidate())
    before = paths.active.read_bytes()
    monkeypatch.setattr(module, "retrain_live", lambda *args: {})
    monkeypatch.setattr(module, "forecast", lambda *args, **kwargs: forecast())
    output = tmp_path / "candidate.json"
    result = module.main("2026-10-30", candidate_output=output, clock=lambda: NOW)
    assert output.exists() and result["race_id"] == "2026-19"
    assert paths.active.read_bytes() == before
    assert not paths.status.exists()


def test_monday_writes_only_active_and_leaves_archive_unchanged(script, monkeypatch):
    module, _ = script
    paths = PublicationPaths(module.DATA_ROOT)
    _atomic_json(paths.archive("2026-18"), {"race_id": "2026-18", "frozen_at": "2026-10-25T18:00:00Z"})
    before = paths.archive("2026-18").read_bytes()
    monkeypatch.setattr(module, "retrain_live", lambda *args: {})
    monkeypatch.setattr(module, "forecast", lambda *args, **kwargs: forecast())
    module.main("2026-10-30", clock=lambda: NOW)
    assert paths.active.exists()
    assert not paths.status.exists() and not paths.index.exists()
    assert paths.archive("2026-18").read_bytes() == before


def test_schedule_refresh_migrates_only_calendar(script, monkeypatch):
    module, schedule = script
    results = module.RAW_ROOT / "results_2026.parquet"
    before = results.read_bytes()
    monkeypatch.setattr(module, "get_schedule", lambda season: pd.DataFrame([schedule]))
    module.refresh_schedule(2026, 19, raw_dir=module.RAW_ROOT)
    actual = pd.read_parquet(module.RAW_ROOT / "schedule_2026.parquet").iloc[0]
    assert actual.qualifying_start_at == "2026-10-31T21:00:00Z"
    assert actual.qualifying_end_at == "2026-11-01T00:00:00Z"
    assert results.read_bytes() == before


def test_invalid_schedule_does_not_replace_existing_cache(script, monkeypatch):
    module, schedule = script
    cache = module.RAW_ROOT / "schedule_2026.parquet"
    pd.DataFrame([schedule]).to_parquet(cache)
    before = cache.read_bytes()
    schedule["qualifying_start_at"] = None
    monkeypatch.setattr(module, "get_schedule", lambda season: pd.DataFrame([schedule]))
    with pytest.raises(ValueError):
        module.refresh_schedule(2026, 19, raw_dir=module.RAW_ROOT)
    assert cache.read_bytes() == before


def test_hourly_status_sync_uses_new_active_estimate_not_old_archive(script, monkeypatch):
    import copy
    module, schedule = script
    path = Path(__file__).parents[1] / "scripts/publish_qualifying_prediction.py"
    spec = importlib.util.spec_from_file_location("hourly_safety", path)
    hourly = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hourly)
    monkeypatch.setattr(hourly, "DATA_ROOT", module.DATA_ROOT)
    monkeypatch.setattr(hourly, "RAW_ROOT", module.RAW_ROOT)
    monkeypatch.setattr(hourly, "get_schedule", lambda season: pd.DataFrame([schedule]))
    def unexpected(*args, **kwargs):
        raise AssertionError("before qualifying: no model or qualifying fetch")
    monkeypatch.setattr(hourly, "train_podium_live", unexpected)
    monkeypatch.setattr(hourly, "get_qualifying_round", unexpected)
    paths = PublicationPaths(module.DATA_ROOT)
    current = candidate()
    old = copy.deepcopy(current)
    old["prediction_updated_at"] = "2026-10-26T06:00:00Z"
    _atomic_json(paths.active, current)
    _atomic_json(paths.archive("2026-19"), old)
    hourly.main(now=NOW)
    from src.publication.service import read_json
    assert read_json(paths.active) == current
    assert read_json(paths.archive("2026-19")) == current
