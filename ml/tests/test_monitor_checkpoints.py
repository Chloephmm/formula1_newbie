"""Durable check markers must survive promotion, crashes, and writer races."""
import json

import pytest

from test_prediction_publication import (
    remote, make_publisher, read_remote, compete, Clock, stage, actual, api,
    EVENT, FEED, PushFault, _event, _prediction,
)
from test_pipeline_integration import _load_script


def baseline(bare):
    return {path: read_remote(bare, path) for path in [
        FEED, f'{EVENT}/event.json', f'{EVENT}/status.json',
        f'{EVENT}/feed.json', f'{EVENT}/final.json',
    ]}


def test_checkpoint_preserves_selection_and_survives_actual_promotion(remote, tmp_path):
    make_publisher(remote).publish_candidate(stage(tmp_path))
    publisher = make_publisher(remote, Clock('2026-11-01T15:15:00Z'))
    before = json.loads(read_remote(remote[1], FEED))
    status = dict(before['status'],
                  final_check_attempted_at='2026-11-01T15:15:00Z',
                  last_qualifying_check_started_at='2026-11-01T15:15:00Z')
    publisher.publish_status(_event(), status, expected_files=baseline(remote[1]))
    checkpoint = json.loads(read_remote(remote[1], FEED))
    assert checkpoint['current'] == before['current']
    candidate = stage(tmp_path, actual(), expected_current_id=_prediction()['prediction_id'])
    publisher.publish_candidate(candidate)
    after = json.loads(read_remote(remote[1], FEED))
    assert after['status']['final_check_attempted_at'] == status['final_check_attempted_at']
    assert after['status']['last_qualifying_check_completed_at'] == '2026-11-01T15:15:00Z'
    assert after['status']['validation_reason'] == 'actual_qualifying_published'


def test_checkpoint_rejects_stale_status_without_overwriting_remote(remote):
    expected = baseline(remote[1])
    compete(remote, f'{EVENT}/status.json', {'last_error': 'newer check'})
    with pytest.raises(api().ReplanRequired):
        make_publisher(remote).publish_status(_event(), {}, expected_files=expected)
    assert json.loads(read_remote(remote[1], f'{EVENT}/status.json')) == {'last_error': 'newer check'}


def test_checkpoint_replays_only_disjoint_concurrent_changes(remote):
    expected = baseline(remote[1])
    stats_path = 'web/public/data/stats.json'
    fault = PushFault(lambda: compete(remote, stats_path, {'fresh': True}))
    make_publisher(remote, runner=fault).publish_status(
        _event(), {'last_error': 'missing_results'}, expected_files=expected,
    )
    assert fault.pushes == 2
    assert json.loads(read_remote(remote[1], stats_path)) == {'fresh': True}
    assert json.loads(read_remote(remote[1], FEED))['status']['last_error'] == 'missing_results'


def test_refreshed_schedule_checkpoint_allows_new_context_publication(remote, tmp_path):
    make_publisher(remote).publish_candidate(stage(tmp_path))
    publisher = make_publisher(remote, Clock('2026-11-01T15:15:00Z'))
    before = json.loads(read_remote(remote[1], FEED))
    refreshed = _event(race_start_at='2026-11-01T19:00:00Z')
    publisher.publish_status(refreshed, before['status'], expected_files=baseline(remote[1]))
    candidate = stage(tmp_path, actual(event=refreshed), event=refreshed,
                      expected_current_id=_prediction()['prediction_id'])
    publisher.publish_candidate(candidate)
    after = json.loads(read_remote(remote[1], FEED))
    assert after['event']['race_start_at'] == refreshed['race_start_at']
    assert after['current']['prediction']['mode'] == 'actual_qualifying'
    assert after['initial'] == before['initial']


def test_production_adapter_persists_start_before_model_crash(tmp_path, monkeypatch):
    check = _load_script('check_qualifying')
    import src.pipeline.controller as controller
    import src.pipeline.publish as publication
    calls = []
    event = _event()
    monkeypatch.setattr(check, 'ROOT', tmp_path)
    monkeypatch.setattr(check, 'DATA_ROOT', tmp_path / 'web/public/data')
    monkeypatch.setattr(check, 'SNAPSHOT_ROOT', tmp_path / 'web/public/data/prediction_snapshots')
    monkeypatch.setattr(check, 'FEED_PATH', tmp_path / FEED)
    monkeypatch.setattr(check, '_load_active_event', lambda now: (event, {}, None))

    class Publisher:
        def __init__(self, *args, **kwargs):
            pass

        def publish_status(self, event, status, **kwargs):
            calls.append(dict(status))
            return kwargs['expected_files']

    def crash(event, status, *, dependencies, **kwargs):
        dependencies.persist_status({'final_check_attempted_at': '2026-11-01T15:15:00Z'})
        assert calls, 'check start must be durable before any fetch/model work'
        raise RuntimeError('model crashed')

    monkeypatch.setattr(publication, 'GitPublisher', Publisher)
    monkeypatch.setattr(controller, 'run_due_work', crash)
    with pytest.raises(RuntimeError, match='model crashed'):
        check._run(Clock()())
    assert calls[0]['final_check_attempted_at'] == '2026-11-01T15:15:00Z'


def test_production_adapter_checkpoints_frozen_status_and_final_together(tmp_path, monkeypatch):
    check = _load_script('check_qualifying')
    import src.pipeline.controller as controller
    import src.pipeline.publish as publication
    event = _event()
    monkeypatch.setattr(check, 'ROOT', tmp_path)
    monkeypatch.setattr(check, 'DATA_ROOT', tmp_path / 'web/public/data')
    monkeypatch.setattr(check, 'SNAPSHOT_ROOT', tmp_path / 'web/public/data/prediction_snapshots')
    monkeypatch.setattr(check, 'FEED_PATH', tmp_path / FEED)
    monkeypatch.setattr(check, '_load_active_event', lambda now: (event, {}, None))
    final_path = tmp_path / EVENT / 'final.json'
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b'{"selection": null}\n')

    class Publisher:
        def __init__(self, *args, **kwargs):
            pass

        def publish_status(self, event, status, **kwargs):
            assert kwargs.get('files', {}).get(f'{EVENT}/final.json') == final_path.read_bytes()
            raise RuntimeError('simulated crash after atomic freeze checkpoint')

    def freeze(event, status, *, dependencies, **kwargs):
        dependencies.persist_status({'final_state': 'frozen'})

    monkeypatch.setattr(publication, 'GitPublisher', Publisher)
    monkeypatch.setattr(controller, 'run_due_work', freeze)
    with pytest.raises(RuntimeError, match='simulated crash after atomic freeze checkpoint'):
        check._run(Clock()())
