# F1 Race Predictor — Streamlit

Dark, read-only "Pit Wall" prediction dashboard. It polls the published prediction
feed every 60 seconds and switches from estimated to actual qualifying automatically.

## Run

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

## Files
- `app.py` — polling UI, status display, race archive selector, and layout.
- `prediction_feed.py` — HTTP/local feed loading and schema validation.
- `assets/bg-sunset2.png` — the background photo (loaded inline as base64).
- `requirements.txt` — Streamlit and the short-timeout HTTP client.

## Feed configuration

The deployed app defaults to `https://formula1-newbie.vercel.app/data`. Set
`PREDICTION_FEED_BASE_URL` only to override that endpoint. Localhost and private-network
development read `web/public/data` from this repository.
Malformed or unavailable polling responses do not replace the last valid in-session snapshot.

The browser never fetches Jolpica or runs a model. GitHub Actions publishes the feed.

Archived races offer a View dropdown below the race selector: Prediction Result
shows the immutable saved forecast; Actual Race Result shows recorded finishing
positions, points, status, and the actual podium. Completed results are published
separately as `predictions/{season}-{round}-results.json` by the hourly publisher
from the raw data refreshed on Monday. Missing results show an unavailable message;
polling failures retain the last valid result. Switching views never runs a model.

Country flags use SVG images (embedded from `web/public/images/flags` where present,
otherwise loaded from FlagCDN) so Windows displays flags instead of letter pairs.
