"""Production adapter safeguards, using no real remote or live API."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ml/scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_requires_explicit_production_environment_before_network(monkeypatch):
    import pytest
    check = script('check_qualifying')
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setattr(sys, 'argv', ['check_qualifying.py', '--run'])
    monkeypatch.setattr(check, 'plan_needs_work', lambda *_: (_ for _ in ()).throw(AssertionError('no side effects')))
    with pytest.raises(SystemExit, match='production'):
        check.main()


def test_model_manifest_includes_all_prediction_code_and_calibration(monkeypatch):
    check = script('check_qualifying')
    paths = []
    monkeypatch.setattr(check, '_code_hash', lambda values: paths.extend(p.name for p in values) or 'x')
    manifest = check.model_manifest(stages=('stage2',))
    assert 'event_forecast.py' in paths
    assert 'config.py' in paths
    assert 'common.py' in paths
    assert manifest['parameters']['stage2']['calibration'] == {'method': 'sigmoid', 'cv': 5}


def test_start_marker_is_persisted_before_an_expensive_check(tmp_path, monkeypatch):
    check = script('check_qualifying')
    calls = []
    monkeypatch.setattr(check, 'DATA_ROOT', tmp_path)
    import publish_refresh
    monkeypatch.setattr(publish_refresh, 'publish_paths', lambda kind: calls.append(kind))
    from test_prediction_artifacts import _event
    check.persist_check_start(_event(), {'last_qualifying_check_started_at': '2026-11-01T01:00:00Z'})
    assert calls == ['monitor']
    assert (tmp_path / 'prediction_snapshots/2026-20/status.json').exists()
