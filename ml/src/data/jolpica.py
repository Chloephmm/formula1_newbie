"""Thin client for the Jolpica F1 REST API (the Ergast successor).

Each public ``get_*`` function returns a tidy pandas DataFrame for one season.
The client handles pagination (the API caps ``limit`` at 100), reuses a single
HTTP session, and pauses briefly between calls to be polite to the free API.

Run nothing here directly — these functions are called by the caching layer
(``cache.py``) and ``scripts/fetch_data.py``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100          # API maximum
MIN_INTERVAL = 0.5       # min seconds between ANY two requests (Jolpica burst limit ~4/s)
MAX_RETRIES = 6          # retries on 429 / 5xx
TIMEOUT = 30

_session = requests.Session()
_session.headers.update({"User-Agent": "f1-guidebook/0.1 (portfolio project)"})
_last_call = [0.0]       # monotonic timestamp of the previous request


@dataclass(frozen=True)
class PaginationMetadata:
    """Evidence that every page reported by Jolpica was collected."""

    reported_total: int
    fetched_count: int
    pages_fetched: int
    offsets: tuple[int, ...]
    limits: tuple[int, ...]
    complete: bool


@dataclass(frozen=True)
class QualifyingFetchResult:
    """Round-scoped qualifying rows plus the pagination evidence."""

    data: pd.DataFrame
    pagination: PaginationMetadata

    @property
    def rows(self) -> pd.DataFrame:
        """Compatibility-friendly alias for callers that think in rows."""
        return self.data


def _throttle() -> None:
    """Space requests out so we stay under the API's per-second burst limit."""
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_call[0] = time.monotonic()


def _get(path: str, params: dict) -> dict:
    """GET {BASE_URL}/{path}.json with throttling + retry on 429/5xx."""
    url = f"{BASE_URL}/{path}.json"
    for attempt in range(MAX_RETRIES):
        _throttle()
        resp = _session.get(url, params=params, timeout=TIMEOUT)
        if resp.status_code == 429 or resp.status_code >= 500:
            # respect Retry-After if present, else exponential backoff
            wait = float(resp.headers.get("Retry-After", 2 ** attempt))
            time.sleep(min(wait, 30))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()  # retries exhausted — surface the error
    return resp.json()


def _iter_pages(path: str, params: dict | None = None):
    """Yield each page's ``MRData`` dict, looping ``offset`` until all rows fetched."""
    params = dict(params or {})
    offset = 0
    while True:
        params.update(limit=PAGE_SIZE, offset=offset)
        mrdata = _get(path, params)["MRData"]
        total = int(mrdata.get("total", 0))
        returned_offset = int(mrdata.get("offset", offset))
        if returned_offset != offset:
            raise ValueError(
                f"pagination returned offset {returned_offset}, expected {offset}"
            )
        raw_limit = mrdata.get("limit", params["limit"])
        try:
            returned_limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid page limit: {raw_limit!r}") from exc
        if returned_limit <= 0:
            raise ValueError(f"page limit must be positive, got {returned_limit}")

        yield mrdata
        offset = returned_offset + returned_limit
        if offset >= total:
            break


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _as_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return _as_utc_iso(datetime.now(timezone.utc).replace(microsecond=0))


def _event_timestamp(date_text: str | None, time_text: str | None) -> str | None:
    """Combine Jolpica's separate date/time values into a UTC ISO timestamp."""
    if not date_text or not time_text:
        return None
    parsed = datetime.fromisoformat(f"{date_text}T{time_text.replace('Z', '+00:00')}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _as_utc_iso(parsed)


def get_race_results(season: int) -> pd.DataFrame:
    """One row per driver per race: finishing position, grid, status, points."""
    rows = []
    for mr in _iter_pages(f"{season}/results"):
        for race in mr["RaceTable"]["Races"]:
            meta = {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "date": race.get("date"),
            }
            for res in race.get("Results", []):
                drv, con = res["Driver"], res["Constructor"]
                rows.append({
                    **meta,
                    "driver_id": drv["driverId"],
                    "code": drv.get("code"),
                    "driver_name": f'{drv["givenName"]} {drv["familyName"]}',
                    "nationality": drv.get("nationality"),
                    "constructor_id": con["constructorId"],
                    "constructor_name": con["name"],
                    "grid": res.get("grid"),
                    "position": res.get("position"),       # classified finishing position
                    "position_text": res.get("positionText"),  # 'R', 'D', etc. for non-finishes
                    "points": res.get("points"),
                    "laps": res.get("laps"),
                    "status": res.get("status"),           # 'Finished', 'Accident', '+1 Lap', ...
                })
    return _coerce_numeric(pd.DataFrame(rows), ["grid", "position", "points", "laps"])


def get_qualifying(season: int) -> pd.DataFrame:
    """One row per driver per race with Q1/Q2/Q3 lap-time strings (e.g. '1:29.708')."""
    rows = []
    for mr in _iter_pages(f"{season}/qualifying"):
        for race in mr["RaceTable"]["Races"]:
            meta = {"season": int(race["season"]), "round": int(race["round"])}
            for q in race.get("QualifyingResults", []):
                drv, con = q["Driver"], q["Constructor"]
                rows.append({
                    **meta,
                    "driver_id": drv["driverId"],
                    "code": drv.get("code"),
                    "constructor_id": con["constructorId"],
                    "quali_position": q.get("position"),
                    "q1": q.get("Q1"),
                    "q2": q.get("Q2"),
                    "q3": q.get("Q3"),
                })
    return _coerce_numeric(pd.DataFrame(rows), ["quali_position"])


def get_qualifying_round(season: int, round_number: int) -> QualifyingFetchResult:
    """Fetch one round's qualifying classification and retain pagination evidence."""
    rows = []
    totals = []
    offsets = []
    limits = []
    for mr in _iter_pages(f"{season}/{round_number}/qualifying"):
        totals.append(int(mr.get("total", 0)))
        offsets.append(int(mr.get("offset", 0)))
        limits.append(int(mr.get("limit", PAGE_SIZE)))
        for race in mr.get("RaceTable", {}).get("Races", []):
            meta = {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
            }
            for q in race.get("QualifyingResults", []):
                drv, con = q["Driver"], q["Constructor"]
                rows.append({
                    **meta,
                    "driver_id": drv["driverId"],
                    "code": drv.get("code"),
                    "driver_name": " ".join(
                        part for part in (drv.get("givenName"), drv.get("familyName")) if part
                    ) or drv["driverId"],
                    "constructor_id": con["constructorId"],
                    "constructor_name": con.get("name") or con["constructorId"],
                    "quali_position": q.get("position"),
                    "q1": q.get("Q1"),
                    "q2": q.get("Q2"),
                    "q3": q.get("Q3"),
                })

    data = _coerce_numeric(pd.DataFrame(rows), ["quali_position"])
    reported_total = totals[0] if totals else 0
    consistent_total = all(total == reported_total for total in totals)
    expected_offset = 0
    offsets_complete = True
    for offset, limit in zip(offsets, limits):
        if offset != expected_offset or limit <= 0:
            offsets_complete = False
            break
        expected_offset += limit
    offsets_complete = offsets_complete and expected_offset >= reported_total
    pagination = PaginationMetadata(
        reported_total=reported_total,
        fetched_count=len(data),
        pages_fetched=len(totals),
        offsets=tuple(offsets),
        limits=tuple(limits),
        complete=consistent_total and offsets_complete and len(data) == reported_total,
    )
    return QualifyingFetchResult(data=data, pagination=pagination)


get_round_qualifying = get_qualifying_round


def get_driver_standings(season: int) -> pd.DataFrame:
    """End-of-season driver standings: position, points, wins, team."""
    rows = []
    for mr in _iter_pages(f"{season}/driverStandings"):
        for sl in mr["StandingsTable"]["StandingsLists"]:
            for s in sl.get("DriverStandings", []):
                drv = s["Driver"]
                cons = s.get("Constructors", [])
                rows.append({
                    "season": int(sl["season"]),
                    "round": int(sl["round"]),
                    "driver_id": drv["driverId"],
                    "code": drv.get("code"),
                    "position": s.get("position"),
                    "points": s.get("points"),
                    "wins": s.get("wins"),
                    "constructor_id": cons[0]["constructorId"] if cons else None,
                })
    return _coerce_numeric(pd.DataFrame(rows), ["position", "points", "wins"])


def get_constructor_standings(season: int) -> pd.DataFrame:
    """End-of-season constructor standings: position, points, wins."""
    rows = []
    for mr in _iter_pages(f"{season}/constructorStandings"):
        for sl in mr["StandingsTable"]["StandingsLists"]:
            for s in sl.get("ConstructorStandings", []):
                con = s["Constructor"]
                rows.append({
                    "season": int(sl["season"]),
                    "round": int(sl["round"]),
                    "constructor_id": con["constructorId"],
                    "constructor_name": con["name"],
                    "nationality": con.get("nationality"),
                    "position": s.get("position"),
                    "points": s.get("points"),
                    "wins": s.get("wins"),
                })
    return _coerce_numeric(pd.DataFrame(rows), ["position", "points", "wins"])


def get_schedule(season: int, *, fetched_at=None) -> pd.DataFrame:
    """The season calendar: round, race name, circuit, date, location."""
    rows = []
    fetched = fetched_at or datetime.now(timezone.utc)
    if isinstance(fetched, str):
        fetched = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    if fetched.tzinfo is None:
        raise ValueError("fetched_at must include a timezone")
    schedule_updated_at = _as_utc_iso(fetched.replace(microsecond=0))
    for mr in _iter_pages(f"{season}"):
        for race in mr["RaceTable"]["Races"]:
            loc = race["Circuit"].get("Location", {})
            qualifying = race.get("Qualifying", {})
            qualifying_start_at = _event_timestamp(
                qualifying.get("date"), qualifying.get("time")
            )
            race_start_at = _event_timestamp(race.get("date"), race.get("time"))
            qualifying_end_at = None
            if qualifying_start_at:
                start = datetime.fromisoformat(qualifying_start_at.replace("Z", "+00:00"))
                qualifying_end_at = _as_utc_iso(start + timedelta(minutes=90))
            rows.append({
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "circuit_name": race["Circuit"]["circuitName"],
                "country": loc.get("country"),
                "locality": loc.get("locality"),
                "date": race.get("date"),
                "qualifying_start_at": qualifying_start_at,
                "qualifying_end_at": qualifying_end_at,
                "end_time_estimated": True,
                "race_start_at": race_start_at,
                "schedule_updated_at": schedule_updated_at,
                "schedule_source": "jolpica",
            })
    return pd.DataFrame(rows)


# --- small helper used later by feature engineering (quali_time_gap_to_pole) ---
def laptime_to_seconds(text: str | None) -> float | None:
    """Convert a lap-time string like '1:29.708' or '58.402' to float seconds."""
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    try:
        if ":" in text:
            minutes, rest = text.split(":", 1)
            return int(minutes) * 60 + float(rest)
        return float(text)
    except (ValueError, TypeError):
        return None
