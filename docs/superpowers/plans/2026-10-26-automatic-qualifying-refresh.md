# Automatic Qualifying Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** A visitor sees the saved forecast switch from estimated qualifying to actual qualifying automatically, with no RUN button, page refresh, visitor-triggered API ingestion, or visitor-triggered model execution.

**Architecture:** Retain the two existing Monday workflows and add one scheduled qualifying monitor. A persistent event state machine controls the five-hour wait, hourly retries, final verification, and publication deadline; validated, versioned JSON is the only forecast source consumed by Streamlit. Parquet remains the historical data store, and Git commits publish coordinated changes while retaining the previous valid prediction on failure.

**Tech Stack:** Python 3.11, pandas/PyArrow, existing LightGBM and scikit-learn models, requests, pytest, GitHub Actions, Streamlit fragments, Git-backed JSON/Parquet.

**Status:** Implementation authorized using fresh subagents with spec and quality reviews after each task. Work branch: feature1 (tracking origin/feature1, explicitly requested). Based on repository commit 5c0ad5bcbc2e104d6e3d886d34261e1575ef77e0; not pushed or deployed.

**Progress:** Tasks 1-5 are implemented and reviewed; 5 tasks remain. Next is Task 6 (safe publication, availability confirmation, and freeze selection). RUN removal remains Task 9; automatic publication is not enabled yet. See [execution record](automatic-qualifying-execution.md) for commits and verification evidence.

**Execution clarification (2026-10-26):** The user accepts strict forecast eligibility with possible display lag: a forecast must be verified available before the two-hour cutoff; the feed/browser may display that already-eligible version later. Candidate verification, not mutable-feed propagation, is the eligibility event. Persist verifiable confirmation evidence; an uncertain or post-cutoff confirmation is ineligible. Feed publication and immutable freeze selection must consistently enforce that rule. The saved ML-based initial remains the fallback when actual qualifying is unavailable. Execution uses the stated GitHub-only, start-plus-90-minute estimated-end and Monday-safety defaults; the estimate remains explicitly labeled.

**Review additions:** Filter historical raw inputs before feature construction (not only training rows afterward). Preserve the existing Monday reconstruction backtest as a labeled benchmark, and separately score saved initial/final forecasts against completed results; do not present reconstructed predictions as archived live accuracy.

---

## 1. Decisions and limits

### Requirements supplied by the user

- Remove RUN and all visitor-triggered data ingestion and model execution.
- Save an initial prediction before qualifying.
- Begin qualifying checks five hours after qualifying ends.
- Retry hourly when qualifying is missing or incomplete; do not train on unsuccessful checks.
- Publish only valid changed inputs and valid resulting predictions.
- Pause qualifying polling after success until one final verification window.
- Finish publication before race start minus two hours.
- Freeze the last successful forecast for evaluation.
- Preserve Monday's data refresh, accuracy backtest, and next-race forecast.
- Keep JSON and Parquet; no database is required.
- Update an already-open page by reading saved outputs.
- Keep previous valid output on errors, and never substitute another race's prediction.

### Execution defaults and explicit clarifications

| Decision | Default used for execution |
|---|---|
| Meaning of “Monday unchanged” | Preserve both schedules and existing work. Permit small changes to common publication code, staged artifact paths, and writer coordination. Do not split out the backtest or remove any Monday work. |
| No observed qualifying finish time | Estimate end as qualifying start + 90 minutes. Set end_time_estimated=true and keep source/provenance. An observed or documented override takes precedence. |
| Scheduling infrastructure | GitHub Actions only. Late/missed runs retain the existing prediction and report their status. No promise of an exact execution minute. |

After requesting explanation, the user requested execution of this plan. These defaults were explicitly announced for execution; the separate cutoff/display-lag clarification above was expressly accepted. No finish timestamp is inferred from ML qualifying performance. If Monday files and scripts must instead be byte-for-byte unchanged, Task 7 needs redesign: the legacy publisher does not archive new records or honor the new eligibility deadline.

### Additional design choices

- Apply the plan to the existing Streamlit prediction app. The Next.js Predict link already points there.
- Add one workflow, giving three workflows total. Keep the existing website stats sync.
- Wake the new workflow every 15 minutes throughout the year; decide locally whether any work is due. This is not a request to fetch qualifying every 15 minutes.
- Refresh schedule metadata daily outside an event window and hourly from 72 hours before qualifying until the cutoff, including while qualifying retries are paused.
- Qualifying retry due time is the previous attempted check start + one hour. A late run makes one check; do not replay missed checks in a burst.
- Final verification is due 45 minutes before the cutoff. Do not start a new expensive generation with less than 15 minutes remaining.
- Page polling defaults to every 60 seconds, with shared server caching and last-good-output retention. This is a refresh target, not a guarantee about network/CDN latency.
- Keep the current date selector as a selector for saved forecasts. Selecting an event without a saved forecast shows its name plus “Prediction temporarily unavailable”; it does not start training.
- Do not reinterpret actual qualifying as the penalty-adjusted final starting grid.
- Current model families and feature definitions remain the baseline. Prediction validation may reveal probability-output defects; handle those explicitly before enabling automatic publication.

### Provider limits verified for this plan

Jolpica's schedule documents race and qualifying start timestamps, but does not document an actual qualifying finish timestamp. Its qualifying endpoint has optional classification/timing fields, and its pagination metadata proves response coverage, not that the provider has finished publishing the entire session. A separately established expected field is therefore necessary.

GitHub scheduled jobs can be delayed or dropped. The controller must evaluate actual UTC time after queueing, installation, API calls, model work, and before publication. A late job must not publish merely because its scheduled trigger was earlier.

Streamlit fragments support timed reruns while the page session is active. A fragment must poll a remote saved output: periodically rereading a stale local deployment file alone does not satisfy automatic open-page updates.

Sources:
- [Jolpica race/schedule schema](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/races.md)
- [Jolpica qualifying schema](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/qualifying.md)
- [Jolpica pagination documentation](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md)
- [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub concurrency and queues](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)

## 2. What changes in the existing project

| Current behavior / file | Required change |
|---|---|
| ml/src/data/jolpica.py::get_schedule discards session times | Preserve race time, Qualifying.date/time, circuit identity and schedule provenance. Do not infer qualifying date from race day. |
| forecast.py computes qualifying as race date minus one day | Use an explicit event record and explicitly supplied mode/validated qualifying. |
| forecast.py accepts any nonempty qualifying response | Require complete validated target-session input plus publication-window eligibility. |
| forecast.py derives entries from the last race | Reconcile an event roster and support substitutes and no-lap classified entrants. |
| forecast.py always computes both modes | Actual-qualifying generation runs Stage 2 with actual inputs; keep the saved initial forecast for comparison. |
| app.py loads a race-matching snapshot or trains inline | Read published saved output only. Remove all inference and training fallbacks. |
| app.py has button-only cache/session state | Replace with read-only snapshot cache and per-event last-good output. |
| precompute_next_race.py overwrites one JSON file | Use the same archive/publisher as the qualifying monitor; retain the compatibility JSON. |
| Monday refresh performs fetch + snapshot + backtest | Preserve all three operations and its Monday schedule. Add publication/archive safety integration. |
| sync-stats.yml independently pushes main | Preserve its stats work and schedule; coordinate its writer and handle moved branch heads. |

### File map

Create:
- ml/src/pipeline/__init__.py
- ml/src/pipeline/events.py — UTC schedules, observed/estimated end, roster and override contracts.
- ml/src/pipeline/state.py — due-action and cutoff decisions; no network/model imports.
- ml/src/pipeline/qualifying.py — target-session fetching, pagination and classification validation, event-only Parquet merge.
- ml/src/pipeline/artifacts.py — JSON contracts, stable hashes, immutable versions, prediction validation.
- ml/src/pipeline/publish.py — candidate staging, Git publication, confirmation and freeze selection.
- ml/src/pipeline/controller.py — compose checks, validation, generation, publication and persisted state.
- ml/scripts/check_qualifying.py — scheduled job CLI: plan work, run due work, report outcomes.
- ml/scripts/publish_refresh.py — safe publisher used by Monday and stats workflows.
- ml/config/event_overrides.json — empty object initially; documented schedule/participant exceptions.
- streamlit_app/prediction_data.py — read saved feed, validate event/version, retain last-good values.
- streamlit_app/prediction_view.py — extracted forecast rendering usable in acceptance tests before RUN removal.
- .github/workflows/qualifying-monitor.yml
- ml/tests/test_event_timing.py
- ml/tests/test_pipeline_state.py
- ml/tests/test_qualifying_validation.py
- ml/tests/test_prediction_artifacts.py
- ml/tests/test_prediction_publication.py
- ml/tests/test_pipeline_controller.py
- ml/tests/test_saved_prediction_ui.py
- ml/tests/test_pipeline_integration.py

Modify:
- ml/src/data/jolpica.py
- ml/src/model/forecast.py
- ml/src/model/retrain.py only where explicit history/cutoff injection is needed.
- ml/scripts/precompute_next_race.py
- ml/scripts/refresh_for_next_race.py
- .github/workflows/refresh-predictions.yml
- .github/workflows/sync-stats.yml
- streamlit_app/app.py
- streamlit_app/requirements.txt
- ml/requirements-dev.txt
- ml/tests/test_forecast.py
- README.md
- docs/specs/prediction-logic.md
- docs/specs/ml-models.md

Do not create refresh-accuracy.yml. The existing Monday backtest stays in place.

## 3. Timing and state contract

For an event:

~~~python
first_check_at = qualifying_end_at + timedelta(hours=5)
cutoff_at = race_start_at - timedelta(hours=2)
final_check_at = cutoff_at - timedelta(minutes=45)
latest_generation_start_at = cutoff_at - timedelta(minutes=15)
~~~

All datetimes are timezone-aware UTC. Missing race start or qualifying start is a scheduling error; do not synthesize midnight.

| State/action | Rule |
|---|---|
| waiting_initial | No valid initial exists; background preparation may generate one only before qualifying_start_at. |
| waiting_qualifying | Initial exists; no qualifying fetch before first_check_at. |
| retry_wait | Missing/incomplete data or recoverable error; next attempt no earlier than one hour after the attempted check began. |
| published_actual | A validated actual-qualifying version was published; pause ordinary qualifying retries. |
| final_check | At/after max(first_check_at, final_check_at), make final verification even if an ordinary retry is not yet due. |
| final_checked | Record the final attempt once; no new ordinary checks. A successful correction must finish before the deadline. |
| frozen | At cutoff, the selection is the latest confirmed eligible prediction; no new prediction generation or promotion. |
| unavailable | There is no valid saved prediction for this event. Do not substitute another event. |

If first_check_at >= cutoff_at, record wait_exceeds_cutoff and keep the initial forecast. If only a shorter processing window remains than the configured reserve, record insufficient_publication_window.

The final check is attempted once, after any initial five-hour wait. When data remains unavailable at that final attempt, preserve the initial or latest actual version. A final-check failure does not restart an uncontrolled retry loop.

A missed freeze run does not move the deadline. The final selection is a deterministic query over confirmed publication records with published_at < cutoff_at. A later job may write final.json describing that already-fixed selection; it cannot generate a new forecast or backdate a publication.

Schedule changes before freezing recompute all deadlines. A change during generation invalidates the candidate's schedule hash and forces a fresh eligibility check. An already-frozen event is not silently reopened after a postponement; preserve it and report schedule_changed_after_freeze for operator review.

### Illustrative weekend (synthetic, not claimed Austin timestamps)

| Time (UTC) | Action |
|---|---|
| Saturday 15:00 | Qualifying starts. |
| Saturday 16:30 | Estimated finish, explicitly labeled estimated. |
| Saturday 21:30 | First qualifying check becomes due. |
| Saturday 22:30 | Retry becomes due if the first response was unavailable/incomplete. |
| Sunday 14:15 | Final verification becomes due for a 17:00 race. |
| Sunday 15:00 | Publication cutoff; latest eligible saved prediction is fixed. |
| Monday | Existing job refreshes completed data/metrics and prepares the next event. |

Actual job starts depend on the next scheduled wakeup and runner availability.

## 4. Validation and forecasting contract

### Target API response

Use /ergast/f1/{season}/{round}/qualifying/ explicitly. Never use “last”, “next”, Sprint, SprintShootout or SprintQualifying for this input.

Retain response pages and retrieval metadata. Validate:
- F1 series, exact season/round/circuit, correct QualifyingResults session.
- Consistent offset, limit and total across pages; contiguous coverage; no duplicate/missing pages.
- Unique driver IDs; unique positive integer classification positions for classified entrants.
- Expected participant coverage, with documented exceptions.
- Present lap strings must parse to finite positive seconds.
- Missing Q2/Q3 is accepted. An entrant with no recorded laps is represented explicitly, not silently dropped.
- There must be enough usable timing data to construct model features. All-missing timings fail validation.

### Expected participants and substitutions

Create an event roster with driver ID, code/name, constructor ID/name, car number when available, expected participation and source metadata.

Use the last completed race as a provisional baseline, then apply evidence-backed event entry changes from event_overrides.json. A same-round provider roster may corroborate entries but must not be the only completeness proof when it can be derived from the same incomplete qualifying response. Never hard-code a season field size.

An unexpected missing entrant is incomplete data, not an inferred withdrawal. A new driver may replace a known car/team slot only when the event roster or a documented substitution confirms it. Exceptional unresolved changes keep the prior forecast and expose a useful reason; the public page still needs no manual control.

Documented exceptions are operational data, with source_url, observed_at and reason. They do not require adding a visitor-facing button. An authoritative automated roster source can replace this override mechanism later without changing the validator.

### Actual qualifying as Stage 2 inputs

- classification position feeds the existing grid_position feature; UI calls it qualifying position.
- Derive the timing feature consistently with the currently trained model: minimum recorded Q1/Q2/Q3 time minus the session minimum across drivers. The current code's “gap to pole” label is imprecise for mixed-session conditions; record feature_policy_version and explain the reference in ML documentation.
- Missing all lap times for a classified no-lap driver: preserve missing timing in displayed results; impute only the model input using the largest valid event gap, or 3.0 seconds when the approved policy permits. If no usable event times exist, reject the response.
- An unclassified entrant permitted to race requires an explicit model-position policy recorded in an exception. Do not invent a classification or silently renumber positions.
- Use event roster participants, including confirmed substitutes, and documented cold-start defaults. Withdrawn drivers are excluded from predictions with their reason preserved.

Keep model training strictly before the target event. For reproducibility, record the cutoff, historical-input digest, feature-policy version, model code digest, hyperparameters and library versions. Actual-qualifying checks never use the target race result as a feature or training label.

Do not retrain on missing, incomplete, unchanged or too-late input. A changed accepted input may fit Stage 2 in the background; Stage 1 is not rerun to rewrite the original forecast. Training on the same historical snapshot makes revisions attributable to the changed qualifying input.

## 5. Storage, versions, publication and freeze

~~~text
ml/data/raw/
  qualifying_<season>.parquet

web/public/data/
  next_race_prediction.json          compatibility output for existing consumers
  prediction_feed.json              single consistent saved page payload
  prediction_snapshots/
    <season>-<round>/
      event.json                    schedule, roster, source references
      initial.json                  first valid pre-qualifying forecast, create once
      versions/
        <prediction_id>.json        append-only forecast versions
      publications/
        <publication_id>.json       confirmed publication receipts
      final.json                    immutable selected prediction + cutoff/provenance
      status.json                   latest control/check state
      checks/
        <check_id>.json             bounded API/validation/outcome audit entries
      sources/
        <qualifying_source_version>.json  accepted response + pagination evidence
~~~

Canonical prediction fields:
~~~json
{
  "schema_version": 2,
  "season": 2026,
  "round": 18,
  "prediction_id": "content-derived identifier",
  "mode": "actual_qualifying",
  "generated_at": "2026-10-24T22:40:00Z",
  "model_version": "digest of model code, parameters, features and dependency versions",
  "training_cutoff": "2026-10-25T00:00:00Z",
  "training_data_hash": "digest of the actual historical inputs used",
  "qualifying_source_version": "digest of accepted session input and roster policy",
  "input_hash": "digest of event, mode, features, training and qualifying input",
  "feature_policy_version": "qualifying-min-session-v1",
  "event_schedule_hash": "digest of schedule values relevant to eligibility",
  "forecast": {
    "predictedQualifying": [],
    "preQualifyingPodium": [],
    "realQualifying": [],
    "realGridPodium": []
  }
}
~~~

This JSON illustrates keys, not a valid prediction fixture: real publication requires complete participant rows. Initial mode is predicted_qualifying and qualifying_source_version is null. Use only these two canonical mode names; legacy hasRealGrid may be emitted as a compatibility field.

If an unpublished version with the same input_hash already exists, validate and reuse it for publication retry; do not fit the model again. Compare against the last successfully generated candidate as well as the last published version. A failed generation can be retried in the next eligible window; a crash before any durable candidate exists cannot guarantee exactly-once computation, but must still produce the same version identity and never duplicate publication.

Hash normalized, sorted semantic inputs. Exclude poll time, generated_at, retry counters and JSON field order from input_hash. Preserve generated_at for repeated identical input. Changing metadata alone must not trigger a new model run.

Prediction validation:
- correct event and mode, supported schema, complete required provenance;
- one prediction per expected eligible entrant;
- finite probabilities between 0 and 1, descending order, sum approximately 3;
- valid unique qualifying positions and finite modeled gaps;
- no actual-qualifying label without an accepted source version;
- no training rows from the target or later event;
- no empty/malformed output promoted by the publisher.

The current multiply-by-3 normalization can in principle exceed 1. Tests must expose this. If it occurs, use capped sum-to-three rescaling of nonnegative scores, preserve rank/ties deterministically, record a new probability-policy version, and describe displayed values as normalized podium estimates. Do not quietly clip without restoring the sum, and do not silently claim calibration survives that adjustment.

### Safe publication

1. Stage candidate raw data, immutable version and page payload in a private temporary directory.
2. Validate candidate data and output before touching any published path.
3. Read the latest remote branch and latest event state after acquiring the writer lock.
4. Recheck schedule hash, source version, mode, event identity, freeze state and UTC deadline.
5. Atomically commit related files and advance the branch only by fast-forward. Never force-push.
6. Confirm the immutable committed candidate is retrievable through the saved-output read path before cutoff, checking exact content and identity. Record the verified timestamp and immutable commit/checksum evidence.
7. Persist that confirmation receipt and promote the eligible version in the feed; preserve the previous version as a fallback. As explicitly approved by the user, delivery of this already-eligible version may lag the cutoff.
8. Persist confirmation/eligibility time separately from model generation and feed-delivery times. A receipt must never claim a verification that did not occur; unknown outcomes without evidence are ineligible.

Use a publication budget, stop candidate promotion before the hard deadline, and bound network calls by the remaining time. Recheck eligibility after every blocking operation. A push timeout is an unknown outcome: reconcile the remote ref and receipt before retrying. Do not treat a local file write or successful model fit as successful publication.

The feed exposes confirmed versions only. An uncertain/unconfirmed candidate must not replace the version read by the app or selected by the evaluator. If candidate availability verification occurs at or after cutoff, retain the last confirmed version and exclude the candidate. On GitHub, multi-request confirmation and public CDN propagation are not a transaction with a server-side deadline. The user approved strict pre-cutoff candidate eligibility with potentially delayed feed/browser display. Keep an early-close budget and refuse ambiguous verification evidence. A late feed push may expose only a version that already has valid pre-cutoff verification; a late candidate upload or verification never qualifies.

Use one revisioned feed containing event identity, schedule/status, the selected prediction and prior confirmed fallback. This avoids reading a new status file together with an old prediction file. Archive URLs reference immutable versions.

### Freeze

final.json selects the latest eligible confirmed version, using publication evidence, not generated_at. Store cutoff_at, selected_prediction_id, selected_publication_id, selected mode and source hash. Once written, only an identical repeat is allowed. If no eligible version exists, write a final unavailable outcome; never create a post-cutoff prediction to fill the gap.

Evaluation reads final.json. A later correction, backtest or retrospective reconstruction is not eligible for that race's frozen forecast. Do not manufacture a historical post-qualifying Austin prediction: only the existing pre-qualifying snapshot is evidenced.

## 6. Implementation tasks

Work directly in C:/Users/user/Documents/Projects/formula1_newbie on feature1, as the user requested after Task 2. Commands below are run from that repository root unless noted. The former isolated checkout is retained only as a backup. Record dependency versions for each published model. Remote push, merge and deployment remain separate from local implementation.

### Task 1 — Event identity, timing and roster contract

**Files:** create ml/src/pipeline/events.py, ml/config/event_overrides.json and ml/tests/test_event_timing.py; modify ml/src/data/jolpica.py.

- [x] Write clock-controlled tests covering UTC conversion, non-Saturday qualifying, Saturday races, missing timestamps, estimated vs observed finish, schedule changes, and distinct Sprint/Grand Prix qualifying.
- [x] Run: python -m pytest ml/tests/test_event_timing.py -v. Confirm assertions fail because the current parser drops these fields.
- [x] Implement explicit fields and timing calculations, retaining existing schedule columns for Monday compatibility.

Core calculation:
~~~python
from datetime import datetime, timedelta, timezone

def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC offset is required")
    return parsed.astimezone(timezone.utc)

def event_windows(event: dict) -> dict:
    qualifying_start = parse_utc(event["qualifying_start_at"])
    race_start = parse_utc(event["race_start_at"])
    observed_end = event.get("qualifying_end_observed_at")
    end = parse_utc(observed_end) if observed_end else qualifying_start + timedelta(minutes=90)
    if end < qualifying_start or race_start <= qualifying_start:
        raise ValueError("Inconsistent session order")
    cutoff = race_start - timedelta(hours=2)
    return {
        "qualifying_end_at": end,
        "end_time_estimated": observed_end is None,
        "first_check_at": end + timedelta(hours=5),
        "cutoff_at": cutoff,
        "final_check_at": cutoff - timedelta(minutes=45),
        "latest_generation_start_at": cutoff - timedelta(minutes=15),
    }
~~~

Concrete test:
~~~python
from src.pipeline.events import event_windows, parse_utc

def test_five_hour_wait_uses_qualifying_timestamp_not_race_minus_one_day():
    event = {
        "qualifying_start_at": "2026-10-23T15:00:00Z",
        "race_start_at": "2026-10-25T17:00:00Z",
    }
    actual = event_windows(event)
    assert actual["first_check_at"] == parse_utc("2026-10-23T21:30:00Z")
    assert actual["cutoff_at"] == parse_utc("2026-10-25T15:00:00Z")
    assert actual["end_time_estimated"] is True
~~~

- [x] Persist event.json fields: season, round, race_name, circuit_id, qualifying_start_at, qualifying_end_at, end_time_estimated, race_start_at, schedule_updated_at, schedule_source, schedule_hash, roster, roster_source and roster_version.
- [x] Initialize event_overrides.json to {}. Accept overrides only for exact event IDs with reason and source reference. Missing critical schedule/entry evidence becomes a visible state, not guessed data.
- [x] Re-run event tests and existing Jolpica helper tests. Commit this isolated change with message: feat: preserve event session timing and roster provenance.

### Task 2 — Persistent due-action and cutoff logic

**Files:** create ml/src/pipeline/state.py and ml/tests/test_pipeline_state.py.

- [x] Add behavioral tests for before-first-check, hourly retry, pause-after-success, final check, short window, exact cutoff, overrun and schedule change.
- [x] Run: python -m pytest ml/tests/test_pipeline_state.py -v; verify failing behavior before implementing the controller policy.
- [x] Implement a pure decide_action(event, status, now) function returning one of wait, check_qualifying, final_check, freeze or unavailable. Keep schedule_refresh_due separate from qualifying polling.

Core policy after schedule validation and initial preparation:
~~~python
from datetime import timedelta
from src.pipeline.events import event_windows, parse_utc

def decide_action(event: dict, status: dict, now) -> str:
    windows = event_windows(event)
    if status.get("frozen_prediction_id") or now >= windows["cutoff_at"]:
        return "freeze"
    if windows["first_check_at"] >= windows["cutoff_at"]:
        return "wait"
    if now < windows["first_check_at"]:
        return "wait"
    if now >= windows["latest_generation_start_at"]:
        return "wait"
    if now >= windows["final_check_at"]:
        return "wait" if status.get("final_check_attempted_at") else "final_check"
    if status.get("actual_publication_confirmed"):
        return "wait"
    last_attempt = status.get("last_qualifying_check_started_at")
    if last_attempt and now < parse_utc(last_attempt) + timedelta(hours=1):
        return "wait"
    return "check_qualifying"
~~~

- [x] Persist status only when a check/schedule/state transition occurs; idle ticks produce no commits. Status records check start/completion, last successful check, next check, validation reason, last error, current prediction ID, final attempt and freeze selection.
- [x] Test exact boundaries using synthetic times, including a check started before cutoff whose generation completes after cutoff. A successful earlier actual forecast still receives one final check.
- [x] Re-run tests. Commit: feat: schedule qualifying checks and enforce publication windows.

### Task 3 — Fetch and validate one qualifying event

**Files:** create ml/src/pipeline/qualifying.py and ml/tests/test_qualifying_validation.py; reuse the existing throttled client in ml/src/data/jolpica.py without changing season-wide Monday fetches. Extend the narrow roster-exception contract in ml/src/pipeline/events.py, with coverage in ml/tests/test_event_timing.py, as clarified below.

Implementation detail for the existing explicit-exception requirement: an unclassified entrant is accepted only with evidence-backed `allow_model_position=true` and an explicit positive-integer `model_position` in its roster exception. This is a model input, never an official classification; preserve the missing official position in accepted source/display rows. A boolean permission alone is insufficient to choose a position. Extend the exception validator and semantic roster hash in events.py, with tests, to preserve this optional field. Existing classified no-lap entrants retain their actual classification and receive only model-gap imputation. No live event overrides are added by this task.

- [x] Write mocked-page tests for zero results, timeout, wrong event, partial pagination, changing total, duplicate IDs/positions, missing expected drivers, no-lap entrants, missing Q2/Q3 and confirmed substitution.
- [x] Run: python -m pytest ml/tests/test_qualifying_validation.py ml/tests/test_jolpica.py -v.
- [x] Implement fetch_target_qualifying(season, round_number, get_page), using the existing throttled HTTP client via injection. Return source pages and normalized rows; do not mutate Parquet during fetching.
- [x] Implement validate_qualifying(event, rows, page_evidence) returning accepted rows, roster, source version, validation notes and imputation policy, or a reason-coded validation failure. No “nonempty means complete” shortcut.
- [x] Implement replace_target_rows(existing, accepted, season, round_number) as a pure merge. Reject incoming mixed-event rows first.

Merge logic:
~~~python
import pandas as pd

def replace_target_rows(existing, accepted, season: int, round_number: int):
    target = (accepted["season"] == season) & (accepted["round"] == round_number)
    if accepted.empty or not target.all():
        raise ValueError("Accepted rows must belong to exactly the target event")
    if accepted.duplicated(["season", "round", "driver_id"]).any():
        raise ValueError("Duplicate qualifying entrants")
    keep = ~((existing["season"] == season) & (existing["round"] == round_number))
    return pd.concat([existing.loc[keep], accepted], ignore_index=True).sort_values(
        ["season", "round", "driver_id"]
    ).reset_index(drop=True)
~~~

- [x] Assert a target update leaves every other event's rows logically identical. Keep Parquet persistence outside these pure helpers; the later controller may stage the merged data only after validation.
- [x] Re-run tests. Commit: feat: validate complete qualifying data before accepting an event.

### Task 4 — Separate initial and actual-qualifying generation

**Files:** modify ml/src/model/forecast.py, ml/src/model/retrain.py and ml/tests/test_forecast.py; add relevant tests to ml/tests/test_pipeline_controller.py.

Task 4 implementation boundaries: add backward-compatible raw-table injection to ml/src/features/build_features.py and ml/src/model/quali.py so live training filters history before constructing features. Create only the generation/reuse seam of ml/src/pipeline/controller.py now: validated inputs and a caller-supplied semantic input hash determine whether to reuse a successful candidate or train the required stage(s). Canonical artifact hashing remains Task 5, and scheduling, fetching, publication, CLI, and workflow orchestration remain Task 7. The seam must not treat its supplied hash as publication evidence. Keep the legacy forecast wrapper usable for offline reconstruction without claiming that a date or cached qualifying proves historical publication/availability.

Offline compatibility only: existing date-only schedule caches may retain the legacy race-minus-one-day `qualifyingDate` display estimate in `forecast(asof, models=None)`, explicitly labeled estimated and with its source recorded. This wrapper produces a predicted-qualifying reconstruction, never claims actual availability, and never writes that estimate into canonical session timestamps. `forecast_event` and the controller seam must use explicit event metadata and must not infer qualifying timing. The legacy UI wiring is replaced in Tasks 8-9.

- [x] Add tests with injected fake regressors/classifiers to capture exact Stage 2 inputs. Test that actual mode never invokes Stage 1 and that missing/incomplete qualifying cannot enter actual mode.
- [x] Replace date-implied production mode selection with this explicit contract:

~~~python
# Public interface to implement by extracting the existing feature/prediction body:
# forecast_event(event, *, mode, history, entries, models, qualifying=None) -> dict
#
# mode == "predicted_qualifying":
#   require qualifying is None
#   build historical features from history strictly before event
#   models["quali"].predict -> estimated gaps and positions
#   models["podium"].predict_proba -> podium estimates
#
# mode == "actual_qualifying":
#   require validated qualifying for the exact event
#   use qualifying positions and modeled gaps
#   models["podium"].predict_proba only
#
# Keep forecast(asof, models=None) as an offline compatibility wrapper.
# Production controller and Streamlit must not infer current availability from
# whatever historical qualifying happens to exist in a checkout.
~~~

- [x] Factor the current feature builder into build_event_features(event, history, entries), keeping current cold-start values and strict historical filtering. Use explicit roster metadata for substitute names/teams.
- [x] For actual mode, call train_podium_live against the recorded historical cutoff only after validated input_hash changes. Do not call retrain_live, which unnecessarily fits Stage 1 too.
- [x] Test no target/future race rows in features or training, true qualifying positions preserved, and no-lap values imputed only in model input. Replace historical tests that assume date alone proves what was published.
- [x] Keep precomputed initial predictions immutable. Comparing against actual qualifying uses the saved initial; it must not regenerate a “pre-qualifying” forecast after results arrived.
- [x] Run: python -m pytest ml/tests/test_forecast.py ml/tests/test_pipeline_controller.py -v. Commit: refactor: generate explicit initial and actual qualifying forecasts.

### Task 5 — Validate and version prediction artifacts

**Files:** create ml/src/pipeline/artifacts.py and ml/tests/test_prediction_artifacts.py.

Task 5 integration boundary: modify `ml/src/model/forecast.py` only as needed to apply the specified capped probability policy and emit canonical driver identity/model-input metadata required by artifact validation. Extend forecast/controller fixture tests accordingly, using at least three eligible entrants for the sum-to-three contract. Update only the affected probability-policy descriptions in `docs/specs/ml-models.md` and `docs/specs/prediction-logic.md`; broad strategy/migration documentation remains Task 10. Do not change model families, feature definitions, training hyperparameters, or the saved initial forecast. Full controller integration, publication/eligibility receipts, and UI wording remain Tasks 6-9; artifact metadata must already identify the values as normalized podium estimates and record the probability-policy version.

- [x] Write tests for stable hashing under row/key ordering, changed timing causing a new version, timestamp-only changes causing no version, immutable collisions, invalid probabilities and wrong event identity.
- [x] Run: python -m pytest ml/tests/test_prediction_artifacts.py -v.
- [x] Implement canonical serialization with allow_nan=False. Sort driver rows by driver_id before hashing; include mode, event, training/source/model/feature versions, but exclude operational timestamps.

Core primitives:
~~~python
import hashlib
import json
import os
import tempfile
from pathlib import Path

def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")

def digest(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()

def write_immutable(path: Path, payload: dict) -> None:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(f"Immutable artifact collision: {path.name}")
        return
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".artifact-")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)  # Atomic exposure; never overwrite an existing version.
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ValueError(f"Immutable artifact collision: {path.name}")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
~~~

Review hardening: the immutable final pathname must not appear before its complete contents are written. Interrupted writes leave no partial final artifact; retries can succeed without clobbering any existing version. Reject malformed existing initial forecasts explicitly, while preserving valid older initials across schedule/roster changes. Atomic no-clobber linking requires filesystem support and fails closed when unavailable; the local Windows and CI Linux paths must be verified separately. Git publication transactions remain Task 6.

- [x] Implement validate_prediction(prediction, event) using the complete contract in section 5. Keep probabilities full precision internally; apply display rounding only at rendering. Add capped-normalization tests if production scores violate bounds.
- [x] Preserve the first initial.json; append revisions under versions/<prediction_id>.json. Status changes do not change prediction_id or generated_at.
- [x] Re-run tests. Commit: feat: store immutable forecast versions with input provenance.

### Task 6 — Publish, confirm and freeze safely

**Files:** create ml/src/pipeline/publish.py and ml/tests/test_prediction_publication.py.

- [ ] Use a temporary local bare Git repository in tests to simulate concurrent writers, rejected fast-forwards, uncertain push outcomes, failed readback and deadline overruns. No production pushes in tests. Add a fake slow transport that completes after the deadline and verify the candidate has no eligibility receipt and never replaces the prior confirmed feed selection.
- [ ] Run: python -m pytest ml/tests/test_prediction_publication.py -v.
- [ ] Implement stage_candidate, publish_candidate and confirm_publication according to section 5. Their injected clock, remote reader and Git runner must make deadline/failure tests deterministic.
- [ ] Use candidate tree/files distinct from published JSON. Promotion must retain an immutable previous confirmed ID. Confirm retrieval by expected version/checksum, not HTTP 200 alone.
- [ ] Use at most two conflict retries. On a changed event schedule, source or published version, discard/replan instead of rebasing stale output over newer data. For a disjoint stats change, rebuild the commit on the latest parent without changing forecast content.
- [ ] Implement select_final(publications, cutoff_at) and write_final(event, selection). Selection uses confirmed publication time and event identity; repeated freeze must be byte-identical.
- [ ] Add tests that a failed write/model/push/readback leaves the served version unchanged, uncertain outcomes are reconciled, an older mode cannot replace newer actual qualifying, and a run that crosses cutoff cannot become eligible.
- [ ] Re-run tests. Commit: feat: publish confirmed snapshots and freeze eligible forecasts.

### Task 7 — Add the monitor while preserving Monday operations

**Files:** create ml/src/pipeline/controller.py, ml/scripts/check_qualifying.py, ml/scripts/publish_refresh.py and .github/workflows/qualifying-monitor.yml; modify both current workflows plus precompute_next_race.py and refresh_for_next_race.py.

- [ ] Add controller tests with injected fetch/model/publisher fakes. Count calls to prove no training on wait, unavailable, incomplete, unchanged, frozen or no-time-left paths.
- [ ] Run: python -m pytest ml/tests/test_pipeline_controller.py -v.
- [ ] Implement the controller sequence: refresh due schedule -> select exact active event -> decide action -> fetch target session if due -> validate -> hash -> generate if changed -> validate output -> recheck deadline -> stage/publish -> record status.
- [ ] Define CLI commands:

~~~text
python ml/scripts/check_qualifying.py --plan --github-output <path>
    stdlib-only due gate; appends needs_work=true|false to the Actions output file;
    no model import, no qualifying fetch, no publication.

python ml/scripts/check_qualifying.py --run
    performs due work using real UTC time and persists successful status/publications.

python ml/scripts/check_qualifying.py --dry-run --now <UTC timestamp>
    fixture/local diagnostic; may read data, never changes tracked output or pushes.
    The production --run command must reject --now.

python ml/scripts/publish_refresh.py --kind weekly
    publishes only approved weekly data, snapshot, archive and metric changes.

python ml/scripts/publish_refresh.py --kind stats
    publishes only web/public/data/stats.json.
~~~

- [ ] Add the workflow below. Gate before installing ML dependencies. Skip idle ticks without creating a status commit.

~~~yaml
name: Automatic qualifying update

on:
  schedule:
    - cron: "7,22,37,52 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: f1-data-writes
  queue: max
  cancel-in-progress: false

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v5
        with:
          ref: main
          fetch-depth: 0
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: ml/requirements.txt
      - name: Check whether event work is due
        id: due
        run: python ml/scripts/check_qualifying.py --plan --github-output "$GITHUB_OUTPUT"
      - name: Install forecast dependencies
        if: steps.due.outputs.needs_work == 'true'
        run: |
          sudo apt-get update
          sudo apt-get install -y libgomp1
          python -m pip install -r ml/requirements.txt
      - name: Perform due checks and publish valid output
        if: steps.due.outputs.needs_work == 'true'
        run: python ml/scripts/check_qualifying.py --run
~~~

- [ ] Preserve Monday prediction cron "0 6 * * 1", its Python setup and its fetch/snapshot/backtest command. Change only the writer lock, additional archive/feed staged paths, and common publication step. Preserve stats cron "0 6 * 3-12 1" and npm run sync-stats; use the same writer group and stats-only publisher.
- [ ] Use queue:max consistently across these three writers, and explicit checkout ref: main after the lock is acquired. Execution re-evaluates current state; queued jobs cannot rely on a stale scheduled checkout. If the repository platform rejects queue:max, use supported serialization with an independently protected Monday path and document that adjustment.
- [ ] Integrate Monday precomputation with the new artifact contract. Before rollover, materialize any due final selection from earlier confirmed publications. Then prepare the next eligible event. Do not overwrite archived predictions or regenerate frozen races.
- [ ] Preserve Monday fetch/metrics even if no new forecast can be generated. Catch a forecast-generation failure at its boundary, retain its previous valid snapshot, record the failure, and continue completed-data/metric work.
- [ ] Before an initial exists, the monitor can prepare it from committed prior-race history only when still before qualifying. If qualifying already started, report missing_initial; do not invent a historical initial. A valid actual forecast may still be produced during its eligible window.
- [ ] Verify Monday behavior with integration tests: all original endpoints fetched, backtest still called, next-event publication occurs, and old final/initial files remain unchanged.
- [ ] Run controller/publication/integration tests. Commit: ci: add qualifying monitor and coordinate existing data writers.

Workflow definitions are local repository changes until separately authorized publication/deployment; do not create external automations during implementation.

### Task 8 — Build the saved-output reader and automatic display

**Files:** create streamlit_app/prediction_data.py, streamlit_app/prediction_view.py and ml/tests/test_saved_prediction_ui.py; modify streamlit_app/requirements.txt and ml/requirements-dev.txt.

- [ ] Add tests for valid event, wrong event, corrupt JSON, unsupported schema, network failure, version update, frozen selection, and per-event fallback isolation. A previous Austin forecast must never appear as Mexico's fallback.
- [ ] Run: python -m pytest ml/tests/test_saved_prediction_ui.py -v.
- [ ] Configure a public saved-output URL with default:
  https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data/prediction_feed.json
  Allow PREDICTION_FEED_URL to override it in the deployment.
- [ ] Implement a server-side HTTP reader with 5-second timeout, ETag/conditional requests when supported and a shared TTL of 60 seconds. Read only saved JSON. Avoid one upstream request per visitor or any API secret in browser code.
- [ ] Validate the whole single-revision feed before accepting it. Keep last-good per event in session state; an on-disk confirmed feed is a cold-start fallback only when its event/version is valid. Do not import forecast, retrain or Jolpica into this module.
- [ ] If CDN data is stale, retain the last-good feed and display its real timestamp; retry on the next fragment interval. Do not promise an exact 60-second end-to-end delay. Publication verification must test this actual URL, not just the repository checkout.
- [ ] Extract existing rendering helpers into prediction_view.py, preserving visual layout. Define render_saved_prediction(event, prediction, status) to display:
  mode text; generated time; last attempted and last successful data checks; next scheduled check;
  validation/unavailability/delay reason when relevant; frozen state after cutoff.
- [ ] Raise Streamlit's minimum to >=1.37 so st.fragment is available; pin the tested release for deployment reproducibility. Add Streamlit to test dependencies for AppTest coverage.
- [ ] Add a dedicated test harness using the saved reader/view:

~~~python
import streamlit as st
from prediction_data import read_saved_event
from prediction_view import render_saved_prediction

@st.fragment(run_every="60s")
def forecast_panel(event_id: str):
    event, prediction, status = read_saved_event(event_id)
    render_saved_prediction(event, prediction, status)
~~~

read_saved_event returns the exact event metadata, its confirmed forecast or None, and status. No inference is permitted on None. The harness renders correctly named unavailability and supports feed replacement during a single open session.

- [ ] Re-run reader/view tests. Commit: feat: display saved predictions with automatic version refresh.

### Task 9 — Verify integration, then remove RUN and model imports

**Files:** modify streamlit_app/app.py, ml/tests/test_pipeline_integration.py, ml/tests/test_saved_prediction_ui.py and docs.

- [ ] Build a synthetic event fixture with an explicit roster and fake UTC clock. Start with an initial publication, serve empty qualifying, then incomplete qualifying, then complete qualifying, then a corrected final response.
- [ ] Drive the controller and saved-output view together. Assert:
  initial survives failures; actual is published only after validation;
  unchanged inputs cause zero extra training calls; correction is eligible only before cutoff;
  freeze chooses the last confirmed version; Monday rollover retains both archives.
- [ ] Test a browser session open throughout a saved-feed update, waiting through the refresh interval without clicking or manually reloading. Assert displayed mode and prediction ID change together. AppTest alone does not prove a timed browser rerun; retain this browser acceptance check.
- [ ] After the above acceptance harness passes, replace production app wiring with the saved reader/view. Remove:
  refresh_season_data, data_version, _live_models, _run_forecast,
  button handler, live_version/refreshed_at button state,
  forecast/retrain imports, inline fallback, button help text and model-loading dependencies no longer needed by the page.
- [ ] Retain last-good display state and saved-output caches; those are read-only presentation state, not removed button state.
- [ ] Move forecast/status rendering inside st.fragment(run_every="60s"). Include automatic rollover/default event selection within the fragment or trigger a full rerun on current_event_id change. A date picker value captured outside the fragment must not prevent Monday rollover.
- [ ] Change “Real grid confirmed”, “Starting Grid”, “locked” and “today's qualifying” wording to actual qualifying, the real session timestamp and a penalties caveat where needed.
- [ ] On first load with no valid forecast, render exact target event + “Prediction temporarily unavailable”. On temporary read failure after a good load, preserve that event's last valid display and show last-checked status.
- [ ] Verify there is no model/import/API path reachable from a visitor action. Use a test that makes any Jolpica fetch or training call raise, then renders and refreshes the app successfully.
- [ ] Commit: feat: remove RUN and serve automatic saved forecasts.

### Task 10 — Documentation, migration and acceptance handoff

**Files:** README.md, docs/specs/prediction-logic.md, docs/specs/ml-models.md; tests above.

- [ ] Update strategy docs with the five-hour wait, hourly retry, final check reserve, two-hour deadline, explicit actual_qualifying mode, UTC schedule fields, source validation, saved-only UI and unchanged Monday responsibilities.
- [ ] Document operational exceptions and timing estimates. Explain that exceptional roster uncertainty fails closed until supported evidence is available; it is not a user-facing RUN workflow.
- [ ] Migrate existing saved snapshots only when their provenance is evidenced. Recover Austin's October 19 JSON from e72637bae4d6475dc2610e4f06b3e4d571577c06 as a legacy initial if needed, preserving date-only generation precision and unknown metadata as unknown. Do not assert the legacy artifact passes the new contract without those caveats.
- [ ] Use a dry run against saved fixtures before enabling the new schedule. A live historical reconstruction must be labeled retrospective and excluded from frozen evaluation.
- [ ] Run:
~~~powershell
python -m pytest ml/tests -v
python -m compileall -q ml/src/pipeline ml/scripts streamlit_app
git diff --check
~~~
  Review any dataset-dependent skips separately; all new event/controller/reader tests must run from fixtures without live network.
- [ ] Validate workflow YAML with a GitHub-aware validator, not string-presence assertions alone. Confirm original cron expressions and original Monday operations remain intact.
- [ ] Inspect the final diff: production changes are confined to this pipeline and display path. Commit the final documentation and verification evidence.
- [ ] After implementation review and deployment authorization, enable the new workflow, seed a valid feed, and verify one hosted open-page transition with saved test output before considering RUN removal deployed successfully.
- [ ] Final implementation report must include test results, saved artifact paths, workflow changes, deployed feed verification, and any still-unperformed hosted checks. Do not claim automation is live from a passing local test.

## 7. Acceptance matrix

| Scenario | Required evidence |
|---|---|
| Before first check | No qualifying HTTP call and no actual-mode forecast. |
| Five-hour wait extends past cutoff | Initial retained; reason recorded; no late model job. |
| No qualifying / timeout / incomplete response | Previous served prediction unchanged; next hourly attempt scheduled. |
| Missing Q2/Q3 for eliminated entrants | Validation accepts normal absence. |
| Substitution / no recorded lap | Explicit roster reconciliation and documented model-input handling. |
| Complete qualifying arrives | Stage 2 receives actual input; candidate validates; confirmed feed updates. |
| Same input arrives again | Same input hash; no new training or prediction version. |
| Model or publication fails | Prior confirmed output remains both served and evaluation-eligible. |
| Overlapping jobs / changed branch head | No stale overwrite; conflict revalidated; archives immutable. |
| Success followed by waiting | No ordinary qualifying polling until final verification; schedule refresh remains independent. |
| Corrections at final verification | Publish only if complete, changed, valid and confirmed before cutoff. |
| Job starts/runs beyond cutoff | No new eligible prediction; prior eligible ID stays selected. |
| Freeze job delayed | Final selection identical to the selection at cutoff, never a late-generated forecast. |
| Page remains open | Mode and prediction change without visitor input; no model or Jolpica call. |
| Wrong-event or corrupt feed | Correct event unavailability or per-event last-good value; no cross-race fallback. |
| Monday runs | Original data/metrics/next-race work occurs; all old initial/version/final archives preserved. |

## 8. Review and execution

The new requirements supersede the earlier plan's hourly weekend fetch, separate accuracy workflow, nonempty-row mode check, mutable phase archives and page-triggered inference fallback.

Execution order:
1. Event timing and roster.
2. Due-action policy.
3. Qualifying validation.
4. Explicit forecasting modes.
5. Versioned output.
6. Safe publication and freeze.
7. Monitor plus Monday integration.
8. Saved-output reader and view.
9. End-to-end verification, followed by removal of RUN.
10. Documentation, migration and deployment acceptance.

The user requested Subagent-Driven execution: a fresh implementer per task, followed by independent specification and code-quality reviews. Track verified progress in automatic-qualifying-execution.md. Keep work on feature1 and report any unperformed hosted checks; do not claim local implementation is deployed automation.
