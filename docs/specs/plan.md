# F1 Guidebook — Implementation Plan

> Phase-by-phase build log. ML phases shipped as planned; the **frontend phases were
> rewritten below to match what actually shipped** (live Jolpica data + a dark, cinematic
> site, with predictions in a separate Streamlit app — not the original static-JSON /
> Recharts / in-app Model page plan). See [`frontend.md`](./frontend.md) for the as-built
> frontend and [`prediction-logic.md`](./prediction-logic.md) for the predictor.

## Project summary (as-built)

Two decoupled parts:

- **`web/` — Next.js (App Router) site.** Renders **live Jolpica data** (standings, season
  stats, whole-career driver records) via server components with **ISR caching + static JSON
  fallback**. Dark, motion-led UI (Tailwind v4 + framer-motion). Deployed on Vercel.
- **`ml/` + Streamlit — the predictor.** A leakage-safe **LightGBM** cascade that forecasts
  each Grand Prix's calibrated **podium**; hosted as a separate **Streamlit** app the site
  links out to. The pipeline also exports static JSON used as the web fallback.

Data: **Jolpica** (Ergast successor) + optional **FastF1**. Scope = **podium prediction only**
(predicted winner = top of the podium).

---

## Phase 0 — Repo scaffold  ✅ DONE
Monorepo (`ml/` + `web/`), Python venv, `.gitignore` (Python + Node).
**macOS / LightGBM:** needs `libomp.dylib`; run `bash ml/scripts/fix_libomp_macos.sh` if import fails.
**Acceptance:** ✅ `python -c "import pandas, lightgbm, sklearn"` works.

## Phase 1 — Data layer  ✅ DONE
`ml/src/data/` Jolpica client + parquet cache; `scripts/fetch_data.py` pulls seasons into `ml/data/raw/`.
**Acceptance:** ✅ parquet files load with expected columns; qualifying includes Q1/Q2/Q3 times.

## Phase 2 — Feature engineering  ✅ DONE
`build_features.py` — one row per driver-race, target `podium` (top-3). Leakage-safe features
(`shift(1)` everywhere): grid, quali gap-to-pole, recent form/points, team strength, track history, DNF rate.
**Acceptance:** ✅ no leakage, class balance reported (~3 podiums per ~20 drivers).

## Phase 3 — Train, calibrate, evaluate, export  ✅ DONE
LightGBM + logistic baseline on `podium`; calibration on a locked chronological split
(≤2022 fit / 2023 calibrate / ≥2024 test) via `CalibratedClassifierCV(FrozenEstimator(...))`.
Evaluate (log-loss, ROC-AUC, top-3/top-1 accuracy, reliability curve, feature importances);
export static JSON into `web/public/data/`.
**Acceptance:** ✅ LightGBM ≥ baseline; calibration curve closer to diagonal; JSON contract present.

## Phase 3.5 — Qualifying model + two-stage prediction  ✅ DONE
Stage 1 LightGBM regressor predicts qualifying gap-to-pole → grid; Stage 2 podium model.
Two modes: pre-qualifying (predicted grid) and real-grid (after qualifying).
Later evolved into the **live-retrain** regime — see [`ml-models.md`](./ml-models.md).
**Acceptance:** ✅ both stages train; Mode 1 always, Mode 2 once qualifying exists.

---

## Phase 4 — Next.js scaffold  ✅ DONE
`web/` via create-next-app (TypeScript, App Router, **Tailwind v4**, ESLint). Added **framer-motion**.
`lib/types.ts` (JSON contract), `lib/data.ts` (static loaders), dark theme tokens + self-hosted
font system in `app/layout.tsx` / `app/fonts.ts` (Horizon, JetBrains Mono, IBM Plex Mono, Mokoto, Cooper Hewitt).
**Acceptance:** ✅ themed shell, working nav, no type errors.

## Phase 5 — Pages + live data  ✅ DONE  *(diverged from the original plan)*

Built as a **dark, cinematic** site on **live Jolpica data** (`lib/jolpica.ts`, ISR-cached with
static fallback) — not static-JSON-only, and predictions moved to an external Streamlit app
(so there is **no in-app Predict/Model/Recharts page**).

1. **Home** (`app/page.tsx`) — interactive **Aurora Field WebGL** background (Home only),
   rotating welcome (5 lines), front car with zoom-in entrance, START HERE + "jump to
   predictions ↗" (Streamlit), animated stat counters.
2. **How F1 Works** + **History** — content pages.
3. **Teams** (`app/teams/page.tsx`) — circular team logos → team detail.
4. **Team detail** (`app/teams/[team]/page.tsx`) — "Ferrari-style" template: top-left lockup,
   team wordmark behind a car that slides in left→right, two 1:1 face-centered driver cutouts
   with permanent numbers, **live** Team Information + 2026 Statistics tables, and a Drivers
   section with **whole-career** stats + nationality flag + classification.
5. **Drivers** (`app/drivers/page.tsx`) — "THE GRID" glitch title + **live standings** cards.
6. **Predict** — navbar link out to the **Streamlit** app (`lib/links.ts → STREAMLIT_URL`).

**Live data** (`lib/jolpica.ts`): `getConstructorStandings`, `getDriverStandings`,
`getSeasonStats` (2026 podiums/poles/fastest-laps from results + qualifying), `getDriverCareer`
(career totals; serial + retry-on-429; cached until the next race), `getSchedule`. Static
reference data in `lib/teamMeta.ts`, `lib/assets.ts`, `lib/flags.ts`.
**Acceptance:** ✅ all pages render live data; standings/career/season stats resolve; Predict opens Streamlit.

## Phase 6 — Polish, docs & deploy  ✅ DONE / ongoing
Responsive passes (fit-to-screen sections, uniform cards), motion polish, ESLint flat-config fix,
docs in `docs/` ([`frontend.md`](./frontend.md), [`prediction-logic.md`](./prediction-logic.md),
[`ml-models.md`](./ml-models.md), index [`../README.md`](../README.md)). Deploy: Vercel root = `web/`.

---

## Changelog

### 2026-06-22 — frontend overhaul + live data + docs refresh
- **Home:** replaced black background with an interactive **Aurora Field WebGL shader**
  (Home only; reduced-motion aware) and removed the smoke clouds; **car zoom-in** entrance;
  **rotating welcome** (5 lines, per visit); **CTA pair** (START HERE + jump-to-predictions);
  animated **stat counters**; vignette scrim for contrast.
- **Team detail pages** rebuilt to the "Ferrari-style" template: team name **behind the car**
  (left→right slide), 1:1 **face-centered, background-removed** driver cutouts with permanent
  numbers, accent **folder-tab** tables, one-screen layout.
- **Live Jolpica data** wired across Teams/Drivers: standings, **season stats** (podiums/poles/
  fastest laps aggregated from results + qualifying), and **whole-career** driver totals
  (with retry-on-429 + race-aligned caching). Nationality **flags**, **Drivers** standings grid.
- Shortened team lockup names; fixed driver-number alignment & missing-number cases; centered/
  renamed section titles per review.
- **Predict** tab points to the Streamlit app (`STREAMLIT_URL`).
- Fixed `web/eslint.config.mjs` (Next 16 native flat config; dropped the crashing FlatCompat bridge).
- **Docs:** added [`frontend.md`](./frontend.md) (as-built) + docs index; annotated `design.md`
  as historical; updated root README; this plan rewritten to match what shipped.

### earlier
- Phases 0–3.5: ML pipeline, two-stage predictor, live-retrain regime, static-JSON export.
