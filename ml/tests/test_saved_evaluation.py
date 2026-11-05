import json
import pandas as pd
from test_confirmed_reader import _feed
from src.pipeline.publish import write_final


def test_scores_only_confirmed_saved_initial_and_frozen_final(tmp_path):
    from src.pipeline.evaluation import evaluate_saved
    feed = _feed(tmp_path, mode='actual_qualifying', updated='2026-11-01T01:02:00Z')
    directory = tmp_path / 'prediction_snapshots' / feed['current_event_id']
    directory.mkdir(parents=True)
    (directory / 'feed.json').write_text(json.dumps(feed))
    write_final(feed['event'], feed['current']['publication'], root=tmp_path)
    podium = sorted(feed['current']['prediction']['forecast']['realGridPodium'], key=lambda row: row['rank'])
    results = pd.DataFrame([{'season': 2026, 'round': 20, 'driver_id': row['driver_id'],
                             'position': n + 1} for n, row in enumerate(podium)])
    metrics = evaluate_saved(tmp_path, results)
    assert metrics['final']['races'] == 1
    assert metrics['final']['podium_hit_rate'] == 1
    assert metrics['final']['winner_accuracy'] == 1
    assert metrics['initial']['races'] == 1
    (directory / 'final.json').unlink()
    assert evaluate_saved(tmp_path, results)['final']['races'] == 0


def test_legacy_or_unconfirmed_forecasts_are_not_live_accuracy(tmp_path):
    from src.pipeline.evaluation import evaluate_saved
    directory = tmp_path / 'prediction_snapshots/2026-20'
    directory.mkdir(parents=True)
    (directory / 'initial.json').write_text('{"prediction": "retrospective"}')
    metrics = evaluate_saved(tmp_path, pd.DataFrame())
    assert metrics['initial']['races'] == metrics['final']['races'] == 0


def test_corrupt_confirmation_is_excluded_without_crashing_metrics(tmp_path):
    from src.pipeline.evaluation import evaluate_saved
    feed = _feed(tmp_path)
    feed['initial']['publication']['checksum'] = '0' * 64
    directory = tmp_path / 'prediction_snapshots' / feed['current_event_id']
    directory.mkdir(parents=True)
    (directory / 'feed.json').write_text(json.dumps(feed))
    results = pd.DataFrame([{'season': 2026, 'round': 20, 'driver_id': str(n),
                             'position': n} for n in (1, 2, 3)])
    metrics = evaluate_saved(tmp_path, results)
    assert metrics['initial']['races'] == 0
    assert len(metrics['excluded']) == 1
