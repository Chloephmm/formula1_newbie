# F1 Guidebook — Implementation Plan (Next.js stack)

> Working plan — build phase by phase. Each phase has an **acceptance check** — don't move
> on until it passes. Design reference: `docs/specs/design.md`.

## Project summary

Decoupled stack: a **Python ML pipeline** produces **calibrated** per-driver podium
probabilities and exports small **static JSON** files; a **Next.js (App Router)**
frontend reads that JSON and renders the site; deployed free on **Vercel**. No backend,
no live inference, no database. Data from **Jolpica** (Ergast successor) + optional
**FastF1**. Model = LightGBM + logistic-regression baseline, wrapped in
`CalibratedClassifierCV`.

**Guardrails:**
- Build the Next.js components incrementally; keep them small and reviewable.
- Keep the frontend simple — Tailwind + Recharts + static JSON. No SSR/API routes/auth.
- Timebox: if the frontend runs long, cut polish, not the deadline.
- Scope = **podium prediction only** (predicted winner = top of the podium). Defer
  FastF1 telemetry + championship mode.

**Monorepo:** `ml/` (Python, offline) and `web/` (Next.js). The ML side writes JSON into
`web/public/data/`.

---

## Phase 0 — Repo scaffold (Day 1, morning) ✅ DONE

**Tasks**
1. Monorepo skeleton: `ml/src/{data,features,model}/ scripts/ notebooks/ data/ models/
   requirements.txt`; `web/` created later by create-next-app (Phase 4).
2. `ml/requirements.txt`: pandas, numpy, requests, scikit-learn, lightgbm, joblib,
   altair, fastf1, pyarrow.
3. Python virtualenv in `ml/.venv`; `pip install -r requirements.txt`.
4. `.gitignore` covers Python + Node (`node_modules/`, `.next/`, `web/.vercel`).

**Acceptance check:** ✅ `python -c "import pandas, lightgbm, sklearn"` works in the venv.

> **macOS / LightGBM note:** LightGBM needs `libomp.dylib` (OpenMP). If import fails with
> a `libomp` error, run `bash ml/scripts/fix_libomp_macos.sh` — it reuses an existing
> libomp (e.g. from Anaconda) and patches LightGBM's rpath. No Homebrew needed. This was
> applied on this machine; re-run the script if you recreate the venv or reinstall lightgbm.

---

## Phase 1 — Data layer (Day 1 afternoon → Day 2)  ✅ DONE

**Tasks** — under `ml/src/data/`
1. `jolpica.py` — thin client for the Jolpica REST API.
   - Base URL: `https://api.jolpi.ca/ergast/f1/`
   - Functions returning tidy DataFrames:
     - `get_race_results(season)` → `/{season}/results.json`
     - `get_qualifying(season)` → `/{season}/qualifying.json`  (includes Q1/Q2/Q3 times)
     - `get_driver_standings(season)` → `/{season}/driverStandings.json`
     - `get_constructor_standings(season)` → `/{season}/constructorStandings.json`
     - `get_schedule(season)` → `/{season}.json`
   - Handle pagination (`limit` max 100; loop with `offset`). Reuse a `requests.Session`;
     small `time.sleep` between calls.
2. `cache.py` — read/write DataFrames to `ml/data/raw/*.parquet`; fetch from API only if
   the cache file is missing.
3. `fastf1_loader.py` — **optional, defer if short on time** (v2 only).
4. `ml/scripts/fetch_data.py` — pull seasons 2014–2025 into cache.

**Acceptance check:** Fetch produces parquet files in `ml/data/raw/` and a season's
results load with expected columns (season, round, circuit, driver, constructor, grid,
position, status, points). Qualifying includes Q1/Q2/Q3 time strings.

---

## Phase 2 — Feature engineering (Day 2 → Day 3)  ✅ DONE

**Tasks** — `ml/src/features/build_features.py`
1. One row **per driver per race**, with one target column:
   `podium = 1 if finished top 3 else 0`.
2. Features (computed using only pre-race data — no leakage):
   - **v1 (Jolpica-only):**
     - `grid_position`
     - `quali_time_gap_to_pole` — driver's best quali lap − pole time, in seconds
       (parse Q1/Q2/Q3 times from Jolpica qualifying; pole = 0.0)
     - `recent_form` (avg finish, last 5 races), `recent_points` (last 5)
     - `team_strength` (constructor recent avg points/finish)
     - `track_history` (driver avg finish at this circuit, prior seasons)
     - `dnf_rate` (share of recent races not "Finished")
   - **v2 (FastF1, add after baseline works — no weather API needed):**
     - `clean_air_race_pace` — representative clean-air lap pace from that weekend's
       practice sessions or a `shift(1)` rolling average of prior races (never the race
       being predicted)
3. Sort chronologically; rolling windows grouped by driver/constructor; **always
   `shift(1)` before any rolling/expanding stat** so the current race is excluded.
   Document NaN fills for cold starts.
4. Output `ml/data/processed/features.parquet`.

**Acceptance check:** No target leakage (spot-check `recent_form` excludes the current
race), no unexpected NaNs, class balance reported (podium finishers are ~3 per ~20 — the
minority class, as expected).

---

## Phase 3 — Train, calibrate, evaluate, export (Day 3 → Day 4)  ✅ DONE

One classifier on the `podium` target. The predicted **winner** is simply the #1 driver
when sorted by podium probability — no separate win model needed.

### Calibration: LOCKED to Approach A (explicit prefit, temporal three-way split)

Do NOT use internal random CV (`cv=5`) — it shuffles seasons together and violates the
no-leakage rule. Use three disjoint, chronological slices:

```
train-fit  : seasons ≤ 2022      → fit LightGBM (learn patterns)
calibration: season   2023       → fit the probability calibrator
test       : seasons ≥ 2024      → final evaluation ONLY (never touched until the end)
```

**Reference code (the contract for `train.py` + `calibrate.py`)** — this project runs
**sklearn 1.8**, so use `FrozenEstimator` (the `cv="prefit"` form is deprecated):

```python
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator   # sklearn >= 1.6

FEATURES = ["grid_position", "quali_time_gap_to_pole", "recent_form",
            "recent_points", "team_strength", "track_history", "dnf_rate"]

train_fit = df[df.season <= 2022]
calib     = df[df.season == 2023]
test      = df[df.season >= 2024]   # set aside; do not touch until evaluate.py

base = lgb.LGBMClassifier(
    n_estimators=400, learning_rate=0.05, num_leaves=31,
    scale_pos_weight=(train_fit.podium == 0).sum() / (train_fit.podium == 1).sum(),
    random_state=42,
)
base.fit(train_fit[FEATURES], train_fit["podium"])

# FrozenEstimator = don't retrain base; fit ONLY the calibrator on the 2023 season.
calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="isotonic")
calibrated.fit(calib[FEATURES], calib["podium"])
# (older sklearn < 1.6: CalibratedClassifierCV(base, method="isotonic", cv="prefit"))
```

**Tasks** — `ml/src/model/`
1. `train.py`:
   - Make the three chronological slices above (train-fit ≤2022, calib 2023, test ≥2024).
   - Train logistic-regression **baseline** + LightGBM on the `podium` target (train-fit).
2. `calibrate.py`:
   - Wrap the fitted LightGBM in `CalibratedClassifierCV(FrozenEstimator(base),
     method="isotonic")`, fitting the calibrator on the **2023 calibration slice only**.
     Save `ml/models/podium_model.pkl` (joblib) with the feature list.
3. `evaluate.py`:
   - log-loss, ROC-AUC, **top-3 accuracy** (predicted podium ∩ actual podium),
     **top-1 accuracy** (did the #1 pick actually win — the "winner" view), baseline
     comparison.
   - Build a **reliability/calibration curve** (predicted vs observed) — the payoff of
     calibrating; export its points for the Model page.
   - Export LightGBM **feature importances** for the Model-page bars.
4. `predict.py` + `ml/scripts/build_predictions.py`:
   - `predict_race(season, round)` → drivers with `podiumProbability`, sorted desc.
   - Normalize per race so podium-probs sum to 3. Predicted podium = top 3;
     predicted winner = index 0.
   - Predict all test-season races + the next race (if qualifying exists).
5. `ml/scripts/export_json.py` — write the **data contract** into `web/public/data/`:
   - `teams.json`, `drivers.json`, `races.json`, `predictions.json`, `metrics.json`
     (shapes per design doc §6 — `metrics.json` has `podium`, `calibration`, and
     `featureImportances`).

**Acceptance check:** LightGBM ≥ baseline on log-loss; calibration curve closer to the
diagonal after calibration; all five JSON files exist in `web/public/data/`; per-race
podium-probs sum to ~3; `featureImportances` present in `metrics.json`.

---

## Phase 3.5 — Qualifying model + dual-mode (two-stage) prediction  ✅ DONE

A two-stage pipeline so a race can be predicted BEFORE qualifying, and compared against
the real grid afterward. Reuses Phase 1 data; does NOT change Phase 1 or Phase 2.

**Stage 1 — qualifying model** (`src/model/quali.py`): predict each driver's
qualifying gap-to-pole from history.
- Target: `quali_time_gap_to_pole` (seconds). Features (leakage-safe, pre-event only):
  recent qualifying form (`recent_quali_gap`, `recent_quali_pos`), qualifying track
  history (`quali_track_hist`), team qualifying pace (`team_quali_strength`).
- LightGBM regressor, season split (train ≤2022). Saves `models/quali_model.pkl`.

**Two prediction modes** (`scripts/predict_dual.py`):
- **MODE 1 — pre-qualifying (two-stage):** Stage-1 predicts the grid → feed predicted
  grid + gap into the Stage-2 race model → podium. Always available.
- **MODE 2 — real-grid:** use actual qualifying (once it exists) → Stage-2 race model →
  podium. Available only after qualifying.

**Honesty:** errors compound (a wrong predicted grid flows into the podium); the
qualifying model is ~3.4 grid positions off on average. Mode 2 (real grid) is always more
trustworthy — Mode 1's value is forecasting before the weekend.

**Website date logic (implemented later in Phase 5):** `export_json.py` writes a
dual-mode `predictions.json` per race
(`{ qualifyingDate, hasRealGrid, preQualifying:[...], realGrid:[...] }`); the Predict page
compares `today` vs `qualifyingDate` to choose which to highlight, and shows both side by
side when available.

**Acceptance check:** `quali_model.pkl` trained; `predict_dual.py` prints Mode 1 always
and Mode 2 once qualifying exists; predicted podiums shown side by side.

---

## Phase 4 — Next.js frontend scaffold (Day 4)

**Tasks** — in repo root, create the app under `web/`
1. `npx create-next-app@latest web` → choose **TypeScript, App Router, Tailwind, ESLint**.
2. `npm install recharts` inside `web/`.
3. `web/lib/types.ts` — TS interfaces mirroring the JSON contract (Team, Driver, Race,
   Prediction, Metrics).
4. `web/lib/data.ts` — helpers to import the JSON from `public/data/` (or `fs`-read at
   build time for the static export).
5. Global layout: `web/app/layout.tsx` with a minimal nav (Home / History / Teams /
   Predict / Model) and Tailwind theme tokens (F1-red accent, light background).

**Acceptance check:** `npm run dev` in `web/` serves a themed shell with working nav and
no type errors; a test import of `teams.json` logs real data.

---

## Phase 5 — Pages (Day 4 → Day 6)

Build in this order; keep each page short and scannable. Build components
incrementally, then review.

1. **Home** (`app/page.tsx`) — 5 welcome variants, pick one at render; 3-line "What is F1?";
   nav cards.
2. **History** (`app/history/page.tsx`) — hand-written ~6-milestone timeline component.
3. **Teams** (`app/teams/page.tsx`) — team cards from `teams.json`; selecting a team
   reveals its drivers + stats (a client component for the selection state); one clean
   points bar chart.
4. **Predict** (`app/predict/page.tsx`) — race `<select>` from `races.json`; a **podium
   visual** for the top-3 (light/minimal re-style — center the P1, subtle gold/silver/
   bronze accents); Recharts horizontal bar of **podium probability** per driver, sorted;
   plain-English explanation of the top pick; caption that these are model estimates.
5. **Model** (`app/model/page.tsx`) — pipeline description, **feature-importance bars**
   (from `metrics.json.featureImportances`), the podium model's metrics (incl. top-3 and
   top-1 accuracy), the **calibration curve** (Recharts line vs diagonal), and an honest
   **Limitations** section. (Do NOT add fake live "feature weight" sliders — importances
   are static, real model output.)

**Acceptance check:** All five pages render from JSON, nav works, the Predict chart
updates on race change, and the Model page shows real metrics + calibration curve.

---

## Phase 6 — Polish, docs & deploy (Day 6 → Day 7)

**Tasks**
1. Responsive pass (mobile widths), consistent spacing/typography, accessible chart colors.
2. README: architecture diagram, screenshots/GIF, "what I learned", run instructions for
   both `ml/` and `web/`, link to live app.
3. Clean notebooks (`eda.ipynb`, `model_dev.ipynb`) into a readable narrative.
4. Commit the exported JSON (so the deployed site needs no Python at build time).
5. **Deploy:** push to GitHub → import the repo on Vercel → set **root directory = `web/`**
   → deploy. Confirm free-tier build succeeds.
6. Final QA: typos, dead links, 404s, theme consistency.

**Acceptance check:** Live Vercel URL works end-to-end; README links to it.
