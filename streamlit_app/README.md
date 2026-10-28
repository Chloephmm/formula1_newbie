# F1 Race Predictor — Streamlit

Dark "Pit Wall" prediction dashboard. Pick an as-of date and the model finds the
next Grand Prix, then predicts qualifying and the podium.

## Run

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

## Files
- `app.py` — the whole app (data, styles, layout).
- `assets/bg-sunset2.png` — the background photo (loaded inline as base64).
- `requirements.txt` — just Streamlit.

## How it works
- `CALENDAR` / `TEAMS` / `DRIVERS` hold the sample 2026 data. Swap these for your
  model's output — `resolve()` picks the next race where `race date >= as-of`.
- **Mode** flips automatically: if the as-of date is on/after the race's quali date
  *and* a `real` grid exists, it shows the green "real grid" view (with predicted-vs-actual
  deltas + the Compare expander). Otherwise it's the yellow "pre-qualifying estimate".
- The visual styling is injected via one `st.markdown` CSS block; cards are built as
  HTML strings so the look matches the prototype exactly.

## Wiring in a real model
Replace the static lists with your predictions. Each grid row is
`(driver_code, team_code, gap_seconds)` sorted P1→Pn; each podium row is
`(driver_code, team_code, probability_pct)`. Keep `gap == 0` for pole.
