# Reproducing and safely correcting a forecast

## Runtime

Both ML Actions use Ubuntu 24.04, CPython 3.11.14 and `ml/requirements-lock.txt`.
The lock pins all resolved runtime dependencies. `requirements-constraints.txt`
preserves the audited core ML versions when deliberately regenerating the lock.
Neither the Monday schedules nor their commit allowlists have changed.

Windows setup from the repository root (does not alter the Streamlit environment):

```powershell
uv venv --python 3.11.14 ml/.venv
uv pip install --python ml/.venv/Scripts/python.exe -r ml/requirements-lock.txt pytest==9.0.2
ml/.venv/Scripts/python.exe -m pytest ml/tests --ignore=ml/tests/test_streamlit_smoke.py -q
python -m pytest ml/tests/test_streamlit_smoke.py -q
```

On Ubuntu use `python3.11 -m venv ml/.venv` and `ml/.venv/bin/python` instead.
Install the same lock with `python -m pip install -r ml/requirements-lock.txt`.
Exact published rounded results are expected to reproduce with the same code,
data and runtime. Windows/Linux numerical identity is not promised. No claim is
made that this reconstructs the unknown environment of the old saved forecast.

Live fits use stable season/round/driver ordering, CPU LightGBM, one thread,
seed 42 and deterministic column-wise histograms. Predictive hyperparameters,
feature lists and sigmoid five-fold calibration are unchanged.

## Correction workflow

Create a candidate outside the public feed; refreshing here fetches only the
calendar. Session dates come from Jolpica, not race-date arithmetic.

```powershell
ml/.venv/Scripts/python.exe ml/scripts/precompute_next_race.py --asof 2026-10-30 --refresh-schedule --candidate-output ml/reports/mexico-2026-candidate.json
ml/.venv/Scripts/python.exe ml/scripts/compare_prediction.py --before web/public/data/next_race_prediction.json --candidate ml/reports/mexico-2026-candidate.json --output ml/reports/mexico-2026-comparison.json
ml/.venv/Scripts/python.exe ml/scripts/precompute_next_race.py --asof 2026-10-30 --publish-candidate ml/reports/mexico-2026-candidate.json
ml/.venv/Scripts/python.exe ml/scripts/backtest_live.py --write
```

The publish command validates the event, UTC timestamps, expected driver codes,
positions, gaps and probabilities before touching the feed. It requires the
same active race, estimated mode, no frozen artifact, and an open processing
window; it checks the cutoff again at the write boundary. After the deadline,
candidate generation remains diagnostic only. The default Monday invocation
still writes only the active snapshot; the hourly publisher synchronizes the
archive and status. A manual candidate publication synchronizes all four JSON
interfaces. It does not commit or push anything.

## Provenance and feature semantics

Schema version 2 accepts optional `training_metadata.stage1` and `.stage2`.
Each genuine fit records exclusive cutoff, row/race counts, raw input hashes,
selected training-table hash, lock hash, code revision/dirty flag/content hash,
runtime/library versions, model parameters and UTC generation time. Raw-file
hashes describe the complete cached files, while the training-table hash describes
only selected pre-cutoff rows. Actual qualifying preserves Stage 1 metadata and
replaces Stage 2 metadata; an unannotated replacement model cannot inherit old
Stage 2 provenance. Historical snapshots are not retroactively annotated.

`Finished`, `Lapped`, and `+N Lap(s)` are non-DNF statuses after case/whitespace
normalization. Unknowns, retirements, non-starts and disqualifications retain the
existing DNF treatment. Pit-lane grid defaults use that event's valid maximum
(or entrant count when all grids are missing), never a future event's field size.

The existing accuracy bar's podium backtest uses **actual qualifying** and an
**uncalibrated base model**. It is not an end-to-end accuracy measurement of the
estimated-qualifying two-stage forecast. The repair recomputes those existing
metrics without changing the evaluation methodology or UI.
