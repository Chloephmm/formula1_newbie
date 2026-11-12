# Phase 1 Streamlit F1 Buddy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free, rule-based chatbot popup that reads the existing prediction website's outputs and optionally reads Jolpica, without changing the prediction engine, strategy, or data.

**Architecture:** Build `f1buddy-ai` as a separate Python package. A pure adapter copies the already displayed race and podium rows into chatbot models; the popup reads existing JSON and uses a separate, cached Jolpica client when needed. A Streamlit fragment isolates chatbot interactions from the surrounding prediction page.

**Tech Stack:** Python 3.11+, Streamlit 1.37+ (installed host inspected: 1.54.0), Pydantic 2, Requests, pytest, responses, existing JSON read-only, Jolpica GET requests.

**Status:** Revised November 5, 2026 to include historical predictions and actual results while preserving the user's read-only boundary. Planning only; no implementation changes have been made.

---

## Mandatory scope boundary

This revision supersedes the previous draft's producer-side work. The user's prediction ML engine, strategy, data, and refresh behavior are out of scope.

- Do not modify any file under `ml/`, including code, tests, trained models, raw data, cached Parquet, metrics, or export scripts.
- Do not modify or regenerate any file under `web/public/data/`; do not add a manifest.
- Do not modify `web/lib/types.ts`, frontend data contracts, or any file under `.github/workflows/`.
- Do not modify `resolve()`, `_run_forecast()`, `_load_snapshot()`, training, feature engineering, probability calculations, ranking, grid selection, backtesting, or refresh-button behavior.
- Do not import or invoke the host's ML, retraining, export, refresh, or cache-writing functions from chatbot code. Do not clear the host's Streamlit caches.
- Do not mutate objects supplied by the page. Chatbot adapters create new objects and preserve the displayed order and rounded percentages.
- Jolpica reads belong to the chatbot only. Keep responses in a small process-memory cache; never save them into the prediction repository or feed them into the model.
- Missing predictions or model metrics are explicitly marked unavailable. For a named historical race, fall back to actual race/qualifying results as appropriate, clearly labelled as results rather than predictions. The chatbot must not train, infer, calculate replacement predictions, or refresh datasets to fill a gap.
- Only the small popup integration in `streamlit_app/app.py`, the package dependency in `streamlit_app/requirements.txt`, and chatbot documentation may change in the existing repository.

Regular website behavior when a user loads the page or presses its existing RUN button remains the website's responsibility. Chatbot clicks use a fragment rerun and must not cause an extra full-page prediction run.

## Scope, cost, and schedule

Existing checkout: `C:/Users/user/Documents/Codex/Formula1`, branch `feature2`.
Planned sibling package: `C:/Users/user/Documents/Codex/f1buddy-ai`, branch `feature2`.

Incremental chatbot service cost: $0 when using existing website hosting and local outputs. Existing hosting and account quotas remain separate. No AI model, database, RAG, WhatsApp, background refresh job, or notification scheduler is needed.

| Estimated day | Deliverable |
|---|---|
| 1 | Package scaffold and read-only output contracts (Task 1) |
| 2 | Existing JSON readers and guarded Jolpica client (Tasks 2–3) |
| 3 | Source selection and deterministic responses (Tasks 4–5) |
| 4 | Pure display adapter and isolated Streamlit popup (Task 6) |
| 5 | Minimal host integration (Task 7) |
| 6 | Read-only checks, failure tests, UI acceptance and documentation (Task 8) |
| 7–8 | Historical race selection, saved prediction stages, actual-results fallback, and regression tests (Task 9) |

The supported intents are next-race details, latest saved driver standings, latest saved constructor standings, displayed podium prediction, saved offline model evaluation, historical race predictions/results, and help/unsupported-question fallback. The original five quick buttons stay; help also explains typed historical questions. The historical extension adds an estimated one to two working days.

## Data sources and behavior

| Question | First source | Fallback |
|---|---|---|
| Next race | Existing `race` display dictionary passed by the page | Existing compatible `next_race_prediction.json`, then Jolpica schedule if no usable local race exists |
| Driver/constructor standings | Existing `web/public/data/stats.json` with its own `updatedAt` | Jolpica standings for the current season |
| Current prediction | Existing `race["podium"]` or `race["podium_real"]`, following the page's `is_real` flag | Existing snapshot only when date/race/mode match; otherwise unavailable |
| Model performance | Existing `web/public/data/metrics.json` | Unavailable; no model execution |
| Named historical prediction | Matching race in existing `next_race_prediction.json`; otherwise `predictions.json["season-round"]` for an unqualified saved estimate | Clearly report any unavailable stage; fetch actual results instead |
| Historical qualifying / race result | Matching saved `realQualifying` when present; existing chatbot response cache | Jolpica qualifying / race-results endpoints for the resolved season and round |
| Help | Static chatbot text | None |

## Historical questions: required behavior

While the page is showing Brazil, a visitor can ask `Mexico prediction`, `Mexico predicted qualifying`, `Mexico prediction after qualifying`, `Mexico qualifying results`, `United States 2025 race results`, or `Compare Mexico prediction and results`. Named-race routing runs before the generic current-prediction rules so these questions never return Brazil's forecast.

- Use an explicit year when provided; otherwise use the displayed race's season and print that year in the answer. Never substitute another season because a prediction is missing.
- Resolve Mexico/Mexican GP to Mexico City Grand Prix, and United States GP/Austin/COTA to United States Grand Prix. Ask for clarification for generic `USA` or multiple named races; do not mix Austin, Miami and Las Vegas.
- Resolve the actual round from existing race metadata or a cached Jolpica season schedule. Never hardcode a year's round number or derive it from a different season.
- Keep these categories distinct: predicted qualifying order, pre-qualifying podium forecast, podium forecast using real qualifying, actual qualifying classification, and actual race finishing classification. Qualifying classification is not necessarily the final starting grid after penalties. Podium probabilities are not win probabilities.
- Show an existing stage only when the saved record identifies that stage and matches the selected race. A general historical estimate without stage/timestamp metadata must be labelled `Saved historical model estimate — qualifying stage and original forecast time not recorded`; it cannot satisfy an explicit pre/post-qualifying request.
- If a requested prediction stage is absent, say so and show actual results if available. If qualifying is requested, include actual qualifying separately. Never replace a prediction with the actual result under a prediction heading.
- If results are not published or the API fails, explain which data is unavailable and preserve any valid saved prediction. Empty results are not zeros, and an outage is not evidence the race has not happened.
- No historical prediction archive is created, and no old model is rerun. Historical forecast coverage is limited to outputs that already exist. Sprint results are outside this extension; explicitly say so rather than returning Grand Prix results for a sprint request.

Repository inspection on November 5 found that `predictions.json` and `races.json` cover 2024, 2025 and only the first five rounds of 2026. `next_race_prediction.json` currently identifies Mexico 2026 with predicted qualifying and pre-qualifying podium output; its `hasRealGrid` is false. The producer overwrites this single snapshot. These findings explain availability today, not a promise that those fields will remain available during Brazil week. The generic export is produced by scoring existing race features; do not describe it as proof of a forecast published before that race.

The fallback uses the official Jolpica [qualifying endpoint](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/qualifying.md) and [race-results endpoint](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/results.md), filtered by season and round. Reuse the same chatbot cache, retry policy, and hourly budget for these GET requests.

Standings are labelled as latest saved standings, not historical standings for the selected date. Offline evaluation is labelled separately from the site's live accuracy panel. Do not invent a publication timestamp when an existing file has none.

The existing display dictionary has `name`, `round`, `race` (ISO race date), `quali`, `podium`, and optional `podium_real`. It has no `season` or `date` keys. The new adapter infers the calendar season from the supplied race date solely for display identity, and converts the already displayed integer percentage back to a fraction for formatting. It does not change probabilities or their order.

Exact session times are optional: show a saved time when one exists; otherwise show the known date and say the exact time is unavailable. Do not add new timestamps to host outputs. The independent Jolpica schedule fallback can read available session times without storing them on disk.

Request flow: popup → rule-based intent router → read-only data service → existing page outputs / existing JSON → guarded Jolpica fallback when needed → formatted reply.

## File map

### Existing repository: allowed modifications

| File | Change |
|---|---|
| `streamlit_app/app.py` | One chatbot import and one guarded rendering call after existing results; all existing prediction functions stay untouched |
| `streamlit_app/requirements.txt` | Add the installable chatbot dependency after its release is available |
| `streamlit_app/README.md` | Explain setup, supported questions, and read-only behavior |
| This plan document | Track the approved scope and execution steps |

No new application, data, manifest, or test file is added to the existing repository. All new chatbot code and tests belong to the sibling package.

### New package: create these files

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.gitignore`, `README.md` | Packaging, exclusions, setup and contract |
| `src/f1buddy_ai/__init__.py` | Expose `render_chatbot` |
| `src/f1buddy_ai/models.py` | Validated copies of data used by the chatbot |
| `src/f1buddy_ai/data/snapshots.py` | Read existing JSON without writes |
| `src/f1buddy_ai/data/jolpica.py` | Independent in-memory cache, request budget and retries |
| `src/f1buddy_ai/services/f1_data.py` | Choose sources without running ML |
| `src/f1buddy_ai/chat/intents.py`, `engine.py` | Recognize questions and format answers |
| `src/f1buddy_ai/chat/history.py` | Resolve named races, read existing saved stages, format historical answers and actual results |
| `src/f1buddy_ai/ui/adapter.py` | Copy the existing page's display output without changing it |
| `src/f1buddy_ai/ui/streamlit.py` | Fragment-scoped popup, buttons and session history |
| `src/f1buddy_ai/{data,services,chat,ui}/__init__.py` | Package markers |
| `examples/streamlit_demo.py` | Synthetic standalone UI demonstration |
| `tests/test_snapshots.py`, `test_jolpica.py`, `test_f1_data.py` | Source and failure behavior |
| `tests/test_intents.py`, `test_engine.py`, `test_public_api.py` | Routing, formatting, public API |
| `tests/test_adapter.py`, `test_read_only.py` | Copy-only integration and unchanged source fixtures |
| `tests/test_history.py` | Named-race/year routing, available/missing stages, result fallback, and unchanged source records |
| `tests/fixtures/public_data/{stats,metrics,next_race_prediction}.json` | Synthetic data confined to the new package |

Use normal filesystem approval for the sibling directory if required by the environment. Local editable installation is enough for review; external publication requires an authorized repository destination and visibility.

## Task 1: Scaffold the separate `f1buddy-ai` package

**Files:**
- Create: `C:/Users/user/Documents/Codex/f1buddy-ai/pyproject.toml`
- Create: `C:/Users/user/Documents/Codex/f1buddy-ai/src/f1buddy_ai/__init__.py`
- Create: `C:/Users/user/Documents/Codex/f1buddy-ai/src/f1buddy_ai/models.py`
- Create: package `__init__.py` files under `data`, `services`, `chat`, and `ui`
- Create: `C:/Users/user/Documents/Codex/f1buddy-ai/README.md`
- Create: `C:/Users/user/Documents/Codex/f1buddy-ai/.gitignore`

- [ ] **Step 1: Create and initialize the repository**

```powershell
Set-Location C:/Users/user/Documents/Codex
New-Item -ItemType Directory -Path f1buddy-ai
Set-Location f1buddy-ai
git init -b main
git switch -c feature2
New-Item -ItemType Directory -Force -Path src/f1buddy_ai/data,src/f1buddy_ai/services,src/f1buddy_ai/chat,src/f1buddy_ai/ui,tests/fixtures/public_data,examples
```

Expected: `git branch --show-current` prints `feature2`.

If the sibling directory already exists, inspect its Git status and contents before using it; do not initialize over existing work. Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
dist/
build/
.env
.env.*
.streamlit/secrets.toml
```

- [ ] **Step 2: Create package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.26"]
build-backend = "hatchling.build"

[project]
name = "f1buddy-ai"
version = "0.1.0"
description = "Deterministic F1 chatbot components for Streamlit and WhatsApp"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.9,<3",
  "requests>=2.32,<3",
  "streamlit>=1.37,<2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "responses>=0.25,<1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Define validated shared models**

Create `src/f1buddy_ai/models.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class RaceInfo(BaseModel):
    name: str
    season: int
    round: int
    country: str | None = None
    date: date
    qualifyingDate: date | None = None
    raceStartUtc: datetime | None = None
    sessions: dict[str, datetime | None] = Field(default_factory=dict)


class DriverStanding(BaseModel):
    position: int
    code: str
    name: str
    team: str
    points: float
    wins: int


class ConstructorStanding(BaseModel):
    position: int
    id: str
    name: str
    points: float
    wins: int


class PodiumPrediction(BaseModel):
    code: str
    driverName: str
    team: str
    podiumProbability: float = Field(ge=0.0, le=1.0)


class ModelPerformance(BaseModel):
    roc_auc: float
    top1_accuracy: float
    top3_accuracy: float
    test_rows: int


class DataResult(BaseModel, Generic[T]):
    data: T
    source: str
    generated_at: datetime | None = None
    stale: bool = False


class HostContext(BaseModel):
    as_of_date: date
    current_race: RaceInfo | None = None
    has_real_grid: bool = False
    current_prediction: list[PodiumPrediction] | None = None


class ChatOption(BaseModel):
    label: str
    command: str


class ChatReply(BaseModel):
    text: str
    intent: str
    options: list[ChatOption] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Create empty `__init__.py` files in `data`, `services`, `chat`, and `ui`.

Create `src/f1buddy_ai/__init__.py` initially with:

```python
from f1buddy_ai.models import HostContext

__all__ = ["HostContext"]
```

- [ ] **Step 4: Install the package in editable mode and verify imports**

```powershell
python -m pip install -e ".[dev]"
python -c "from f1buddy_ai.models import HostContext, ChatReply; print('f1buddy-ai import OK')"
```

Expected: `f1buddy-ai import OK`.

- [ ] **Step 5: Add an initial README and commit**

Create `README.md` with:

```markdown
# F1 Buddy

Phase 1 is a deterministic Streamlit popover for next-race details, latest saved
driver standings, constructor standings, current podium prediction, saved model
evaluation, and help. It uses local formula1-newbie JSON first, with Jolpica as a
bounded fallback for missing schedule, standings, qualifying or race results.
Named historical predictions are read only when already saved; no AI key is required.

Install locally: `python -m pip install -e ".[dev]"`.
Run tests: `python -m pytest -v`.
Run demo: `streamlit run examples/streamlit_demo.py`.

Public API: `from f1buddy_ai import render_chatbot`.
Pass `data_dir`, `as_of_date`, `displayed_race`, `has_real_grid`, `driver_names`,
and `team_names`. The adapter copies existing display outputs. Popup interactions
rerun only its Streamlit fragment. Existing ML functions and source files are never
modified by the chatbot. History is session-only; no database is used.
```

```powershell
git add .gitignore pyproject.toml README.md src
git commit -m "chore: scaffold f1buddy Python package"
```

## Task 2: Implement the snapshot repository

**Files:**
- Create: `src/f1buddy_ai/data/snapshots.py`
- Create: `tests/test_snapshots.py`
- Create: `tests/fixtures/public_data/stats.json`
- Create: `tests/fixtures/public_data/metrics.json`
- Create: `tests/fixtures/public_data/next_race_prediction.json`

- [ ] **Step 1: Create minimal fixture data**

These fixtures are synthetic test data, not real race results, and are created only in the new package.

Create `tests/fixtures/public_data/stats.json`:

```json
{"season":"2026","updatedAt":"2026-11-03T15:00:00Z","drivers":[{"position":1,"code":"NOR","givenName":"Lando","familyName":"Norris","constructorName":"McLaren","points":300,"wins":5},{"position":2,"code":"PIA","givenName":"Oscar","familyName":"Piastri","constructorName":"McLaren","points":290,"wins":4}],"constructors":[{"position":1,"constructorId":"mclaren","name":"McLaren","points":590,"wins":9},{"position":2,"constructorId":"red_bull","name":"Red Bull","points":400,"wins":3}]}
```

Create `tests/fixtures/public_data/metrics.json`:

```json
{"podium":{"rocAuc":0.82,"top1Accuracy":0.6,"top3Accuracy":0.7,"testRows":100}}
```

Create `tests/fixtures/public_data/next_race_prediction.json`:

```json
{"asof":"2026-11-03","race":{"name":"São Paulo Grand Prix","season":2026,"round":21,"date":"2026-11-08","raceStartUtc":"2026-11-08T17:00:00Z"},"forecast":{"preQualifyingPodium":[{"code":"NOR","driverName":"Lando Norris","team":"McLaren","podiumProbability":0.42},{"code":"PIA","driverName":"Oscar Piastri","team":"McLaren","podiumProbability":0.35},{"code":"VER","driverName":"Max Verstappen","team":"Red Bull","podiumProbability":0.3}],"realGridPodium":[{"code":"VER","driverName":"Max Verstappen","team":"Red Bull","podiumProbability":0.8}],"hasRealGrid":true}}
```

- [ ] **Step 2: Write snapshot repository tests**

Create `tests/test_snapshots.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from f1buddy_ai.data.snapshots import SnapshotRepository

FIXTURES = Path(__file__).parent / "fixtures" / "public_data"


def test_repository_reads_next_race_and_prediction():
    repository = SnapshotRepository(FIXTURES)

    race = repository.next_race()
    podium = repository.current_prediction()

    assert race.name == "São Paulo Grand Prix"
    assert race.round == 21
    assert [entry.code for entry in podium[:3]] == ["NOR", "PIA", "VER"]


def test_repository_adds_positions_to_ordered_standings():
    repository = SnapshotRepository(FIXTURES)

    assert repository.driver_standings()[0].position == 1
    assert repository.constructor_standings()[1].position == 2


def test_repository_uses_real_grid_only_when_requested():
    repository = SnapshotRepository(FIXTURES)
    assert repository.current_prediction(use_real_grid=True)[0].code == "VER"


def test_repository_raises_for_missing_file(tmp_path):
    repository = SnapshotRepository(tmp_path)

    with pytest.raises(FileNotFoundError):
        repository.next_race()


def test_repository_rejects_invalid_prediction(tmp_path):
    (tmp_path / "next_race_prediction.json").write_text(
        '{"race": {"name": "X"}, "forecast": {"preQualifyingPodium": []}}',
        encoding="utf-8",
    )
    repository = SnapshotRepository(tmp_path)

    with pytest.raises(ValidationError):
        repository.next_race()
```

- [ ] **Step 3: Run tests and confirm the missing module failure**

```powershell
python -m pytest tests/test_snapshots.py -v
```

Expected: collection fails because `f1buddy_ai.data.snapshots` does not exist.

- [ ] **Step 4: Implement the repository**

Create `src/f1buddy_ai/data/snapshots.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from f1buddy_ai.models import (
    ConstructorStanding,
    DriverStanding,
    ModelPerformance,
    PodiumPrediction,
    RaceInfo,
)


class SnapshotRepository:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def _read(self, name: str):
        path = self.data_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def generated_at(self) -> datetime | None:
        value = self._read("next_race_prediction.json").get("generatedAt")
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None

    def prediction_as_of(self) -> str:
        return self._read("next_race_prediction.json")["asof"]

    def standings_timestamp(self) -> datetime:
        return datetime.fromisoformat(self._read("stats.json")["updatedAt"].replace("Z", "+00:00"))

    def next_race(self) -> RaceInfo:
        return RaceInfo.model_validate(self._read("next_race_prediction.json")["race"])

    def driver_standings(self) -> list[DriverStanding]:
        rows = self._read("stats.json")["drivers"]
        if not rows:
            raise ValueError("Empty driver standings")
        return [
            DriverStanding(
                position=int(row["position"]),
                code=row["code"],
                name=f'{row["givenName"]} {row["familyName"]}',
                team=row["constructorName"],
                points=row["points"],
                wins=row["wins"],
            )
            for row in sorted(rows, key=lambda r: int(r["position"]))
        ]

    def constructor_standings(self) -> list[ConstructorStanding]:
        rows = self._read("stats.json")["constructors"]
        if not rows:
            raise ValueError("Empty constructor standings")
        return [
            ConstructorStanding(position=int(row["position"]), id=row["constructorId"],
                                name=row["name"], points=row["points"], wins=row["wins"])
            for row in sorted(rows, key=lambda r: int(r["position"]))
        ]

    def current_prediction(self, use_real_grid: bool = False) -> list[PodiumPrediction]:
        payload = self._read("next_race_prediction.json")
        forecast = payload["forecast"]
        rows = (forecast.get("realGridPodium") if use_real_grid
                else forecast["preQualifyingPodium"])
        if not rows:
            raise ValueError("Requested prediction mode unavailable")
        return [PodiumPrediction.model_validate(row) for row in rows]

    def model_performance(self) -> ModelPerformance:
        podium = self._read("metrics.json")["podium"]
        return ModelPerformance(
            roc_auc=podium["rocAuc"],
            top1_accuracy=podium["top1Accuracy"],
            top3_accuracy=podium["top3Accuracy"],
            test_rows=podium["testRows"],
        )
```

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/test_snapshots.py -v
git add src/f1buddy_ai/data/snapshots.py tests
git commit -m "feat: read validated Formula 1 snapshots"
```

Expected: all snapshot tests pass.

## Task 3: Implement the guarded Jolpica fallback

**Files:**
- Create: `src/f1buddy_ai/data/jolpica.py`
- Create: `tests/test_jolpica.py`

- [ ] **Step 1: Write fallback-client tests**

Create `tests/test_jolpica.py`:

```python
import pytest
import requests
import responses
from f1buddy_ai.data.jolpica import JolpicaClient, JolpicaUnavailable

URL = "https://api.jolpi.ca/ergast/f1/2026/driverstandings/?limit=100"
PAYLOAD = {"MRData": {"StandingsTable": {"StandingsLists": [{
    "DriverStandings": [{"position": "1", "points": "300", "wins": "5",
        "Driver": {"driverId": "norris", "code": "NOR", "givenName": "Lando",
                   "familyName": "Norris"},
        "Constructors": [{"name": "McLaren"}]}]
}]}}}


@responses.activate
def test_client_sets_user_agent_and_caches_standings():
    responses.get(URL, json=PAYLOAD)
    client = JolpicaClient(min_interval_seconds=0)
    rows = client.driver_standings(2026)
    assert rows[0].code == "NOR"
    assert responses.calls[0].request.headers["User-Agent"].startswith("f1buddy-ai/")
    client.driver_standings(2026)
    assert len(responses.calls) == 1


@responses.activate
def test_client_retries_429_then_returns_data(monkeypatch):
    monkeypatch.setattr("f1buddy_ai.data.jolpica.time.sleep", lambda seconds: None)
    responses.get(URL, status=429, headers={"Retry-After": "0"})
    responses.get(URL, json=PAYLOAD)
    client = JolpicaClient(min_interval_seconds=0, max_retries=2)
    rows = client.driver_standings(2026)
    assert rows[0].code == "NOR"
    assert len(responses.calls) == 2


@responses.activate
def test_client_rejects_empty_standings():
    responses.get(URL, json={"MRData": {"StandingsTable": {"StandingsLists": []}}})
    client = JolpicaClient(min_interval_seconds=0)
    with pytest.raises(JolpicaUnavailable):
        client.driver_standings(2026)


@responses.activate
def test_timeout_is_bounded_and_failure_is_cooled_down(monkeypatch):
    monkeypatch.setattr("f1buddy_ai.data.jolpica.time.sleep", lambda seconds: None)
    responses.get(URL, body=requests.Timeout("test"))
    client = JolpicaClient(min_interval_seconds=0, max_retries=2)
    for _ in range(2):
        with pytest.raises(JolpicaUnavailable):
            client.driver_standings(2026)
    assert len(responses.calls) == 2


@responses.activate
def test_hourly_budget_blocks_before_request():
    client = JolpicaClient(hourly_budget=0)
    with pytest.raises(JolpicaUnavailable):
        client.driver_standings(2026)
    assert len(responses.calls) == 0


@responses.activate
def test_long_retry_after_does_not_retry_early():
    responses.get(URL, status=429, headers={"Retry-After": "120"})
    client = JolpicaClient(min_interval_seconds=0)
    with pytest.raises(JolpicaUnavailable):
        client.driver_standings(2026)
    assert len(responses.calls) == 1


@responses.activate
def test_throttle_spaces_distinct_requests(monkeypatch):
    now = [100.0]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
    monkeypatch.setattr("f1buddy_ai.data.jolpica.time.monotonic", lambda: now[0])
    monkeypatch.setattr("f1buddy_ai.data.jolpica.time.sleep", sleep)
    responses.get(URL, json=PAYLOAD)
    other = "2025/driverstandings/?limit=100"
    responses.get(f"{JolpicaClient.BASE_URL}/{other}", json=PAYLOAD)
    client = JolpicaClient()
    client.driver_standings(2026)
    client._get(other)
    assert len(responses.calls) == 2
    assert sum(sleeps) >= 1.0


@responses.activate
def test_next_race_selects_by_date():
    from datetime import date
    responses.get(f"{JolpicaClient.BASE_URL}/2026/?limit=100", json={"MRData": {"RaceTable": {"Races": [
        {"season":"2026", "round":"1", "raceName":"Past race", "date":"2026-01-01", "Circuit":{}},
        {"season":"2026", "round":"2", "raceName":"Future race", "date":"2026-02-01", "time":"13:00:00Z", "Circuit":{}}
    ]}}})
    race = JolpicaClient(min_interval_seconds=0).next_race(date(2026, 1, 20))
    assert race.name == "Future race"
    assert race.raceStartUtc.hour == 13
```

All HTTP calls in this file are intercepted by `responses`; tests need no network.

- [ ] **Step 2: Run tests and confirm the missing module failure**

```powershell
python -m pytest tests/test_jolpica.py -v
```

Expected: collection fails because `f1buddy_ai.data.jolpica` does not exist.

- [ ] **Step 3: Implement the client with a conservative request gate**

Create `src/f1buddy_ai/data/jolpica.py` with:

```python
from __future__ import annotations

import time
import math
from collections import deque
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock

import requests

from f1buddy_ai.models import ConstructorStanding, DriverStanding, RaceInfo


class JolpicaUnavailable(RuntimeError):
    pass


class JolpicaClient:
    BASE_URL = "https://api.jolpi.ca/ergast/f1"

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        max_retries: int = 3,
        timeout_seconds: float = 5.0,
        hourly_budget: int = 60,
    ):
        self.min_interval_seconds = min_interval_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.hourly_budget = hourly_budget
        self._attempts = deque()
        self._cache = {}
        self._blocked_until = 0.0
        self._lock = Lock()
        self._last_request = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "f1buddy-ai/0.1.0"

    def _get(self, path: str) -> dict:
        with self._lock:
            now = time.monotonic()
            cached = self._cache.get(path)
            if cached and now - cached[0] < 900:
                return cached[1]
            if now < self._blocked_until:
                raise JolpicaUnavailable("Fallback cooling down")
            for attempt in range(self.max_retries):
                now = time.monotonic()
                while self._attempts and now - self._attempts[0] >= 3600:
                    self._attempts.popleft()
                if len(self._attempts) >= self.hourly_budget:
                    raise JolpicaUnavailable("Fallback hourly budget exhausted")
                time.sleep(max(0, self.min_interval_seconds - (now - self._last_request)))
                self._last_request = time.monotonic()
                self._attempts.append(self._last_request)
                wait = 2 ** attempt
                try:
                    response = self._session.get(
                        f"{self.BASE_URL}/{path}", timeout=self.timeout_seconds
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        raw_wait = response.headers.get("Retry-After")
                        if raw_wait:
                            try:
                                wait = float(raw_wait)
                            except ValueError:
                                try:
                                    wait = (parsedate_to_datetime(raw_wait) - datetime.now(timezone.utc)).total_seconds()
                                except (ValueError, TypeError, OverflowError):
                                    wait = 60
                            if not math.isfinite(wait):
                                wait = 60
                            wait = max(0, wait)
                        if wait > 8:
                            self._blocked_until = time.monotonic() + wait
                            raise JolpicaUnavailable("Server requested a longer cooldown")
                    else:
                        response.raise_for_status()
                        payload = response.json()
                        self._cache[path] = (time.monotonic(), payload)
                        return payload
                except requests.RequestException:
                    pass
                if attempt + 1 < self.max_retries:
                    time.sleep(wait)
            self._blocked_until = time.monotonic() + 60
            raise JolpicaUnavailable("Fallback attempts exhausted")

    def driver_standings(self, season: int) -> list[DriverStanding]:
        payload = self._get(f"{season}/driverstandings/?limit=100")
        lists = payload["MRData"].get("StandingsTable", {}).get("StandingsLists", [])
        rows = lists[0].get("DriverStandings", []) if lists else []
        if not rows:
            raise JolpicaUnavailable("Jolpica returned no driver standings")
        return [
            DriverStanding(
                position=int(row["position"]),
                code=row["Driver"].get("code", row["Driver"]["driverId"][:3].upper()),
                name=f'{row["Driver"]["givenName"]} {row["Driver"]["familyName"]}',
                team=row.get("Constructors", [{}])[0].get("name", "Unknown"),
                points=float(row["points"]),
                wins=int(row["wins"]),
            )
            for row in rows
        ]

    def constructor_standings(self, season: int) -> list[ConstructorStanding]:
        payload = self._get(f"{season}/constructorstandings/?limit=100")
        lists = payload["MRData"].get("StandingsTable", {}).get("StandingsLists", [])
        rows = lists[0].get("ConstructorStandings", []) if lists else []
        if not rows:
            raise JolpicaUnavailable("Jolpica returned no constructor standings")
        return [
            ConstructorStanding(
                position=int(row["position"]),
                id=row["Constructor"]["constructorId"],
                name=row["Constructor"]["name"],
                points=float(row["points"]),
                wins=int(row["wins"]),
            )
            for row in rows
        ]

    def next_race(self, as_of: date) -> RaceInfo:
        payload = self._get(f"{as_of.year}/?limit=100")
        rows = payload["MRData"].get("RaceTable", {}).get("Races", [])
        rows = sorted((row for row in rows if date.fromisoformat(row["date"]) >= as_of),
                      key=lambda row: row["date"])
        if not rows:
            raise JolpicaUnavailable("Jolpica returned no next race")
        row = rows[0]
        start = None
        if row.get("date") and row.get("time"):
            start = f'{row["date"]}T{row["time"]}'
        return RaceInfo(
            name=row["raceName"],
            season=int(row["season"]),
            round=int(row["round"]),
            country=row["Circuit"].get("Location", {}).get("country"),
            date=date.fromisoformat(row["date"]),
            raceStartUtc=start,
            qualifyingDate=row.get("Qualifying", {}).get("date"),
            sessions={
                label: f'{session["date"]}T{session["time"]}'
                for key, label in (("FirstPractice", "firstPractice"),
                                   ("SecondPractice", "secondPractice"),
                                   ("ThirdPractice", "thirdPractice"),
                                   ("Qualifying", "qualifying"),
                                   ("Sprint", "sprint"),
                                   ("SprintQualifying", "sprintQualifying"))
                if (session := row.get(key)) and session.get("date") and session.get("time")
            },
        )
```

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/test_jolpica.py -v
git add src/f1buddy_ai/data/jolpica.py tests/test_jolpica.py
git commit -m "feat: add rate-limited Jolpica fallback"
```

Expected: retry, parsing, and empty-data tests pass without network access.

Policy: 15-minute cache, at least one second between requests, three total attempts,
60 attempted requests/hour for this chatbot process, and a cooldown after failures.
The singleton in Task 6 preserves these across Streamlit reruns. This is an
application budget, not Jolpica's published allowance. Existing host refresh jobs
and other processes have separate traffic; deployment verification must consider
their combined usage. These process-local guards are sufficient for the one-process
POC, not a distributed rate limiter.

## Task 4: Build the static-first F1 data service

**Files:**
- Create: `src/f1buddy_ai/services/f1_data.py`
- Create: `tests/test_f1_data.py`

- [ ] **Step 1: Write source-priority and consistency tests**

Create `tests/test_f1_data.py` with an isolated fixture copy and a network spy:

```python
from datetime import date
from pathlib import Path
from shutil import copytree
import pytest
from f1buddy_ai.data.snapshots import SnapshotRepository
from f1buddy_ai.models import HostContext, RaceInfo, DriverStanding
from f1buddy_ai.services.f1_data import F1DataService, DataUnavailable


class FakeJolpica:
    def __init__(self):
        self.calls = []

    def driver_standings(self, season):
        self.calls.append(("drivers", season))
        return [DriverStanding(position=1, code="NOR", name="Lando Norris",
                               team="McLaren", points=300, wins=5)]


@pytest.fixture
def components(tmp_path):
    copytree(Path(__file__).parent / "fixtures" / "public_data", tmp_path / "data")
    repository = SnapshotRepository(tmp_path / "data")
    jolpica = FakeJolpica()
    return F1DataService(repository, jolpica), repository, jolpica


def test_host_race_wins_over_snapshot_and_network(components):
    service, repository, jolpica = components
    context = HostContext(as_of_date=date(2026, 11, 3), current_race=RaceInfo(
        name="Host race", season=2026, round=22, date=date(2026, 11, 15)))
    result = service.next_race(context)
    assert result.data.name == "Host race"
    assert result.source == "streamlit-page"
    assert jolpica.calls == []


def test_snapshot_is_used_before_jolpica(components):
    service, repository, jolpica = components
    result = service.driver_standings(2026)
    assert result.source == "formula1-newbie"
    assert jolpica.calls == []


def test_missing_snapshot_falls_back_to_jolpica(components):
    service, repository, jolpica = components
    (repository.data_dir / "stats.json").unlink()
    result = service.driver_standings(2026)
    assert result.source == "jolpica"


def test_prediction_failure_returns_data_unavailable(components):
    service, repository, jolpica = components
    (repository.data_dir / "next_race_prediction.json").unlink()
    with pytest.raises(DataUnavailable):
        service.current_prediction(HostContext(as_of_date=date(2026, 11, 3)))


def test_snapshot_prediction_is_rejected_for_different_date(components):
    service, repository, jolpica = components
    with pytest.raises(DataUnavailable):
        service.current_prediction(HostContext(as_of_date=date(2026, 11, 4)))


def test_host_prediction_wins_even_when_snapshot_date_differs(components):
    service, repository, jolpica = components
    rows = repository.current_prediction(use_real_grid=True)
    context = HostContext(as_of_date=date(2026, 11, 4), has_real_grid=True,
                          current_prediction=rows)
    assert service.current_prediction(context).data[0].code == "VER"
    assert jolpica.calls == []
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

```powershell
python -m pytest tests/test_f1_data.py -v
```

Expected: collection fails because `f1buddy_ai.services.f1_data` does not exist.

- [ ] **Step 3: Implement static-first behavior**

Create `src/f1buddy_ai/services/f1_data.py`:

```python
from __future__ import annotations

from f1buddy_ai.data.jolpica import JolpicaClient
from f1buddy_ai.data.snapshots import SnapshotRepository
from f1buddy_ai.models import DataResult, HostContext


class DataUnavailable(RuntimeError):
    pass


class F1DataService:
    def __init__(self, repository: SnapshotRepository, jolpica: JolpicaClient):
        self.repository = repository
        self.jolpica = jolpica

    def _generated_at(self):
        try:
            return self.repository.generated_at()
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def next_race(self, context: HostContext):
        if context.current_race is not None:
            return DataResult(data=context.current_race, source="streamlit-page")
        try:
            race = self.repository.next_race()
            if race.date < context.as_of_date or self.repository.prediction_as_of() != context.as_of_date.isoformat():
                raise ValueError("Snapshot does not match selected date")
            return DataResult(
                data=race,
                source="formula1-newbie",
                generated_at=self._generated_at(),
            )
        except (FileNotFoundError, KeyError, ValueError):
            return DataResult(
                data=self.jolpica.next_race(context.as_of_date), source="jolpica"
            )

    def driver_standings(self, season: int):
        try:
            return DataResult(
                data=self.repository.driver_standings(),
                source="formula1-newbie",
                generated_at=self.repository.standings_timestamp(),
            )
        except (FileNotFoundError, KeyError, ValueError):
            return DataResult(data=self.jolpica.driver_standings(season), source="jolpica")

    def constructor_standings(self, season: int):
        try:
            return DataResult(
                data=self.repository.constructor_standings(),
                source="formula1-newbie",
                generated_at=self.repository.standings_timestamp(),
            )
        except (FileNotFoundError, KeyError, ValueError):
            return DataResult(
                data=self.jolpica.constructor_standings(season), source="jolpica"
            )

    def current_prediction(self, context: HostContext):
        if context.current_prediction is not None:
            if not context.current_prediction:
                raise DataUnavailable("Empty host prediction")
            return DataResult(data=context.current_prediction, source="streamlit-page")
        try:
            if self.repository.prediction_as_of() != context.as_of_date.isoformat():
                raise ValueError("Snapshot does not match selected date")
            race = self.repository.next_race()
            if context.current_race and (race.season, race.round) != (
                context.current_race.season, context.current_race.round
            ):
                raise ValueError("Snapshot does not match displayed race")
            return DataResult(
                data=self.repository.current_prediction(use_real_grid=context.has_real_grid),
                source="formula1-newbie",
                generated_at=self._generated_at(),
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise DataUnavailable("Current prediction is unavailable") from exc

    def model_performance(self):
        try:
            return DataResult(
                data=self.repository.model_performance(),
                source="formula1-newbie",
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise DataUnavailable("Model performance is unavailable") from exc
```

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/test_f1_data.py -v
git add src/f1buddy_ai/services/f1_data.py tests/test_f1_data.py
git commit -m "feat: add static-first F1 data service"
```

## Task 5: Implement deterministic intents and response formatting

**Files:**
- Create: `src/f1buddy_ai/chat/intents.py`
- Create: `src/f1buddy_ai/chat/engine.py`
- Create: `tests/test_intents.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write intent tests**

Create `tests/test_intents.py`:

```python
import pytest

from f1buddy_ai.chat.intents import Intent, recognize_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("When is the next race?", Intent.NEXT_RACE),
        ("show the driver championship", Intent.DRIVER_STANDINGS),
        ("constructor standings", Intent.CONSTRUCTOR_STANDINGS),
        ("who is predicted to win?", Intent.CURRENT_PREDICTION),
        ("how accurate is the model?", Intent.MODEL_PERFORMANCE),
        ("what can you do?", Intent.HELP),
        ("why is Ferrari slow?", Intent.HELP),
    ],
)
def test_recognize_intent(message, expected):
    assert recognize_intent(message) is expected


def test_constructor_words_take_priority_over_generic_standings():
    assert recognize_intent("team championship standings") is Intent.CONSTRUCTOR_STANDINGS
```

- [ ] **Step 2: Implement ordered, deterministic recognition**

Create `src/f1buddy_ai/chat/intents.py`:

```python
from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    NEXT_RACE = "next_race"
    DRIVER_STANDINGS = "driver_standings"
    CONSTRUCTOR_STANDINGS = "constructor_standings"
    CURRENT_PREDICTION = "current_prediction"
    MODEL_PERFORMANCE = "model_performance"
    HELP = "help"


def _normalise(message: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", message.lower()).split())


def is_help_request(message: str) -> bool:
    return _normalise(message) in {"", "help", "menu", "what can you do", "commands", "hi", "hello"}


def recognize_intent(message: str) -> Intent:
    text = _normalise(message)
    if is_help_request(message):
        return Intent.HELP
    if any(word in text for word in ("accuracy", "accurate", "performance", "roc auc", "top 3")):
        return Intent.MODEL_PERFORMANCE
    if any(word in text for word in ("constructor", "constructors", "team standings", "team championship")):
        return Intent.CONSTRUCTOR_STANDINGS
    if re.search(r"\b(prediction|predicted|predict|win|podium)\b", text):
        return Intent.CURRENT_PREDICTION
    if any(word in text for word in ("driver standings", "driver championship", "standings", "championship")):
        return Intent.DRIVER_STANDINGS
    if any(word in text for word in ("next race", "schedule", "when is", "grand prix")):
        return Intent.NEXT_RACE
    return Intent.HELP
```

- [ ] **Step 3: Run intent tests**

```powershell
python -m pytest tests/test_intents.py -v
```

Expected: all intent cases pass.

- [ ] **Step 4: Write engine tests for exact behavior**

Create `tests/test_engine.py` using the deterministic local fixtures:

```python
from datetime import date
from pathlib import Path
import pytest
from f1buddy_ai.chat.engine import ChatEngine
from f1buddy_ai.data.snapshots import SnapshotRepository
from f1buddy_ai.models import HostContext
from f1buddy_ai.services.f1_data import F1DataService, DataUnavailable


@pytest.fixture
def engine():
    repository = SnapshotRepository(Path(__file__).parent / "fixtures" / "public_data")
    # No HTTP client: any unexpected fallback fails this fixture.
    return ChatEngine(F1DataService(repository, None),
                      HostContext(as_of_date=date(2026, 11, 3)))


def test_help_returns_five_quick_actions(engine):
    reply = engine.respond("help")
    assert reply.intent == "help"
    assert [option.command for option in reply.options] == [
        "next race",
        "driver standings",
        "constructor standings",
        "current prediction",
        "model performance",
    ]


def test_prediction_formats_top_three_as_percentages(engine):
    reply = engine.respond("who will win?")
    assert "Lando Norris — 42.0%" in reply.text
    assert "Oscar Piastri — 35.0%" in reply.text


def test_unsupported_question_explains_phase_one_limit(engine):
    reply = engine.respond("Why is Ferrari slow this year?")
    assert "Phase 1" in reply.text
    assert reply.options


def test_data_failure_returns_helpful_reply(engine, monkeypatch):
    def fail():
        raise DataUnavailable("private implementation detail")
    monkeypatch.setattr(engine.service, "model_performance", fail)
    reply = engine.respond("model performance")
    assert "temporarily unavailable" in reply.text.lower()
    assert "private implementation detail" not in reply.text


@pytest.mark.parametrize("command", ["next race", "driver standings", "constructor standings", "model performance"])
def test_data_intents_return_source_and_nonempty_text(engine, command):
    reply = engine.respond(command)
    assert reply.text
    assert reply.metadata["source"] == "formula1-newbie"
```

- [ ] **Step 5: Implement the chat engine**

Create `src/f1buddy_ai/chat/engine.py`:

```python
from datetime import date
import requests
from f1buddy_ai.chat.intents import Intent, recognize_intent, is_help_request
from f1buddy_ai.data.jolpica import JolpicaUnavailable
from f1buddy_ai.models import ChatOption, ChatReply, HostContext
from f1buddy_ai.services.f1_data import F1DataService, DataUnavailable

QUICK_ACTIONS = [
    ChatOption(label="🏁 Next race", command="next race"),
    ChatOption(label="🏎️ Driver standings", command="driver standings"),
    ChatOption(label="🏆 Constructor standings", command="constructor standings"),
    ChatOption(label="🔮 Current prediction", command="current prediction"),
    ChatOption(label="📊 Model performance", command="model performance"),
]


class ChatEngine:
    def __init__(self, service: F1DataService, context: HostContext):
        self.service = service
        self.context = context

    def respond(self, message: str) -> ChatReply:
        intent = recognize_intent(message)
        if intent == Intent.HELP:
            prefix = ("Hi! I'm F1 Buddy. " if is_help_request(message)
                      else "I can't analyse open-ended F1 questions in Phase 1. ")
            return ChatReply(text=prefix + "I can show the next race, standings, the current prediction, or model performance. Choose an option below.",
                             intent=intent.value, options=QUICK_ACTIONS)
        try:
            if intent == Intent.NEXT_RACE:
                result = self.service.next_race(self.context)
                race = result.data
                text = f"{race.name} — round {race.round}, {race.season}\n\nRace date: {race.date.isoformat()}"
                if race.raceStartUtc:
                    text += f"\n\nStart: {race.raceStartUtc.isoformat()} (UTC)"
                else:
                    text += "\n\nExact start time is not available in this saved data."
                for name, start in race.sessions.items():
                    if start:
                        text += f"\n\n{name}: {start.isoformat()} (UTC)"
            elif intent == Intent.DRIVER_STANDINGS:
                result = self.service.driver_standings(date.today().year)
                text = "Latest saved driver standings (not historical standings for the selected date):\n\n"
                text += "\n\n".join(f"{r.position}. {r.name} — {r.points:g} points" for r in result.data[:10])
            elif intent == Intent.CONSTRUCTOR_STANDINGS:
                result = self.service.constructor_standings(date.today().year)
                text = "Latest saved constructor standings (not historical standings for the selected date):\n\n"
                text += "\n\n".join(f"{r.position}. {r.name} — {r.points:g} points" for r in result.data[:10])
            elif intent == Intent.CURRENT_PREDICTION:
                result = self.service.current_prediction(self.context)
                mode = "real qualifying grid" if self.context.has_real_grid else "predicted qualifying grid"
                text = f"Podium probabilities using the {mode}:\n\n"
                text += "\n\n".join(f"{r.driverName} — {r.podiumProbability:.1%}" for r in result.data[:3])
                text += "\n\nThese estimate a top-three finish, not a race win. They are model estimates, not guarantees."
            else:
                result = self.service.model_performance()
                metrics = result.data
                text = (f"Saved offline model evaluation (separate from the live accuracy panel):\n\n"
                        f"ROC AUC: {metrics.roc_auc:.3f}\n\n"
                        f"Top-one accuracy: {metrics.top1_accuracy:.1%}\n\n"
                        f"Top-three accuracy: {metrics.top3_accuracy:.1%}\n\n"
                        f"Test driver-race rows: {metrics.test_rows}")
            text += f"\n\nSource: {result.source}."
            if result.generated_at:
                label = "Standings updated" if intent in (Intent.DRIVER_STANDINGS, Intent.CONSTRUCTOR_STANDINGS) else "Prediction snapshot generated"
                text += f" {label}: {result.generated_at.isoformat()}."
            return ChatReply(text=text, intent=intent.value,
                             metadata={"source": result.source})
        except (DataUnavailable, JolpicaUnavailable, requests.RequestException,
                OSError, KeyError, ValueError, TypeError):
            return ChatReply(text="That data is temporarily unavailable. Please try again later or choose another option.",
                             intent=intent.value, options=QUICK_ACTIONS)
```

- [ ] **Step 6: Run all chat tests and commit**

```powershell
python -m pytest tests/test_intents.py tests/test_engine.py -v
git add src/f1buddy_ai/chat tests/test_intents.py tests/test_engine.py
git commit -m "feat: add deterministic F1 chat engine"
```

## Task 6: Build the copy-only display adapter and isolated popup

**Files (new package only):**
- Create: `src/f1buddy_ai/ui/adapter.py`
- Create: `src/f1buddy_ai/ui/streamlit.py`
- Modify: `src/f1buddy_ai/__init__.py`
- Create: `tests/test_adapter.py`
- Create: `tests/test_public_api.py`
- Create: `examples/streamlit_demo.py`

- [ ] **Step 1: Write the display-adapter tests**

Create `tests/test_adapter.py`:

```python
from copy import deepcopy
from datetime import date

from f1buddy_ai.ui.adapter import context_from_display


def test_adapter_copies_displayed_prediction_without_mutating_input():
    race = {
        "name": "Fixture GP", "round": 7, "race": "2026-05-17",
        "quali": "2026-05-16",
        "podium": [("NOR", "MCL", 42), ("PIA", "MCL", 35)],
        "podium_real": [("VER", "RBR", 80), ("NOR", "MCL", 55)],
    }
    drivers = {"NOR": "Norris", "PIA": "Piastri", "VER": "Verstappen"}
    teams = {"MCL": "McLaren", "RBR": "Red Bull"}
    before = deepcopy((race, drivers, teams))
    context = context_from_display(
        as_of_date=date(2026, 5, 17), displayed_race=race,
        has_real_grid=True, driver_names=drivers, team_names=teams,
    )
    assert context.current_race.name == "Fixture GP"
    assert context.current_race.date == date(2026, 5, 17)
    assert [r.code for r in context.current_prediction] == ["VER", "NOR"]
    assert [round(r.podiumProbability * 100) for r in context.current_prediction] == [80, 55]
    assert (race, drivers, teams) == before
    context.current_prediction[0].driverName = "Changed copy"
    assert (race, drivers, teams) == before


def test_adapter_uses_existing_prequalifying_rows():
    context = context_from_display(
        as_of_date=date(2026, 5, 15),
        displayed_race={"name": "Fixture GP", "round": 7, "race": "2026-05-17",
                        "quali": "2026-05-16", "podium": [("NOR", "MCL", 42)]},
        has_real_grid=False, driver_names={}, team_names={},
    )
    assert context.current_prediction[0].podiumProbability == 0.42
    assert context.has_real_grid is False
```

- [ ] **Step 2: Confirm the initial failure**

Run `python -m pytest tests/test_adapter.py -v`.
Expected: collection fails because `f1buddy_ai.ui.adapter` does not exist.

- [ ] **Step 3: Implement the adapter without touching the host's resolve function**

Create `src/f1buddy_ai/ui/adapter.py`:

```python
from datetime import date
from collections.abc import Mapping

from f1buddy_ai.models import HostContext, RaceInfo, PodiumPrediction


def context_from_display(
    *, as_of_date: date, displayed_race: Mapping | None,
    has_real_grid: bool, driver_names: Mapping[str, str],
    team_names: Mapping[str, str],
) -> HostContext:
    if displayed_race is None:
        return HostContext(as_of_date=as_of_date)
    race_date = date.fromisoformat(displayed_race["race"])
    # Exactly the same row choice already used by the host's podium_html().
    using_real = has_real_grid and "podium_real" in displayed_race
    rows = displayed_race["podium_real"] if using_real else displayed_race["podium"]
    prediction = [
        PodiumPrediction(
            code=code, driverName=driver_names.get(code, code),
            team=team_names.get(team, team),
            # Convert display units only; do not recompute or normalize the model.
            podiumProbability=float(display_percent) / 100,
        )
        for code, team, display_percent in rows
    ]
    return HostContext(
        as_of_date=as_of_date,
        current_race=RaceInfo(
            name=displayed_race["name"], season=race_date.year,
            round=displayed_race["round"], date=race_date,
            qualifyingDate=displayed_race.get("quali"),
        ),
        has_real_grid=using_real,
        current_prediction=prediction,
    )
```

Run `python -m pytest tests/test_adapter.py -v`. Expected: both tests pass.

- [ ] **Step 4: Implement the fragment-scoped popup**

Create `src/f1buddy_ai/ui/streamlit.py`:

```python
from datetime import date
from pathlib import Path
from collections.abc import Mapping

import streamlit as st

from f1buddy_ai.chat.engine import ChatEngine, QUICK_ACTIONS
from f1buddy_ai.data.jolpica import JolpicaClient
from f1buddy_ai.data.snapshots import SnapshotRepository
from f1buddy_ai.services.f1_data import F1DataService
from f1buddy_ai.ui.adapter import context_from_display


@st.cache_resource
def _jolpica_client() -> JolpicaClient:
    # A separate client: never reuse or clear the prediction application's cache.
    return JolpicaClient()


@st.fragment
def render_chatbot(
    *, data_dir: str | Path, as_of_date: date,
    displayed_race: Mapping | None, has_real_grid: bool,
    driver_names: Mapping[str, str], team_names: Mapping[str, str],
    state_key: str = "f1buddy",
) -> None:
    try:
        context = context_from_display(
            as_of_date=as_of_date, displayed_race=displayed_race,
            has_real_grid=has_real_grid, driver_names=driver_names,
            team_names=team_names,
        )
    except (KeyError, ValueError, TypeError):
        with st.popover("💬 Ask F1 Buddy"):
            st.info("The displayed prediction is unavailable to the chatbot.")
        return
    engine = ChatEngine(
        F1DataService(SnapshotRepository(data_dir), _jolpica_client()), context
    )
    history_key = f"{state_key}_messages"
    context_key = f"{state_key}_context"
    fingerprint = context.model_dump_json()
    if st.session_state.get(context_key) != fingerprint or history_key not in st.session_state:
        st.session_state[context_key] = fingerprint
        st.session_state[history_key] = [
            {"role": "assistant", "content": engine.respond("help").text}
        ]
    command = None
    with st.popover("💬 Ask F1 Buddy"):
        st.caption("Existing F1 data and the prediction currently on this page.")
        for message in st.session_state[history_key]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        columns = st.columns(2)
        for index, option in enumerate(QUICK_ACTIONS):
            if columns[index % 2].button(option.label, key=f"{state_key}_{index}"):
                command = option.command
        with st.form(f"{state_key}_form", clear_on_submit=True):
            typed = st.text_input("Ask about F1", max_chars=500)
            submitted = st.form_submit_button("Send")
        if submitted and typed.strip():
            command = typed.strip()
    if command:
        reply = engine.respond(command)
        st.session_state[history_key] = (st.session_state[history_key] + [
            {"role": "user", "content": command},
            {"role": "assistant", "content": reply.text},
        ])[-20:]
        st.rerun(scope="fragment")
```

Opening/submitting the popup must not call `resolve()`, `forecast()`, `retrain_live()`, or `refresh_season_data()`. Do not replace the fragment rerun with an app-wide rerun.

- [ ] **Step 5: Export the public API**

Replace `src/f1buddy_ai/__init__.py` with:

```python
from f1buddy_ai.models import HostContext
from f1buddy_ai.ui.streamlit import render_chatbot

__all__ = ["HostContext", "render_chatbot"]
```

Create `tests/test_public_api.py`:

```python
from f1buddy_ai import render_chatbot


def test_render_chatbot_is_public():
    assert callable(render_chatbot)
```

Run `python -m pytest tests/test_public_api.py tests/test_adapter.py -v`.
Expected: imports work and the adapter tests pass.

- [ ] **Step 6: Create the synthetic demo**

Create `examples/streamlit_demo.py`:

```python
from datetime import date
from pathlib import Path

import streamlit as st

from f1buddy_ai import render_chatbot

st.title("F1 Buddy — synthetic fixture demo")
st.session_state["demo_page_runs"] = st.session_state.get("demo_page_runs", 0) + 1
st.caption(f"Full-page runs: {st.session_state['demo_page_runs']}")
render_chatbot(
    data_dir=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "public_data",
    as_of_date=date(2026, 11, 3),
    displayed_race={
        "name": "São Paulo Grand Prix", "round": 21, "race": "2026-11-08",
        "quali": "2026-11-07",
        "podium": [("NOR", "MCL", 42), ("PIA", "MCL", 35), ("VER", "RBR", 30)],
    },
    has_real_grid=False,
    driver_names={"NOR": "Norris", "PIA": "Piastri", "VER": "Verstappen"},
    team_names={"MCL": "McLaren", "RBR": "Red Bull"},
)
```

- [ ] **Step 7: Verify the popup and fragment isolation**

```powershell
python -m pytest -v
streamlit run examples/streamlit_demo.py
```

Expected: welcome text, five buttons, typed questions, help fallback and 20-message cap work. The demo's full-page run counter stays unchanged while chatting. A hard browser reload may reset the session. Changing the page's selected forecast resets chat history.

- [ ] **Step 8: Commit only new-package code**

```powershell
git add src/f1buddy_ai/ui src/f1buddy_ai/__init__.py examples tests/test_adapter.py tests/test_public_api.py
git commit -m "feat: add read-only F1 Buddy popup"
```

## Task 7: Add the minimal host integration

**Only existing-repository files in this task:**
- Modify: `streamlit_app/app.py`
- Modify on release: `streamlit_app/requirements.txt`
- Modify: `streamlit_app/README.md`

- [ ] **Step 1: Record the existing state**

In `Formula1`:

```powershell
git branch --show-current
git diff --name-only
git diff --name-only -- ml web .github
git ls-files --others --exclude-standard -- ml web .github
```

Expected branch: `feature2`. Record pre-existing edits and untracked files so they are not mistaken for chatbot changes or removed. The current plan does not authorize any edits under those protected paths.

- [ ] **Step 2: Install the sibling package locally**

```powershell
python -m pip install -e ../f1buddy-ai
python -c "import streamlit as st; import f1buddy_ai; print(st.__version__); print(f1buddy_ai.__file__)"
```

Expected: Streamlit supports `fragment` and the package path points to the sibling repository. The inspected environment already has Streamlit 1.54.0. If another environment is older than 1.37, use the package's declared dependency; do not work around the missing fragment by rerunning the full app.

- [ ] **Step 3: Add one import near the existing imports**

In `streamlit_app/app.py`:

```python
try:
    from f1buddy_ai import render_chatbot
except ImportError:
    render_chatbot = None
```

Do not change any existing imports from the prediction engine, or any existing function body.

- [ ] **Step 4: Append the rendering call after the existing results**

Append after the existing final `st.html(DISCLAIMER_HTML)`:

```python
if render_chatbot is not None:
    render_chatbot(
        data_dir=ML_DIR.parent / "web" / "public" / "data",
        as_of_date=as_of,
        displayed_race=race,
        has_real_grid=is_real,
        driver_names=dict(DRIVERS),
        team_names={code: details[0] for code, details in TEAMS.items()},
    )
else:
    st.caption("F1 Buddy is not installed in this environment.")
```

This consumes the `race` and `is_real` values that the page has already computed.
Do not add calls to `resolve()` or `_run_forecast()`, change their return values, add
fields to their dictionaries, or change `podium_html()`.

- [ ] **Step 5: Document the integration**

Append to `streamlit_app/README.md`:

```markdown
## F1 Buddy popup

F1 Buddy is a free, rule-based chatbot that reads the prediction already displayed
on this page. It supports next-race details, latest saved standings, the displayed
podium prediction, saved offline model evaluation, and help.

Local setup, from the repository root:
`python -m pip install -e ../f1buddy-ai`

The chatbot never runs or changes the ML engine, strategy, models, datasets,
prediction calculations, refresh logic, or export workflows. Existing JSON is
read-only. Missing schedule/standings and historical qualifying/race results can
use a separate cached Jolpica GET client. Missing prediction stages are stated
explicitly; historical queries then show actual results separately if available.
Missing model metrics remain unavailable.

Chat interactions run in a Streamlit fragment. They do not rerun the prediction
page. Session history is capped at 20 messages and resets when the displayed
forecast changes. No database, AI key, RAG, or notification scheduler is used.
```

- [ ] **Step 6: Verify the integration without running refresh jobs**

```powershell
git diff -- streamlit_app/app.py
git diff -- ml web .github
streamlit run streamlit_app/app.py
```

Expected host-code diff: the import block and rendering call only. The protected
paths have no new changes relative to the recorded initial state.

After the website has loaded normally, chat using each quick action. Confirm
that race name, date, prediction order and percentages match the existing page,
and that no training/refresh spinner starts because of a chatbot action. Verify
the standalone demo's full-page counter stays fixed during chat. Do not press RUN,
start a refresh workflow, or regenerate outputs as a chatbot verification step.

- [ ] **Step 7: Record the release dependency when available**

For hosted deployment, after the user authorizes the package repository destination
and visibility and the tested release exists, add this line to
`streamlit_app/requirements.txt`:

```text
f1buddy-ai @ git+https://github.com/Chloephmm/f1buddy-ai.git@v0.1.0
```

Do not add an unresolvable URL. Until publication is authorized, keep the local
editable installation and mark hosted release as pending. Do not change existing
ML dependencies or create/modify deployment workflows.

- [ ] **Step 8: Commit the limited integration**

```powershell
git add streamlit_app/app.py streamlit_app/README.md
git commit -m "feat: embed read-only F1 Buddy popup"
```

If the dependency release was completed, stage and commit
`streamlit_app/requirements.txt` separately:

```powershell
git add streamlit_app/requirements.txt
git commit -m "build: pin F1 Buddy popup package"
```

## Task 8: Verify read-only behavior and finish documentation

**Files (new package only):**
- Create: `tests/test_read_only.py`
- Modify: `README.md`

- [ ] **Step 1: Add regression tests against copied synthetic outputs**

Create `tests/test_read_only.py`:

```python
import hashlib
from datetime import date
from pathlib import Path
from shutil import copytree

from f1buddy_ai.chat.engine import ChatEngine
from f1buddy_ai.data.snapshots import SnapshotRepository
from f1buddy_ai.models import HostContext, DriverStanding
from f1buddy_ai.services.f1_data import F1DataService


def fingerprint(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*") if path.is_file()
    }


def test_all_local_answers_leave_source_files_unchanged(tmp_path, monkeypatch):
    directory = tmp_path / "read_only_outputs"
    copytree(Path(__file__).parent / "fixtures" / "public_data", directory)
    before = fingerprint(directory)

    def forbidden_write(*args, **kwargs):
        raise AssertionError("Chatbot attempted to write source data")

    monkeypatch.setattr(Path, "write_text", forbidden_write)
    monkeypatch.setattr(Path, "write_bytes", forbidden_write)
    repository = SnapshotRepository(directory)
    engine = ChatEngine(
        F1DataService(repository, None),
        HostContext(as_of_date=date(2026, 11, 3)),
    )
    for command in ("next race", "driver standings", "constructor standings",
                    "current prediction", "model performance", "help"):
        reply = engine.respond(command)
        assert "temporarily unavailable" not in reply.text
    assert fingerprint(directory) == before


def test_missing_stats_fallback_does_not_save_into_source_directory(tmp_path):
    directory = tmp_path / "outputs"
    copytree(Path(__file__).parent / "fixtures" / "public_data", directory)
    (directory / "stats.json").unlink()  # synthetic fixture only
    before = fingerprint(directory)

    class ApiStub:
        def driver_standings(self, season):
            return [DriverStanding(position=1, code="NOR", name="Norris",
                                   team="McLaren", points=300, wins=5)]

    service = F1DataService(SnapshotRepository(directory), ApiStub())
    assert service.driver_standings(2026).source == "jolpica"
    assert fingerprint(directory) == before
```

- [ ] **Step 2: Run the new-package test suite**

In `f1buddy-ai`:

```powershell
python -m pytest -v
git diff --check
```

Expected: adapter immutability, read-only source checks, source selection, bounded
API retries, deterministic responses, and public API tests pass. No tests or
training commands in the prediction repository are added or changed.

- [ ] **Step 3: Review the existing-repository diff**

In `Formula1`:

```powershell
git diff --name-only
git diff -- ml web .github
git diff -- streamlit_app/app.py streamlit_app/requirements.txt streamlit_app/README.md
git status --short
```

For committed implementation changes, also compare the implementation commits
against the pre-implementation base recorded in Step 1 of Task 7. Only the allowed
integration, dependency and documentation paths may be changed. Preserve all
pre-existing user work. Explicitly confirm no new data, manifest, model, producer,
workflow, strategy or prediction-function changes were introduced.

- [ ] **Step 4: Complete the acceptance matrix**

| Scenario | Expected result |
|---|---|
| First open | Welcome text and five quick actions |
| Next race | Same name and date as the website |
| Current prediction | Same ordered drivers and percentages as the displayed panel |
| Real-grid mode | Reuse the exact real-grid rows already selected by the website |
| Standings | Existing saved standings with the source timestamp |
| Model performance | Existing offline evaluation, clearly distinguished from the live panel |
| Missing current prediction/metrics | Friendly unavailable response; no ML invocation |
| Named historical prediction missing | State the missing stage; show actual results separately if available |
| Mexico question during Brazil week | Resolve Mexico for the requested/default season; never show Brazil's prediction |
| Missing standings/schedule | Independent bounded Jolpica GET fallback |
| API timeout/429 | Bounded retries/cooldown; website stays usable |
| Chat clicks and submission | Only the chatbot fragment reruns |
| Source objects/files | Unchanged after chatbot queries |
| Date selection changes | Website behaves normally; chat history resets for its new output |
| Existing RUN behavior | Function and button wiring unchanged |
| No paid credentials | Core popup works from existing outputs without keys |

- [ ] **Step 5: Document the read-only release contract**

Append to the new package's `README.md`:

```markdown
## Read-only integration contract

Version: 0.1.0. The popup consumes existing website output; it does not produce or
alter predictions. It never imports the host's ML code or invokes training,
inference, refresh, export, or cache-clearing operations.

Inputs: the existing display dictionary, driver/team label dictionaries, and
read-only stats.json, metrics.json, and compatible next_race_prediction.json.
No manifest or producer-side data-schema changes are required.

Jolpica is an optional independent GET fallback for public schedule, standings,
qualifying classification and race results.
Its cache stays in memory. API responses are never written into the host data
directory or supplied to the prediction model. Missing ML output stays unavailable.

The popup is a Streamlit fragment so chat does not retrigger the page's prediction
execution. Scope of host edits: app import/render call, dependency, and chatbot
documentation. All chatbot implementation and tests live in f1buddy-ai.

Phase 2 is outside this release. No OpenAI, WhatsApp, database or notification
infrastructure is created in Phase 1.
```

- [ ] **Step 6: Commit package acceptance tests and documentation**

```powershell
git add tests/test_read_only.py README.md
git commit -m "test: enforce read-only chatbot integration"
git status --short --branch
```

## Task 9: Add historical predictions and actual qualifying/race results

Implement this task before final Phase 1 acceptance. All files below belong to the new `f1buddy-ai` package; the existing repository's allowed-change list does not expand.

**Files:**
- Create: `src/f1buddy_ai/chat/history.py`
- Modify: `src/f1buddy_ai/chat/engine.py`
- Create: `tests/test_history.py`
- Modify: `README.md`

- [ ] **Step 1: Write historical lookup tests using synthetic in-memory records**

Create `tests/test_history.py`:

```python
from copy import deepcopy

from f1buddy_ai.chat.history import HistoricalChat


class Repository:
    def __init__(self, stage=True):
        race = {"name": "Mexico City Grand Prix", "season": 2026,
                "round": 19, "date": "2026-11-01"}
        self.files = {"races.json": [race], "predictions.json": {},
                      "next_race_prediction.json": {"race": race, "forecast": {}}}
        if stage:
            self.files["next_race_prediction.json"]["forecast"] = {
                "predictedQualifying": [{"position": 1, "code": "NOR", "driverName": "Norris", "gap": 0.0}],
                "preQualifyingPodium": [{"code": "NOR", "driverName": "Norris", "podiumProbability": 0.42}],
                "hasRealGrid": True,
                "realGridPodium": [{"code": "VER", "driverName": "Verstappen", "podiumProbability": 0.8}],
                "realQualifying": [{"position": 1, "code": "VER", "driverName": "Verstappen"}],
            }

    def _read(self, name):
        return self.files[name]


class Api:
    def __init__(self):
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        season = path.split("/")[0]
        race = {"season": season, "round": "19", "raceName": "Mexico City Grand Prix",
                "date": f"{season}-11-01", "Circuit": {}}
        if "/results/" in path:
            race["Results"] = [{"position": "1", "status": "Finished",
                                "Driver": {"givenName": "Test", "familyName": "Winner"}}]
        if "/qualifying/" in path:
            race["QualifyingResults"] = [{"position": "1", "Q3": "1:16.000",
                                          "Driver": {"givenName": "Test", "familyName": "Qualifier"}}]
        return {"MRData": {"RaceTable": {"Races": [race]}}}


def test_saved_stages_are_distinct_and_do_not_mutate_data():
    repository, api = Repository(), Api()
    before = deepcopy(repository.files)
    history = HistoricalChat(repository, api)
    assert "Norris" in history.respond("Mexico predicted qualifying", 2026).text
    assert "42.0%" in history.respond("Mexico prediction before qualifying", 2026).text
    assert "80.0%" in history.respond("Mexico prediction after qualifying", 2026).text
    assert api.calls == []
    assert repository.files == before


def test_missing_prediction_returns_actual_race_result():
    reply = HistoricalChat(Repository(stage=False), Api()).respond("Mexico prediction", 2026)
    assert "not available" in reply.text
    assert "Actual race result" in reply.text
    assert "Test Winner" in reply.text


def test_unknown_stage_estimate_cannot_fill_postqualifying_request():
    repository = Repository(stage=False)
    repository.files["predictions.json"] = {"2026-19": [
        {"driver": "NOR", "driverName": "Norris", "podiumProbability": 0.42}
    ]}
    history = HistoricalChat(repository, Api())
    assert "qualifying stage and original forecast time not recorded" in history.respond("Mexico prediction", 2026).text
    reply = history.respond("Mexico prediction after qualifying", 2026)
    assert "not available" in reply.text
    assert "42.0%" not in reply.text
    assert "Actual race result" in reply.text


def test_explicit_year_never_uses_other_season_prediction():
    api = Api()
    reply = HistoricalChat(Repository(), api).respond("Mexico 2025 prediction", 2026)
    assert "Mexico City Grand Prix — 2025" in reply.text
    assert "42.0%" not in reply.text
    assert all(path.startswith("2025/") for path in api.calls)


def test_generic_usa_is_clarified_before_api_access():
    api = Api()
    reply = HistoricalChat(Repository(), api).respond("USA result", 2026)
    assert "Austin" in reply.text and "Miami" in reply.text
    assert api.calls == []


def test_api_failure_preserves_available_prediction():
    class OfflineApi:
        def _get(self, path):
            raise OSError("offline")
    reply = HistoricalChat(Repository(), OfflineApi()).respond("Mexico prediction and results", 2026)
    assert "42.0%" in reply.text
    assert "temporarily unavailable" in reply.text


def test_actual_qualifying_is_separate_from_prediction():
    reply = HistoricalChat(Repository(), Api()).respond("Mexico qualifying results", 2026)
    assert "Actual qualifying classification" in reply.text
    assert "Norris" not in reply.text


def test_current_prediction_question_is_left_to_existing_router():
    assert HistoricalChat(Repository(), Api()).respond("current prediction", 2026) is None


def test_unpublished_results_are_not_reported_as_zero_or_winner():
    class EmptyApi:
        def _get(self, path):
            return {"MRData": {"RaceTable": {"Races": []}}}
    reply = HistoricalChat(Repository(stage=False), EmptyApi()).respond("Mexico race results", 2026)
    assert "not available in Jolpica yet" in reply.text
    assert "Test Winner" not in reply.text


def test_united_states_request_uses_exact_season_and_round():
    repository, api = Repository(stage=False), Api()
    repository.files["races.json"] = [{"name": "United States Grand Prix", "season": 2025,
                                      "round": 19, "date": "2025-10-19"}]
    reply = HistoricalChat(repository, api).respond("United States 2025 race results", 2026)
    assert "United States Grand Prix — 2025" in reply.text
    assert api.calls == ["2025/19/results/?limit=100"]
    assert "Saved" not in reply.text
```

- [ ] **Step 2: Confirm the missing-module failure**

Run `python -m pytest tests/test_history.py -v`. Expected: collection fails because `f1buddy_ai.chat.history` does not yet exist.

- [ ] **Step 3: Implement the read-only historical responder**

Create `src/f1buddy_ai/chat/history.py`:

```python
import re
import unicodedata

import requests

from f1buddy_ai.data.jolpica import JolpicaUnavailable
from f1buddy_ai.models import ChatReply

ERRORS = (OSError, KeyError, ValueError, TypeError, requests.RequestException, JolpicaUnavailable)


def normalise(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())


def contains(text, phrase):
    return f" {phrase} " in f" {text} "


ALIASES = {
    "mexico": "Mexico City Grand Prix", "mexican gp": "Mexico City Grand Prix",
    "united states": "United States Grand Prix", "us gp": "United States Grand Prix",
    "austin": "United States Grand Prix", "cota": "United States Grand Prix",
    "brazil": "São Paulo Grand Prix", "brazilian gp": "São Paulo Grand Prix",
    "sao paulo": "São Paulo Grand Prix", "interlagos": "São Paulo Grand Prix",
    "miami": "Miami Grand Prix", "las vegas": "Las Vegas Grand Prix",
    "monaco": "Monaco Grand Prix",
}


class HistoricalChat:
    def __init__(self, repository, api):
        self.repository = repository
        self.api = api

    def _read(self, name, default):
        try:
            value = self.repository._read(name)
            return value if isinstance(value, type(default)) else default
        except ERRORS:
            return default

    def _catalog(self):
        rows = list(self._read("races.json", []))
        snapshot = self._read("next_race_prediction.json", {})
        if isinstance(snapshot.get("race"), dict):
            rows.append(snapshot["race"])
        return [row for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"]]

    def _resolve(self, name, season, catalog):
        matches = [row for row in catalog if str(row.get("season")) == str(season)
                   and normalise(row["name"]) == normalise(name)]
        if not matches:
            payload = self.api._get(f"{season}/?limit=100")
            rows = payload["MRData"]["RaceTable"]["Races"]
            matches = [{"name": row["raceName"], "season": int(row["season"]),
                        "round": int(row["round"]), "date": row["date"]}
                       for row in rows if int(row["season"]) == season
                       and normalise(row["raceName"]) == normalise(name)]
        ids = {(int(row["season"]), int(row["round"])) for row in matches}
        if len(ids) != 1:
            raise ValueError("Race could not be uniquely resolved")
        return matches[0]

    def _forecast(self, race):
        snapshot = self._read("next_race_prediction.json", {})
        outer = snapshot.get("race", {})
        if not isinstance(outer, dict):
            return {}
        expected = (str(race["season"]), str(race["round"]))
        if (str(outer.get("season")), str(outer.get("round"))) != expected:
            return {}
        forecast = snapshot.get("forecast", {})
        if not isinstance(forecast, dict):
            return {}
        inner = forecast.get("race", outer)
        if not isinstance(inner, dict):
            return {}
        if (str(inner.get("season")), str(inner.get("round"))) != expected:
            return {}
        return forecast

    def _saved_section(self, rows, label, probability=True):
        if not isinstance(rows, list) or not rows:
            return None
        try:
            lines = []
            for index, row in enumerate(rows[:3 if probability else 10], 1):
                name = row.get("driverName") or row.get("code") or row.get("driver")
                if not name:
                    return None
                if probability:
                    value = float(row["podiumProbability"])
                    if not 0 <= value <= 1:
                        return None
                    lines.append(f"{name} — {value:.1%}")
                else:
                    lines.append(f'{row.get("position", index)}. {name}')
            return label + "\n" + "\n".join(lines)
        except ERRORS:
            return None

    def _actual(self, race, forecast, qualifying=False):
        label = "Actual qualifying classification" if qualifying else "Actual race result"
        if qualifying and forecast.get("hasRealGrid"):
            saved = self._saved_section(forecast.get("realQualifying"),
                                        label + " — saved snapshot", probability=False)
            if saved:
                return saved + "\nQualifying classification may differ from the final starting grid."
        kind = "qualifying" if qualifying else "results"
        field = "QualifyingResults" if qualifying else "Results"
        try:
            payload = self.api._get(f'{int(race["season"])}/{int(race["round"])}/{kind}/?limit=100')
            races = payload["MRData"]["RaceTable"]["Races"]
            matches = [r for r in races if isinstance(r, dict) and str(r.get("season")) == str(race["season"])
                       and str(r.get("round")) == str(race["round"])]
            rows = matches[0].get(field, []) if matches else []
            if not rows:
                return label + ": not available in Jolpica yet."
            lines = []
            for row in rows[:10]:
                driver = row["Driver"]
                name = f'{driver["givenName"]} {driver["familyName"]}'
                detail = ""
                if qualifying:
                    detail = "; ".join(f"{q}: {row[q]}" for q in ("Q1", "Q2", "Q3") if row.get(q))
                else:
                    detail = row.get("status", "")
                lines.append(f'{row["position"]}. {name}' + (f" — {detail}" if detail else ""))
            note = "\nQualifying classification may differ from the final starting grid." if qualifying else ""
            return label + " — Jolpica\n" + "\n".join(lines) + note
        except ERRORS:
            return label + ": temporarily unavailable; the data source could not be read."

    def respond(self, message, default_season):
        text = normalise(message)
        catalog = self._catalog()
        aliases = dict(ALIASES)
        for row in catalog:
            phrase = normalise(row["name"]).removesuffix(" grand prix").strip()
            if phrase:
                aliases[phrase] = row["name"]
        names = {name for phrase, name in aliases.items() if contains(text, phrase)}
        reply = lambda body: ChatReply(text=body, intent="history")
        if contains(text, "usa") or contains(text, "us race"):
            return reply("Which event: United States GP (Austin), Miami GP, or Las Vegas GP? Please include the year if needed.")
        if not names:
            if any(contains(text, phrase) for phrase in ("history", "historical", "previous race", "last race")):
                return reply("Please name the race, for example 'Mexico prediction' or 'United States 2025 race results'.")
            return None
        if len(names) != 1:
            return reply("Please ask about one named race at a time and include its year if needed.")
        if contains(text, "sprint"):
            return reply("Sprint results are not supported in Phase 1. Ask for the Grand Prix race or qualifying results.")
        years = re.findall(r"\b(?:19|20)\d{2}\b", text)
        if len(set(years)) > 1:
            return reply("Please choose one season for this race.")
        season = int(years[0]) if years else default_season
        try:
            race = self._resolve(next(iter(names)), season, catalog)
            forecast = self._forecast(race)
        except ERRORS:
            return reply(f"I could not resolve that race for {season}. Check the event name/year or try again when the schedule source is available.")
        prediction = bool(re.search(r"\b(predict|predicted|prediction|predictions|forecast)\b", text))
        actual = bool(re.search(r"\b(result|results|compare|actual|qualified)\b", text))
        qualifying = "qualifying" in text or "qualified" in text
        if not prediction and not actual and not qualifying:
            prediction = actual = True  # A bare event name requests an overview.
        if qualifying and not prediction:
            actual = True
        after = "after qualifying" in text or "post qualifying" in text or "real grid" in text
        before = "before qualifying" in text or "pre qualifying" in text
        qualifying_prediction = prediction and qualifying and not after and not before
        parts = [f'{race["name"]} — {season} (round {race["round"]})']
        missing = False
        if prediction:
            wanted = ([("predictedQualifying", "Saved predicted qualifying order", False)] if qualifying_prediction
                      else [("realGridPodium", "Saved podium forecast using real qualifying", True)] if after
                      else [("preQualifyingPodium", "Saved pre-qualifying podium forecast", True)] if before
                      else [("predictedQualifying", "Saved predicted qualifying order", False),
                            ("preQualifyingPodium", "Saved pre-qualifying podium forecast", True),
                            ("realGridPodium", "Saved podium forecast using real qualifying", True)])
            found = []
            absent = []
            for key, label, probability in wanted:
                rows = forecast.get(key) if key != "realGridPodium" or forecast.get("hasRealGrid") else None
                section = self._saved_section(rows, label + " — next_race_prediction.json", probability)
                if section:
                    found.append(section)
                else:
                    absent.append(label)
                    if after or before or qualifying_prediction:
                        missing = True
            if found and absent:
                parts.extend(f"{label}: not available." for label in absent)
                missing = True
            if not found and not (after or before or qualifying_prediction):
                records = self._read("predictions.json", {})
                section = self._saved_section(records.get(f'{season}-{int(race["round"])}'),
                    "Saved historical model estimate — qualifying stage and original forecast time not recorded — predictions.json")
                if section:
                    found.append(section)
            missing = missing or not found
            parts.extend(found)
            if missing:
                parts.append("The requested saved prediction is not available. Actual results are shown separately when available.")
            else:
                parts.append("Only available saved stages are shown. These are stored model outputs, not guaranteed pre-event publications. Podium probabilities are not win probabilities.")
        if actual or missing:
            if qualifying:
                parts.append(self._actual(race, forecast, qualifying=True))
            if not qualifying or missing or contains(text, "race results") or contains(text, "race result"):
                parts.append(self._actual(race, forecast))
        return reply("\n\n".join(parts))
```

Every external request above uses the existing guarded `JolpicaClient._get`; do not introduce a separate `requests.get` path. The API never supplies or reconstructs model predictions. Local records are only read; no prediction archive, Git-history reconstruction, new dataset, or Parquet writer is added.

- [ ] **Step 4: Route named questions before current-page intents**

In `src/f1buddy_ai/chat/engine.py`, add:

```python
from f1buddy_ai.chat.history import HistoricalChat
```

Append to `ChatEngine.__init__`:

```python
        self.history = HistoricalChat(service.repository, service.jolpica)
```

At the start of `ChatEngine.respond`, before `recognize_intent(message)`:

```python
        season = self.context.current_race.season if self.context.current_race else self.context.as_of_date.year
        historical = self.history.respond(message, season)
        if historical is not None:
            return historical
```

Replace the help return with:

```python
            return ChatReply(
                text=prefix + "I can show the next race, standings, the current prediction, or model performance. Choose an option below. For past races, type 'Mexico prediction', 'Mexico predicted qualifying', or 'United States 2025 race results'.",
                intent=intent.value, options=QUICK_ACTIONS,
            )
```

- [ ] **Step 5: Add the Brazil-page regression test**

Append to `tests/test_history.py`:

```python
def test_mexico_request_does_not_return_displayed_brazil_prediction():
    from datetime import date
    from f1buddy_ai.chat.engine import ChatEngine
    from f1buddy_ai.models import HostContext, RaceInfo
    from f1buddy_ai.services.f1_data import F1DataService

    context = HostContext(as_of_date=date(2026, 11, 5), current_race=RaceInfo(
        name="São Paulo Grand Prix", season=2026, round=20, date=date(2026, 11, 8)))
    engine = ChatEngine(F1DataService(Repository(), Api()), context)
    reply = engine.respond("Mexico prediction")
    assert reply.intent == "history"
    assert "Mexico City Grand Prix" in reply.text
    assert "São Paulo" not in reply.text
```

- [ ] **Step 6: Run the full chatbot suite and manual examples**

```powershell
python -m pytest tests/test_history.py tests/test_engine.py tests/test_read_only.py -v
python -m pytest -v
git diff --check
```

Expected: all tests pass with no live network. In the popup, verify these cases: Brazil on the page while asking Mexico; explicit United States 2025; predicted qualifying available; only pre-qualifying saved; post-qualifying absent; generic historical estimate without mode metadata; results-only request; API outage; future/unpublished results; ambiguous USA. Existing source data and prediction behavior must remain unchanged.

- [ ] **Step 7: Document availability and commit**

Append to the new package `README.md`:

```markdown
## Historical races

Ask for a named race and optionally a year: Mexico prediction, Mexico predicted
qualifying, Mexico prediction after qualifying, Mexico qualifying results, or
United States 2025 race results. Without a year, the displayed race's season is used.

Saved model outputs are read from existing files only. Qualifying-stage labels are
shown only when the saved data identifies that stage. Generic historical estimates
are labelled separately; they are not proof of forecasts published before a race.
If the requested prediction is missing, actual qualifying/race results are fetched
from Jolpica and labelled as actual results. No prediction is recreated or saved.

The single next-race snapshot can be overwritten by the existing application.
Therefore full historical pre/post-qualifying coverage is not guaranteed. This
feature does not change the ML pipeline or create a prediction archive.
```

```powershell
git add src/f1buddy_ai/chat/history.py src/f1buddy_ai/chat/engine.py tests/test_history.py README.md
git commit -m "feat: add read-only historical race questions"
```

## Completion criteria

Phase 1 is complete when the popup works with all seven intents, including named historical requests, matches the
website's displayed prediction, and passes the package and manual UI checks.
The existing ML engine, prediction strategy, data files, models, producer scripts,
data contracts and scheduled workflows must have no chatbot-related changes.
All Jolpica use must be read-only and isolated from the prediction pipeline.

Hosted package publication is a separate release step if its authorization is
still pending; it does not prevent testing the completed local popup.

## Planning review

The earlier timestamp-export, manifest, ML-file and workflow tasks have been
removed. The integration no longer changes `resolve()` or passes new fields
through the prediction engine. The new adapter copies its existing display output.
The revised plan includes explicit tests for unchanged inputs and source files,
and a fragment-isolation demo. Task 9 adds historical questions without expanding
the protected-file boundary or recreating missing forecasts. This is the original
planning review; see the execution update below for the current status.

## Execution update — 2026-11-05

The local Phase 1 implementation is now in the sibling `f1buddy-ai` repository,
on `feature2`; the Formula1 integration remains on `feature2` as requested.
The task checklists above preserve the original step-by-step plan rather than
claiming that every proposed intermediate commit/publication was performed.

- Implemented the package, typed models, read-only JSON adapter, independent
  throttled Jolpica client, deterministic engine, historical lookup, and popup.
- Added only the optional import and final popup hook to the host application,
  plus chatbot setup documentation. No host prediction function was edited.
- Added regression tests for stage/season/race identity, missing forecasts,
  API outages and malformed data, immutability, and the Streamlit UI.
- Verification: 111 tests pass; editable install and wheel build succeed.
- Browser smoke test: quick-action and typed messages left the synthetic demo's
  full-page execution count at 1. This verifies fragment isolation without
  invoking the actual ML pipeline. The host hook was also tested separately.
- Live network smoke test: `Mexico 2025 race results` returned Jolpica's actual
  classification through the chatbot after allowing the read-only lookup outside
  the network sandbox. All automated tests remain network-independent.
- SHA-256 comparison: all 296 tracked protected files under `ml`, `web`, and
  `.github` match their pre-implementation hashes. AST comparison confirms all
  pre-existing host statements and functions are unchanged.

Implementation adjustments supported by tests: the popup fills a reserved
transcript container after handling input, so it needs no explicit second rerun;
calendar identity takes precedence over conflicting snapshots; malformed sources
fail gracefully; unconfirmed real-grid forecasts are rejected. The delegated
historical worker stopped at its usage limit after writing tests; the main agent
implemented and reviewed that module locally against those tests.

The independent API budget is 60 attempts/hour with 1-second spacing, 15-minute
in-memory caching, bounded retries, and Retry-After handling. Official provider
limits were rechecked on 2026-11-05 and are linked in the package README.

Pending separate release work: public repository/package publication and a
version-pinned hosted dependency. No GitHub/PyPI publication or hosted deployment
was authorized or performed. The host requirements remain unchanged. Phase 2
is not part of this implementation. Run commands and limitations are documented
in both repositories' chatbot setup sections.
