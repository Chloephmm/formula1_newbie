# Native F1 Buddy Chatbot Design

**Date:** 2026-11-10

**Branch:** `feature2`

**Status:** Approved design; implementation not started

## Objective

Replace the current Streamlit-iframe chatbot integration with a native Next.js,
TypeScript and Tailwind F1 Buddy. The new chatbot uses a rule-based server API and
real data already available to the Formula1 website. It must match the approved
dark racing mockups, remain beginner-friendly, and preserve a clean boundary for
a future LLM responder.

The separate `f1buddy-ai` repository is preserved unchanged but disconnected
completely. This work does not modify or execute the prediction pipeline, model,
strategy, generated data, refresh workflows or other website functionality.

## Product scope

F1 Buddy supports exactly five Phase 1 topics:

1. Race details
2. Standings
3. Drivers
4. Teams
5. Predictions

There is no sixth F1 Basics card. Unsupported questions receive a short response
that identifies the five supported topics and invites the user to select one.
The chatbot is rule-based; no LLM, RAG, database, WhatsApp integration or
notification scheduler is introduced.

## Visual direction

F1 Buddy is a compact pit-wall communication console adapted to the existing F1
Guidebook site. It does not copy the supplied examples literally. The distinctive
element is the user-provided front-facing red racing-car image in the launcher.
The rest of the interface stays quiet and functional.

### Tokens

| Role | Value |
| --- | --- |
| Pit black | `#0B0D12` |
| Carbon surface | `#151820` |
| Grid line | `#343945` |
| F1 red | `#E8002D` |
| Paper white | `#F4F6F8` |
| Telemetry gray | `#A6ADB8` |

Use the existing site typography: Horizon only for the compact F1 Buddy identity,
Cooper Hewitt for conversation text and controls, and JetBrains Mono sparingly for
dates, points, timestamps and prediction percentages. Copy uses sentence case.

### Launcher and tooltip

- Fixed to the bottom-right on every page.
- White circular button, red border and restrained red edge glow.
- Contains the supplied racing-car image, copied into the website's public assets.
- Pointer hover/focus scales slightly and reveals a white tooltip above it:

  > **Hello, F1 fan! 🏁**
  >
  > Need help with Formula 1? Ask me about races, drivers, standings, and predictions!
  >
  > *Currently English only.*

- Pointer leave/focus loss hides the tooltip. Touch activation opens the chat
  immediately; hover is never required.
- The launcher is a real button with an accessible name and visible focus state.

### Window

- Near-black panel with one restrained red edge light, functional borders, soft
  shadow and rounded corners.
- Desktop target: approximately 400 px wide and 550 px tall.
- Mobile: fills the available viewport with safe margins and keeps the launcher
  reachable.
- Header contains `F1 Buddy`, a small `Beta` badge, minimize and close controls.
- Four topic cards form a two-column grid; Predictions spans the full width.
- The supplied examples' extra F1 logo, background racing imagery and repeated
  glow treatments are intentionally excluded to avoid competing with the site.

```text
┌──────────────────────────────┐
│ F1 Buddy  Beta        —   × │
├──────────────────────────────┤
│ [car] Hello! 👋              │
│       I'm F1 Buddy...        │
│                              │
│ [Race details] [Standings]   │
│ [Drivers]      [Teams]       │
│ [Predictions — full width]   │
│                              │
├──────────────────────────────┤
│ Ask about Formula 1...  [➤] │
└──────────────────────────────┘
             ◇
 [white circular car launcher]
```

### Conversation

- User messages are right-aligned red bubbles.
- Bot messages are left-aligned paper-white/light-gray bubbles with the car avatar.
- Structured race, standings, driver, team and prediction data uses compact
  content blocks inside bot bubbles, not free-form HTML from the server.
- The header and input remain fixed while messages scroll.
- Placeholder: `Ask a question about Formula 1...`
- Enter submits; Shift+Enter is not required because the input is single-line.
- The send control becomes a compact three-light pit-signal typing indicator while
  a request is pending.
- Each successful answer may include up to three contextual quick replies.
- Clicking a topic or quick reply submits its default question immediately.
- Clicking outside never closes the window.
- Minimize preserves history. Close clears history and returns the next opening to
  the welcome screen. Browser refresh does not promise persistence.

## Architecture

The browser UI calls a same-origin Next.js server route. The route returns typed
JSON response sections, never HTML.

```text
Native Next.js UI
      │ POST /api/f1-buddy { message }
      ▼
Intent detector
      ├─ Race details ─ website schedule/results helpers
      ├─ Standings ──── website stats + cached Jolpica fallback
      ├─ Drivers ────── website metadata/stats/assets
      ├─ Teams ──────── website metadata/stats/assets
      └─ Predictions ── published prediction JSON only
      ▼
Typed response { sections, image?, link?, quickReplies }
```

### UI components

- `F1Buddy.tsx`: state machine, conversation history and request coordination.
- `F1BuddyLauncher.tsx`: car button and pointer/focus tooltip.
- `ChatHeader.tsx`: title, Beta badge, minimize and close actions.
- `ChatMessage.tsx`: user and bot message presentation.
- `TopicCards.tsx`: five approved topic actions.
- `QuickReplies.tsx`: contextual follow-up actions.
- `ChatInput.tsx`: input validation, Enter handling and pending state.
- `ResponseCard.tsx`: typed structured response sections.

Paths may be grouped under `web/components/f1-buddy/` to keep the feature bounded.

### Rule and data modules

- `web/lib/chatbot/types.ts`: public request, message, section and response types.
- `web/lib/chatbot/intents.ts`: normalized keywords, aliases and intent detection.
- `web/lib/chatbot/responses.ts`: beginner-friendly response construction.
- `web/lib/chatbot/data.ts`: adapters over existing website data and helpers.
- `web/app/api/f1-buddy/route.ts`: validated server boundary.

The responder has a small interface so a future Phase 2 LLM implementation can
replace intent/response construction without changing visual components or the
API response contract.

## Data-source priority

Reuse the website's current sources and helpers instead of creating a second data
client. For every answer, use this priority:

1. Generated JSON already shipped under `web/public/data`.
2. Static metadata and image mappings already used by the website.
3. Existing cached `web/lib/jolpica.ts` functions when local data is missing or a
   current schedule/result lookup is required.
4. An explicit unavailable response if neither source succeeds.

Specific sources:

- Race details: current schedule/results through existing schedule helpers with
  `races.json` fallback. Determine the next event from dates; after a season ends,
  identify the last completed Grand Prix. Use session timezone information only
  when the source provides it; never invent a local timezone.
- Standings: `stats.json` first, including its update timestamp; existing driver
  and constructor standings fallback second.
- Drivers: `drivers.json`, `stats.json`, existing driver images and existing
  Jolpica career helpers. Omit unavailable career fields rather than inferring.
- Teams: `teams.json`, `teamMeta.ts`, `stats.json` and existing team images.
- Predictions: `next_race_prediction.json` only for the latest published detailed
  forecast. Validate race identity, generation/as-of timestamp, podium rows and
  qualifying mode. Never generate, normalize, re-rank or substitute predictions.
  Link to the existing prediction website through the existing site link helper.

Server caching remains owned by the existing website helpers. Opening or reopening
the window makes no request until a topic, quick reply or typed question is sent.

## Response behavior

### Race details

Show race name, date, circuit, city/country and race start with source timezone
when available. Quick replies: Qualifying Schedule, Circuit Details, Previous Race
Results.

### Standings

Show top three drivers and constructors with points and the saved update context.
Quick replies: Full Standings, Constructor Standings, How Does F1 Scoring Work?

### Drivers

Resolve a named driver or offer a supported example. Show nationality, current
team and only available career/season fields, plus an existing driver image when
present. Quick replies: Compare Drivers, Career Statistics, Current Season
Performance.

### Teams

Resolve a named team or offer a supported example. Show headquarters, drivers,
championship position, points, wins and an existing logo. Quick replies: Compare
Teams, Team History, Season Performance.

### Predictions

Show the saved race, top-three podium probabilities, generation timestamp and
whether predicted or actual qualifying data was used. Explain that probabilities
are not guarantees and link to the prediction website. Quick replies: Model
Accuracy, How Predictions Work, Qualifying Predictions.

## Validation and error handling

- Accept POST requests with a plain-text message only; trim whitespace, reject
  empty input and enforce a conservative maximum length.
- Never evaluate user content or allow the client to select a filesystem/API path.
- Prevent double submission while a request is pending.
- Abort or bound external requests through the existing helper behavior.
- API/rate-limit failure: `Live F1 data is temporarily unavailable. Try again
  shortly or choose another topic.`
- Missing driver/team: name what could not be found and offer the corresponding
  topic quick reply.
- Missing prediction: state that no published forecast is available; never show a
  replacement probability.
- A stale forecast may be shown only when its race and generation time are explicit.
- The UI shows a friendly retry action for failed requests and remains usable.

Accessibility requirements include semantic buttons, labelled controls, keyboard
submission, visible focus, logical tab order, sufficient contrast, reduced-motion
support and no reliance on hover alone.

## Streamlit disconnection and deletion scope

Remove the Formula1 branch's chatbot-only Streamlit integration:

- Remove the optional chatbot hook from `streamlit_app/app.py` while preserving all
  original prediction behavior.
- Remove the chatbot wheel from `streamlit_app/requirements.txt`.
- Delete `chatbot_app/` and its vendored wheel.
- Remove the iframe URL helper/configuration and `NEXT_PUBLIC_F1BUDDY_URL`.
- Replace the iframe-based `F1Buddy.tsx` implementation.
- Remove or rewrite obsolete Streamlit-chatbot deployment documentation and tests.

Do not delete or edit the separate sibling `f1buddy-ai` repository. Do not run or
modify ML training, prediction refresh, generated data, source datasets or GitHub
workflows. Before implementation, record hashes for protected ML/data/workflow
files and compare them again before completion.

## Verification

- Unit tests for intent aliases, unsupported input, response formatting, source
  priority, missing data and prediction safeguards.
- Route tests for validation, successful structured responses and failure mapping.
- Component-level checks for the five cards and initial lazy/closed state without
  requiring a network request.
- Browser verification for every topic, quick replies, typed input, Enter, pending
  indicator, minimize history, close reset, tooltip, desktop and mobile layouts.
- Confirm the Streamlit prediction dashboard has no chatbot hook and remains
  otherwise unchanged.
- Run focused frontend tests, ESLint, TypeScript and a production Next.js build.
- Compare protected-file hashes and inspect the complete scoped diff.

## Acceptance criteria

The native chatbot appears on every Next.js page and closely follows the approved
pit-wall design. All five topics return real, safely sourced information when
available. Predictions are never fabricated. The car tooltip, quick replies,
keyboard input, loading/error states, minimize and close semantics work on desktop
and mobile. No iframe or Streamlit chatbot integration remains in the Formula1
branch, while the sibling Python repository is preserved and disconnected. No
existing website or prediction functionality is broken.
