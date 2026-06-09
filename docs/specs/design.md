# F1 Guidebook — Design Doc

**Date:** 2026-06-01
**Author:** Chloe Pham

## 1. Purpose

A beginner-friendly website that makes Formula 1 fun and easy. The site teaches F1 basics through clean content pages and showcases a real, decoupled ML pipeline that predicts each race's **podium (top 3)** with **calibrated** probabilities (the top pick = predicted winner).

## 2. Goals

**Goals**
- Teach F1 history, teams, and drivers simply and at a high level.
- Demonstrate an end-to-end, **decoupled** data-science pipeline: ingest → clean →
  feature-engineer → train → **calibrate** → evaluate → export static JSON.
- Predict, per race, each driver's **podium (top-3) probability**. The highest-ranked
  driver is the predicted winner — so the single podium model covers both.
- A modern, minimal, aesthetic frontend that renders that JSON.


## 3. Architecture

```
┌─────────────────────────┐        ┌──────────────────────────┐
│   Python ML pipeline     │  JSON  │     Next.js frontend      │
│  (offline, run by you)   │ ─────▶ │  (App Router + Tailwind)  │
│                          │ static │                           │
│ Jolpica/FastF1 → features│ files  │ reads JSON → renders pages│
│ → train → CALIBRATE →    │        │ → charts (Recharts)       │
│ evaluate → export JSON   │        │                           │
└─────────────────────────┘        └──────────────┬───────────┘
                                                   │ git push
                                                   ▼
                                            ┌─────────────┐
                                            │   Vercel    │ (free, auto-deploy)
                                            └─────────────┘
```

**Key principle — decoupling:** the ML side never runs in production. It produces small
JSON artifacts that are committed into the web app's `public/data/`. The frontend is a
pure static renderer. This is the portfolio-friendly separation reviewers like.

## 4. Tech Stack

- **ML / data (Python):** pandas, numpy, requests, scikit-learn, LightGBM, joblib.
  - Data: **Jolpica** API (Ergast successor) + **FastF1** library (optional in v1).
  - **Calibration:** `CalibratedClassifierCV` (isotonic or Platt) + reliability curve.
- **Frontend:** **Next.js (App Router)** + **TypeScript** + **Tailwind CSS** +
  **Recharts** (charts). Static data loaded from `public/data/*.json`.
- **Hosting:** **Vercel** (free), auto-deploy from GitHub.
- **Cost:** $0.


**Guardrails (to fit 1 week):**
1. Build frontend components incrementally — keep them small and reviewable.
2. Keep frontend simple — Tailwind, one chart lib, static JSON only. No SSR/API
   routes/auth.
3. Timebox: if frontend runs long, cut polish, not the deadline.

## 5. Repository Layout (monorepo)

```
formula1_newbie/
├── ml/                       # Python pipeline
│   ├── src/
│   │   ├── data/             # jolpica.py, fastf1_loader.py, cache.py
│   │   ├── features/         # build_features.py
│   │   └── model/            # train.py, calibrate.py, evaluate.py, predict.py
│   ├── scripts/              # fetch_data.py, build_predictions.py, export_json.py,
│   │                         #   fix_libomp_macos.sh
│   ├── notebooks/            # eda.ipynb, model_dev.ipynb
│   ├── data/                 # raw/ (gitignored), processed/
│   ├── models/               # saved calibrated model
│   └── requirements.txt
├── web/                      # Next.js app
│   ├── app/                  # App Router: page.tsx, history/, teams/, predict/, model/
│   ├── components/           # cards, charts, nav, layout
│   ├── public/data/          # JSON exported by the ML pipeline (committed)
│   ├── lib/                  # JSON loaders, types
│   └── package.json
├── docs/specs/
└── README.md
```

## 6. Data Contract (JSON the ML side exports → web consumes)

Small, versioned files in `web/public/data/`:

- `teams.json` — `[{ id, name, color, points, wins, drivers: [...] }]`
- `drivers.json` — `[{ id, name, team, nationality, wins, podiums, points }]`
- `races.json` — `[{ season, round, name, circuit, date }]` (for the Predict selector)
- `predictions.json` — `{ "<season>-<round>": [{ driver, team, podiumProbability }], ... }`
  (podium probabilities calibrated and normalized to sum to 3 per race — three podium
  spots; drivers sorted by podiumProbability, so index 0 = predicted winner)
- `metrics.json` — `{ podium: {logLoss, rocAuc, top3Accuracy, top1Accuracy, baseline}, calibration: [...], featureImportances: [{feature, importance}] }`
  (`top1Accuracy` = did the #1 driver by podium-prob actually win — the "winner" view)


## 7. ML Pipeline Detail

- **Target (single binary classifier):** `podium` — `y = 1 if finished top 3 else 0`.
- **Features (v1, Jolpica-only):** grid position, **`quali_time_gap_to_pole`** (driver's
  best quali lap minus pole time, in seconds — from Jolpica Q1/Q2/Q3 times), recent form
  (last 5), team strength, track history, DNF rate.
- **Features (v2, FastF1 — add after baseline works):** **`clean_air_race_pace`** — the
  driver's representative pace in clean air (no car close ahead), computed from that
  weekend's practice sessions or a rolling average of prior races (never the race being
  predicted). Requires FastF1 lap data; no weather API needed.
- **Models:** logistic-regression baseline + LightGBM. Wrap the chosen model in
  `CalibratedClassifierCV` so probabilities are trustworthy.
- **Feature importance:** export LightGBM `feature_importances_` for the Model page bars.
- **Split (LOCKED — three-way, chronological):** train-fit ≤2022, calibration = 2023,
  test ≥2024. Calibrate with **Approach A**: `CalibratedClassifierCV(FrozenEstimator(base),
  method="isotonic")` (sklearn ≥1.6 — this project runs sklearn 1.8; on older sklearn use
  `cv="prefit"`) fit on the 2023 slice only. No random CV — it would shuffle seasons and
  leak. Test is touched only for final evaluation.
- **Evaluate:** log-loss, ROC-AUC, top-3 accuracy (predicted podium ∩ actual podium),
  top-1 accuracy (did the #1 pick win), baseline comparison, and a
  **reliability/calibration curve** (the reason to calibrate — show predicted vs actual).
- **Per-race normalization:** scale each race's podium-probs to sum to 3 (three spots).
  Sort drivers by podium-prob → top 3 = predicted podium, #1 = predicted winner.
- **Honesty:** explore predictions on held-out past races; predict the next race only
  once its qualifying exists; Limitations section on the Model page.
- **Caching:** API responses cached to parquet so re-runs are fast.

## 8. Visual / Aesthetic Direction

- **Light & minimal** — generous whitespace, clean sans-serif, restrained F1-red accent.
  Editorial, not "broadcast dashboard."
- Tailwind design tokens for consistency; cards + simple charts; short paragraphs.
- Recharts kept clean (no clutter, clear labels, accessible colors).
- **Component inspiration** (from a reference artifact, re-styled light/minimal): a
  podium visual for the top-3, horizontal feature-importance bars, metric cards, and a
  full predictions table with subtle gold/silver/bronze accents for P1–P3.
- **Honesty note:** unlike the reference mockup, I do NOT show fake live "feature
  weight" sliders or fabricated confidence numbers. Feature importances are the real,
  static output of the trained model; probabilities are calibrated.

## 9. Success Criteria

- A newcomer understands F1 basics in a few minutes from the content pages.
- Predict page shows a ranked, calibrated podium-probability chart per chosen race.
- Model page shows honest metrics + a calibration curve + limitations.
- Decoupled repo (ml/ + web/) is clean and documented for a portfolio.
- Deploys free on Vercel.

## 10. Risks & Mitigations

- **Frontend is the schedule risk (Next.js, new to author):** scope components tightly;
  keep it static/simple; timebox.
- **Sparse positives (~3 podiums per ~20 drivers):** per-driver probability framing;
  calibration + `scale_pos_weight` help.
- **JSON/type drift between ml/ and web/:** single documented data contract (§6);
  TypeScript types mirror it.

## 11. Out of Scope (future ideas)

- Auto-refresh predictions via scheduled GitHub Action committing fresh JSON.
- FastF1 telemetry analysis (tire strategy, lap times).
- Championship-winner prediction mode.
- Astro/alternative frontend (Next.js chosen for resume recognizability).
