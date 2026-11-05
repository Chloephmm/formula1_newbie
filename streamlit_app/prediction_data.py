"""Read and validate confirmed prediction feeds without importing the ML stack."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Mapping, MutableMapping


DEFAULT_FEED_URL = (
    "https://raw.githubusercontent.com/Chloephmm/formula1_newbie/"
    "main/web/public/data/prediction_feed.json"
)
LOCAL_DATA_ROOT = Path(__file__).resolve().parents[1] / "web" / "public" / "data"
TTL_SECONDS = 60.0
TIMEOUT_SECONDS = 5.0
HEX64 = re.compile(r"[0-9a-f]{64}")
EVENT_ID = re.compile(r"([1-9][0-9]*)-([1-9][0-9]*)")


class FeedValidationError(ValueError):
    pass


@dataclass(frozen=True)
class _CacheEntry:
    etag: str | None
    feed: dict[str, Any]
    checked_at: float


_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise FeedValidationError("feed timestamps must be strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeedValidationError("feed timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeedValidationError("feed timestamp lacks a timezone")
    return parsed.astimezone(timezone.utc)


def _identity(value: Mapping[str, Any]) -> tuple[int, int]:
    season, round_number = value.get("season"), value.get("round")
    if (
        isinstance(season, bool)
        or not isinstance(season, int)
        or season <= 0
        or isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number <= 0
    ):
        raise FeedValidationError("feed event identity is invalid")
    return season, round_number


def _canonical_forecast(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FeedValidationError("prediction forecast is invalid")
    result = copy.deepcopy(dict(value))
    for field in (
        "predictedQualifying",
        "preQualifyingPodium",
        "realQualifying",
        "realGridPodium",
    ):
        rows = result.get(field)
        if isinstance(rows, list):
            result[field] = sorted(rows, key=lambda row: row.get("driver_id", ""))
    return result


def _prediction_semantic(prediction: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "schema_version",
        "season",
        "round",
        "mode",
        "model_version",
        "model_manifest",
        "training_cutoff",
        "training_data_hash",
        "training_manifest",
        "qualifying_source_version",
        "qualifying_manifest",
        "input_hash",
        "feature_input_hash",
        "feature_policy_version",
        "probability_policy_version",
        "event_schedule_hash",
        "roster_version",
    )
    result = {field: prediction.get(field) for field in fields}
    result["forecast"] = _canonical_forecast(prediction.get("forecast"))
    return result


def _validate_prediction(prediction: Any, event: Mapping[str, Any]) -> None:
    if not isinstance(prediction, Mapping):
        raise FeedValidationError("selection prediction is missing")
    if prediction.get("schema_version") != 2 or _identity(prediction) != _identity(event):
        raise FeedValidationError("prediction has the wrong event or schema")
    mode = prediction.get("mode")
    if mode not in {"predicted_qualifying", "actual_qualifying"}:
        raise FeedValidationError("prediction mode is unsupported")
    prediction_id = prediction.get("prediction_id")
    if not isinstance(prediction_id, str) or not HEX64.fullmatch(prediction_id):
        raise FeedValidationError("prediction id is invalid")
    if prediction_id != _digest(_prediction_semantic(prediction)):
        raise FeedValidationError("prediction id does not match its content")
    forecast = prediction.get("forecast")
    if not isinstance(forecast, Mapping) or forecast.get("error") is not None:
        raise FeedValidationError("prediction forecast is unavailable")
    if forecast.get("mode") != mode or _identity(forecast.get("race", {})) != _identity(event):
        raise FeedValidationError("forecast has the wrong event or mode")
    _utc(prediction.get("generated_at"))


def _validate_receipt(receipt: Any, prediction: Mapping[str, Any], event) -> None:
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != 1:
        raise FeedValidationError("publication receipt is invalid")
    if receipt.get("confirmed") is not True or _identity(receipt) != _identity(event):
        raise FeedValidationError("publication is not confirmed for this event")
    if receipt.get("prediction_id") != prediction.get("prediction_id"):
        raise FeedValidationError("publication points at another prediction")
    expected_checksum = hashlib.sha256(_canonical(prediction) + b"\n").hexdigest()
    if receipt.get("checksum") != expected_checksum:
        raise FeedValidationError("publication checksum does not match")
    publication_id = receipt.get("publication_id")
    body = {key: value for key, value in receipt.items() if key != "publication_id"}
    if not isinstance(publication_id, str) or publication_id != _digest(body):
        raise FeedValidationError("publication id does not match its receipt")
    published = _utc(receipt.get("published_at"))
    cutoff = _utc(receipt.get("cutoff_at"))
    if published >= cutoff or published < _utc(prediction.get("generated_at")):
        raise FeedValidationError("publication is not deadline eligible")
    if prediction.get("mode") == "predicted_qualifying" and published >= _utc(
        receipt.get("qualifying_start_at")
    ):
        raise FeedValidationError("initial publication missed qualifying")


def _validate_selection(selection: Any, target: Mapping[str, Any]) -> None:
    if selection is None:
        return
    if not isinstance(selection, Mapping) or set(selection) != {
        "event",
        "prediction",
        "publication",
    }:
        raise FeedValidationError("feed selection is malformed")
    original_event = selection["event"]
    if not isinstance(original_event, Mapping) or _identity(original_event) != _identity(target):
        raise FeedValidationError("feed selection belongs to another event")
    _validate_prediction(selection["prediction"], original_event)
    _validate_receipt(selection["publication"], selection["prediction"], original_event)


def validate_feed(value: Any, *, expected_event_id: str | None = None) -> dict[str, Any]:
    """Validate one atomic feed revision and return an isolated copy."""

    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        raise FeedValidationError("feed schema is unsupported")
    feed = copy.deepcopy(dict(value))
    revision = feed.pop("revision", None)
    if not isinstance(revision, str) or revision != _digest(feed):
        raise FeedValidationError("feed revision does not match its content")
    feed["revision"] = revision
    event = feed.get("event")
    status = feed.get("status")
    if not isinstance(event, Mapping) or not isinstance(status, Mapping):
        raise FeedValidationError("feed event/status is malformed")
    season, round_number = _identity(event)
    event_id = f"{season}-{round_number}"
    if feed.get("current_event_id") != event_id:
        raise FeedValidationError("feed current event id is inconsistent")
    if expected_event_id is not None and event_id != expected_event_id:
        raise FeedValidationError("feed belongs to another event")
    _utc(feed.get("feed_updated_at"))
    for field in ("current", "previous", "initial"):
        _validate_selection(feed.get(field), event)
    initial = feed.get("initial")
    if initial is not None and initial["prediction"].get("mode") != "predicted_qualifying":
        raise FeedValidationError("feed initial has the wrong mode")
    return feed


def _default_transport(url: str, *, headers: Mapping[str, str], timeout: float):
    import requests

    return requests.get(url, headers=dict(headers), timeout=timeout)


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", {}) or {}
    return headers.get(name) or headers.get(name.lower())


def fetch_feed(
    url: str,
    *,
    transport: Callable | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Fetch a validated feed with shared TTL and conditional ETag requests."""

    now = float(monotonic())
    with _CACHE_LOCK:
        cached = _CACHE.get(url)
        if cached is not None and now - cached.checked_at < TTL_SECONDS:
            return copy.deepcopy(cached.feed)
    headers = {"Accept": "application/json"}
    if cached is not None and cached.etag:
        headers["If-None-Match"] = cached.etag
    response = (transport or _default_transport)(
        url, headers=headers, timeout=TIMEOUT_SECONDS
    )
    status_code = int(getattr(response, "status_code", 0))
    if status_code == 304:
        if cached is None:
            raise FeedValidationError("received 304 without a cached feed")
        entry = _CacheEntry(cached.etag, cached.feed, now)
    elif status_code == 200:
        try:
            payload = response.json()
        except Exception as exc:
            raise FeedValidationError("saved feed is not valid JSON") from exc
        validated = validate_feed(payload)
        entry = _CacheEntry(_header(response, "ETag"), validated, now)
    else:
        raise ConnectionError(f"saved feed request failed with HTTP {status_code}")
    with _CACHE_LOCK:
        _CACHE[url] = entry
    return copy.deepcopy(entry.feed)


def reset_shared_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _event_url(global_url: str, event_id: str) -> str:
    suffix = "prediction_feed.json"
    if global_url.endswith(suffix):
        return global_url[: -len(suffix)] + f"prediction_snapshots/{event_id}/feed.json"
    raise ValueError("PREDICTION_FEED_URL must end in prediction_feed.json")


def current_saved_event_id(
    *,
    state: MutableMapping | None = None,
    url: str | None = None,
    transport: Callable | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    disk_path: str | Path | None = None,
) -> str | None:
    """Return the current saved event, retaining the last valid rollover value."""

    session = _state_mapping(state)
    global_url = url or os.environ.get("PREDICTION_FEED_URL", DEFAULT_FEED_URL)
    feed = None
    try:
        feed = fetch_feed(global_url, transport=transport, monotonic=monotonic)
    except Exception:
        candidates = []
        if disk_path is not None:
            candidates.append(Path(disk_path))
        candidates.append(LOCAL_DATA_ROOT / "prediction_feed.json")
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                feed = validate_feed(payload)
                break
            except (OSError, UnicodeError, json.JSONDecodeError, FeedValidationError):
                pass
    if feed is not None:
        session["_prediction_current_event_id"] = feed["current_event_id"]
    return session.get("_prediction_current_event_id")


def _state_mapping(state: MutableMapping | None) -> MutableMapping:
    if state is not None:
        return state
    import streamlit as st

    return st.session_state


def _last_good_store(state: MutableMapping) -> dict[str, Any]:
    key = "_prediction_last_good_by_event"
    if key not in state:
        state[key] = {}
    return state[key]


def _from_feed(feed: Mapping[str, Any]):
    selection = feed.get("current")
    event = copy.deepcopy(dict(feed["event"]))
    status = copy.deepcopy(dict(feed["status"]))
    status["feed_updated_at"] = feed["feed_updated_at"]
    status["feed_revision"] = feed["revision"]
    status["last_checked_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    if feed.get("initial") is not None:
        status["initial_prediction"] = copy.deepcopy(
            feed["initial"]["prediction"]
        )
    prediction = (
        None if selection is None else copy.deepcopy(dict(selection["prediction"]))
    )
    return event, prediction, status


def _load_disk_feed(path: Path, event_id: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_feed(payload, expected_event_id=event_id)
    except (OSError, UnicodeError, json.JSONDecodeError, FeedValidationError):
        return None


def _event_hint(event_id: str, root: Path) -> dict[str, Any]:
    match = EVENT_ID.fullmatch(event_id)
    if match is None:
        raise ValueError("event_id must use season-round")
    path = root / "prediction_snapshots" / event_id / "event.json"
    value = None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    if isinstance(value, dict):
        try:
            if _identity(value) == tuple(map(int, match.groups())):
                return value
        except FeedValidationError:
            pass
    return {
        "season": int(match.group(1)),
        "round": int(match.group(2)),
        "race_name": f"Round {int(match.group(2))}",
    }


def read_saved_event(
    event_id: str,
    *,
    state: MutableMapping | None = None,
    url: str | None = None,
    transport: Callable | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    disk_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    """Return the exact saved event, its confirmed prediction (or ``None``), and status.

    Failures and stale CDN responses retain only this event's newer last-good value.
    Another race is never used as a fallback.
    """

    if EVENT_ID.fullmatch(event_id) is None:
        raise ValueError("event_id must use season-round")
    session = _state_mapping(state)
    last_good = _last_good_store(session)
    global_url = url or os.environ.get("PREDICTION_FEED_URL", DEFAULT_FEED_URL)
    warning = None
    feed = None
    try:
        global_feed = fetch_feed(
            global_url, transport=transport, monotonic=monotonic
        )
        if global_feed["current_event_id"] == event_id:
            feed = global_feed
        else:
            feed = fetch_feed(
                _event_url(global_url, event_id),
                transport=transport,
                monotonic=monotonic,
            )
            feed = validate_feed(feed, expected_event_id=event_id)
    except Exception as exc:
        warning = f"saved_feed_unavailable:{type(exc).__name__}"
        try:
            feed = fetch_feed(
                _event_url(global_url, event_id),
                transport=transport,
                monotonic=monotonic,
            )
            feed = validate_feed(feed, expected_event_id=event_id)
        except Exception:
            feed = None

    local_root = LOCAL_DATA_ROOT
    if feed is None:
        candidates = []
        if disk_path is not None:
            candidates.append(Path(disk_path))
        candidates.extend(
            [
                local_root / "prediction_snapshots" / event_id / "feed.json",
                local_root / "prediction_feed.json",
            ]
        )
        for candidate in candidates:
            feed = _load_disk_feed(candidate, event_id)
            if feed is not None:
                warning = warning or "using_confirmed_disk_feed"
                break

    if feed is not None:
        event, prediction, status = _from_feed(feed)
        prior = last_good.get(event_id)
        if prior is not None and _utc(prior["status"]["feed_updated_at"]) > _utc(
            status["feed_updated_at"]
        ):
            event = copy.deepcopy(prior["event"])
            prediction = copy.deepcopy(prior["prediction"])
            status = copy.deepcopy(prior["status"])
            warning = "stale_feed_ignored"
        elif prediction is not None:
            last_good[event_id] = {
                "event": copy.deepcopy(event),
                "prediction": copy.deepcopy(prediction),
                "status": copy.deepcopy(status),
            }
        elif prior is not None:
            event = copy.deepcopy(prior["event"])
            prediction = copy.deepcopy(prior["prediction"])
            status = copy.deepcopy(prior["status"])
            warning = "empty_feed_ignored"
        if warning:
            status["reader_warning"] = warning
        return event, prediction, status

    prior = last_good.get(event_id)
    if prior is not None:
        status = copy.deepcopy(prior["status"])
        status["reader_warning"] = warning or "saved_feed_unavailable"
        return (
            copy.deepcopy(prior["event"]),
            copy.deepcopy(prior["prediction"]),
            status,
        )
    event = _event_hint(event_id, local_root)
    return event, None, {
        "validation_reason": warning or "prediction_unavailable",
        "reader_warning": warning,
    }
