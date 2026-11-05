# F1 Prediction Publication Logic

The predictor is a scheduled publication pipeline. Visitors read saved, validated
JSON; Streamlit never fetches Jolpica or trains a model.

Production entry points: `ml/scripts/precompute_confirmed.py` (initial forecast),
`ml/scripts/check_qualifying.py` (monitor), `ml/src/pipeline/` (validation,
state, immutable artifacts, publication), and `streamlit_app/confirmed_feed.py`
(saved-feed adapter). Older publication scripts remain for compatibility and
diagnostics; the three Actions do not invoke them.

## Workflow responsibilities

| Action | Trigger (UTC) | Input and responsibility |
| --- | --- | --- |
| Qualifying prediction publisher | Minute 7, 22, 37, 52 of every hour | Cheap due gate; exact-event Jolpica qualifying; Stage 2 only after valid changed input; confirmed publication and freeze |
| Weekly refresh (data + accuracy bar) | Monday 06:00 | Refresh results, qualifying, both standings datasets and schedule; archive prior final; prepare next initial; update benchmark and saved-forecast metrics |
| Sync F1 stats | Monday 06:00, March–December | Refresh website driver/team statistics through `npm run sync-stats`; does not train ML |

All writers share `f1-data-writes`, `cancel-in-progress: false`, `queue: max`.
Writes use fast-forward commits with conflict checks, never force pushes.
Production workflow jobs and publishing entry points are guarded for the original
repository's `main` branch. Work on `feature2` is not a live deployment.

## Race lifecycle

| Window | Background work | Saved page |
| --- | --- | --- |
| Before qualifying | Stage 1 estimates qualifying; Stage 2 predicts podium; confirm immutable initial | Using estimated qualifying |
| Qualifying end + 5 hours | First exact-event API check at the next monitor tick | Existing forecast remains |
| Missing/incomplete results | Retry no earlier than one hour after the previous check started; no training | Existing forecast remains |
| Valid results | Validate roster, classification and laps; run Stage 2; verify remote immutable bytes before cutoff | Using actual qualifying |
| After successful publication | Pause qualifying retries; continue independent schedule refresh | Latest confirmed forecast |
| Cutoff − 45 minutes | One final check for missing results or corrections | Update only on successful publication |
| Cutoff − 15 minutes | Do not start new generation | Latest confirmed forecast |
| Race start − 2 hours | Freeze the latest eligible confirmation receipt | Final saved prediction |
| Monday | Preserve previous archive and prepare next event | Roll forward |

Schedule timestamps, not hard-coded weekday assumptions, control the lifecycle.
If no observed end exists, qualifying end is explicitly estimated as start + 90
minutes. Evidence-backed observed ends and entrant exceptions belong in
`ml/config/event_overrides.json`. Schedule refresh is hourly within 72 hours of
qualifying until cutoff, otherwise daily. It is also rechecked after generation.
GitHub scheduling and queues can be delayed: ticks are opportunities, not exact
wall-clock guarantees. No delayed run may publish a new eligible forecast after
the deadline.

## Data input and model safeguards

- Fetch the exact season/round qualifying endpoint, including every validated page.
- Require event identity, unique drivers/positions, complete expected roster and
  valid lap strings. Missing Q2/Q3 is normal; evidence-backed no-lap cases retain
  their official values and carry explicit model-input fallbacks.
- Derive provisional entrants from the previous completed race. Substitutions,
  exclusions and withdrawals require documented overrides; unknown entrants fail closed.
- Filter raw historical results and qualifying before constructing rolling features.
  Target/future results never enter the training snapshot.
- Actual mode never retrains Stage 1. Unavailable and semantically unchanged
  qualifying results never retrain either model.
- Keep feature2's deterministic model settings and record code, dependency, training,
  feature, roster, schedule and qualifying hashes in each artifact.
- Probabilities are normalized estimates totaling three podium places. Qualifying
  classification is not a penalty-adjusted starting grid.

## Publication and reader contract

`web/public/data/prediction_feed.json` is the atomic current-event revision,
containing event metadata, prediction, status and publication receipt together.
Per-event files live under `prediction_snapshots/{season}-{round}/`:
`event.json`, `status.json`, immutable `initial.json`, `versions/`,
`sources/`, `publications/`, `checks/`, `feed.json` and terminal `final.json`.
`predictions/index.json` supplies archive navigation only.
`next_race_prediction.json` remains a compatibility output.

A commit/push alone is not publication proof. The publisher reads exact immutable
bytes from GitHub's raw origin and records the actual successful readback time.
Only confirmation before the deadline qualifies; feed delivery may finish later.
Freeze uses confirmation receipts, never generation time or a reconstructed forecast.
If a selected receipt's original prediction context is missing, publication fails
closed instead of inventing a replacement.

Streamlit polls every 60 seconds with a process-shared ETag cache. Failed/corrupt
reads retain the same event's last good display. Deployed default origin is
`raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data`.
`PREDICTION_FEED_URL` can select another origin ending in
`prediction_feed.json`. Legacy archives remain viewable but explicitly unconfirmed.

## Accuracy and rollout

`ml/models/live_metrics.json` remains the reconstruction benchmark, not proof of
live prediction accuracy. `ml/models/saved_forecast_metrics.json` separately
scores confirmed saved initial and frozen final forecasts. Unevidenced legacy
snapshots are excluded; no retrospective prediction is called an original.

Before merging/deploying, inspect the implementation and test report in
[feature2 execution notes](../superpowers/plans/2026-11-04-feature2-qualifying-execution.md).
Hosted Actions and an already-open deployed browser still require acceptance
verification after an authorized merge/deployment.
