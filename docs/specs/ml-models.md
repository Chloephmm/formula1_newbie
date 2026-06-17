# ML models — data-science reference

The single source of truth for the **machine-learning** side of the predictor: which
models, which features, how they're split/trained/calibrated, and what runs when the
RUN button retrains them.

Companion docs: [`prediction-logic.md`](./prediction-logic.md) (UX flow & modes) ·
visual one-pager: [`assets/prediction-flow.svg`](./assets/prediction-flow.svg).

Code: `ml/src/features/build_features.py` · `ml/src/model/quali.py` ·
`ml/src/model/retrain.py` · `ml/src/model/forecast.py` · `ml/src/model/train.py`.

---

## TL;DR

Two LightGBM models in a cascade:

| | Stage 1 — Quali model | Stage 2 — Podium model |
|---|---|---|
| Algorithm | `LGBMRegressor` | `LGBMClassifier` + `CalibratedClassifierCV` (sigmoid, 5-fold CV) |
| Output | `quali_gap` (seconds to pole) → ranked → grid | calibrated **P(top-3)** per driver → normalized → 🥇🥈🥉 |
| Features | 4 (quali form, team pace, track history) | 7 (grid+gap, recent form, team strength, track, DNF) |
| Rows | ~4.5k (one per driver-quali) | ~5k (one per driver-race) |
| Calibrated | n/a | yes (sigmoid / Platt) |

**Both stages are retrained live on every prediction**: fit on every race strictly
before the target Grand Prix (expanding window, leakage-safe). No `.pkl` is loaded
at runtime. The offline trainers in `train.py` / `quali.train_quali` still exist
solely to produce honest **held-out evaluation metrics** for the metrics page —
they never serve a live prediction.

---

## Stage 1 — Qualifying model

### What it predicts

- **Target `y` = `quali_gap`** — each driver's best qualifying lap minus the pole
  lap, in **seconds**. Pole sitter = 0.000.
- The continuous predictions are **ranked per race** → predicted grid P1…P20.

### Features (4)

All features are computed **before** the target session — `shift(1)` everywhere, no
peeking at the current race.

| Feature | Definition |
|---|---|
| `recent_quali_gap` | Driver's avg gap-to-pole over their last 5 qualifyings (rolling, `shift(1)`) |
| `recent_quali_pos` | Driver's avg quali position over their last 5 qualifyings |
| `quali_track_hist` | Driver's avg gap-to-pole **at this circuit** in prior visits (expanding, `shift(1)`) |
| `team_quali_strength` | Constructor's avg gap-to-pole over its last 5 races (race-level aggregation) |

Cold-start fills: mid-field defaults (`recent_quali_gap=1.0s`, `recent_quali_pos=11.0`,
`team_quali_strength=1.0s`), `quali_track_hist` falls back to `recent_quali_gap`.

### Hyperparameters

Conservative config — small dataset → favor shallow trees + regularization:

```python
n_estimators=200, learning_rate=0.05, num_leaves=15, max_depth=4,
min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
reg_lambda=1.0, random_state=42, verbosity=-1
```

### Training (live, every prediction)

```python
# retrain.py
target = int(season) * 100 + int(rnd)
q = build_quali_features().dropna(subset=[QTARGET])
q = q[(q["season"] * 100 + q["round"]) < target]
model = LGBMRegressor(**_LGBM_KW).fit(q[QUALI_FEATURES], q[QTARGET])
```

The `season*100 + round` integer is a cheap "race index" — `202607` < `202608` so
the target race cleanly excludes itself. No calibration step (it's a regressor).

---

## Stage 2 — Podium model

### What it predicts

- **Target `y` = `podium`** ∈ {0, 1}, where `podium = (position ≤ 3)`.
- The classifier outputs `P(top-3)` per driver, calibrated so the probability
  literally means what it says (a "70%" really *is* ~70%).
- Per race, the 20 probabilities are **normalized to sum to 3** (3 podium slots) and
  sorted descending → top 3 = predicted podium, #1 = predicted winner.

```python
p = podium_model.predict_proba(X)[:, 1]   # calibrated P(top-3) per driver
p = p * 3 / p.sum()                        # normalize: ~20 drivers → 3 slots
# sort desc → top 3 = predicted podium
```

### Features (7)

| Feature | Definition |
|---|---|
| `grid_position` | Starting grid slot. Source = Stage-1 *predicted* grid in **Mode 1**; **real qualifying** in Mode 2. |
| `quali_time_gap_to_pole` | Lap-time gap to pole (s). Same source as `grid_position`. |
| `recent_form` | Driver's avg finish over last 5 races |
| `recent_points` | Driver's avg points over last 5 races |
| `team_strength` | Constructor's race-level finish avg over last 5 races (computed at **race-level** → no teammate same-race leakage) |
| `track_history` | Driver's avg finish at this circuit, prior visits only |
| `dnf_rate` | Driver's DNF rate over last 5 races |

Cold-start fills: `recent_form/team_strength/track_history → 11.0` (mid-field),
`recent_points → 0.0`, `dnf_rate → 0.1`, `quali_time_gap_to_pole → race-max → 3.0s`.

### Hyperparameters

Same as Stage 1.

### Training (live, every prediction)

```python
# retrain.py
cutoff = pd.Timestamp(cutoff_date).normalize()
df = build_feature_table()
train = df[df["date"] < cutoff].dropna(subset=["podium"])
model = CalibratedClassifierCV(LGBMClassifier(**_LGBM_KW), method="sigmoid", cv=5)
model.fit(train[FEATURES], train["podium"])
```

**Why 5-fold CV calibration?** With an expanding window the most recent season is
usually the *most informative* — holding it out for calibration would waste it.
CV calibrates without sacrificing any rows for fitting.

---

## The training rule, in one line

> **Train on every race strictly before the target Grand Prix.**

Stage 2 uses a **date** cutoff (`date < target_date`); Stage 1 uses an integer
**race index** (`season*100 + round < target_index`). Same intent, two natural
boundaries for the two row shapes.

---

## Leakage safety

Two independent walls:

1. **Feature-level** — every rolling/expanding stat uses `.shift(1)` so the current
   race is excluded from its own input features. Team strength is aggregated at
   the race level (not driver level) to prevent teammate same-race leakage.
2. **Row-level** — `date < cutoff` (Stage 2) or `(season*100+round) < target`
   (Stage 1) guarantees no future-race **row** ever enters training.

---

## Evaluation

### Held-out metrics (reported on the metrics page)

Produced offline by `train.py` and `quali.train_quali` on a locked split
(≤2022 fit / 2023 calibrate / ≥2024 test). These numbers don't change when the
live model retrains — that's deliberate, so the reported accuracy stays honest
and stable.

| | LightGBM (shipped) | XGBoost (benchmark) | Logistic (baseline) |
|---|---|---|---|
| AUC | 0.935 | 0.937 | (lower) |
| Top-1 accuracy | shipped | tied AUC, weaker top-1 | baseline |
| Calibration | sigmoid on 2023 | sigmoid on 2023 | — |

Stage 1 (from `quali_metrics.json`): grid error **±3.4** positions,
gap MAE **0.60s**, **182** training races.

### Walk-forward backtest (live model)

`ml/scripts/backtest_live.py` simulates the live regime race-by-race over recent
seasons (for each test race: fit on all prior races, predict, score), and
compares against a frozen ≤2022 fit on the same races. Run with `--write` to dump
`ml/models/live_metrics.json` — the **Streamlit accuracy bar reads its `2024-2026`
window from this file**, so the headline numbers describe the production regime,
not a frozen split. (The separate Next.js metrics page still uses the held-out
`metrics.json` / `quali_metrics.json`.)

| Window | metric | FROZEN ≤2022 | LIVE (all-before) |
|---|---|---|---|
| 2024–26 (54 races) | podium hit | 69.8% | **70.4%** |
| | quali pole acc | 22.2% | **31.5%** |
| | quali gap MAE | 0.669s | **0.584s** |
| 2026 only (6 races) | podium hit | 55.6% | **61.1%** |
| | quali pole acc | 0.0% | **16.7%** |
| | quali gap MAE | 0.623s | **0.470s** |

Gains grow with **recency** — biggest on 2026, where new regulations and rookies
make pre-2023 racing the least representative.

**What the quali metrics mean:**

- **Quali pole accuracy** — share of races where the predicted P1 matches the
  actual pole sitter. Higher is better.
- **Quali gap MAE** — mean absolute error (seconds) between predicted and actual
  gap-to-pole, taken per driver and averaged. Lower is better. This feeds Stage 2,
  so a better gap → a better podium.

---

## Inference flow

```
First paint (or date change)
   │
   ├─ matching precomputed snapshot in web/public/data/next_race_prediction.json?
   │     yes → use snapshot (instant)
   │     no  → forecast() retrains inline (one-time spinner, then cached)
   │
RUN clicked
   │
   └─ refresh_season_data() pulls fresh Jolpica parquet → cache invalidated
        │
        ▼
     retrain_live(target_date, season, rnd)
       ├─ quali model       (fit on races < target index)
       └─ podium model      (fit on races < target date, 5-fold sigmoid)
        │
        ▼
     forecast(asof, models=<retrained pair>)
       ├─ Mode 1 (date ≤ quali day):
       │     Stage 1 → predict gaps → rank → grid → feed Stage 2
       │     Stage 2 → P(top-3) → normalize → 🥇🥈🥉
       └─ Mode 2 (date > quali day, real quali present):
             skip Stage 1; pull real grid + real gap from Jolpica
             Stage 2 → P(top-3) on the real grid → 🥇🥈🥉
```

Caching keys the retrain result by the raw-data fingerprint, so re-clicking RUN
without new data is instant.

The **precomputed snapshot** is the same forecast result stored as JSON, written
by `ml/scripts/precompute_next_race.py`. It exists only to skip the ~10–15s retrain
on first page load — re-run it before each Grand Prix weekend (or in CI) to keep
it current.

---

## What the live model does **not** do

- ❌ No warm-start / fine-tuning. Each retrain is a clean fit from scratch.
- ❌ No hyperparameter search at runtime. We reuse `_LGBM_KW` (offline-tuned).
- ❌ No model selection at runtime. LightGBM is hardcoded; the logistic baseline
  and XGBoost benchmark are evaluated offline only.
- ❌ No incremental learning between races within a session. Each forecast call
  refits; the Streamlit app caches by data fingerprint.

---

## File map

| File | Role |
|---|---|
| `ml/src/features/build_features.py` | Stage-2 feature table + `FEATURES` constant |
| `ml/src/model/quali.py` | Stage-1 feature builder, `QUALI_FEATURES`, offline trainer (for metrics) |
| `ml/src/model/train.py` | Stage-2 offline trainer (for metrics — locked split, FrozenEstimator) |
| `ml/src/model/retrain.py` | **Live trainers** (`train_podium_live`, `train_quali_live`, `retrain_live`) |
| `ml/src/model/forecast.py` | Inference: Mode 1 / Mode 2 pipeline; retrains internally when no models passed |
| `ml/scripts/precompute_next_race.py` | Writes `next_race_prediction.json` for instant first paint |
| `ml/scripts/refresh_for_next_race.py` | One command: fetch → precompute snapshot → (opt) backtest |
| `.github/workflows/refresh-predictions.yml` | Scheduled CI that runs the refresh and commits the results |
| `ml/scripts/backtest_live.py` | Walk-forward backtest, frozen vs live (`--write` → `live_metrics.json`) |
| `ml/models/live_metrics.json` | Live-model backtest numbers shown in the Streamlit accuracy bar |
| `streamlit_app/app.py` | RUN button → `refresh_season_data` + `retrain_live` (cached) |
