# 🏁 F1 Guidebook

A beginner-friendly Formula 1 knowledge website that makes F1 fun and easy to learn —
and showcases a decoupled, end-to-end data-science pipeline that predicts race winners
with **calibrated** probabilities.

**Architecture:** Python ML pipeline → calibrated model → static JSON → Next.js frontend
→ deployed on Vercel. Data from **Jolpica** and **FastF1**; ML with **LightGBM**
(logistic-regression baseline).

## What it does

- **Learn F1** — simple, high-level pages on F1 history, teams, and drivers.
- **Predict** — pick a race and see calibrated ML win probabilities for each driver.
- **See the data science** — a transparent, decoupled pipeline (ingest → features →
  train → calibrate → evaluate → export JSON) with honest metrics, a calibration curve,
  and limitations.

## Status

🚧 In development.

## Tech stack

| Layer | Choice |
|---|---|
| ML / data | Python, pandas, scikit-learn, **LightGBM** (+ calibration) |
| Data sources | Jolpica API, FastF1 |
| Data exchange | Static JSON (`web/public/data/`) |
| Frontend | **Next.js** (App Router) + TypeScript + Tailwind + Recharts |
| Hosting | **Vercel** (free) |

## Repository layout

```
ml/    Python ML pipeline (offline) — produces static JSON
web/   Next.js frontend — renders the JSON
docs/  design + implementation plan
```

## Running locally (once built)

```bash
# ML pipeline
cd ml && pip install -r requirements.txt
python scripts/fetch_data.py && python scripts/build_predictions.py && python scripts/export_json.py

# Frontend
cd ../web && npm install && npm run dev
```
