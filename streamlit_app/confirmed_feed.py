"""Adapt confirmed, single-revision feeds to the existing feature2 dashboard.

Legacy archives remain viewable but are never called confirmed or used for frozen
evaluation. Only a missing new feed permits migration fallback; corrupt or failed
reads keep the caller's last-good bundle instead.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from streamlit_app import prediction_feed as legacy
from streamlit_app.prediction_data import fetch_feed, validate_feed, FeedValidationError


def _read(root, base_url, relative):
    try:
        if base_url:
            return fetch_feed(urljoin(base_url.rstrip('/') + '/', relative))
        path = Path(root) / relative
        if not path.exists():
            return None
        return validate_feed(json.loads(path.read_text(encoding='utf-8')))
    except ConnectionError as exc:
        if 'HTTP 404' in str(exc):
            return None
        raise legacy.FeedError(str(exc)) from exc
    except Exception as exc:
        raise legacy.FeedError(f'Confirmed feed unavailable: {exc}') from exc


def _entry(feed):
    event = feed['event']
    return {'race_id': feed['current_event_id'], 'season': event['season'],
            'round': event['round'], 'race_name': event['race_name'],
            'race_start_at': event['race_start_at'],
            'artifact_url': f"prediction_snapshots/{feed['current_event_id']}/feed.json"}


def load_index(local_root, *, base_url):
    feed = _read(local_root, base_url, 'prediction_feed.json')
    if feed is None:
        return legacy.load_index(local_root, base_url=base_url)
    try:
        old = legacy._read_json(local_root, base_url, 'predictions/index.json')
        legacy.validate_index(old)
    except legacy.FeedError:
        old = {'races': []}
    entries = {item['race_id']: item for item in old['races']}
    entries[feed['current_event_id']] = _entry(feed)
    return {'schema_version': 2, 'active_race_id': feed['current_event_id'],
            'races': sorted(entries.values(), key=lambda x: (x['season'], x['round']), reverse=True),
            '_confirmed_feed': feed}


def bundle_from_feed(feed, index):
    try:
        validate_feed(feed)
    except FeedValidationError as exc:
        raise legacy.FeedError(str(exc)) from exc
    selection = feed.get('current')
    if selection is None:
        raise legacy.FeedError(f"{feed['event']['race_name']}: Prediction temporarily unavailable")
    prediction = selection['prediction']
    forecast = copy.deepcopy(prediction['forecast'])
    initial = feed.get('initial')
    if initial and prediction['mode'] == 'actual_qualifying':
        for field in ('predictedQualifying', 'preQualifyingPodium'):
            forecast[field] = copy.deepcopy(initial['prediction']['forecast'][field])
    # Semantic hashing sorts rows by identity; presentation must restore their ranks.
    for field in ('predictedQualifying', 'realQualifying'):
        forecast[field] = sorted(forecast.get(field) or [],
                                 key=lambda row: row.get('position') or row.get('modelPosition') or 999)
    for field in ('preQualifyingPodium', 'realGridPodium'):
        forecast[field] = sorted(forecast.get(field) or [],
                                 key=lambda row: (row.get('rank', 999), -row['podiumProbability']))
    forecast['actualQualifying'] = forecast['realQualifying']
    forecast['actualQualifyingPodium'] = forecast['realGridPodium']
    event = feed['event']
    forecast['race']['qualifyingStartAt'] = event['qualifying_start_at']
    forecast['race']['raceStartAt'] = event['race_start_at']
    status = dict(feed['status'])
    cutoff = datetime.fromisoformat(event['race_start_at'].replace('Z', '+00:00')) - timedelta(hours=2)
    frozen = status.get('frozen_at')
    artifact = {'schema_version': 2, 'race_id': feed['current_event_id'],
                'race': forecast['race'], 'forecast': forecast,
                'input_mode': ('actual_qualifying' if prediction['mode'] == 'actual_qualifying'
                               else 'estimated_qualifying'),
                'prediction_id': prediction['prediction_id'], 'publication_confirmed': True,
                'prediction_updated_at': prediction['generated_at'],
                'publication_confirmed_at': selection['publication']['published_at'],
                'feed_updated_at': feed['feed_updated_at'],
                'publication_cutoff_at': cutoff.isoformat(), 'frozen_at': frozen,
                'status_reason': status.get('validation_reason')}
    status.update(last_data_check_at=status.get('last_qualifying_check_started_at'),
                  next_scheduled_check_at=status.get('next_qualifying_check_at'),
                  status_reason=status.get('validation_reason'))
    return legacy.PredictionBundle(index=index, artifact=artifact, status=status)


def load_bundle(local_root, *, base_url, race_id, index=None):
    index = index or load_index(local_root, base_url=base_url)
    feed = index.get('_confirmed_feed')
    if feed and feed['current_event_id'] == race_id:
        return bundle_from_feed(feed, index)
    feed = _read(local_root, base_url, f'prediction_snapshots/{race_id}/feed.json')
    if feed:
        if feed['current_event_id'] != race_id:
            raise legacy.FeedError('Confirmed feed belongs to another race')
        return bundle_from_feed(feed, index)
    return legacy.load_bundle(local_root, base_url=base_url, race_id=race_id, index=index)


def retain_latest_bundle(previous, incoming):
    if previous and previous.artifact['race_id'] == incoming.artifact['race_id']:
        before, after = previous.artifact, incoming.artifact
        if before.get('publication_confirmed'):
            if not after.get('publication_confirmed') or before.get('frozen_at'):
                return previous
            if before.get('feed_updated_at', '') > after.get('feed_updated_at', ''):
                return previous
    return incoming
