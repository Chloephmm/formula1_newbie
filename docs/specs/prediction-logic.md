# F1 Prediction Logic

The single source of truth for how the Predict app works — the end-to-end flow, the two
prediction modes (chosen by the user's **as-of date**), and the machine-learning models.

Code: `streamlit_app/app.py` (UI) · `ml/src/model/forecast.py` (pipeline) ·
`ml/src/model/quali.py` (Stage 1) · `ml/src/model/train.py` (Stage 2).

---

## Full logic flow

```
USER picks a date  (app.py: st.date_input)
   │   [🔄 Run / refresh button → re-fetch season from Jolpica + clear cache + rerun]
   ▼
resolve(date)  →  forecast(date)   (src/model/forecast.py)
   │
   ├─ 1. Find next race ≥ date            (schedule)            → Barcelona, round 7…
   ├─ 2. Keep only data BEFORE that race  (t[date < race_date]) → no leakage
   ├─ 3. Entry list = drivers from the most recent completed race
   ├─ 4. Build each driver's feature row (form signals + qualifying signals)
   │
   ├─ STAGE 1 (quali model) ───────────────┐
   │     predict gap-to-pole → rank → grid │
   │                                        ▼
   ├─ MODE pick by date:        date ≤ quali day → use PREDICTED grid (2-stage)
   │                            date >  quali day → use REAL grid (if cached)
   │                                        │
   ├─ STAGE 2 (podium model) ◄──────────────┘
   │     P(top-3) per driver → normalize (sum=3) → rank → podium
   ▼
race dict {predictedQualifying, preQualifyingPodium, realGridPodium, realQualifying, hasRealGrid}
   ▼
app.py renders → race strip · mode badge · quali_html · podium_html · compare_html  (the design)
                 (+ "📡 Real data from today's qualifying." line when in real-grid mode)
```

---

## Two prediction types (chosen by date)

```
find the NEXT race on/after the date → it has a qualifying date and a race date
      │
      ├── date ≤ qualifying date   → TYPE 1: PRE-QUALIFYING  (two-stage, predicted grid)
      └── date > qualifying date   → TYPE 2: REAL GRID        (uses actual qualifying)
```

Boundary: **on/before** quali day → two-stage; **after** quali day → real grid.
Real grid *also* requires the qualifying to be present in the cache (use the 🔄 Run button
after a session is published).

### TYPE 1 — Pre-qualifying (date ≤ qualifying date): two-stage

**Stage 1 — predict the grid** (`quali_model`, LightGBM regressor)
Inputs (pre-race only, no leakage):
- `quali_track_hist` — qualifying history at this circuit in prior years
- `recent_quali_gap`, `recent_quali_pos` — recent qualifying form / recent average grid
- `team_quali_strength` — team's recent qualifying pace

Output: predicted **gap-to-pole** per driver → rank → **predicted grid**.

**Stage 2 — predict the podium** (`podium_model`, calibrated LightGBM classifier)
Inputs:
- the **predicted grid** from Stage 1 (`grid_position`, `quali_time_gap_to_pole`)
- `recent_form`, `recent_points` (recent form)
- `team_strength`, `track_history`, `dnf_rate` (team, track, reliability)

Output: **P(top-3)** per driver → normalize (sum = 3) → rank → **predicted podium**.

### TYPE 2 — Real grid (date > qualifying date): one stage

Skip Stage 1. Use the **actual qualifying** (real grid position + real gap-to-pole) in
place of the predicted grid, then run the **same** Stage-2 podium model with the same
form/team/track/reliability features → **podium on the real grid**. A **Compare** panel
shows predicted grid vs actual grid with ▲/▼ movement, and the app shows the line
**"📡 Real data from today's qualifying."**

---

## Machine-learning models

| Role | File | Algorithm | Predicts | Calibrated | Train / eval |
|---|---|---|---|---|---|
| **Stage 1 — Qualifying** | `models/quali_model.pkl` | **LightGBM regressor** | gap-to-pole (s) → grid | n/a | train ≤2022, test ≥2024 |
| **Stage 2 — Podium (shipped)** | `models/podium_model.pkl` | **LightGBM classifier** | P(top-3) | **yes** (sigmoid, on 2023) | train ≤2022, calibrate 2023, test ≥2024 |
| Baseline | (in artifact) | Logistic regression | P(top-3) | — | benchmark only |
| Benchmark | (metrics.json only) | **XGBoost** (calibrated) | P(top-3) | yes | benchmark only |

Discipline (all): **no leakage** (features use only pre-race data, `shift(1)` in training),
**split by season**, probabilities **calibrated**.

### How the podium is produced (Stage 2)
```python
p = podium_model.predict_proba(X)[:, 1]   # calibrated P(top-3) per driver
p = p * 3 / p.sum()                        # normalize: ~20 drivers sum to 3 podium spots
# sort desc → top 3 = predicted podium; #1 (highest podium prob) = predicted winner
```
Each driver is scored independently, then normalized per race and ranked. (Podium-only
model; the "winner" is the top of the podium — `top1Accuracy` is reported separately.)

### Measured accuracy (test 2024–2026)
grid error **±3.4** positions · podium hit rate **70%** · gap MAE **0.60s** · **182**
training races. Benchmarks: LightGBM AUC 0.935, XGBoost 0.937 (a statistical tie), both
beat the logistic baseline → **LightGBM shipped** (stronger top-1 accuracy).

---

## Data flow / live update

```
Jolpica API ──(🔄 Run: fetch refresh)──▶ ml/data/raw/*.parquet ──(read live)──▶ models ──▶ app
```

Predictions run **live** in the app from the **cached** parquet. The cache changes only on
refresh. The 🔄 Run button does: re-fetch season (`refresh=True`) → `st.cache_data.clear()`
→ `st.rerun()` → `forecast()` re-reads the new data → mode flips 🟡→🟢 if qualifying is now
present and date > quali day.

| Moment (predicting Race N) | Needs | Action |
|---|---|---|
| Before qualifying (Type 1) | races 1…N−1 | refresh after Race N−1 |
| After qualifying (Type 2) | + Race N's **qualifying** | 🔄 Run after qualifying → unlocks real grid |
| After the race | + Race N's **result** | 🔄 Run after the race (to compare) |

Notes:
- The button only fetches what Jolpica has **published** (qualifying appears a few hours
  after the real session). Click after qualifying → real grid; click before → stays
  pre-qualifying (expected).
- **Models are not retrained per race** — only the input data is refreshed. Retraining
  (`train_model.py`, `build_quali_model.py`) is optional, e.g. end of season.
- macOS: LightGBM/XGBoost need `libomp` — run `bash ml/scripts/fix_libomp_macos.sh` if an
  import fails after recreating the venv.
