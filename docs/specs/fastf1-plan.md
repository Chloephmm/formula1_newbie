# FastF1 Practice-Pace Plan (deferred / "if I build it later")

A documented plan for adding a **practice-pace feature** (from FastF1) to sharpen the
Stage-1 qualifying model. Not built yet — this is the reference for if/when we do.

## Why (the spike result)
A quick test ranked drivers by **FP3 practice pace alone** vs the actual qualifying order
(6 × 2024 races):

| | mean grid error | notes |
|---|---|---|
| Practice pace **alone** | **3.07 positions** | 2 of 6 were sprint weekends (FP1 only → weaker) |
| Current history-based model | 3.45 positions | |
| Spearman (practice gap ↔ quali pos) | **0.71** | moderately strong |

Conclusion: practice pace is a **real, positive signal** — it beats the current model even
used alone. Blended into the model, estimated grid error ≈ **2.6–2.9** (a modest ~0.5–0.9
position gain). Floor remains: qualifying is genuinely chaotic.

## Two data sources

```
Jolpica  →  results, qualifying, standings, schedule   (outcomes & history)
FastF1   →  practice-session lap times (FP1/FP2/FP3)    (pre-qualifying pace)  ← NEW
```

## A. OFFLINE — build features + train (periodic)

```
Jolpica history ─┐
                 ├─► build feature tables
FastF1 practice ─┘     Stage-1 (quali) features:
   per race/driver:        recent_quali_gap, recent_quali_pos, quali_track_hist,
   best practice lap →      team_quali_strength,  + practice_pace   ← NEW
   gap-to-fastest          Stage-2 (podium): unchanged (optionally + practice_pace)
   = practice_pace
                 ▼
   train Stage-1 quali model (now includes practice_pace) + Stage-2 podium model
                 ▼
   save quali_model.pkl + podium_model.pkl
```

- `practice_pace` is **leakage-safe** (practice runs before qualifying & the race).
- FastF1 only goes back to **2018** → older training rows have `practice_pace` missing
  (LightGBM handles NaN natively).
- One-time cost: download practice for all training seasons (GBs, 30–90 min first time).

## B. ONLINE — when the user picks a date and hits RUN

```
USER picks date → RUN
   ├─ Jolpica: refresh season                              ~15–30s
   ├─ FastF1:  download the TARGET race's practice session  ~+15–45s (first time; cached after)  ← NEW
   │            → compute practice_pace for this race
   ▼
forecast(date):
   1. find next race ≥ date
   2. use data before it (no leakage)
   3. build feature row (form features + practice_pace)
   4. STAGE 1 quali model → predict grid (sharper, with practice_pace)
   5. mode: date ≤ quali day → predicted grid;  date > quali day → real grid
   6. STAGE 2 podium model → P(top-3) → normalize → rank → podium
```

## C. Refined weekend timeline (where FastF1 helps)

```
│ before the weekend │ Fri/Sat AFTER practice  │ Sat AFTER qualifying │
├────────────────────┼─────────────────────────┼──────────────────────┤
│ 🟡 PRE-QUALI       │ 🟡 PRE-QUALI (sharper)  │ 🟢 REAL GRID         │
│ practice_pace      │ practice_pace = real     │ uses actual grid;    │
│   missing →        │   → better grid pred     │ practice irrelevant  │
│   form-only (~3.4) │   (~2.6–2.9)             │ (grid error = 0)     │
```

FastF1's benefit lands only in the **narrow window**: during the race weekend, *after
practice runs but before qualifying*. Before practice → falls back to form-only. After
qualifying → the real grid takes over and practice doesn't matter.

## D. Runtime cost (RUN latency)

| | Jolpica-only (now) | + FastF1 practice |
|---|---|---|
| RUN time | 15–30s | **45–90s** first time per weekend, ~15–30s when cached |

RUN roughly doubles the first time you predict a given race weekend (downloads that race's
practice), then it's cached.

## E. Caching & deployment
- **Local:** FastF1 caches each session to `cache/` → later RUNs for that race are fast.
- **Streamlit Cloud:** can't bundle GBs of cache → would download practice **live per
  request** (the +15–45s on cold starts, ephemeral storage). Heavier/slower deploy than
  the lean Jolpica-only version.

## Build checklist (when implementing)
1. `ml/src/data/fastf1_loader.py` — enable cache; `get_practice_pace(year, round)` →
   per-driver gap-to-fastest from best practice lap (FP3 → FP2 → FP1 fallback; handle
   sprint weekends / missing data).
2. Add `practice_pace` to `build_quali_features` (join on season/round/driver), leakage-safe.
3. Retrain + re-evaluate the quali model; update `quali_metrics.json`.
4. In `forecast()`, fetch the target race's practice (if it exists) and add `practice_pace`
   to the feature row; fall back to NaN when practice hasn't happened.
5. Show a spinner on RUN (download latency); add a "practice in" indicator for the refined
   pre-quali state.

## Verdict
Real but **modest** accuracy gain, only during the race weekend, at ~2× RUN latency and a
heavier deploy. Worth it as a **FastF1 showcase**; not essential for accuracy since the
real-grid mode already gives the exact grid once qualifying runs.
