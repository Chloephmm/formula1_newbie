# F1 Guidebook — docs index

A beginner-friendly F1 site (**Next.js**, live Jolpica data) plus a separate **Streamlit**
race-podium predictor (**Python / LightGBM**). These specs are the source of truth for both.

## Specs

| Doc | What it covers |
|---|---|
| [`frontend.md`](./specs/frontend.md) | **As-built frontend** — pages, components, theme/fonts, live-vs-static data, assets. Start here for the website. |
| [`prediction-logic.md`](./specs/prediction-logic.md) | **Prediction strategy** — the Streamlit predictor's end-to-end flow, the two modes, the live-retrain RUN button. |
| [`ml-models.md`](./specs/ml-models.md) | Data-science reference — the two LightGBM models, features, training/calibration, leakage safety, evaluation. |
| [`quali-improvement-options.md`](./specs/quali-improvement-options.md) | Notes on improving the Stage-1 qualifying model. |
| [`fastf1-plan.md`](./specs/fastf1-plan.md) | Plan for adding FastF1-derived features. |
| [`design.md`](./specs/design.md) | Original design doc / intent (historical — see `frontend.md` for what shipped). |
| [`plan.md`](./specs/plan.md) | Original implementation plan. |
| [`assets/prediction-flow.svg`](./specs/assets/prediction-flow.svg) | One-page visual of the prediction flow. |

## Prediction strategy — in one paragraph

The Streamlit app predicts each Grand Prix's **podium (top 3)** with a two-stage,
**leakage-safe** cascade that **retrains live** on the RUN button (fit on every race strictly
before the target GP). **Stage 1** (LightGBM regressor) predicts each driver's qualifying
**gap-to-pole** → ranked into a predicted grid. **Stage 2** (calibrated LightGBM classifier)
takes that grid plus recent form / team strength / track history / DNF rate and outputs a
**calibrated P(top-3)** per driver, normalized to sum to 3 → 🥇🥈🥉 (the top pick = predicted
winner). The mode is chosen by the user's as-of date: **on/before** qualifying day → predicted
grid (two-stage); **after** qualifying day → the **real grid** from Jolpica feeds Stage 2. Full
detail in [`prediction-logic.md`](./specs/prediction-logic.md) and [`ml-models.md`](./specs/ml-models.md).

## Repo layout

```
ml/      Python ML pipeline (offline) — features, live retrain, metrics, JSON export
web/     Next.js frontend (this site) — live Jolpica data + static JSON fallback
docs/    these specs
```
