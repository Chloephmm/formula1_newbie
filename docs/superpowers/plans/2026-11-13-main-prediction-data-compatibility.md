# Main Prediction Data Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production Next.js build read the prediction data committed on `main` without changing or regenerating that data.

**Architecture:** Keep `web/public/data/next_race_prediction.json` as the authoritative current snapshot and adapt it at the chatbot JSON boundary. The current legacy Las Vegas snapshot passes through the existing legacy contract, while schema-v2 archives already on `main` continue through the existing normalizer.

**Tech Stack:** Next.js 16, TypeScript 5, Node test runner with `tsx`, ESLint 9, Vercel Git deployment.

**Execution prerequisite:** This plan is reviewed and committed before Task 1 begins.

---

## File map

| File | Responsibility |
|---|---|
| `web/lib/chatbot/data.ts` | Accept the current snapshot as either supported input schema before normalization. |
| `web/tests/chatbot-data.test.ts` | Assert driver stats, local/fallback race resolution, and current-race selection from `main`. |
| `web/tests/chatbot-responder.test.ts` | Assert that the latest prediction response reflects `main`'s Las Vegas snapshot. |

No file under `web/public/data/`, `ml/`, or `.github/workflows/` may change.

### Task 1: Fix the imported current-snapshot type boundary

**Files:**
- Modify: `web/lib/chatbot/data.ts:193`

- [ ] **Step 1: Reproduce the failing TypeScript check**

Run:

```powershell
Set-Location web
npx tsc --noEmit
```

Expected: FAIL with `TS2352` at `lib/chatbot/data.ts(193,44)` because the legacy
Las Vegas JSON is being asserted directly as `SchemaV2PredictionFile`.

- [ ] **Step 2: Route the imported JSON through the supported union boundary**

Replace:

```ts
const prediction = normalizePredictionFile(predictionData as SchemaV2PredictionFile);
```

with:

```ts
const prediction = normalizePredictionFile(
  predictionData as unknown as PredictionInput,
);
```

The `unknown` boundary is limited to the imported repository JSON. Runtime
selection remains in `normalizePredictionFile`: legacy input passes through and
schema-v2 input is mapped to the shared legacy-shaped contract.

- [ ] **Step 3: Verify TypeScript accepts the data committed on main**

Run:

```powershell
npx tsc --noEmit
```

Expected: PASS with exit code 0 and no TypeScript diagnostics.

- [ ] **Step 4: Commit the adapter correction**

```powershell
git add web/lib/chatbot/data.ts
git commit -m "fix: accept main prediction snapshot schema"
```

### Task 2: Align chatbot regression expectations with main data

**Files:**
- Modify: `web/tests/chatbot-data.test.ts`
- Modify: `web/tests/chatbot-responder.test.ts`

- [ ] **Step 1: Preserve the failing main-data regression evidence**

Run:

```powershell
npm run test:chatbot
```

Expected: 73 pass and 4 fail. The failures show stale feature-branch expectations:
Hamilton position, Las Vegas local lookup, the active race name, and the latest
prediction response.

- [ ] **Step 2: Update saved driver expectations to main's stats snapshot**

In `web/tests/chatbot-data.test.ts`, use:

```ts
assert.equal(driver.standing?.position, 4);
assert.equal(driver.standing?.points, 261);
assert.equal(driver.seasonStats?.podiums, 7);
```

- [ ] **Step 3: Keep schedule fallback coverage on a race absent from local snapshots**

Replace the Las Vegas fallback case with this Abu Dhabi case:

```ts
test("named race lookup falls back to the selected season's Jolpica schedule", async () => {
  const requestedSeasons: string[] = [];
  const race = await resolveRaceSnapshot("abu dhabi", 2026, async (season) => {
    requestedSeasons.push(season ?? "");
    return {
      live: true,
      data: [
        {
          season: 2026,
          round: 22,
          name: "Abu Dhabi Grand Prix",
          circuit: "Yas Marina Circuit",
          locality: "Abu Dhabi",
          country: "UAE",
          date: "2026-12-06",
        },
      ],
    };
  });

  assert.deepEqual(requestedSeasons, ["2026"]);
  assert.equal(race?.name, "Abu Dhabi Grand Prix");
  assert.equal(race?.round, 22);
});
```

- [ ] **Step 4: Assert that main's compatible current snapshot is selected locally**

Update the next-race test to:

```ts
test("next-race lookup uses a compatible prediction snapshot before Jolpica", async () => {
  let fallbackCalls = 0;
  const race = await getNextRaceSnapshot(new Date("2026-11-09T12:00:00Z"), async () => {
    fallbackCalls += 1;
    return { data: [], live: false };
  });

  assert.equal(race?.name, "Las Vegas Grand Prix");
  assert.equal(fallbackCalls, 0);
});
```

- [ ] **Step 5: Assert that the latest response reflects main's Las Vegas output**

Update the latest-prediction test in `web/tests/chatbot-responder.test.ts` to:

```ts
test("latest prediction exposes only published values and a disclaimer", async () => {
  const reply = await answerF1Question(
    "Show the latest F1 Buddy prediction",
    {
      ...fixedDependencies,
      now: () => new Date("2026-11-09T12:00:00Z"),
    },
  );

  assert.equal(reply.intent, "predictions");
  assert.equal(reply.heading, "Las Vegas Grand Prix prediction");
  assert.match(textOf(reply), /Charles Leclerc/);
  assert.match(textOf(reply), /Max Verstappen/);
  assert.match(textOf(reply), /76\.6%/);
  assert.match(textOf(reply), /not guarantees/i);
  assert.match(textOf(reply), /2026-11-09/);
  assert.ok(reply.sections.some((section) => section.kind === "link"));
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Model Accuracy", "How Predictions Work", "Qualifying Predictions"],
  );
  assertReplyContract(reply);
});
```

- [ ] **Step 6: Run the chatbot regression suite**

Run:

```powershell
npm run test:chatbot
```

Expected: 77 tests pass, 0 fail.

- [ ] **Step 7: Commit the main-data expectations**

```powershell
git add web/tests/chatbot-data.test.ts web/tests/chatbot-responder.test.ts
git commit -m "test: align chatbot with main prediction data"
```

### Task 3: Verify and release the direct main fix

**Files:**
- Verify only: `web/`
- Verify unchanged: `web/public/data/`, `ml/`, `.github/workflows/`

- [ ] **Step 1: Run all web verification gates**

Run from `web/`:

```powershell
npm run test:chatbot
npx tsc --noEmit
npx eslint app/api/f1-buddy/route.ts components/F1Buddy.tsx components/Reveal.tsx components/f1-buddy lib/chatbot tests/chatbot-contract.test.ts tests/chatbot-back-home.test.ts tests/chatbot-data.test.ts tests/chatbot-disconnection.test.ts tests/chatbot-intents.test.ts tests/chatbot-responder.test.ts tests/chatbot-route.test.ts tests/chatbot-state.test.ts tests/chatbot-ui.test.ts
npm run build
```

Expected: 77 chatbot tests pass; TypeScript and ESLint exit 0; Next.js reports
`Compiled successfully` and completes static page generation.

- [ ] **Step 2: Prove the protected data and pipeline scope is unchanged**

Run from the repository root:

```powershell
git diff --name-only 104b3c7..HEAD
git diff --check 104b3c7..HEAD
```

Expected changed paths are limited to:

```text
docs/superpowers/specs/2026-11-13-main-prediction-data-compatibility-design.md
docs/superpowers/plans/2026-11-13-main-prediction-data-compatibility.md
web/lib/chatbot/data.ts
web/tests/chatbot-data.test.ts
web/tests/chatbot-responder.test.ts
```

Expected: `git diff --check` exits 0. No path begins with `web/public/data/`,
`ml/`, or `.github/workflows/`.

- [ ] **Step 3: Create a recoverable remote backup of the failed main commit**

```powershell
git push origin 104b3c7:refs/heads/backup/main-before-prediction-compatibility-2026-11-13
```

Expected: GitHub creates `backup/main-before-prediction-compatibility-2026-11-13`
at `104b3c7`.

- [ ] **Step 4: Push main normally without force**

```powershell
git push origin main:main
```

Expected: GitHub advances `main` from `104b3c7` to the verified local HEAD.

- [ ] **Step 5: Verify the new Vercel production deployment**

Use the Vercel deployment list filtered to the new `main` commit SHA, then inspect
the deployment and its build events.

Expected: target `production`, state `READY`, and no TypeScript failure at
`web/lib/chatbot/data.ts:193`. If Vercel reports `ERROR`, report the exact new log
failure and do not claim deployment success.
