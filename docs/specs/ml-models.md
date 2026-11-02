# ML models — production reference

The predictor is a two-stage LightGBM cascade. Models run only in background jobs; the
Streamlit app reads confirmed JSON and has no ML runtime dependencies.

Companion operational contract: [prediction-logic.md](prediction-logic.md).

## Summary

| | Stage 1 — qualifying | Stage 2 — podium |
|---|---|---|
| Algorithm | `LGBMRegressor` | `LGBMClassifier` wrapped by sigmoid `CalibratedClassifierCV(cv=5)` |
| Output | qualifying gap estimate, ranked to positions | per-driver top-three score, normalized to three podium slots |
| Runs for initial | Yes | Yes, using Stage-1 position/gap |
| Runs for accepted actual qualifying | No | Yes, using validated actual/model position/gap |
| Historical rows | Exact raw results/qualifying snapshot strictly before target event |

There is no warm start, online incremental update, runtime hyperparameter search, or
visitor-triggered fit. Every due changed candidate is a clean fit on a recorded snapshot.

## Leakage boundary

The pipeline filters raw history before feature construction by both event identity and
recorded result time:

```text
(season, round) < target event
and result date < recorded training cutoff
```

Qualifying rows are retained only for completed result events in that filtered set. The
target race result cannot enter training; accepted target qualifying appears only in the
actual-mode input features. Rolling/expanding historical features are also shifted so a
row cannot use its own outcome.

Each artifact records the exact training event/date/count manifest and digest. The model
manifest records code digest, hyperparameters, feature names, and library versions.

## Stage 1: qualifying gap

Target: each historical driver's best recorded Q1/Q2/Q3 time minus that event's minimum
recorded session time. Predictions are shifted to a zero minimum and ranked to model
qualifying positions.

| Feature | Definition before target event | Cold-start policy |
|---|---|---|
| `recent_quali_gap` | Mean qualifying gap over last 5 events | 1.0 s |
| `recent_quali_pos` | Mean qualifying position over last 5 | 11.0 |
| `quali_track_hist` | Mean prior qualifying gap at target circuit | recent qualifying gap |
| `team_quali_strength` | Constructor's recent event-level qualifying gap | 1.0 s |

Stage 1 runs only for `predicted_qualifying`. It is not rerun after the session; this
preserves the immutable initial for a meaningful pre-vs-actual comparison.

## Stage 2: podium estimate

The binary historical target is `position <= 3`. The classifier returns sigmoid-calibrated
per-driver scores before race-level normalization.

| Feature | Definition/source |
|---|---|
| `grid_position` | Stage-1 predicted position for initial; validated qualifying `modelPosition` for actual mode |
| `quali_time_gap_to_pole` | Stage-1 predicted gap for initial; validated model gap for actual mode |
| `recent_form` | Driver mean finish over last 5 races |
| `recent_points` | Driver mean points over last 5 races |
| `team_strength` | Constructor event-level mean finish over last 5 races |
| `track_history` | Driver mean finish at this circuit in prior visits |
| `dnf_rate` | Driver DNF share over last 5 races |

Cold starts use midfield/reliability defaults: recent form/team strength/track history
11.0, recent points 0.0, DNF rate 0.1. Actual qualifying requires an explicit accepted
position and finite model gap for every eligible entrant. A classified no-lap entrant
keeps a missing displayed gap but uses the largest valid event gap for model input. An
unclassified entrant needs an evidence-backed explicit model position; no classification
is invented.

## Hyperparameters

Both LightGBM estimators use the fixed production baseline:

```python
n_estimators=200
learning_rate=0.05
num_leaves=15
max_depth=4
min_child_samples=40
subsample=0.8
colsample_bytree=0.8
reg_lambda=1.0
random_state=42
verbosity=-1
```

Stage 2 uses sigmoid calibration with five folds. This calibrates the underlying binary
scores; the subsequent race-level normalization changes their interpretation.

## Podium-output policy

Artifact policy `capped-sum-to-three-v1` finds a proportional scale such that:

```text
estimate_i = min(1, scale * nonnegative_score_i)
sum(estimate_i) = 3
```

Inputs must be finite/nonnegative with at least three positive scores. Values remain in
`[0, 1]`, total three podium slots, and stay full precision in JSON. The display rounds
only at render time. Capping-induced ties preserve original score order; genuine score
ties use driver ID. These are normalized podium estimates, not guarantees or independent
post-normalization calibrated probabilities.

The earlier multiply-by-three rule could exceed 1. Legacy forecasts are not rewritten.

## Generation sequence

### Monday initial

1. Build the next exact event and provisional/evidence-backed roster.
2. Filter and hash the historical snapshot and pre-event feature rows.
3. Fit Stage 1 and Stage 2.
4. Build and validate a `predicted_qualifying` schema-2 artifact.
5. Publish immutable bytes, verify them through raw GitHub before qualifying starts,
   and preserve the first confirmed initial.

If Monday runs after qualifying starts, it records `missing_initial` and performs no
backdated generation. Actual mode can still be produced later.

### Actual-qualifying update

1. Wait until the state policy says a check is due.
2. Fetch and validate the exact target qualifying response.
3. Compare its semantic source version with the confirmed current source.
4. If changed and enough time remains, fit Stage 2 only on the same historical snapshot
   policy, build/validate `actual_qualifying`, and stage raw/source/check evidence.
5. Confirm exact saved bytes before the two-hour cutoff; otherwise retain the prior.

Missing, incomplete, unchanged, frozen, or insufficient-window paths make zero model
calls. A final pre-cutoff corrected session can create one further version.

## Reproducibility fields

Every canonical prediction stores:

- schema/event identity, explicit mode, generation time, and content-derived ID;
- schedule and roster versions;
- training cutoff, table/event/date/count manifest, and training data hash;
- model code hash, fixed parameters, feature columns, and dependency versions;
- exact feature-input hash and feature/probability policy versions;
- for actual mode, the accepted qualifying source version, positions/gaps, and
  imputation policy.

`initial.json`, `versions/*.json`, receipts, and `final.json` are immutable. The current
feed is a versioned projection of confirmed selections, not a model output cache.

## Evaluation

Two metrics families must remain distinct:

1. **Retrospective walk-forward benchmark** — Monday reconstructs each historical race
   by fitting on earlier races. It measures model behavior but is not evidence of what
   was shown live.
2. **Saved live evaluation** — compare the immutable confirmed `initial` and `final`
   predictions with completed results. Only this measures the forecasts actually eligible
   before their deadlines.

The existing Streamlit accuracy bar continues to show the labeled walk-forward benchmark
from `ml/models/live_metrics.json`. A later scorer may add saved-live metrics without
reclassifying retrospective reconstructions as archived forecasts.

## File map

| File | Role |
|---|---|
| `ml/src/model/forecast.py` | explicit predicted/actual forecast modes and feature assembly |
| `ml/src/model/retrain.py` | leakage-safe Stage-1/Stage-2 fits |
| `ml/src/pipeline/qualifying.py` | exact-session validation and semantic source version |
| `ml/src/pipeline/artifacts.py` | provenance, content identity, validation, immutable archives |
| `ml/src/pipeline/publish.py` | safe Git publication, availability receipts, feeds, freeze |
| `ml/src/pipeline/controller.py` | due-action orchestration and no-training failure paths |
| `ml/scripts/precompute_next_race.py` | Monday final rollover and next initial |
| `ml/scripts/check_qualifying.py` | cheap plan gate and one due monitor action |
| `streamlit_app/prediction_data.py` | validated saved-feed reader, ETag/last-good logic |
| `streamlit_app/app.py` | read-only timed fragment; no model/data API imports |

## Austin 2026 legacy caveat

The October 19 Austin snapshot predates this artifact contract. Its generation time is
known only as the date `2026-10-19`; model manifest, exact training inputs, roster/schedule
versions, and publication availability are unknown. It is retained through an immutable
Git reference for user access, but it is not schema 2, cannot be promoted into the
confirmed feed, and is excluded from frozen live evaluation.
