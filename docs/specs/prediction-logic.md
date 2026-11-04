# F1 Prediction Publication Logic

The predictor is a scheduled publication pipeline. A visitor only reads validated JSON;
the Streamlit process does not fetch Jolpica data or run either model.

Code: `ml/scripts/precompute_next_race.py` (Monday estimate) ·
`ml/scripts/publish_qualifying_prediction.py` (hourly publisher) ·
`ml/src/publication/` (timing, validation, state machine) ·
`streamlit_app/app.py` (polling viewer).

## Forecast stages

1. Stage 1 estimates each entrant's gap to pole and qualifying classification from
   prior form, team pace, and circuit history.
2. Stage 2 combines qualifying position/gap with race-form features to estimate each
   driver's calibrated podium probability.
3. Before qualifying validation, Stage 2 receives Stage 1's estimates. After validation,
   Stage 2 receives **actual qualifying results**.

The Stage 2 probabilities are normalized to total three podium places. All training data
is strictly earlier than the target Grand Prix.

## Automated schedule

```text
Monday refresh
  └─ publish estimated-qualifying forecast for the next Grand Prix

qualifying_end_at + 5 hours
  └─ first Jolpica qualifying check at the next hourly :17 tick
       ├─ missing/invalid → update status only; retry hourly
       └─ valid → train Stage 2, validate artifact, publish actual-qualifying forecast

race_start_at - 2h30m
  └─ latest safe processing start; the final :17 tick occurs on/before this point

race_start_at - 2h
  └─ publication cutoff; freeze the latest valid race artifact
```

All decisions use UTC timestamps from the current Jolpica schedule. Qualifying end is
estimated as qualifying start plus 180 minutes. The schedule is fetched on each publisher
run so postponements move the first check and cutoff. There is no assumption that
qualifying occurs one calendar day before the race.

## Qualifying validation

The publisher accepts a classification only when:

- season, round, race, and circuit match the scheduled event;
- pagination metadata proves every response page was fetched;
- driver IDs and positive classification positions are unique;
- entrants match the latest completed race after documented withdrawals, exclusions,
  and substitutions from `ml/config/qualifying_exceptions.v1.json`;
- every supplied lap string parses to a positive finite duration and at least one valid
  lap exists.

Missing Q2/Q3 values are normal. A classified driver without a lap receives the slowest
valid qualifying gap for Stage 2. Normalized inputs are hashed; unchanged results do not
retrain, while corrected results can trigger one final republish.

## Published feed

- `next_race_prediction.json` — active compatibility snapshot
- `prediction_status.json` — mutable check/publication state
- `predictions/index.json` — active race plus archive entries
- `predictions/{season}-{round}.json` — race artifact, immutable after freezing

Streamlit polls this feed every 60 seconds. It retains the last valid in-session snapshot
on HTTP or schema failure and preserves a visitor's selected historical race.

## Model accuracy

The Monday job retains the existing walk-forward backtest. Its output is
`ml/models/live_metrics.json`; it does not run in the hourly qualifying publisher.
