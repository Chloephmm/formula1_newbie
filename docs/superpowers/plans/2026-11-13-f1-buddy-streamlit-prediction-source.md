# F1 Buddy Streamlit Prediction Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every F1 Buddy race forecast answer use only prediction publications available to the Streamlit ML Prediction dashboard, and show the latest confirmed upcoming-race forecast regardless of its generation date.

**Architecture:** The Next.js server reads the same fixed GitHub `main` prediction feed as deployed Streamlit. A focused reader validates and briefly caches published JSON; a selector maps confirmed current and Streamlit-visible archived forecasts into the existing chat reply contract. The chatbot never invokes Streamlit or ML code and never substitutes Jolpica results as predictions.

**Tech Stack:** Next.js 16 route handler, TypeScript 5, Node `fetch` and `crypto`, `tsx`/Node tests, ESLint 9, Vercel.

---

## Source and scope contract

The authoritative source is `https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data/prediction_feed.json`, which deployed Streamlit reads through `streamlit_app/app.py:67` and `streamlit_app/confirmed_feed.py:43`. Streamlit's archive index is `predictions/index.json` under the same fixed data root. `streamlit_app/prediction_data.py:182-223` defines validation of confirmed feed revisions and receipts; `streamlit_app/confirmed_feed.py:59-101` defines row ordering and display mode.

“Latest” means `feed.current.prediction` for `feed.current_event_id`, with its confirmed receipt. It does not mean the feed's most recent status update or a prediction generated today. On the inspected November 13 data, `current_event_id=2026-21`, the race is Las Vegas on November 22, and the confirmed prediction was generated November 9.

Prediction values must not come from `next_race_prediction.json`, `predictions.json`, Jolpica, or a chat-generated model run. The existing standalone race schedule and actual result paths may still use Jolpica. The model accuracy answer continues to read `metrics.json` because it is an evaluation metric, not a race forecast.

## File map

| Path | Responsibility |
|---|---|
| `web/lib/chatbot/prediction-feed.ts` (new) | Fetch fixed Streamlit publication URLs, validate confirmed feed integrity, and retain a short last-good cache. |
| `web/lib/chatbot/published-predictions.ts` (new) | Select current or named dashboard-visible forecast and map rows into the chat prediction contract. |
| `web/lib/chatbot/data.ts` | Remove the old synchronous forecast getter and `predictions.json` import; retain race/schedule/actual-result helpers and their needed imports. |
| `web/lib/chatbot/responder.ts` | Await the published prediction provider; label publication time, mode, and cached responses. |
| `web/tests/chatbot-prediction-feed.test.ts` (new) | Cover feed validation, caching, outages, race rollover, and archive path safety. |
| `web/tests/chatbot-published-predictions.test.ts` (new) | Cover current, post-qualifying, named archive, unavailable, and source-boundary behavior. |
| `web/app/api/f1-buddy/route.ts` | Pin the server route to the Node.js runtime used by the feed reader. |
| `web/tests/chatbot-data.test.ts`, `web/tests/chatbot-responder.test.ts`, `web/tests/chatbot-route.test.ts` | Replace old snapshot/estimate expectations with provider-backed behavior. |
| `web/package.json` | Include the two new test files in `test:chatbot`. |

Do not change `web/public/data/`, `ml/`, `streamlit_app/`, or `.github/workflows/`. Preserve unrelated untracked files. Do not commit or push; the user will commit.

### Task 1: Read and validate the published current feed

**Files:** Create `web/lib/chatbot/prediction-feed.ts`; create `web/tests/chatbot-prediction-feed.test.ts`; modify `web/package.json`.

- [ ] **Step 1: Add feed reader tests before implementation.** Use the repository's `web/public/data/prediction_feed.json` as a read-only valid fixture. Inject `fetch` and a clock. Assert: a valid confirmed Las Vegas selection loads; a changed `revision`, `prediction_id`, receipt checksum, publication ID, or event identity fails; a missing `current` yields unavailable; a timeout or HTTP 503 uses only a previously validated last-good copy. Assert a second request inside 60 seconds does not fetch again. Use test-local copies of the fixture and never rewrite publication files.
- [ ] **Step 2: Run the focused test red.** From `web/`, run `node --import tsx --test tests/chatbot-prediction-feed.test.ts`. Expected: failure because the reader does not exist.
- [ ] **Step 3: Implement a server-only reader with this interface.** The URL must be a constant, never derived from a chat message or an archive entry. Cap response size (for example 1 MiB), abort after five seconds, cache only validated bodies for 60 seconds, and use `If-None-Match` when an ETag exists.

```ts
export const FEED_URL =
  "https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data/prediction_feed.json";
export const DATA_BASE_URL = FEED_URL.slice(0, -"prediction_feed.json".length);

export type ConfirmedFeed = {
  schema_version: 1;
  current_event_id: string;
  feed_updated_at: string;
  event: Record<string, unknown>;
  current: ConfirmedSelection | null;
  previous: ConfirmedSelection | null;
  initial: ConfirmedSelection | null;
  status: Record<string, unknown>;
  revision: string;
};
export type ConfirmedSelection = {
  event: Record<string, unknown>;
  prediction: Record<string, unknown>;
  publication: Record<string, unknown>;
};
export type FeedRead =
  | { available: true; feed: ConfirmedFeed; cached: boolean }
  | { available: false };
export type FeedTransport = (url: string, init: RequestInit) => Promise<Response>;

export function validateConfirmedFeed(value: unknown): ConfirmedFeed;
export function createFeedReader(options?: {
  transport?: FeedTransport;
  nowMs?: () => number;
  ttlMs?: number;
}): {
  readCurrent(): Promise<FeedRead>;
  readArchiveIndex(): Promise<unknown>;
  readArchiveArtifact(relative: string): Promise<unknown>;
};
```

Implement canonical JSON recursively with sorted object keys, unchanged array order, UTF-8 SHA-256, and no non-finite numbers. Match `streamlit_app/prediction_data.py` for `revision`, the prediction semantic hash (`predictedQualifying`, `preQualifyingPodium`, `realQualifying`, `realGridPodium` sorted by `driver_id` for hashing), receipt checksum (`SHA256(canonical(prediction) + "\n")`), and publication ID (SHA-256 of receipt without `publication_id`). Check `confirmed === true`, event `(season, round)` identity throughout, `prediction.mode` in `predicted_qualifying | actual_qualifying`, forecast error absent, and timezone-aware generated/published/cutoff timestamps with `generated_at <= published_at < cutoff_at`. Do not return partially validated data.

For archive reads, accept only the exact `predictions/index.json` path and artifact paths matching `^prediction_snapshots/[1-9][0-9]*-[1-9][0-9]*/feed\.json$` or `^predictions/[1-9][0-9]*-[1-9][0-9]*\.json$`. Check the URL after joining remains under `DATA_BASE_URL`. Do not accept redirects to a different host. Never cache an invalid response. If a refresh returns an older `feed_updated_at` for the same event, retain the newer validated cache; accept a newly validated event when its race is upcoming.

- [ ] **Step 4: Run the focused test green.** Expected: all Task 1 cases pass. Run `npx tsc --noEmit`; expected exit 0.
- [ ] **Step 5: Review the reader diff.** `git diff --check` must pass. Confirm the reader has no write, subprocess, ML import, arbitrary URL input, or bundled forecast fallback.

### Task 2: Select only Streamlit-visible current and archived forecasts

**Files:** Create `web/lib/chatbot/published-predictions.ts` and `web/tests/chatbot-published-predictions.test.ts`; modify `web/lib/chatbot/data.ts`.

- [ ] **Step 1: Write selection tests red.** Inject a feed reader, archive index reader, artifact reader, and clock. Test a generic November 13 request returns the November 9 confirmed Las Vegas prediction; a `feed.current` post-qualifying update selects actual qualifying and updated podium rows; rows are sorted by `position` and `rank` before taking three; a race whose `race_start_at` is past returns unavailable for a generic request; a new event supersedes the old cached event. Test named Mexico and United States predictions from Streamlit archive entries, a named current Las Vegas request, unmatched race/year, a malformed archive artifact, and a legacy Monaco 2025 estimate that exists only in `predictions.json` (must be unavailable).
- [ ] **Step 2: Run `node --import tsx --test tests/chatbot-published-predictions.test.ts`.** Expected: failure because the selector does not exist.
- [ ] **Step 3: Implement the prediction selection interface and mapping.** The current selection must come only from `readCurrent()`. If `race_start_at <= now`, return unavailable for an unnamed request. A named request may select the matching current event or one unique archive index entry; fetch only the entry's allowlisted `prediction_snapshots/<season>-<round>/feed.json` or `predictions/<season>-<round>.json` under `DATA_BASE_URL`. Validate index schema, identity, path, and artifact content before mapping. Confirmed archive feeds use the Task 1 validator; legacy artifacts use the same `schema_version=2`, race ID, forecast row, probability, and timestamp checks used by `streamlit_app/prediction_feed.py:64-103` and are labelled “saved dashboard archive,” not “confirmed publication.” No request may look up `predictions.json`.

```ts
export type PublishedPrediction =
  | { available: false }
  | {
      available: true;
      source: "confirmed-feed" | "dashboard-archive";
      cached: boolean;
      generatedAt: string;
      publishedAt?: string;
      race: { name: string; season: number; round: number; country: string; date: string };
      predictedQualifying: Array<{ position: number; driverName: string; gap: number | null }>;
      podium: Array<{ driverName: string; podiumProbability: number }>;
      qualifyingMode: "predicted" | "actual";
      predictionUrl: string;
    };

export async function getPublishedPrediction(
  search?: string,
  season?: number,
  now?: Date,
): Promise<PublishedPrediction>;
```

For a confirmed `actual_qualifying` selection, choose `realQualifying` and `realGridPodium` from `feed.current.prediction.forecast`; otherwise choose `predictedQualifying` and `preQualifyingPodium`. Map `feed.event.race_name` and `race_start_at`, prediction `generated_at`, and receipt `published_at`. Preserve the Streamlit URL as a link only. Build an injectable factory around the exported function so tests need no network.

- [ ] **Step 4: Remove `getPublishedPrediction`, `historicalPredictions`, and the `predictions.json` import from `web/lib/chatbot/data.ts`.** Keep `getSavedSessionResults`, race lookup, and schedule/actual result behavior. Keep a detailed prediction import only where those non-forecast helpers still need race identity or actual qualifying; no forecast reply may read it.
- [ ] **Step 5: Run the two focused tests and `npx tsc --noEmit`.** Expected: pass. Update the old `web/tests/chatbot-data.test.ts` cases that called the removed synchronous prediction function to call the new injected selector or delete only duplicate cases covered by the new suite. Keep unrelated race and data tests intact.

### Task 3: Wire prediction replies to the new source

**Files:** Modify `web/lib/chatbot/responder.ts`, `web/app/api/f1-buddy/route.ts`, `web/tests/chatbot-responder.test.ts`, and `web/tests/chatbot-route.test.ts`.

- [ ] **Step 1: Write responder and route tests red.** Inject a published prediction provider. Assert that “next race prediction” shows Las Vegas, top three qualifying and podium rows, generated and published timestamps, a Streamlit link, and a disclaimer when the confirmed forecast predates the question. Assert cached responses say they are cached. Assert `actual_qualifying` says “post-qualifying.” Assert an unavailable provider never produces prediction values from `predictions.json`, `next_race_prediction.json`, or Jolpica; named unavailable races may still show separately labelled actual results. The route should return the typed JSON contract and `Cache-Control: no-store`.
- [ ] **Step 2: Run `node --import tsx --test tests/chatbot-responder.test.ts tests/chatbot-route.test.ts`.** Expected: the new source and provenance assertions fail.
- [ ] **Step 3: Add an injectable async provider to `ResponderDependencies` and await it in `answerPrediction`.** Remove the `allowHistoricalEstimate` argument and the `historical-estimate` response branches. Keep the existing heading, ranking, quick replies, disclaimer, and Streamlit link shapes. Use `publishedAt` for the publication label when present, `generatedAt` for generation, `qualifyingMode` for stage, and a short cached notice only when `cached` is true.

```ts
import { getPublishedPrediction, type PublishedPrediction } from "./published-predictions";

export interface ResponderDependencies {
  now: () => Date;
  getSessionResults: typeof getSessionResults;
  getNextRaceSnapshot: typeof getNextRaceSnapshot;
  resolveRaceSnapshot: typeof resolveRaceSnapshot;
  getSavedDriverStandings: () => DriverStandingsSnapshot;
  getSavedConstructorStandings: () => ConstructorStandingsSnapshot;
  getLiveDriverStandings: typeof getLiveDriverStandings;
  getLiveConstructorStandings: typeof getLiveConstructorStandings;
  getSavedSessionResults: typeof getSavedSessionResults;
  getPreviousRaceFromSchedule: typeof getPreviousRaceFromSchedule;
  getPublishedPrediction: (
    search?: string,
    season?: number,
    now?: Date,
  ) => Promise<PublishedPrediction>;
}

// In answerPrediction, after the accuracy and explanation branches:
const prediction = await dependencies.getPublishedPrediction(
  parsed.searchTerm,
  parsed.season,
  dependencies.now(),
);
```

Set `getPublishedPrediction` in `defaultResponderDependencies`. In `web/app/api/f1-buddy/route.ts`, add `export const runtime = "nodejs";` next to the existing route constants.

- [ ] **Step 4: Run the responder and route tests.** Expected: all pass. Run `npm run test:chatbot`; expected: every chatbot test passes with zero failures.

### Task 4: Verify source isolation and production readiness

**Files:** Test and inspect only; no prediction artifact edits.

- [ ] **Step 1: Run from `web/`:** `npm run test:chatbot`, `npx tsc --noEmit`, `npx eslint app/api/f1-buddy/route.ts components/F1Buddy.tsx components/Reveal.tsx components/f1-buddy lib/chatbot tests`, and `npm run build`. Expected: all exit 0 and Next.js completes static generation.
- [ ] **Step 2: Inspect imports and calls:** `rg -n 'next_race_prediction|predictionsData|historicalPredictions|getPublishedPrediction|prediction_feed' web/lib/chatbot web/app/api/f1-buddy`. Expected: forecast replies depend only on `published-predictions.ts`, while legacy snapshot references, if any, serve race identity or actual results only.
- [ ] **Step 3: Inspect scope:** `git diff --check` and `git status --short`. Confirm no changed path under `web/public/data/`, `ml/`, `streamlit_app/`, or `.github/workflows/`. Preserve the user's unrelated untracked files. Leave the finished implementation uncommitted for the user's own commit.
