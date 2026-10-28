"""Saved-feed reader and presentation tests; all transport is fixture-backed."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.pipeline.artifacts import canonical_bytes
from src.pipeline.publish import build_feed, confirm_publication, stage_candidate
from test_prediction_artifacts import _event, _prediction
from test_prediction_publication import Clock, actual

ROOT = Path(__file__).resolve().parents[2]


class Response:
    def __init__(self, status_code, payload=None, *, etag=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = {} if etag is None else {"ETag": etag}

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return copy.deepcopy(self._payload)


def _selection(tmp_path, prediction, *, at):
    event = _event()
    candidate = stage_candidate(tmp_path / prediction["prediction_id"], event, prediction)
    receipt = confirm_publication(
        candidate,
        "1" * 40,
        remote_reader=lambda commit, path, *, timeout: canonical_bytes(prediction) + b"\n",
        clock=Clock(at),
    )
    return {"event": event, "prediction": prediction, "publication": receipt}


def _feed(tmp_path, *, mode="predicted_qualifying", updated="2026-10-30T13:01:00Z", status=None):
    event = _event()
    initial = _selection(
        tmp_path,
        _prediction(),
        at="2026-10-30T13:00:00Z",
    )
    if mode == "actual_qualifying":
        current = _selection(
            tmp_path,
            actual(),
            at="2026-11-01T01:01:00Z",
        )
        previous = initial
    else:
        current = initial
        previous = None
    return build_feed(
        event,
        status or {},
        current=current,
        previous=previous,
        initial=initial,
        updated_at=updated,
    )


@pytest.fixture(autouse=True)
def clear_reader_cache():
    from streamlit_app.prediction_data import reset_shared_cache

    reset_shared_cache()
    yield
    reset_shared_cache()


def test_valid_feed_returns_exact_confirmed_event_prediction_and_status(tmp_path):
    from streamlit_app.prediction_data import read_saved_event

    feed = _feed(
        tmp_path,
        mode="actual_qualifying",
        status={"actual_publication_confirmed": True},
    )
    transport = lambda url, **kwargs: Response(200, feed, etag='"v2"')

    event, prediction, status = read_saved_event(
        "2026-20", state={}, transport=transport, monotonic=lambda: 1.0
    )

    assert event["race_name"] == "Artifact Grand Prix"
    assert prediction["mode"] == "actual_qualifying"
    assert status["actual_publication_confirmed"] is True
    assert status["initial_prediction"]["mode"] == "predicted_qualifying"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda feed: feed.update(schema_version=99),
        lambda feed: feed.update(revision="0" * 64),
        lambda feed: feed["current"]["prediction"].update(season=2025),
    ],
)
def test_corrupt_or_unsupported_feed_never_crosses_validation_boundary(tmp_path, mutation):
    from streamlit_app.prediction_data import read_saved_event

    feed = _feed(tmp_path)
    mutation(feed)
    event, prediction, status = read_saved_event(
        "2026-20",
        state={},
        transport=lambda url, **kwargs: Response(200, feed),
        monotonic=lambda: 1.0,
        disk_path=tmp_path / "absent.json",
    )

    assert (event["season"], event["round"]) == (2026, 20)
    assert prediction is None
    assert status["reader_warning"].startswith("saved_feed_unavailable")


def test_etag_ttl_and_version_update_use_one_shared_server_fetch(tmp_path):
    from streamlit_app.prediction_data import fetch_feed

    first = _feed(tmp_path, updated="2026-10-30T13:01:00Z")
    second = _feed(tmp_path, updated="2026-10-30T13:03:00Z")
    calls = []

    def transport(url, *, headers, timeout):
        calls.append(dict(headers))
        if len(calls) == 1:
            return Response(200, first, etag='"one"')
        return Response(200, second, etag='"two"')

    assert fetch_feed("https://example.test/prediction_feed.json", transport=transport, monotonic=lambda: 0)["revision"] == first["revision"]
    assert fetch_feed("https://example.test/prediction_feed.json", transport=transport, monotonic=lambda: 30)["revision"] == first["revision"]
    updated = fetch_feed(
        "https://example.test/prediction_feed.json",
        transport=transport,
        monotonic=lambda: 61,
    )

    assert updated["revision"] == second["revision"]
    assert len(calls) == 2
    assert calls[1]["If-None-Match"] == '"one"'


def test_304_reuses_validated_cached_revision(tmp_path):
    from streamlit_app.prediction_data import fetch_feed

    feed = _feed(tmp_path)
    responses = iter([Response(200, feed, etag='"same"'), Response(304)])
    transport = lambda url, **kwargs: next(responses)

    first = fetch_feed("https://example.test/prediction_feed.json", transport=transport, monotonic=lambda: 0)
    second = fetch_feed("https://example.test/prediction_feed.json", transport=transport, monotonic=lambda: 61)

    assert second == first


def test_wrong_event_uses_only_exact_per_event_fallback(tmp_path):
    from streamlit_app.prediction_data import read_saved_event

    global_feed = _feed(tmp_path)
    calls = []

    def transport(url, **kwargs):
        calls.append(url)
        if url.endswith("prediction_feed.json"):
            return Response(200, global_feed)
        return Response(404)

    event, prediction, _status = read_saved_event(
        "2026-21", state={}, transport=transport, monotonic=lambda: 1
    )

    assert event["round"] == 21
    assert prediction is None
    assert calls[-1].endswith("prediction_snapshots/2026-21/feed.json")


def test_network_failure_and_older_cdn_revision_keep_newer_event_last_good(tmp_path):
    from streamlit_app.prediction_data import read_saved_event, reset_shared_cache

    newer = _feed(tmp_path, mode="actual_qualifying", updated="2026-11-01T01:02:00Z")
    older = _feed(tmp_path, updated="2026-10-30T13:01:00Z")
    state = {}
    first = read_saved_event(
        "2026-20",
        state=state,
        transport=lambda url, **kwargs: Response(200, newer),
        monotonic=lambda: 0,
    )
    reset_shared_cache()
    stale = read_saved_event(
        "2026-20",
        state=state,
        transport=lambda url, **kwargs: Response(200, older),
        monotonic=lambda: 61,
    )
    reset_shared_cache()
    failed = read_saved_event(
        "2026-20",
        state=state,
        transport=lambda url, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        monotonic=lambda: 122,
    )

    assert first[1]["mode"] == "actual_qualifying"
    assert stale[1]["prediction_id"] == first[1]["prediction_id"]
    assert stale[2]["reader_warning"] == "stale_feed_ignored"
    assert failed[1]["prediction_id"] == first[1]["prediction_id"]
    assert failed[2]["reader_warning"].startswith("saved_feed_unavailable")


def test_cold_start_accepts_only_valid_exact_event_disk_feed(tmp_path):
    from streamlit_app.prediction_data import read_saved_event

    path = tmp_path / "feed.json"
    path.write_text(json.dumps(_feed(tmp_path)), encoding="utf-8")
    event, prediction, status = read_saved_event(
        "2026-20",
        state={},
        transport=lambda url, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        disk_path=path,
    )

    assert prediction["mode"] == "predicted_qualifying"
    assert status["reader_warning"].startswith("saved_feed_unavailable")
    event2, prediction2, _ = read_saved_event(
        "2026-21",
        state={},
        transport=lambda url, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        disk_path=path,
    )
    assert event2["round"] == 21
    assert prediction2 is None


def test_frozen_status_is_returned_without_changing_prediction(tmp_path):
    from streamlit_app.prediction_data import read_saved_event

    feed = _feed(
        tmp_path,
        status={
            "frozen_at": "2026-11-01T16:00:00Z",
            "freeze_selection": {"prediction_id": _prediction()["prediction_id"]},
        },
    )
    _, prediction, status = read_saved_event(
        "2026-20",
        state={},
        transport=lambda url, **kwargs: Response(200, feed),
    )

    assert prediction["prediction_id"] == _prediction()["prediction_id"]
    assert status["frozen_at"] == "2026-11-01T16:00:00Z"


def test_apptest_saved_fragment_renders_confirmed_prediction(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    feed_path = tmp_path / "feed.json"
    feed = _feed(tmp_path)
    feed_path.write_text(json.dumps(feed), encoding="utf-8")
    monkeypatch.setenv("PREDICTION_EVENT_ID", "2026-20")
    monkeypatch.setenv("PREDICTION_FEED_FILE", str(feed_path))
    monkeypatch.setenv(
        "PREDICTION_FEED_URL", "http://127.0.0.1:9/prediction_feed.json"
    )
    harness = ROOT / "streamlit_app" / "saved_prediction_harness.py"

    app = AppTest.from_file(str(harness)).run(timeout=15)

    assert not app.exception
    assert any(feed["current"]["prediction"]["prediction_id"] in item.value for item in app.caption)


def test_production_app_has_no_visitor_model_or_jolpica_path():
    source = (ROOT / "streamlit_app" / "app.py").read_text(encoding="utf-8")

    assert "st.button" not in source
    assert "refresh_season_data" not in source
    assert "retrain_live" not in source
    assert "src.model" not in source
    assert "jolpica" not in source.lower()


def test_production_entrypoint_bootstraps_repo_root_in_isolated_python(tmp_path):
    env = os.environ.copy()
    env["PREDICTION_FEED_URL"] = "http://127.0.0.1:9/prediction_feed.json"

    completed = subprocess.run(
        [sys.executable, "-I", str(ROOT / "streamlit_app" / "app.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_production_app_refreshes_saved_mode_and_id_together(tmp_path, monkeypatch):
    """AppTest drives reruns; the retained browser-timer check remains deployment work."""

    from streamlit.testing.v1 import AppTest
    from streamlit_app.prediction_data import reset_shared_cache

    feed_path = tmp_path / "feed.json"
    predicted = _feed(tmp_path)
    actual_feed = _feed(
        tmp_path,
        mode="actual_qualifying",
        updated="2026-11-01T01:02:00Z",
    )
    feed_path.write_text(json.dumps(predicted), encoding="utf-8")
    monkeypatch.setenv("PREDICTION_FEED_FILE", str(feed_path))
    monkeypatch.setenv(
        "PREDICTION_FEED_URL", "http://127.0.0.1:9/prediction_feed.json"
    )
    app = AppTest.from_file(str(ROOT / "streamlit_app" / "app.py")).run(timeout=15)
    predicted_id = predicted["current"]["prediction"]["prediction_id"]

    assert not app.exception
    assert not app.button
    assert any(predicted_id in item.value for item in app.caption)
    feed_path.write_text(json.dumps(actual_feed), encoding="utf-8")
    reset_shared_cache()
    app.run(timeout=15)
    actual_id = actual_feed["current"]["prediction"]["prediction_id"]

    assert not app.exception
    assert any(
        actual_id in item.value and "Mode: Actual qualifying" in item.value
        for item in app.caption
    )
    assert not any(predicted_id in item.value for item in app.caption)
