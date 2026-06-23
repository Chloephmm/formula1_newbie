# Frontend — as-built reference

The current state of the **Next.js** site in `web/`. This supersedes the visual
direction in [`design.md`](./design.md) (which captured the original "light & minimal /
Recharts" plan); the site shipped as a **dark, cinematic, motion-led** experience driven
by **live Jolpica data**.

Stack: **Next.js (App Router) + TypeScript + Tailwind CSS v4 + framer-motion**, deployed on
Vercel. Predictions live in a **separate Streamlit app** (see
[`prediction-logic.md`](./prediction-logic.md)); the site links out to it.

---

## Theme & typography

**Theme** (`app/globals.css`): near-black background (`--bg: #000`), white text, F1 coral/red
accents (`--accent: #f0453c`, `--red: #e8002d`), `--muted`, `--border` tokens. Dark mode only.

**Fonts** (`app/fonts.ts`, all wired in `app/layout.tsx`):

| Token | Font | Used for |
|---|---|---|
| `--font-horizon` (`font-display`) | Horizon (self-hosted) | Big display headings, team wordmarks, numbers |
| `--font-jet` (`font-mono`) | JetBrains Mono | Body / labels |
| `--font-plex` | IBM Plex Mono | Team detail pages (matches the team wireframe) |
| `--font-mokoto` (`font-pixel`) | Mokoto Glitch | Glitch titles ("THE GRID") |
| `--font-cooper` (`font-nav`) | Cooper Hewitt | Navbar |
| `--font-holiday` (`font-script`) | Holiday | Script accents |

---

## Pages

### Home — `app/page.tsx`
- **Aurora Field background** — an interactive WebGL smoke shader (`components/AuroraField.tsx`),
  fullscreen and cursor-reactive, **mounted on Home only** (other pages keep the flat black
  background for data legibility). Respects `prefers-reduced-motion`. A radial **vignette scrim**
  frames it toward the car and guarantees text contrast.
- **Rotating welcome** (`components/WelcomeHeadline.tsx`) — a different opener each visit, picked
  from 5 lines on the client (no hydration mismatch; the `Reveal` fade masks the pick).
- **Hero car** — front-on car image with a **zoom-in ("coming toward you") entrance**
  (`Reveal scaleFrom`).
- **CTAs** — primary **START HERE** → `/how-f1-works`; secondary "jump to predictions ↗" → Streamlit.
- **Stat counters** (`components/StatCounters.tsx`) — count-up of Drivers / Teams / Races
  (race count pulled live from the 2026 Jolpica schedule).

### Teams grid — `app/teams/page.tsx`
Circular team logos (per-team zoom/focal via `LOGO_CFG`), linking to each team page.

### Team detail — `app/teams/[team]/page.tsx`  (the "Ferrari-style" template, all 11 teams)
- **Top-left lockup**: team logo (in a clipped circle, `LOGO_CFG` scale/focal) + short team name
  + "FORMULA 1 · 2026 SEASON".
- **Hero**: giant team wordmark sitting **behind the car**; the car **slides in left→right**
  (`Reveal direction="left" distance duration`). Wordmark font-size is length-aware so every
  name stays on one line. Sized with `vh` so Section 1 fits one screen.
- **Driver headshots**: two **1:1 square, face-centered, background-removed** cutouts
  (transparent PNGs) with each driver's **permanent number**.
- **Team Information** table (BASE / TEAM CHIEF / CHASSIS / POWER UNIT) + **2026 Statistics**
  table (Classification / Points / Wins / Podiums / Poles / Fastest Laps) — accent "folder-tab"
  headers, flush-stacked.
- **Drivers** section: per-driver **whole-career** stats (World Championships, Races, Wins,
  Podiums, Poles, Fastest Laps) + nationality **flag** + current-season classification, in
  stacked alternating rows that fit one screen.

### Drivers — `app/drivers/page.tsx`
"THE GRID" glitch title; **live standings** rendered as uniform cards (team accent strip,
fixed-width position number, points/wins, team-colored wins, hover lift).

### Predict (nav)
Not a page — the navbar "PREDICT ↗" links to the external Streamlit app (`STREAMLIT_URL`).

---

## Components

| Component | Role |
|---|---|
| `Navbar.tsx` | Sticky top nav (`z-50`); Predict is an external link |
| `Footer.tsx` | Footer (raised above the Home aurora canvas) |
| `Reveal.tsx` | framer-motion entrance wrapper — `direction`, `distance`, `duration`, `scaleFrom`; reduced-motion friendly |
| `AuroraField.tsx` | WebGL shader background (Home), cursor heat-bloom + click flare |
| `WelcomeHeadline.tsx` | Client; rotates the 5 welcome lines per visit |
| `StatCounters.tsx` | Client; animated count-up stats |
| `GlitchTitle.tsx` | Pixel/glitch section title |

---

## Data layer — live vs static

**Live, from Jolpica (Ergast successor)** — `lib/jolpica.ts`, ISR-cached with a graceful
static fallback if the API is down:

| Function | Provides |
|---|---|
| `getConstructorStandings` / `getDriverStandings` | Live standings (position, points, wins) |
| `getSeasonStats` | Aggregates the 2026 season's race results + qualifying → per-driver podiums / poles / fastest laps (team totals = sum of its drivers) |
| `getDriverCareer` | Whole-career totals (races, wins, podiums, poles, fastest laps) per driver. **Serial calls + retry-on-429** to avoid rate-limit bursts; cached until just after the next race (`getCareerRevalidate`) |
| `getSchedule` | Season calendar (drives Home's race count) |

**Static reference data** (not available from the standings API):

| File | Provides |
|---|---|
| `lib/data.ts` | `teams.json` / `drivers.json` / `races.json` loaders + `shortTeamName` |
| `lib/teamMeta.ts` | Per-team Base / Team Chief / Chassis / Power Unit, logo filename, accent fallback, `LOGO_CFG` |
| `lib/assets.ts` | Car images, driver photos, **driver cutouts** (`*_nobg.png`), `DRIVER_NUMBER` (permanent numbers), `DRIVER_CHAMPIONSHIPS` (curated WDC counts) |
| `lib/flags.ts` | Nationality → local flag SVG |
| `lib/links.ts` | `STREAMLIT_URL` (the Predict app) |

**Why some fields are static:** team facilities/personnel/chassis aren't in any standings API,
driver permanent numbers aren't reliable from Jolpica for the 2026 grid, and all-time
championship counts can't be queried without per-season requests. Every *performance statistic*
is live; only descriptive/reference data and imagery are static.

---

## Assets

- `public/images/assets/<team>/` — side-profile car + driver photos, plus **`*_nobg.png`**
  cutouts (backgrounds removed offline with U²-Net, then squared & face-centered).
- `public/images/flags/` — 15 nationality flag SVGs.
- `public/images/teams/` — team logos.
- `public/data/` — JSON exported by the ML pipeline (static fallback + first-paint snapshot).

---

## Tooling note

`web/eslint.config.mjs` uses Next 16's native flat configs directly (the old `@eslint/eslintrc`
`FlatCompat` bridge crashed on load). `npm run lint` is clean apart from two pre-existing
`<img>` advisories on the home page.
