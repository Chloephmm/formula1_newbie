# 🏁 F1 Guidebook

A beginner-friendly Formula 1 knowledge website that makes F1 fun and easy to learn —
and showcases a decoupled, end-to-end data-science pipeline that predicts race winners
with **calibrated** probabilities.

**Architecture:** a **Next.js** site driven by **live Jolpica data** (with static JSON
fallback), plus a separate **Streamlit** predictor — a leakage-safe **LightGBM** cascade that
forecasts each Grand Prix's calibrated **podium**. Deployed on Vercel.

## What it does

- **Learn F1** — a dark, cinematic, motion-led site: an interactive Aurora-shader home, and
  live **Teams** and **Drivers** pages rendering real-time standings, season stats, and
  whole-career driver records from Jolpica.
- **Predict** — the **Predict** tab opens the Streamlit app, where the **RUN** button re-fetches
  the latest data and **retrains both models on every race before that Grand Prix**
  (leakage-safe) before predicting the podium.
- **See the data science** — a transparent, decoupled pipeline (ingest → features →
  train → calibrate → evaluate → export JSON) with honest metrics and a calibration curve.

## Status

✅ Frontend built and running on live Jolpica data. Streamlit predictor live at
[f1forecast.streamlit.app](https://f1forecast.streamlit.app/).

## Tech stack

| Layer | Choice |
|---|---|
| ML / data | Python, pandas, scikit-learn, **LightGBM** (+ calibration) |
| Data sources | **Jolpica** API (live, ISR-cached) + FastF1 (planned); static JSON fallback |
| Frontend | **Next.js** (App Router) + TypeScript + **Tailwind v4** + **framer-motion** |
| Predictor | **Streamlit** (separate app) |
| Hosting | **Vercel** (free) |

## Docs

See [`docs/`](./docs/README.md) — frontend reference, prediction strategy, and ML models.

## Repository layout

```
ml/    Python ML pipeline (offline) — features, live retrain, metrics, JSON export
web/   Next.js frontend — live Jolpica data + static JSON fallback
docs/  specs (frontend, prediction strategy, ML models)
```

## Running locally (once built)

```bash
# ML pipeline
cd ml && pip install -r requirements.txt
python scripts/fetch_data.py && python scripts/build_predictions.py && python scripts/export_json.py

# Frontend
cd ../web && npm install && npm run dev
```
