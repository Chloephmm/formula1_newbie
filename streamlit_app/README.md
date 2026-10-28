# F1 Race Predictor — Streamlit

The Streamlit app is a read-only view of confirmed prediction JSON. Visitors do
not fetch Jolpica data, train a model, or publish forecasts, and there is no RUN
button. GitHub Actions owns ingestion, validation, prediction, and publication.

## Run locally

From the repository root:

```bash
pip install -r streamlit_app/requirements.txt
streamlit run streamlit_app/app.py
```

By default the app reads the confirmed feed from the repository's public GitHub
raw URL. Set `PREDICTION_FEED_URL` to another URL ending in
`prediction_feed.json`, or set `PREDICTION_FEED_FILE` to a local confirmed feed
for development and tests.

## Files

- `app.py` — page layout and the automatic 60-second saved-forecast fragment.
- `prediction_data.py` — feed retrieval, validation, ETag/TTL caching, and
  per-event last-good fallback.
- `prediction_view.py` — rendering for saved predicted-qualifying and
  actual-qualifying modes.
- `saved_prediction_harness.py` — focused AppTest/development harness.
- `assets/bg-sunset2.png` — inline dashboard background.
- `requirements.txt` — pinned Streamlit runtime and HTTP reader dependency.

The page displays only saved, publication-confirmed forecasts. Missing or invalid
data is shown as temporarily unavailable; it never triggers an inline model run.
