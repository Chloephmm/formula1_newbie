# F1 prediction and publication logic

This is the operational source of truth for how an event moves from a saved initial
forecast to an actual-qualifying forecast and then to a frozen evaluation selection.
The model details are in [ml-models.md](ml-models.md).

## Principle: the website is a reader

`streamlit_app/app.py` imports only the saved-feed reader and view. It cannot call
Jolpica, write Parquet, load LightGBM, or train a model. Its timed fragment checks the
confirmed JSON feed about every 60 seconds while a page is open. A network, validation,
or stale-CDN failure retains only that same event's newer last-good revision; another
race is never substituted.

The global feed is:

```text
https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/
  web/public/data/prediction_feed.json
```

`PREDICTION_FEED_URL` can override this in a controlled deployment. Responses use a
shared 60-second server cache and ETag conditional requests. A single feed revision
contains the event, status, current/previous/initial selections, and receipts so mode
and prediction ID cannot change independently.

## Event timing (UTC)

Every event requires explicit `qualifying_start_at` and `race_start_at`. Jolpica does
not provide an observed qualifying finish. Unless an evidence-backed observed finish
or event override exists, the controller records:

```python
qualifying_end_at = qualifying_start_at + 90 minutes
end_time_estimated = True
first_check_at = qualifying_end_at + 5 hours
cutoff_at = race_start_at - 2 hours
final_check_at = cutoff_at - 45 minutes
latest_generation_start_at = cutoff_at - 15 minutes
```

These are timestamps, not weekday assumptions. Friday qualifying, Saturday races, and
schedule changes use the same rules. Cron jobs may be delayed, so every decision is
recalculated from real UTC at execution time.

## State machine

| State/action | Rule |
|---|---|
| `waiting_initial` | Monday may create the first initial only before qualifying starts. A missed deadline becomes `missing_initial`; it is never backdated. |
| `waiting_qualifying` | Keep the confirmed initial and make no qualifying request before `first_check_at`. |
| `check_qualifying` | Fetch only `/{season}/{round}/qualifying`; validate exact event/session, pagination, roster, positions, and timing. |
| `retry_wait` | Missing, timeout, incomplete, or recoverable validation failure; next ordinary attempt is one hour after the prior attempt started. No training. |
| `published_actual` | A changed complete source produced and confirmed an `actual_qualifying` artifact. Pause ordinary retries. |
| `final_check` | Once at/after `final_check_at`, even after an earlier actual success. A corrected complete source may replace the current version only before cutoff. |
| `frozen` | At cutoff, select the latest receipt whose real availability was confirmed before cutoff. A delayed freeze writer may materialize that fixed choice later. |
| `unavailable` | No confirmed eligible selection exists. Display the exact event plus “Prediction temporarily unavailable”. |

If the five-hour wait reaches/exceeds the cutoff, keep the initial and record
`wait_exceeds_cutoff`. If less than the 15-minute generation reserve remains, do not
start a model. A final-check failure never restarts an uncontrolled retry loop.

## Qualifying validation

The qualifying input must prove all of the following before model code is called:

- Formula 1 series, exact season/round/race/circuit, and `QualifyingResults` session.
- Stable provider `limit`/`total`, contiguous offsets, and exact declared row coverage.
- Unique driver IDs and official positive classification positions when present.
- Coverage of the evidence-backed event roster, including confirmed substitutes,
  withdrawals, and explicitly authorized no-lap cases.
- Every present Q1/Q2/Q3 value parses to a finite positive lap time; absent Q2/Q3 for
  eliminated drivers is normal.
- At least one usable event lap time. An all-missing response is rejected.

The roster begins with the last completed race only as a provisional baseline. Changes
need a same-event source or an entry in `ml/config/event_overrides.json` with reason,
source URL, and observation timestamp. Uncertain entries fail closed; they do not add a
visitor control.

The accepted source version hashes semantic qualifying content, roster policy, and exact
event identity. Retrieval time, page layout, page/row order, and equivalent lap strings
do not create a new version. A repeated version produces no additional training.

## Two explicit forecast modes

### `predicted_qualifying`

Created before qualifying. Stage 1 predicts each eligible driver's qualifying gap and
ranks it; Stage 2 uses that predicted position/gap plus pre-event form/team/track inputs
to estimate the podium. The first confirmed initial is immutable.

### `actual_qualifying`

Created only from `AcceptedQualifying`. Stage 1 is not rerun and the original initial is
not reconstructed. Stage 2 uses:

- official qualifying classification as displayed `position`;
- model-only `modelPosition` for an explicitly authorized unclassified/no-lap entrant;
- each driver's minimum recorded Q1/Q2/Q3 time minus the event's minimum recorded
  session time as the timing feature;
- largest valid event gap for a classified no-lap driver's model input, while the
  displayed official gap remains missing.

“Actual qualifying” is not a penalty-adjusted starting grid. The UI says so explicitly.

## Artifacts and eligibility

```text
web/public/data/
  prediction_feed.json
  next_race_prediction.json             compatibility projection
  prediction_snapshots/<season>-<round>/
    event.json
    initial.json
    versions/<prediction_id>.json
    publications/<publication_id>.json
    final.json
    status.json
    checks/<check_id>.json
    sources/<qualifying_source_version>.json
```

Schema-2 predictions are content-addressed and validate event identity, mode, roster,
schedule, model/provenance manifests, input hashes, entrant coverage, positions/gaps,
and podium-output policy. Versions and the first initial are append-only.

Publication uses a private Git index on the latest remote head and fast-forward-only
pushes. It confirms the exact committed prediction bytes through the same raw GitHub
origin used by the page. That readback timestamp—not generation time, local commit time,
workflow trigger time, or later feed delivery—is eligibility evidence. Feed display may
lag, but a newly confirmed forecast at/after the cutoff is ineligible.

At freeze, `final.json` records the deterministic latest eligible receipt. It cannot be
reconstructed from model output later or silently reopened after a schedule change.

## GitHub Actions responsibilities

### Monday data + accuracy (`refresh-predictions.yml`)

The original Monday 06:00 UTC work remains:

1. Fetch results, qualifying, driver standings, constructor standings, and schedule.
2. Materialize the prior event's due final from existing receipts.
3. Prepare the next event and confirm one initial if still before qualifying.
4. Recompute the existing walk-forward accuracy benchmark.
5. Publish completed outputs even if an independent snapshot/backtest step fails, then
   report the failure.

It never overwrites an old initial/version/final. A failed next-event model does not
discard data or metrics already completed.

### Stats (`sync-stats.yml`)

The existing March–December Monday job still runs `npm run sync-stats` and publishes only
`web/public/data/stats.json`.

### Qualifying monitor (`qualifying-monitor.yml`)

The workflow wakes at minutes 07, 22, 37, and 52. A standard-library-only `--plan` gate
runs before installing model dependencies. A due `--run` refreshes schedule metadata,
performs at most one exact-session attempt, and publishes only validated changed work.
`--dry-run --now <UTC>` reports the decision without fetch, model, tracked write, commit,
or push. Production `--run` rejects an injected clock.

All writers share `f1-data-writes` with `queue: max`; none force-push.

## Evaluation and legacy Austin forecast

The Monday reconstruction backtest remains a retrospective benchmark and is labeled as
such. Live accuracy must instead score saved `initial.json`/`final.json` artifacts against
completed results.

Austin 2026's October 19 snapshot is preserved by immutable Git evidence in
`prediction_snapshots/2026-18/legacy_initial_reference.json`. Its generation time has
date-only precision; training input, model, roster, schedule, and publication metadata
are unknown. It is accessible as a legacy forecast but is not schema 2, is not a
confirmed publication receipt, and must not enter automatic frozen evaluation.

## Failure behavior

- Missing/incomplete/unchanged/late input: no model fit; keep prior confirmed output.
- Model or publication failure: keep prior served and evaluation-eligible output.
- Wrong-event/corrupt feed: exact-event last-good or explicit unavailability only.
- Concurrent writer/path change: revalidate/replan; never stale-overwrite or force-push.
- Schedule change before freeze: recompute deadlines and require a new event hash.
- Schedule change after freeze: preserve final and flag operator review.
