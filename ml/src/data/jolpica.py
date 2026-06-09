"""Thin client for the Jolpica F1 REST API (the Ergast successor).

Each public ``get_*`` function returns a tidy pandas DataFrame for one season.
The client handles pagination (the API caps ``limit`` at 100), reuses a single
HTTP session, and pauses briefly between calls to be polite to the free API.

Run nothing here directly — these functions are called by the caching layer
(``cache.py``) and ``scripts/fetch_data.py``.
"""
from __future__ import annotations

import time

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
        yield mrdata
        total = int(mrdata.get("total", 0))
        offset += PAGE_SIZE
        if offset >= total:
            break


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


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


def get_schedule(season: int) -> pd.DataFrame:
    """The season calendar: round, race name, circuit, date, location."""
    rows = []
    for mr in _iter_pages(f"{season}"):
        for race in mr["RaceTable"]["Races"]:
            loc = race["Circuit"].get("Location", {})
            rows.append({
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "circuit_name": race["Circuit"]["circuitName"],
                "country": loc.get("country"),
                "locality": loc.get("locality"),
                "date": race.get("date"),
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
