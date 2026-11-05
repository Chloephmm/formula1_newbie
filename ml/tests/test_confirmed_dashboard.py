"""The feature2 dashboard consumes one confirmed revision without a redesign."""
import json
import pytest
from test_confirmed_reader import _feed


def test_dashboard_reads_one_confirmed_revision_and_preserves_initial(tmp_path):
    from streamlit_app.confirmed_feed import load_index, load_bundle
    feed = _feed(tmp_path, mode="actual_qualifying", updated="2026-11-01T01:02:00Z")
    (tmp_path / "prediction_feed.json").write_text(json.dumps(feed))
    index = load_index(tmp_path, base_url=None)
    bundle = load_bundle(tmp_path, base_url=None, race_id=feed["current_event_id"], index=index)
    assert bundle.artifact["input_mode"] == "actual_qualifying"
    assert bundle.artifact["prediction_id"] == feed["current"]["prediction"]["prediction_id"]
    assert bundle.artifact["forecast"]["predictedQualifying"]
    assert bundle.artifact["forecast"]["actualQualifying"]
    assert bundle.artifact["publication_confirmed"] is True


def test_invalid_confirmed_feed_does_not_fall_back_to_unconfirmed_data(tmp_path):
    from streamlit_app.confirmed_feed import load_index
    from streamlit_app.prediction_feed import FeedError
    (tmp_path / "prediction_feed.json").write_text('{"schema_version": 1}')
    with pytest.raises(FeedError):
        load_index(tmp_path, base_url=None)


def test_same_event_stale_revision_does_not_replace_last_good(tmp_path):
    from streamlit_app.confirmed_feed import bundle_from_feed, retain_latest_bundle
    actual = bundle_from_feed(_feed(tmp_path, mode="actual_qualifying", updated="2026-11-01T01:02:00Z"), {})
    initial = bundle_from_feed(_feed(tmp_path), {})
    assert retain_latest_bundle(actual, initial) is actual


def test_confirmed_navigation_preserves_saved_legacy_races(tmp_path):
    from streamlit_app.confirmed_feed import load_index
    (tmp_path / "predictions").mkdir()
    (tmp_path / "predictions/index.json").write_text(json.dumps({
        "schema_version": 2, "active_race_id": "2026-18", "races": [{
            "race_id": "2026-18", "season": 2026, "round": 18,
            "race_name": "Legacy race", "artifact_url": "predictions/2026-18.json"}]}))
    feed = _feed(tmp_path)
    (tmp_path / "prediction_feed.json").write_text(json.dumps(feed))
    index = load_index(tmp_path, base_url=None)
    assert index["active_race_id"] == feed["current_event_id"]
    assert any(r["race_id"] == "2026-18" for r in index["races"])


def test_open_dashboard_rerun_changes_mode_and_id_without_any_model_or_api(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from streamlit_app import confirmed_feed
    from src.data import jolpica
    from src.model import retrain
    def forbidden(*args, **kwargs):
        raise AssertionError('visitor must not fetch race data or train models')
    monkeypatch.setattr(jolpica, 'get_schedule', forbidden)
    monkeypatch.setattr(jolpica, 'get_qualifying', forbidden)
    monkeypatch.setattr(retrain, 'retrain_live', forbidden)
    monkeypatch.setattr(retrain, 'train_podium_live', forbidden)
    feed = [_feed(tmp_path)]
    def index(*args, **kwargs):
        return {'schema_version': 2, 'active_race_id': feed[0]['current_event_id'],
                'races': [confirmed_feed._entry(feed[0])], '_confirmed_feed': feed[0]}
    monkeypatch.setattr(confirmed_feed, 'load_index', index)
    app = Path(__file__).parents[2] / 'streamlit_app/app.py'
    result = AppTest.from_file(str(app)).run(timeout=20)
    assert not list(result.exception)
    first_id = feed[0]['current']['prediction']['prediction_id']
    assert first_id in ' '.join(item.value for item in result.caption)
    feed[0] = _feed(tmp_path, mode='actual_qualifying', updated='2026-11-01T01:02:00Z')
    result.run(timeout=20)
    assert not list(result.exception)
    assert 'Using actual qualifying results' in ' '.join(item.proto.body for item in result.get('html'))
    assert feed[0]['current']['prediction']['prediction_id'] in ' '.join(item.value for item in result.caption)
    assert not list(result.button)


def test_official_missing_position_is_not_replaced_by_model_rank(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from streamlit_app import confirmed_feed
    feed = _feed(tmp_path, mode='actual_qualifying')
    index = {'schema_version': 2, 'active_race_id': feed['current_event_id'],
             'races': [confirmed_feed._entry(feed)], '_confirmed_feed': feed}
    bundle = confirmed_feed.bundle_from_feed(feed, index)
    # Rendering-only fixture: official unclassified/no-lap entrant, model fallback present.
    bundle.artifact['forecast']['actualQualifying'][0].update(position=None, gap=None)
    monkeypatch.setattr(confirmed_feed, 'load_index', lambda *a, **kw: index)
    monkeypatch.setattr(confirmed_feed, 'load_bundle', lambda *a, **kw: bundle)
    app = Path(__file__).parents[2] / 'streamlit_app/app.py'
    result = AppTest.from_file(str(app)).run(timeout=20)
    assert not list(result.exception)
    html = ' '.join(item.proto.body for item in result.get('html'))
    assert '<span class="pos">—</span>' in html
    assert 'No time' in html
