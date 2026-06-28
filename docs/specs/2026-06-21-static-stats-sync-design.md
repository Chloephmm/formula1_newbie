# Static Driver/Team Stats via Scheduled Sync — Design

**Date:** 2026-06-21
**Status:** Approved (pending spec review)

## Context

The Teams detail pages (`web/app/teams/[team]/page.tsx`) and the Drivers page
(`web/app/drivers/page.tsx`) currently fetch driver/team stats **live from Jolpica at
render time**. Each team page makes ~16–20 Jolpica calls (constructor + driver standings,
season-wide results pagination + qualifying, and 6 career-total calls per driver × 2
drivers). When many pages render in a short window — notably the build, which generates all
11 team pages with 3 workers — Jolpica rate-limits (429). A failed `getDriverCareer` call
returns `null`, and because career data is cached with a long revalidate (up to ~30 days
via `getCareerRevalidate`), the failure is baked in and the UI shows "—" for races / wins /
podiums / poles / fastest laps for a long time.

**Goal:** Make all driver/team display stats **static**, regenerated on a weekly schedule by
a GitHub Action, so visitors trigger **zero** Jolpica calls and the stats are always present
and consistent. Stats effectively update after each new race (the weekly job picks up new
results and commits only when something changed).

## Non-goals

- The **Races tab schedule** stays live (`getSchedule`) — out of scope (this was the
  declined "option 3").
- The **ML/prediction pipeline** (`ml/`, `predictions.json`, `metrics.json`, the Streamlit
  app) is untouched.
- No change to the visual design of the Teams/Drivers pages — only the data source.

## Architecture

```
GitHub Action (weekly cron + manual dispatch)
  └─ npm run sync-stats   (web/scripts/sync-stats.ts)
       └─ Jolpica (throttled, sequential, retryable)
            └─ writes web/public/data/stats.json
                 └─ git commit + push (only if changed)
                      └─ Vercel auto-deploy → site renders new numbers
```

At runtime the Next.js pages read **only** `web/public/data/stats.json`. They become fully
static (no render-time fetch, no ISR-from-Jolpica, no rate-limit surface).

## Components

### 1. Sync script — `web/scripts/sync-stats.ts`
- Run via `tsx` (added as a dev dependency): `"sync-stats": "tsx scripts/sync-stats.ts"` in
  `web/package.json`.
- Reuses the aggregation logic in `lib/jolpica.ts` (`getConstructorStandings`,
  `getDriverStandings`, `getSeasonStats`, `getDriverCareer`). The Ergast `driverId` for each
  driver comes from the live driver standings; career totals are fetched per driver.
- **Polite fetching:** all Jolpica requests go through a single throttled helper —
  sequential (no `Promise.all` bursts), ~300ms spacing, retry with backoff on 429/5xx
  (e.g., 3–4 attempts). Total volume ≈ 150 calls completing in ~1 minute, well under
  Jolpica's hourly cap.
- **Atomic output:** build the full result object in memory; only `writeFile` once every
  critical section succeeded. If any critical fetch ultimately fails, `process.exit(1)`
  without writing — so a partial/broken file is never produced.
- Writes `web/public/data/stats.json`:
  ```jsonc
  {
    "updatedAt": "2026-06-21T06:00:00Z",
    "season": "2026",
    "constructors": [ { "position", "constructorId", "name", "points", "wins" } ],
    "drivers":      [ { "position", "driverId", "code", "givenName", "familyName",
                        "nationality", "points", "wins", "constructorId", "constructorName" } ],
    "seasonStats":  { "<CODE>": { "races", "wins", "podiums", "poles", "fastestLaps" } },
    "career":       { "<driverId>": { "races", "wins", "podiums", "poles", "fastestLaps" } }
  }
  ```

### 2. Frontend reader — `web/lib/stats.ts`
- Imports `stats.json` and exposes typed getters mirroring the shapes the pages already
  consume:
  - `getConstructorStandings(): ConstructorStanding[]`
  - `getDriverStandings(): DriverStanding[]`
  - `seasonStat(code): SeasonDriverStat | undefined`
  - `career(driverId): DriverCareer | null`
  - `statsUpdatedAt(): string`
- Pure synchronous reads (no network). Falls back to `teams.json` / `drivers.json` when an
  entry is missing so the core numbers never render "—".

### 3. Page changes
- `app/teams/[team]/page.tsx`: replace the `await getConstructorStandings()/getDriverStandings()
  /getSeasonStats()` and per-driver `await getDriverCareer(...)` calls with synchronous
  `lib/stats.ts` reads. Remove `getCareerRevalidate` usage and the career revalidate loop.
- `app/drivers/page.tsx`: replace its live `getDriverStandings()` with the static read.
- Drop `export const revalidate` tied to Jolpica on these pages (they're static now;
  they refresh when `stats.json` changes and Vercel redeploys). The "Live from Jolpica"
  badge on the Drivers page becomes a **"Last updated &lt;date&gt;"** badge driven by
  `stats.json.updatedAt` (formatted, e.g., "Last updated 21 Jun 2026").
- `lib/jolpica.ts` stays (now consumed by the sync script). The Races tab keeps using
  `getSchedule` live.

### 4. GitHub Action — `.github/workflows/sync-stats.yml`
- Triggers: `schedule` weekly cron **scoped to the race season** — Mondays ~06:00 UTC,
  March–December only (`cron: "0 6 * 3-12 1"`) **and** `workflow_dispatch` (manual, available
  year-round for off-season/ad-hoc refreshes).
- Steps: `actions/checkout` → `actions/setup-node` (Node 20+) → `npm ci` (working dir `web/`)
  → `npm run sync-stats` → if `web/public/data/stats.json` has a git diff, configure a bot
  identity, commit (`chore: refresh F1 stats [skip ci]`) and push to `main` using the
  built-in `GITHUB_TOKEN`.
- A week with no new results → no git diff → no commit → no deploy.

## Data flow

1. Action runs weekly → script fetches fresh Jolpica data (throttled) → `stats.json`.
2. If changed, committed to `main` → Vercel redeploys.
3. Visitors load fully static pages that read `stats.json`. No live calls.

## Error handling

- **Script:** ret/backoff on transient errors; non-zero exit + no write on unrecoverable
  failure. The previous good `stats.json` remains in the repo, so the deployed site keeps
  showing the last successful race's numbers.
- **Action:** a failed run surfaces as a red check / notification; nothing is committed.
- **Frontend:** missing driver/team entry falls back to `drivers.json` / `teams.json` values.

## Testing / verification

- Run `npm run sync-stats` locally → confirm `stats.json` is written with all 22 drivers'
  career totals populated (e.g., Gasly ≈ 185 races) and per-team season aggregates.
- `npm run build` → confirm no Jolpica calls at build (offline build succeeds) and team /
  drivers pages show real numbers, no "—".
- Temporarily simulate a fetch failure → confirm the script exits non-zero and does **not**
  overwrite `stats.json`.
- Trigger the Action via `workflow_dispatch` → confirm it commits an updated `stats.json`
  and Vercel redeploys.

## Rollout

1. Add script + `lib/stats.ts` + generate the first `stats.json` (commit it).
2. Switch the two pages to static reads; verify build + visuals.
3. Add the workflow; test via manual dispatch.
