# Native F1 Buddy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the iframe-based Streamlit chatbot with a polished, native Next.js F1 Buddy that answers five approved Formula 1 topics from the website's published data, using Jolpica only when saved data cannot answer a race-data question.

**Architecture:** Keep the existing root-layout mount, but replace the iframe shell with reusable React components and a client-side reducer. A server-only responder behind `POST /api/f1-buddy` classifies rule-based questions, reads the existing JSON/metadata helpers first, and calls the existing throttled Jolpica client only for missing schedule or official-result data. The API returns typed presentation sections rather than HTML or Markdown, allowing a future AI responder to replace the rule engine without redesigning the UI.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript 5, Tailwind CSS 4, Node's built-in test runner with `tsx`, existing Jolpica client, existing generated JSON in `web/public/data`.

---

## Guardrails and fixed decisions

- Work only on branch `feature2` in `C:\Users\user\Documents\Codex\Formula1`.
- Do not edit or run anything under `ml/`, `web/public/data/`, or `.github/`.
- Do not run model training, prediction generation, data synchronization, or refresh workflows.
- Do not edit the sibling repository `C:\Users\user\Documents\Codex\f1buddy-ai`; preserve it as a disconnected reference implementation.
- Keep exactly five topics: Race details, Standings, Drivers, Teams, and Predictions.
- Keep RAG, an LLM, a database, WhatsApp, and user accounts out of this phase.
- Never synthesize a missing prediction. Return an explicit unavailable response instead.
- Preserve chat history when minimizing. Clear the chat and restore the welcome screen when closing.
- Do not close when the user clicks outside the panel.

## Final file map

Create:

- `web/app/api/f1-buddy/route.ts`
- `web/components/f1-buddy/ChatHeader.tsx`
- `web/components/f1-buddy/ChatInput.tsx`
- `web/components/f1-buddy/ChatMessage.tsx`
- `web/components/f1-buddy/F1BuddyLauncher.tsx`
- `web/components/f1-buddy/F1BuddyPanel.tsx`
- `web/components/f1-buddy/QuickReplies.tsx`
- `web/components/f1-buddy/ResponseSections.tsx`
- `web/components/f1-buddy/TopicCards.tsx`
- `web/components/f1-buddy/chatReducer.ts`
- `web/lib/chatbot/data.ts`
- `web/lib/chatbot/intents.ts`
- `web/lib/chatbot/responder.ts`
- `web/lib/chatbot/topics.ts`
- `web/lib/chatbot/types.ts`
- `web/public/images/f1-buddy-car.jpg`
- `web/tests/chatbot-contract.test.ts`
- `web/tests/chatbot-data.test.ts`
- `web/tests/chatbot-disconnection.test.ts`
- `web/tests/chatbot-intents.test.ts`
- `web/tests/chatbot-responder.test.ts`
- `web/tests/chatbot-route.test.ts`
- `web/tests/chatbot-state.test.ts`
- `web/tests/chatbot-ui.test.ts`

Modify:

- `.gitignore`
- `streamlit_app/app.py`
- `streamlit_app/README.md`
- `streamlit_app/requirements.txt`
- `web/components/F1Buddy.tsx`
- `web/lib/jolpica.ts`
- `web/lib/types.ts`
- `web/package.json`

Delete:

- `chatbot_app/README.md`
- `chatbot_app/app.py`
- `chatbot_app/requirements.txt`
- `chatbot_app/vendor/README.md`
- `chatbot_app/vendor/f1buddy_ai-0.2.1-py3-none-any.whl`
- `web/.env.example`
- `web/lib/chatbot.ts`
- `web/tests/chatbot.test.ts`

Leave unchanged:

- `web/app/layout.tsx` (it already mounts `F1Buddy` globally)
- all files in `ml/`, `web/public/data/`, and `.github/`
- all files in `C:\Users\user\Documents\Codex\f1buddy-ai`

---

### Task 1: Record the protected baseline and disconnect the Streamlit chatbot

**Files:**

- Create: `web/tests/chatbot-disconnection.test.ts`
- Modify: `.gitignore`
- Modify: `streamlit_app/app.py:20-23,608-619`
- Modify: `streamlit_app/README.md`
- Modify: `streamlit_app/requirements.txt`
- Delete: `chatbot_app/`

- [ ] **Step 1: Confirm the branch and establish clean protected paths**

Run from the repository root:

```powershell
git branch --show-current
git diff --exit-code -- ml web/public/data .github
git -C ..\f1buddy-ai status --short
```

Expected: the branch is `feature2`; the protected-path diff command prints nothing and exits 0. Record the sibling repository's exact status so the same status can be confirmed at the end.

- [ ] **Step 2: Write the failing disconnection test**

Create `web/tests/chatbot-disconnection.test.ts` with source-level assertions that:

```ts
assert.doesNotMatch(streamlitApp, /f1buddy_ai|render_chatbot/);
assert.doesNotMatch(streamlitRequirements, /f1buddy_ai|chatbot_app/);
assert.equal(existsSync(resolve(repoRoot, "chatbot_app")), false);
assert.doesNotMatch(gitignore, /f1buddy_ai.*\.whl/);
```

Resolve `repoRoot` from `import.meta.url` so the test works regardless of the current shell directory.

- [ ] **Step 3: Run the test and verify it fails for the old integration**

Run:

```powershell
cd web
node --import tsx --test tests/chatbot-disconnection.test.ts
```

Expected: FAIL because the Streamlit hook, wheel dependency, and `chatbot_app` still exist.

- [ ] **Step 4: Remove only the chatbot hook from the prediction dashboard**

Use `apply_patch` to remove the optional `f1buddy_ai` import block and the final `render_chatbot(...)`/fallback-caption block from `streamlit_app/app.py`. Do not touch `forecast`, `next_race`, `retrain_live`, `ML_DIR`, date selection, refresh behavior, or prediction rendering.

Remove the wheel line from `streamlit_app/requirements.txt`, remove the entire “Optional F1 Buddy popup” section from `streamlit_app/README.md`, and change the requirements file description to “dashboard dependencies.”

- [ ] **Step 5: Remove the standalone Streamlit chatbot copy**

Run the explicit tracked deletion:

```powershell
git rm -r chatbot_app
```

Then remove this obsolete allow-list line from `.gitignore`:

```gitignore
!chatbot_app/vendor/f1buddy_ai-0.2.1-py3-none-any.whl
```

The sibling `..\f1buddy-ai` repository remains untouched and recoverable independently.

- [ ] **Step 6: Run the disconnection test and dashboard syntax check**

Run:

```powershell
cd web
node --import tsx --test tests/chatbot-disconnection.test.ts
cd ..
python -m py_compile streamlit_app/app.py
```

Expected: PASS and no Python output.

- [ ] **Step 7: Commit the isolated disconnection**

```powershell
git add .gitignore streamlit_app web/tests/chatbot-disconnection.test.ts
git commit -m "refactor: disconnect Streamlit F1 Buddy"
```

---

### Task 2: Define the stable chatbot contract, five topics, and intent parser

**Files:**

- Create: `web/lib/chatbot/types.ts`
- Create: `web/lib/chatbot/topics.ts`
- Create: `web/lib/chatbot/intents.ts`
- Create: `web/tests/chatbot-contract.test.ts`
- Create: `web/tests/chatbot-intents.test.ts`

- [ ] **Step 1: Write contract and topic tests first**

Test that there are exactly five unique topic IDs and that each topic has a non-empty title, description, prompt, and icon key. Assert these IDs in this order:

```ts
["race", "standings", "drivers", "teams", "predictions"]
```

Test these representative intent cases:

```ts
[
  ["When is the next F1 race?", "race"],
  ["Show the Mexico 2026 race result", "race"],
  ["Who leads the constructor standings?", "standings"],
  ["Tell me about Lewis Hamilton", "drivers"],
  ["Who drives for Ferrari?", "teams"],
  ["Show the latest podium prediction", "predictions"],
  ["Explain DRS", "unsupported"],
]
```

Also assert that `parseQuestion("Mexico 2026 qualifying results")` extracts season `2026`, a normalized `mexico` search term, and `resultKind: "qualifying"`.

- [ ] **Step 2: Run the tests and verify missing-module failures**

```powershell
cd web
node --import tsx --test tests/chatbot-contract.test.ts tests/chatbot-intents.test.ts
```

Expected: FAIL because the contract, topics, and parser do not exist.

- [ ] **Step 3: Add the presentation contract**

In `web/lib/chatbot/types.ts`, implement this discriminated contract:

```ts
export type ChatIntent =
  | "race"
  | "standings"
  | "drivers"
  | "teams"
  | "predictions"
  | "unsupported";

export type ResultKind = "schedule" | "race" | "qualifying";

export type ChatSection =
  | { kind: "facts"; items: Array<{ label: string; value: string }> }
  | { kind: "ranking"; title: string; items: Array<{ rank: number; label: string; value: string; image?: string }> }
  | { kind: "paragraph"; text: string }
  | { kind: "link"; label: string; href: string };

export interface ChatReply {
  intent: ChatIntent;
  heading: string;
  body: string;
  sections: ChatSection[];
  quickReplies: Array<{ label: string; prompt: string }>;
  sourceUpdatedAt?: string;
}

export interface ChatRequest {
  message: string;
}

export interface ParsedQuestion {
  intent: ChatIntent;
  normalized: string;
  season?: number;
  searchTerm?: string;
  resultKind?: ResultKind;
  standingKind?: "drivers" | "constructors";
}
```

Keep the API free of rendered HTML, raw Markdown, React nodes, and model-specific fields.

- [ ] **Step 4: Add the five topic definitions**

In `web/lib/chatbot/topics.ts`, export `CHAT_TOPICS` with these exact launcher prompts:

```ts
[
  { id: "race", title: "Race details", description: "Schedule, results, circuit info", prompt: "When is the next F1 race?", icon: "flag" },
  { id: "standings", title: "Standings", description: "Driver and team rankings", prompt: "Show the current driver standings.", icon: "chart" },
  { id: "drivers", title: "Drivers", description: "Stats and career information", prompt: "Tell me about Max Verstappen.", icon: "driver" },
  { id: "teams", title: "Teams", description: "Performance and lineups", prompt: "Tell me about Ferrari.", icon: "shield" },
  { id: "predictions", title: "Predictions", description: "Published qualifying and podium forecasts", prompt: "Show the latest F1 Buddy prediction.", icon: "trend" },
] as const;
```

- [ ] **Step 5: Implement deterministic parsing**

In `web/lib/chatbot/intents.ts`:

1. Normalize Unicode, lowercase, replace punctuation with spaces, and collapse whitespace.
2. Extract a four-digit season matching `20\d{2}`.
3. Recognize prediction terms before generic race terms.
4. Recognize driver and team names/codes from existing `drivers` and `teams` arrays rather than maintaining duplicate lists.
5. Recognize `constructor/team standings` separately from driver standings.
6. Recognize `qualifying`, `race result`, and schedule/date/circuit wording as `resultKind`.
7. Return `unsupported` for topics outside the approved five.

Use word-boundary/token checks so `race` does not accidentally match arbitrary substrings.

- [ ] **Step 6: Run the focused tests**

```powershell
node --import tsx --test tests/chatbot-contract.test.ts tests/chatbot-intents.test.ts
```

Expected: all tests PASS.

- [ ] **Step 7: Commit the contract and parser**

```powershell
git add web/lib/chatbot web/tests/chatbot-contract.test.ts web/tests/chatbot-intents.test.ts
git commit -m "feat: define F1 Buddy chat contract"
```

---

### Task 3: Build website-first data adapters with bounded Jolpica fallback

**Files:**

- Create: `web/lib/chatbot/data.ts`
- Create: `web/tests/chatbot-data.test.ts`
- Modify: `web/lib/jolpica.ts`
- Modify: `web/lib/types.ts`

- [ ] **Step 1: Write failing data-adapter tests**

Cover these behaviors with fixed dates and no network calls:

- `findDriverSnapshot("hamilton")` returns Lewis Hamilton, Ferrari, saved standings position/points, saved season stats, saved career totals, and the existing driver image path.
- `findTeamSnapshot("ferrari")` returns Ferrari metadata, its two saved drivers, constructor position/points, and the existing team logo path.
- `getStandingsSnapshot("drivers")` and `getStandingsSnapshot("constructors")` use `stats.json` through `web/lib/stats.ts` and expose `statsUpdatedAt()`.
- `findRaceSnapshot("mexico", 2026)` resolves the saved race metadata without Jolpica.
- `getPublishedPrediction("mexico", 2026)` uses `next_race_prediction.json` when it matches and returns the saved predicted qualifying, podium probabilities, generation/as-of timestamp, and qualifying mode.
- `getPublishedPrediction("unavailable race", 2026)` returns `{ available: false }` rather than generating values or reading the less-detailed historical probability archive.
- `getModelMetricsSnapshot()` reads the already-published `metrics.json` values needed by the Model Accuracy follow-up without recalculating them.

- [ ] **Step 2: Run the test and verify it fails**

```powershell
cd web
node --import tsx --test tests/chatbot-data.test.ts
```

Expected: FAIL because `web/lib/chatbot/data.ts` does not exist.

- [ ] **Step 3: Add official-result types and one Jolpica helper**

Extend `web/lib/types.ts` with UI-safe result types:

```ts
export interface SessionResult {
  position: number;
  driverId: string;
  code: string;
  driverName: string;
  constructorName: string;
}

export interface RaceSessionResults {
  raceName: string;
  season: number;
  round: number;
  results: SessionResult[];
}
```

Add this public helper to `web/lib/jolpica.ts` while reusing the existing private `jget`, 500 ms request gate, retries, and Next revalidation:

```ts
export async function getSessionResults(
  season: number,
  round: number,
  session: "results" | "qualifying"
): Promise<{ data: RaceSessionResults | null; live: boolean }>;
```

Map `Results` for a race result and `QualifyingResults` for qualifying. Return `{ data: null, live: false }` on an outage or empty result; never throw into the UI and never substitute a different session.

- [ ] **Step 4: Implement local snapshots**

In `web/lib/chatbot/data.ts`, import and reuse:

- `drivers`, `teams`, `races`, `getDriversForTeam`, and `getTeam` from `web/lib/data.ts`
- saved standings, career, season stats, and update timestamp from `web/lib/stats.ts`
- `TEAM_META`/`teamLogo` from `web/lib/teamMeta.ts`
- `driverPhoto` from `web/lib/assets.ts`
- `next_race_prediction.json` and `metrics.json` as read-only imports
- the existing prediction-site URL from `web/lib/links.ts`

Define explicit TypeScript interfaces for the prediction and metrics JSON shapes in this module. Do not use `any` and do not edit the JSON files. Do not import `predictions.json`: the approved chat response requires the detailed, identity-checked `next_race_prediction.json` publication and must return unavailable for any other race.

Local resolution order must be:

1. published generated JSON and current website helpers;
2. saved static race metadata;
3. `getSessionResults` only when official session results are requested and not saved locally.

For “next race,” find the first saved race with a session date on or after the injected `now` value. If no saved future race exists, call existing `getSchedule()` as a fallback. Inject `now` in the adapter signature so tests do not depend on the clock.

- [ ] **Step 5: Keep caching ownership in existing website helpers**

Do not add a second chatbot cache. Reuse the `next: { revalidate }` behavior, request gate, and retry policy already inside `web/lib/jolpica.ts`. Local JSON imports remain build-time/static data.

- [ ] **Step 6: Run the focused tests and type-check**

```powershell
node --import tsx --test tests/chatbot-data.test.ts
npx tsc --noEmit
```

Expected: all tests PASS and TypeScript exits 0.

- [ ] **Step 7: Commit data access separately**

```powershell
git add web/lib/chatbot/data.ts web/lib/jolpica.ts web/lib/types.ts web/tests/chatbot-data.test.ts
git commit -m "feat: add website-first F1 Buddy data adapters"
```

---

### Task 4: Implement the rule-based responder and native API route

**Files:**

- Create: `web/lib/chatbot/responder.ts`
- Create: `web/app/api/f1-buddy/route.ts`
- Create: `web/tests/chatbot-responder.test.ts`
- Create: `web/tests/chatbot-route.test.ts`

- [ ] **Step 1: Write failing responder tests for every topic**

Use dependency injection for any result lookup so tests never access the network. Assert structured reply content for:

- next race: date, circuit, country/location when available;
- current standings: top three drivers and top three constructors with points and saved update context;
- named driver: team, nationality, position/points, wins/podiums/career facts when saved;
- named team: base, principal, chassis, power unit, lineup, position/points;
- latest prediction: saved race/as-of date, qualifying mode, top predicted qualifying entries, top three podium probabilities, probability disclaimer, and the existing prediction-site link;
- historical prediction unavailable: an explicit “No saved prediction is available” body and no invented ranking;
- unsupported topic: a friendly scope explanation plus the five topic prompts;
- Jolpica outage: a friendly “official results are temporarily unavailable” response, not a thrown exception.

Also assert that every reply has zero to three follow-up suggestions, uses only the `ChatSection` union, and follows the approved labels for its topic.

- [ ] **Step 2: Write failing route validation tests**

Call `POST` directly with `Request` objects and assert:

- malformed JSON returns 400;
- missing/blank `message` returns 400;
- a message longer than 500 characters returns 400;
- a valid prediction request returns 200, `content-type: application/json`, and a `ChatReply`;
- the response includes `Cache-Control: no-store`.

- [ ] **Step 3: Run the tests and verify they fail**

```powershell
cd web
node --import tsx --test tests/chatbot-responder.test.ts tests/chatbot-route.test.ts
```

Expected: FAIL because responder and route modules do not exist.

- [ ] **Step 4: Implement one responder entry point**

Export this signature from `web/lib/chatbot/responder.ts`:

```ts
export async function answerF1Question(
  message: string,
  dependencies: ResponderDependencies = defaultResponderDependencies
): Promise<ChatReply>;
```

Keep all response copy and follow-up selection here. The UI must not know how facts are retrieved. Cap rankings at five rows in chat responses, use `Intl.DateTimeFormat("en-US", { dateStyle: "long" })`, and format probabilities as percentages with one decimal place.

Suggested follow-up mapping:

```ts
const QUICK_REPLIES = {
  race: ["Qualifying Schedule", "Circuit Details", "Previous Race Results"],
  standings: ["Full Standings", "Constructor Standings", "How Does F1 Scoring Work?"],
  drivers: ["Compare Drivers", "Career Statistics", "Current Season Performance"],
  teams: ["Compare Teams", "Team History", "Season Performance"],
  predictions: ["Model Accuracy", "How Predictions Work", "Qualifying Predictions"],
} as const;
```

Use each approved string as the user-visible `label`, and return a resolved, self-contained `prompt` whenever a follow-up depends on a race, driver, or team. For example, a Lewis Hamilton response can return `{ label: "Career Statistics", prompt: "Show Lewis Hamilton career statistics" }`. Do not rely on server chat memory. If saved data cannot support Compare Drivers or Team History, keep the answer inside the approved topic and state what is unavailable rather than inventing facts.

Race responses must include race name, date, circuit, city/country, and source timezone when available. Standings responses must show both top-three tables. Prediction responses must state that probabilities are not guarantees.

- [ ] **Step 5: Implement the route as a thin validation boundary**

In `web/app/api/f1-buddy/route.ts`, export `POST`. Parse JSON in a `try/catch`, require a trimmed 1–500 character string, call `answerF1Question`, and return `NextResponse.json(reply, { headers: { "Cache-Control": "no-store" } })`.

Return this safe 503 payload on unexpected errors:

```json
{
  "error": "F1 Buddy could not answer that right now. Please try again."
}
```

Do not return stack traces, environment values, upstream URLs, or raw upstream response bodies.

- [ ] **Step 6: Run focused tests, lint, and type-check**

```powershell
node --import tsx --test tests/chatbot-responder.test.ts tests/chatbot-route.test.ts
npm run lint
npx tsc --noEmit
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit the native response boundary**

```powershell
git add web/app/api/f1-buddy web/lib/chatbot/responder.ts web/tests/chatbot-responder.test.ts web/tests/chatbot-route.test.ts
git commit -m "feat: add native F1 Buddy response API"
```

---

### Task 5: Implement the client state machine before the visual shell

**Files:**

- Create: `web/components/f1-buddy/chatReducer.ts`
- Create: `web/tests/chatbot-state.test.ts`

- [ ] **Step 1: Write reducer tests first**

Test these transitions without rendering React:

1. initial state is `closed` with no messages, no draft, no error, and not pending;
2. `OPEN` displays the welcome state;
3. `SUBMIT` appends a right-aligned user message and sets pending;
4. `SUCCEED` appends the structured bot reply and clears pending;
5. `FAIL` preserves history and adds the friendly error state;
6. `MINIMIZE` changes only the window mode and preserves messages/draft;
7. `RESTORE` restores the same conversation;
8. `CLOSE` returns the exact initial state and therefore clears history;
9. a second `SUBMIT` while pending is ignored.

- [ ] **Step 2: Run the test and verify it fails**

```powershell
cd web
node --import tsx --test tests/chatbot-state.test.ts
```

Expected: FAIL because the reducer does not exist.

- [ ] **Step 3: Implement typed state and actions**

Use this state model in `chatReducer.ts`:

```ts
export type WindowMode = "closed" | "open" | "minimized";

export type ConversationMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; reply: ChatReply };

export interface ChatState {
  mode: WindowMode;
  messages: ConversationMessage[];
  draft: string;
  pending: boolean;
  error: string | null;
}
```

Create IDs in the event handler with `crypto.randomUUID()` and pass them into actions; keep the reducer pure and deterministic.

- [ ] **Step 4: Run the state tests**

```powershell
node --import tsx --test tests/chatbot-state.test.ts
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the state machine**

```powershell
git add web/components/f1-buddy/chatReducer.ts web/tests/chatbot-state.test.ts
git commit -m "test: define F1 Buddy conversation state"
```

---

### Task 6: Build reusable dark F1 UI components and use the supplied car asset

**Files:**

- Create: `web/public/images/f1-buddy-car.jpg`
- Create: `web/components/f1-buddy/ChatHeader.tsx`
- Create: `web/components/f1-buddy/ChatInput.tsx`
- Create: `web/components/f1-buddy/ChatMessage.tsx`
- Create: `web/components/f1-buddy/F1BuddyLauncher.tsx`
- Create: `web/components/f1-buddy/F1BuddyPanel.tsx`
- Create: `web/components/f1-buddy/QuickReplies.tsx`
- Create: `web/components/f1-buddy/ResponseSections.tsx`
- Create: `web/components/f1-buddy/TopicCards.tsx`
- Create: `web/tests/chatbot-ui.test.ts`

- [ ] **Step 1: Add failing server-rendered component tests**

Use `renderToStaticMarkup` to test components individually. Assert:

- launcher contains the car image, `aria-expanded`, `aria-controls`, and the full tooltip text;
- header contains “F1 Buddy,” “Beta,” minimize, and close accessible names;
- welcome panel contains exactly five topic buttons and no “F1 basics” card;
- input has placeholder “Ask a question about Formula 1...”, a 500-character limit, and an accessible Send label;
- assistant messages render structured sections as text and links without `dangerouslySetInnerHTML`;
- pending state includes a status/typing indicator;
- quick replies are buttons labelled with `label`; clicking submits the hidden self-contained `prompt`.

- [ ] **Step 2: Run the UI test and verify missing-component failures**

```powershell
cd web
node --import tsx --test tests/chatbot-ui.test.ts
```

Expected: FAIL because the new components do not exist.

- [ ] **Step 3: Copy the approved launcher image**

Copy the user-provided source without modifying it:

```powershell
Copy-Item -LiteralPath "C:\Users\user\Downloads\909cafd309d3fb516deed322a4626778.jpg" -Destination "web\public\images\f1-buddy-car.jpg"
```

Use `next/image` with an explicit alt string: `Red Formula 1 car — open F1 Buddy`.

- [ ] **Step 4: Implement the launcher and tooltip**

`F1BuddyLauncher.tsx` must be a 72 px desktop/64 px mobile circular white button with a 2 px `#E8002D` border, clipped car image, red glow, slight hover/focus scale, and `motion-reduce:transform-none`.

The tooltip appears above the launcher on pointer hover and keyboard focus, and contains exactly:

```text
Hello, F1 fan! 🏁
Need help with Formula 1? Ask me about races, drivers, standings, and predictions!
Currently English only.
```

Do not make hover a prerequisite for touch: the button's `onClick` opens immediately.

- [ ] **Step 5: Implement the panel structure**

`F1BuddyPanel.tsx` must use:

- desktop width `min(400px, calc(100vw - 2rem))` and height `min(550px, calc(100dvh - 7rem))`;
- mobile inset of 12–16 px and a height that leaves the launcher reachable;
- near-black `#0B0D12` background, red `#E8002D` accents, `#343945` borders, and existing `font-nav`/`font-mono` typography;
- sticky header, scrollable conversation, sticky input footer;
- `role="dialog"`, `aria-modal="false"`, and a labelled heading;
- a live region for pending/error/response updates.

Do not add an outside-click listener.

- [ ] **Step 6: Implement welcome, messages, and response sections**

The welcome copy is:

```text
Hello! 👋
I'm F1 Buddy, your Formula 1 assistant.
Ask me about races, drivers, teams, standings, or our predictions!
```

Render Race details, Standings, Drivers, and Teams in a two-column grid. The final Predictions card spans both columns at every panel width.

Render user bubbles on the right in red. Render assistant bubbles on the left in light gray/white with the car avatar. Map every `ChatSection.kind` to a dedicated semantic renderer. Links must be internal relative links or validated `https:` links and include a visible focus style.

- [ ] **Step 7: Implement input and feedback behavior**

- Enter submits; Shift+Enter is not required because this is a single-line input.
- Disable submit for a blank draft or while pending.
- Show three animated typing dots with `role="status"`; disable animation under reduced motion.
- Keep the header and input visible while only the message body scrolls.
- Keep a friendly inline retry message on fetch failure.
- Follow-up suggestions remain clickable buttons after each assistant response.

- [ ] **Step 8: Run UI tests, lint, and type-check**

```powershell
node --import tsx --test tests/chatbot-ui.test.ts
npm run lint
npx tsc --noEmit
```

Expected: all commands exit 0.

- [ ] **Step 9: Commit the component library and asset**

```powershell
git add web/components/f1-buddy web/public/images/f1-buddy-car.jpg web/tests/chatbot-ui.test.ts
git commit -m "feat: build native F1 Buddy interface"
```

---

### Task 7: Replace the iframe shell and wire the native conversation

**Files:**

- Modify: `web/components/F1Buddy.tsx`
- Modify: `web/package.json`
- Delete: `web/lib/chatbot.ts`
- Delete: `web/tests/chatbot.test.ts`
- Delete: `web/.env.example`

- [ ] **Step 1: Extend the UI test with failing shell assertions**

Assert that `F1Buddy.tsx`:

- does not contain `iframe`, `NEXT_PUBLIC_F1BUDDY_URL`, `getChatbotUrl`, or `streamlit`;
- imports the native launcher, panel, and reducer;
- sends requests to `/api/f1-buddy`;
- does not register a document/window click listener;
- renders the launcher in its initial closed state.

Run the test now and verify it fails against the old iframe shell.

- [ ] **Step 2: Replace `F1Buddy.tsx` with the reducer-driven controller**

The controller must:

1. keep `useReducer(chatReducer, initialChatState)` at the top level;
2. expose one `submit(question: string)` function used by topic card prompts, quick-reply prompts, typed input, and Enter;
3. append the user message before calling `fetch("/api/f1-buddy", ...)`;
4. validate `response.ok` and parse `ChatReply`;
5. dispatch the friendly error on failure;
6. scroll to the latest message after state changes;
7. focus the input after opening and after a successful response;
8. minimize without clearing messages;
9. close/reset on the close button and Escape;
10. restore launcher focus after close;
11. never close on outside click.

Use this request shape:

```ts
await fetch("/api/f1-buddy", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: question }),
});
```

Do not store conversation history in local storage, cookies, a database, or the URL.

- [ ] **Step 3: Remove the old iframe configuration**

Delete `web/lib/chatbot.ts`, the old `web/tests/chatbot.test.ts`, and `web/.env.example`. There is no longer a chatbot deployment URL or Streamlit connection to configure.

- [ ] **Step 4: Make the full chatbot suite explicit in `package.json`**

Set `test:chatbot` to this platform-independent explicit list:

```json
"test:chatbot": "node --import tsx --test tests/chatbot-contract.test.ts tests/chatbot-data.test.ts tests/chatbot-disconnection.test.ts tests/chatbot-intents.test.ts tests/chatbot-responder.test.ts tests/chatbot-route.test.ts tests/chatbot-state.test.ts tests/chatbot-ui.test.ts"
```

- [ ] **Step 5: Run the complete automated suite**

```powershell
cd web
npm run test:chatbot
npm run lint
npx tsc --noEmit
npm run build
```

Expected: all tests PASS, lint/type-check exit 0, and Next.js reports a successful production build including `/api/f1-buddy`.

- [ ] **Step 6: Commit native integration**

```powershell
git add web
git commit -m "feat: replace iframe with native F1 Buddy"
```

---

### Task 8: Verify behavior in the browser and prove protected systems are unchanged

**Files:**

- Verify only; do not modify protected files.

- [ ] **Step 1: Start the production-like local web app**

```powershell
cd web
npm run dev
```

Open the reported local URL in the in-app browser.

- [ ] **Step 2: Verify desktop launcher and welcome state**

At a desktop viewport:

- hover and keyboard-focus the launcher; confirm the full tooltip and English-only note;
- click the car; confirm the ~400×550 dark panel, red accent, Beta badge, five cards, and input;
- confirm there is no sixth card and no iframe/loading of a Streamlit URL;
- click outside; confirm the panel stays open.

- [ ] **Step 3: Exercise all five topics against real saved data**

Submit each welcome card and verify:

- Race details returns saved schedule/circuit information, and official results either return Jolpica data or a clear unavailable message.
- Standings match `web/public/data/stats.json` values visible elsewhere on the website.
- Drivers match the existing driver/team/stats helpers and reuse the existing image.
- Teams match `TEAM_META`, saved standings, and existing lineups.
- Predictions match `next_race_prediction.json`; an unavailable historical prediction is labelled unavailable and never replaced by a result.

Click at least one follow-up for every topic and confirm it submits a complete, context-resolved question.

- [ ] **Step 4: Verify conversation and error behavior**

- Type a question and press Enter.
- Confirm the typing indicator appears and duplicate submissions are disabled.
- Minimize and restore; confirm history remains.
- Close and reopen; confirm the welcome screen returns with empty history.
- Press Escape; confirm close/reset and launcher focus restoration.
- Temporarily test a failed request in browser dev mode or a route test; confirm the friendly retry message and preserved history.

- [ ] **Step 5: Verify responsive and accessible behavior**

At 375×667 and 320×568 viewports:

- confirm panel, header controls, conversation, input, and launcher remain reachable;
- confirm no horizontal scroll or clipped send button;
- confirm touch/click opens directly without tooltip interaction;
- tab through launcher, topic cards, header buttons, quick replies, input, and Send;
- enable reduced motion and confirm glow/typing/hover motion is suppressed without hiding state changes.

- [ ] **Step 6: Scan for disconnected implementation remnants**

From the repository root, run:

```powershell
rg -n "NEXT_PUBLIC_F1BUDDY_URL|render_chatbot|f1buddy_ai|chatbot_app|<iframe" web streamlit_app .gitignore
```

Expected: no matches. The unrelated prediction link `NEXT_PUBLIC_STREAMLIT_URL` in `web/lib/links.ts` is not part of the scan and must remain because it opens the prediction website, not the chatbot.

- [ ] **Step 7: Re-run all verification and protected-path checks**

```powershell
cd web
npm run test:chatbot
npm run lint
npx tsc --noEmit
npm run build
cd ..
python -m py_compile streamlit_app/app.py
git diff --exit-code 3af81a1 -- ml web/public/data .github
git -C ..\f1buddy-ai status --short
git status --short
```

Expected:

- all automated checks exit 0;
- protected paths have no diff from the approved design-spec commit;
- sibling `f1buddy-ai` status exactly matches the status recorded in Task 1;
- only intended implementation changes and the pre-existing untracked `docs/superpowers/plans/2026-10-26-automatic-qualifying-refresh.md` appear.

- [ ] **Step 8: Request code review and address only in-scope findings**

Use `superpowers:requesting-code-review` to review the complete implementation against `docs/superpowers/specs/2026-11-10-native-f1-buddy-design.md`. Fix any High or Medium findings with focused tests, then rerun Step 7.

- [ ] **Step 9: Commit final verification fixes if needed**

If review required changes:

```powershell
git add web streamlit_app .gitignore
git commit -m "fix: harden native F1 Buddy behavior"
```

If no changes were needed, do not create an empty commit.

---

## Completion criteria

- Native F1 Buddy appears on every Next.js page through the existing root layout.
- The approved car launcher, tooltip, dark panel, Beta badge, five topic cards, messages, typing state, follow-ups, and responsive layout work.
- The API answers only the five approved topics from published website data first and Jolpica fallback second.
- Missing predictions are explicitly unavailable; they are never fabricated or replaced with actual results.
- Minimize preserves conversation; close/Escape reset it; outside clicks do nothing.
- No chatbot iframe, chatbot Streamlit app, wheel dependency, or chatbot deployment environment variable remains in this repository.
- The prediction Streamlit dashboard still compiles and its prediction/ML code is unchanged.
- `ml/`, `web/public/data/`, `.github/`, and sibling `f1buddy-ai` are unchanged.
- Tests, lint, TypeScript, production build, Python compile, desktop checks, mobile checks, and accessibility checks pass.
