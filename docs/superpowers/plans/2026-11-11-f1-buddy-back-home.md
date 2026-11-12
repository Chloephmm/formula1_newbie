# F1 Buddy Back-to-Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a contextual Back button that clears the active F1 Buddy conversation and returns the still-open popup to its welcome screen.

**Architecture:** Add a `RETURN_HOME` state transition to the existing reducer, expose a conditional Back control through `F1BuddyPanel` and `ChatHeader`, and let the top-level `F1Buddy` controller invalidate any in-flight request before resetting. Keep the API, responder, prediction pipeline, and data sources unchanged.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, Node test runner, React server rendering for component contract tests.

---

## File Map

- Create `web/tests/chatbot-back-home.test.ts`: focused reducer, component, panel, and controller-contract coverage for this feature.
- Modify `web/package.json`: include the new test file in the existing chatbot suite.
- Modify `web/components/f1-buddy/chatReducer.ts`: define and handle the clean return-home transition.
- Modify `web/components/f1-buddy/ChatHeader.tsx`: render the contextual, accessible Back button.
- Modify `web/components/f1-buddy/F1BuddyPanel.tsx`: determine when Back is available and pass the callback to the header.
- Modify `web/components/F1Buddy.tsx`: invalidate pending work, dispatch the reset, and restore input focus.

## Working-Tree Safety

The branch already contains unrelated uncommitted compatibility changes in `web/components/Reveal.tsx` and `web/tests/chatbot-ui.test.ts`, plus an untracked plan at `docs/superpowers/plans/2026-10-26-automatic-qualifying-refresh.md`. Preserve them. Every commit below stages only the explicitly listed files, and `git diff --cached --name-only` must be checked before committing.

### Task 1: Add the clean return-home state transition

**Files:**
- Create: `web/tests/chatbot-back-home.test.ts`
- Modify: `web/package.json:10`
- Modify: `web/components/f1-buddy/chatReducer.ts:16-66`

- [ ] **Step 1: Write the failing reducer test**

Create `web/tests/chatbot-back-home.test.ts` with:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import {
  chatReducer,
  initialChatState,
  type ChatState,
} from "../components/f1-buddy/chatReducer";

test("return home clears the session and keeps the panel open", () => {
  const activeState: ChatState = {
    mode: "open",
    messages: [{ id: "user-1", role: "user", text: "Who won the last race?" }],
    draft: "another question",
    pending: true,
    error: "temporary failure",
  };

  const next = chatReducer(activeState, { type: "RETURN_HOME" });

  assert.deepEqual(next, { ...initialChatState, mode: "open" });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
```

Run from `web/`.

Expected: FAIL because `RETURN_HOME` is not handled and the reducer returns `undefined`.

- [ ] **Step 3: Implement the minimal reducer transition**

In `web/components/f1-buddy/chatReducer.ts`, add the action:

```ts
  | { type: "RETURN_HOME" }
```

Add this reducer branch immediately before `CLOSE`:

```ts
    case "RETURN_HOME":
      return { ...initialChatState, mode: "open" };
```

- [ ] **Step 4: Register the feature test in the normal suite**

Update the `test:chatbot` script in `web/package.json` so `tests/chatbot-back-home.test.ts` appears after `tests/chatbot-contract.test.ts`:

```json
"test:chatbot": "node --import tsx --test tests/chatbot-contract.test.ts tests/chatbot-back-home.test.ts tests/chatbot-data.test.ts tests/chatbot-disconnection.test.ts tests/chatbot-intents.test.ts tests/chatbot-responder.test.ts tests/chatbot-route.test.ts tests/chatbot-state.test.ts tests/chatbot-ui.test.ts"
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
```

Expected: PASS with 1 test and 0 failures.

- [ ] **Step 6: Commit the state transition**

```powershell
git add -- web/package.json web/tests/chatbot-back-home.test.ts web/components/f1-buddy/chatReducer.ts
git diff --cached --name-only
git commit -m "feat: add F1 Buddy return-home state"
```

Expected staged paths: exactly the three files listed above.

### Task 2: Add the contextual Back control to the header and panel

**Files:**
- Modify: `web/tests/chatbot-back-home.test.ts`
- Modify: `web/components/f1-buddy/ChatHeader.tsx:3-55`
- Modify: `web/components/f1-buddy/F1BuddyPanel.tsx:8-50`
- Modify: `web/components/F1Buddy.tsx:81-94`

- [ ] **Step 1: Add failing header and panel tests**

Add these imports to `web/tests/chatbot-back-home.test.ts`:

```ts
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ChatHeader from "../components/f1-buddy/ChatHeader";
import F1BuddyPanel from "../components/f1-buddy/F1BuddyPanel";
```

Add the shared callback and tests:

```ts
const noop = () => undefined;

test("header shows Back only for an active chat", () => {
  const welcome = renderToStaticMarkup(
    createElement(ChatHeader, {
      showBack: false,
      onBack: noop,
      onMinimize: noop,
      onClose: noop,
    }),
  );
  const active = renderToStaticMarkup(
    createElement(ChatHeader, {
      showBack: true,
      onBack: noop,
      onMinimize: noop,
      onClose: noop,
    }),
  );

  assert.doesNotMatch(welcome, /Back to F1 Buddy home/);
  assert.match(active, /aria-label="Back to F1 Buddy home"/);
  assert.match(active, />←</);
});

test("panel derives Back visibility from conversation state", () => {
  const shared = {
    draft: "",
    pending: false,
    error: null,
    onDraftChange: noop,
    onSubmit: noop,
    onQuickReply: noop,
    onBack: noop,
    onMinimize: noop,
    onClose: noop,
  };
  const welcome = renderToStaticMarkup(
    createElement(F1BuddyPanel, { ...shared, messages: [] }),
  );
  const active = renderToStaticMarkup(
    createElement(F1BuddyPanel, {
      ...shared,
      messages: [{ id: "user-1", role: "user" as const, text: "Next race?" }],
    }),
  );

  assert.doesNotMatch(welcome, /Back to F1 Buddy home/);
  assert.match(active, /Back to F1 Buddy home/);
});
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
```

Expected: FAIL because `ChatHeader` and `F1BuddyPanel` do not accept or render the Back behavior.

- [ ] **Step 3: Add the Back contract and control to `ChatHeader`**

Change `ChatHeaderProps` to:

```ts
interface ChatHeaderProps {
  showBack: boolean;
  onBack: () => void;
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: Ref<HTMLButtonElement>;
}
```

Destructure `showBack` and `onBack`. Inside the existing left-side header group, before the F1 mark, add:

```tsx
{showBack ? (
  <button
    type="button"
    aria-label="Back to F1 Buddy home"
    onClick={onBack}
    className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-lg text-[#F4F6F8] transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-[#E8002D]"
  >
    <span aria-hidden="true">←</span>
  </button>
) : null}
```

Do not change the right-side Minimize and Close controls.

- [ ] **Step 4: Derive and pass Back visibility in `F1BuddyPanel`**

Add the callback to `F1BuddyPanelProps` and its destructuring:

```ts
onBack: () => void;
```

Replace the welcome calculation with:

```ts
const showBack = messages.length > 0 || pending || Boolean(error);
const welcome = !showBack;
```

Update the header call to:

```tsx
<ChatHeader
  showBack={showBack}
  onBack={onBack}
  onMinimize={onMinimize}
  onClose={onClose}
  closeButtonRef={closeButtonRef}
/>
```

- [ ] **Step 5: Wire the basic panel callback**

In the existing `F1BuddyPanel` call in `web/components/F1Buddy.tsx`, add:

```tsx
onBack={() => dispatch({ type: "RETURN_HOME" })}
```

This makes the component contract complete. Task 3 replaces this basic callback with the request-safe controller required by the specification.

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
```

Expected: PASS with 3 tests and 0 failures.

- [ ] **Step 7: Run TypeScript validation for the changed component contract**

Run:

```powershell
npx tsc --noEmit
```

Expected: TypeScript exits with code 0.

- [ ] **Step 8: Commit the header and panel behavior**

Run the focused feature test as the commit gate, then stage only:

```powershell
git add -- web/tests/chatbot-back-home.test.ts web/components/f1-buddy/ChatHeader.tsx web/components/f1-buddy/F1BuddyPanel.tsx web/components/F1Buddy.tsx
git diff --cached --name-only
git commit -m "feat: add F1 Buddy back-home control"
```

Expected staged paths: exactly the four files listed above.

### Task 3: Wire reset, request invalidation, and focus restoration

**Files:**
- Modify: `web/tests/chatbot-back-home.test.ts`
- Modify: `web/components/F1Buddy.tsx:11-94`

- [ ] **Step 1: Add the failing controller-contract test**

Add this import to `web/tests/chatbot-back-home.test.ts`:

```ts
import { readFileSync } from "node:fs";
```

Add:

```ts
test("top-level return home invalidates pending work before reset", () => {
  const source = readFileSync(
    new URL("../components/F1Buddy.tsx", import.meta.url),
    "utf8",
  );
  const start = source.indexOf("function returnHome()");
  const end = source.indexOf("async function submit", start);
  const block = source.slice(start, end);

  assert.ok(start >= 0, "returnHome controller must exist");
  assert.match(block, /requestVersion\.current \+= 1/);
  assert.match(block, /dispatch\(\{ type: "RETURN_HOME" \}\)/);
  assert.match(block, /inputRef\.current\?\.focus\(\)/);
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
```

Expected: FAIL with `returnHome controller must exist`.

- [ ] **Step 3: Implement the top-level controller**

In `web/components/F1Buddy.tsx`, replace the basic inline `onBack` callback with a named controller. Add this function after `close` and before `submit`:

```ts
function returnHome() {
  requestVersion.current += 1;
  dispatch({ type: "RETURN_HOME" });
  window.setTimeout(() => inputRef.current?.focus(), 0);
}
```

Pass it to `F1BuddyPanel`:

```tsx
onBack={returnHome}
```

This uses the existing version guard in `submit`, so a response completing after Back is ignored.

- [ ] **Step 4: Run focused tests and TypeScript validation**

Run:

```powershell
node --import tsx --test tests/chatbot-back-home.test.ts
npx tsc --noEmit
```

Expected: 4 focused tests pass and TypeScript exits with code 0.

- [ ] **Step 5: Commit the controller wiring**

```powershell
git add -- web/tests/chatbot-back-home.test.ts web/components/F1Buddy.tsx
git diff --cached --name-only
git commit -m "feat: reset F1 Buddy from the back control"
```

Expected staged paths: exactly the two files listed above.

### Task 4: Verify behavior and protect existing functionality

**Files:**
- Verify only; no planned source changes.

- [ ] **Step 1: Run the complete chatbot suite**

Run from `web/`:

```powershell
npm run test:chatbot
```

Expected: all chatbot tests pass, including 4 tests in `chatbot-back-home.test.ts`, with 0 failures.

- [ ] **Step 2: Run static validation**

```powershell
npx tsc --noEmit
npx eslint components/F1Buddy.tsx components/f1-buddy/ChatHeader.tsx components/f1-buddy/F1BuddyPanel.tsx components/f1-buddy/chatReducer.ts tests/chatbot-back-home.test.ts
git diff --check
```

Expected: every command exits with code 0 and produces no errors.

- [ ] **Step 3: Run the production build**

```powershell
npm run build
```

Expected: Next.js completes the production build with exit code 0.

- [ ] **Step 4: Perform the browser interaction check**

Use a normal Chrome or Edge tab at `http://localhost:3020/`, because the in-app browser does not hydrate the Next.js client reliably.

Verify this sequence:

1. Open F1 Buddy; Back is absent on the five-topic welcome screen.
2. Submit `What is the next F1 race?`; Back appears in the header.
3. Select Back; the popup remains open and the welcome screen returns.
4. Confirm the previous exchange, draft, typing indicator, and error are absent.
5. Submit another topic-card question to confirm the new session works.
6. Start a request and select Back before it completes; confirm the late response does not reappear.

- [ ] **Step 5: Confirm final repository scope**

```powershell
git status --short --branch
git log -4 --oneline
```

Expected: feature commits contain only the files named in Tasks 1-3. The previously existing `Reveal.tsx`, `chatbot-ui.test.ts`, and automatic-qualifying plan changes remain preserved and are not silently included in these commits.
