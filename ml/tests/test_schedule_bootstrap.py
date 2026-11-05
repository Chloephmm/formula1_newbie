"""Migration regression: legacy schedule caches must not invent source evidence."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.data import jolpica
from src.model import event_forecast
from test_event_forecast import _result
from test_pipeline_integration import _load_script


NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    script = _load_script('precompute_confirmed')
    raw = tmp_path / 'raw'
    raw.mkdir()
    # Same columns and old +180-minute estimate as the committed cache in run #4.
    legacy = {
        'season': 2026, 'round': 20, 'race_name': 'Brazilian Grand Prix',
        'circuit_id': 'interlagos', 'country': 'Brazil', 'date': '2026-11-08',
        'qualifying_start_at': '2026-11-07T18:00:00Z',
        'qualifying_end_at': '2026-11-07T21:00:00Z', 'end_time_estimated': True,
        'race_start_at': '2026-11-08T17:00:00Z',
        'schedule_updated_at': '2026-10-30T17:18:25Z',
    }
    cache_path = raw / 'schedule_2026.parquet'
    pd.DataFrame([legacy]).to_parquet(cache_path, index=False)
    monkeypatch.setattr(event_forecast, 'RAW', raw)
    prior = pd.DataFrame([_result(2026, 19, '2026-11-01', f'driver_{d}', n)
                          for n, d in enumerate('abcd', 1)])
    monkeypatch.setattr(script, '_load_history', lambda: {'results': prior})
    monkeypatch.setattr(script, 'ML_DIR', tmp_path)
    monkeypatch.setattr(script, 'DATA_ROOT', tmp_path / 'public')
    return script, legacy, cache_path


def response_race(**updates):
    race = {
        'season': '2026', 'round': '20', 'raceName': 'Brazilian Grand Prix',
        'Circuit': {'circuitId': 'interlagos', 'circuitName': 'Interlagos',
                    'Location': {'country': 'Brazil', 'locality': 'Sao Paulo'}},
        'date': '2026-11-08', 'time': '18:00:00Z',
        'Qualifying': {'date': '2026-11-07', 'time': '18:00:00Z'},
    }
    race.update(updates)
    return race


def api_response(monkeypatch, races):
    calls = []
    def pages(endpoint):
        calls.append(endpoint)
        return iter([{'RaceTable': {'Races': races}}])
    monkeypatch.setattr(jolpica, '_iter_pages', pages)
    return calls


@pytest.mark.parametrize('source', ['absent', None, '', '   '])
def test_legacy_cache_refetches_real_schedule_evidence(bootstrap, monkeypatch, source):
    script, legacy, path = bootstrap
    if source != 'absent':
        legacy['schedule_source'] = source
        pd.DataFrame([legacy]).to_parquet(path, index=False)
    before = path.read_bytes()
    calls = api_response(monkeypatch, [response_race(round='19'), response_race()])
    event = script.build_next_event('2026-11-05', observed_at=NOW)
    assert calls == ['2026']
    assert (event['season'], event['round']) == (2026, 20)
    assert event['schedule_source'] == 'jolpica'
    assert event['schedule_updated_at'] == '2026-11-05T00:00:00Z'
    assert event['race_start_at'] == '2026-11-08T18:00:00Z'
    assert event['qualifying_end_at'] == '2026-11-07T19:30:00Z'
    assert event['roster_source']['round'] == 19
    assert path.read_bytes() == before  # No uncoordinated raw-data write.


def test_complete_cached_evidence_does_not_refetch(bootstrap, monkeypatch):
    script, legacy, path = bootstrap
    pd.DataFrame([dict(legacy, schedule_source='jolpica')]).to_parquet(path, index=False)
    monkeypatch.setattr(jolpica, '_iter_pages', lambda *a: pytest.fail('unnecessary API call'))
    event = script.build_next_event('2026-11-05', observed_at=NOW)
    assert event['schedule_updated_at'] == legacy['schedule_updated_at']


@pytest.mark.parametrize('races', [[], [response_race(round='19')],
                                 [response_race(season='2025')],
                                 [response_race(), response_race()]])
def test_refresh_requires_one_exact_target_event(bootstrap, monkeypatch, races):
    script, _, _ = bootstrap
    api_response(monkeypatch, races)
    with pytest.raises(ValueError, match='exact target event'):
        script.build_next_event('2026-11-05', observed_at=NOW)


def test_refresh_failure_stops_before_training_or_publication(bootstrap, monkeypatch):
    script, _, _ = bootstrap
    def fail_fetch(*args):
        raise ConnectionError('schedule unavailable')
    monkeypatch.setattr(jolpica, '_iter_pages', fail_fetch)
    monkeypatch.setattr(script, 'build_initial_prediction', lambda *a, **kw: pytest.fail('must not train'))
    monkeypatch.setattr(script, 'publish_initial', lambda *a, **kw: pytest.fail('must not publish'))
    with pytest.raises(ConnectionError, match='schedule unavailable'):
        script.main('2026-11-05', now=NOW)
    assert not script.DATA_ROOT.exists()
