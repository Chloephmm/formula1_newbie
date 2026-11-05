from test_confirmed_reader import _feed


def test_freeze_displays_selected_receipt_not_last_delivered_prediction(tmp_path):
    from src.pipeline.publish import build_feed
    feed = _feed(tmp_path, mode='actual_qualifying')
    status = {'frozen_at': '2026-11-01T16:00:00Z',
              'freeze_selection': feed['initial']['publication']}
    frozen = build_feed(feed['event'], status, current=feed['current'],
                        previous=feed['previous'], initial=feed['initial'],
                        updated_at='2026-11-01T16:00:00Z')
    assert frozen['current'] == feed['initial']


def test_freeze_without_eligible_receipt_displays_unavailable(tmp_path):
    from src.pipeline.publish import build_feed
    feed = _feed(tmp_path)
    frozen = build_feed(feed['event'], {'frozen_at': '2026-11-01T16:00:00Z',
                        'freeze_selection': None}, current=feed['current'],
                        initial=feed['initial'], updated_at='2026-11-01T16:00:00Z')
    assert frozen['current'] is None


def test_monday_rollover_freezes_archived_feed_without_model_calls(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timezone
    from test_adapter_safety import script
    precompute = script('precompute_confirmed')
    feed = _feed(tmp_path, mode='actual_qualifying')
    (tmp_path / 'prediction_feed.json').write_text(json.dumps(feed))
    directory = tmp_path / 'prediction_snapshots' / feed['current_event_id']
    receipts = directory / 'publications'
    receipts.mkdir(parents=True)
    for selection in (feed['initial'], feed['current']):
        receipt = selection['publication']
        (receipts / (receipt['publication_id'] + '.json')).write_text(json.dumps(receipt))
    monkeypatch.setattr(precompute, 'DATA_ROOT', tmp_path)
    precompute.materialize_previous_final(datetime(2026, 11, 2, tzinfo=timezone.utc))
    archived = json.loads((directory / 'feed.json').read_text())
    assert archived['status']['frozen_at']
    assert archived['current'] == feed['current']
