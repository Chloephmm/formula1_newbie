# 🏁 F1 Guidebook

A beginner-friendly Formula 1 site plus a leakage-safe two-stage race predictor.
The Next.js guidebook uses Jolpica-backed statistics; the Streamlit predictor reads
only versioned forecasts saved by the background ML pipeline.

## What it does

- **Learn F1** — teams, drivers, rules, statistics, and motion-led explainers.
- **Predict** — show the next saved pre-qualifying or actual-qualifying forecast.
- **Update automatically** — GitHub Actions fetch, validate, train, publish, and freeze
  predictions. A visitor never fetches Jolpica data or runs a model.
- **Keep evidence** — each canonical forecast records its exact event, roster, historical
  input digest, feature policy, model configuration, qualifying source, and confirmed
  publication receipt.

## Automatic forecast lifecycle

1. Monday's existing refresh fetches the season data, refreshes the retrospective
   accuracy benchmark, finalizes the prior event when due, and saves the next event's
   initial two-stage forecast before qualifying.
2. Qualifying is estimated to end 90 minutes after its scheduled start unless an
   observed/evidence-backed finish is available.
3. The monitor first checks Jolpica five hours after that end, then retries hourly for
   missing or incomplete data. Failed/unchanged checks do not train.
4. A complete changed session runs Stage 2 with actual qualifying positions/timing.
   The candidate must be confirmed available before race start minus two hours.
5. One final verification is due 45 minutes before the cutoff. At the cutoff, the
   latest confirmed eligible forecast is frozen for evaluation.
6. An open Streamlit page polls the saved feed about once per minute and keeps its
   per-event last-good revision on temporary network/CDN failures.

Scheduled GitHub jobs can start late. The controller always evaluates real UTC after
queueing and before generation/publication; it never treats a cron trigger time as proof
of eligibility.

## GitHub Actions

| Workflow | Schedule | Responsibility |
|---|---|---|
| `refresh-predictions.yml` | Monday 06:00 UTC | Original five-endpoint fetch, next initial/final rollover, and walk-forward benchmark |
| `sync-stats.yml` | Monday 06:00 UTC, March–December | Existing Next.js `stats.json` refresh |
| `qualifying-monitor.yml` | minutes 07/22/37/52 every hour | Cheap due gate, exact qualifying check, changed-input actual forecast, status/freeze |

All three use the same `f1-data-writes` concurrency queue and fast-forward-only
publication. No force push is used.

## Status

The automatic-refresh implementation is on `feature1`. Local fixture, publication,
controller, and Streamlit tests cover the lifecycle. It has not been pushed, merged,
enabled, seeded, or verified on the hosted Streamlit app by this implementation work;
the public deployment may therefore still show the earlier behavior until deployment is
explicitly authorized.

## Tech stack

| Layer | Choice |
|---|---|
| ML/data | Python, pandas, PyArrow, scikit-learn, LightGBM |
| Source | Jolpica API with validated exact-event pagination evidence |
| Guidebook | Next.js, TypeScript, Tailwind, Framer Motion |
| Predictor | Streamlit 1.54, saved JSON only |
| Automation | GitHub Actions, Git-backed immutable artifacts |

## Repository layout

```text
ml/src/pipeline/       event, state, validation, artifact, publication, controller contracts
ml/scripts/            Monday refresh, qualifying monitor, safe publishers, acceptance tools
ml/data/raw/           historical Parquet tables
web/public/data/       compatibility JSON, atomic feed, per-event archives
streamlit_app/         saved-feed reader and read-only forecast view
docs/specs/            prediction and ML reference
```

## Run locally

```bash
# ML pipeline tests
cd ml
pip install -r requirements-dev.txt
python -m pytest tests

# Saved-only predictor (from repository root)
pip install -r streamlit_app/requirements.txt
streamlit run streamlit_app/app.py

# Read-only schedule decision; does not fetch, train, write, commit, or push
python ml/scripts/check_qualifying.py --dry-run --now 2026-10-31T23:00:00Z
```

See [prediction logic](docs/specs/prediction-logic.md) and
[ML models](docs/specs/ml-models.md) for the full contracts.
