# Dual-site F1 Buddy Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Preserve feature2 as requested.

**Goal:** Make the existing rule-based chatbot available in the prediction dashboard and an embedded Vercel panel, with no changes to ML or source data.

**Architecture:** Both Streamlit entrypoints install the same versioned wheel built from the sibling f1buddy-ai repository. The prediction dashboard retains its existing popup and displayed context. A chatbot-only entrypoint reads the checked-out JSON outputs without importing ML; Vercel embeds its configured public Streamlit URL on demand. Sessions remain separate.

**Tech Stack:** Existing Python/Streamlit/Pydantic/requests package, Next.js/React/TypeScript, native iframe, pytest and Node tests. No database, LLM, RAG, or new backend API.

## Approved design and boundaries

The user approved the embedded approach and requested implementation on 2026-11-05. Keep both repositories on feature2 rather than moving their checkouts. Only chatbot UI/deployment files, layout mounting, tests, and documentation may change. Hash ml/, web/public/data/, and .github/ before and after. Do not alter existing prediction functions or run training/refresh.

The standalone app must call a new public render_chatbot_panel(data_dir=...) entrypoint. Both UI modes reuse one conversation renderer. It uses today's date for race/history context; current-prediction questions in saved-only mode return an explicitly dated saved forecast. Never pretend that a previous race's snapshot is the current prediction. Existing native popup behavior remains unchanged.

The Next.js panel uses NEXT_PUBLIC_F1BUDDY_URL, accepts a public HTTPS *.streamlit.app origin and localhost HTTP only for development, adds embed=true, and mounts the iframe only after opening. Without a valid configuration it shows deployment/setup guidance, not a fabricated live URL. Provide an accessible close button, parent-page Escape handling, focus return, and mobile sizing. Escape inside the cross-origin Streamlit frame cannot reach the parent; retain normal keyboard navigation and visible Close/launcher controls. Do not claim iframe load means the remote app is healthy.

## Task 1 — Vercel launcher (delegated)

**Files:** web/components/F1Buddy.tsx, web/lib/chatbot.ts, web/tests/chatbot.test.ts, web/app/layout.tsx, web/package.json and chatbot deployment documentation/environment example as needed.

- [x] Write Node tests before implementation for absent/invalid/HTTPS public Streamlit URLs, embed=true preservation, credential rejection, localhost development allowance and production rejection. Use node:assert/strict and node:test via tsx.
- [x] Run `npx tsx --test tests/chatbot.test.ts`; confirm failure for missing module/behavior.
- [x] Implement a pure `getChatbotUrl(value, development)` validator returning a string or null. Build a client `F1Buddy` launcher around it, initially closed; no iframe before first open. Preserve mounted iframe across close/reopen without leaving hidden controls focusable. Mount `<F1Buddy />` once after the footer in layout.
- [ ] Run tests, focused ESLint and TypeScript checks. Browser-test launcher, close, keyboard handling, narrow layout, absent configuration and a real local embedded chat. Do not change site data readers or ML.

## Task 2 — Shared saved-output panel

**Files:** sibling f1buddy-ai/src/f1buddy_ai/{models.py,data/snapshots.py,services/f1_data.py,chat/engine.py,ui/streamlit.py,__init__.py}, sibling tests/test_saved_panel.py and existing UI tests, sibling pyproject.toml.

- [x] Add failing tests: saved-only current-prediction replies name the stored race, as-of date and qualifying mode; no API/ML used for saved predictions; malformed/missing snapshots fail gracefully; a confirmed real-grid mode uses only that stage; ordinary popup remains unchanged.
- [x] Add a typed saved-forecast result from existing snapshot fields, rejecting conflicting identity and absent requested stage. Render saved-only prediction replies separately in ChatEngine; leave historical routing first.
- [x] Extract common conversation UI and expose `render_chatbot_panel(*, data_dir, as_of_date=None, state_key='f1buddy_panel')` as a fragment with a plain panel, not a nested popover. Keep the old render_chatbot signature backward-compatible.
- [x] Run `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider`; require all old and new tests green. Bump package to 0.2.0.

## Task 3 — Deployable entrypoints and pinned artifact

**Files:** chatbot_app/app.py, chatbot_app/requirements.txt, chatbot_app/vendor/f1buddy_ai-0.2.0-py3-none-any.whl, chatbot_app/README.md, streamlit_app/requirements.txt, streamlit_app/README.md, .gitignore (one exact wheel exception).

- [x] Add integration tests asserting the chatbot entrypoint contains no ML imports and resolves the existing web/public/data directory, and both requirements reference the same artifact.
- [x] Create the small entrypoint:

```python
from pathlib import Path
import streamlit as st
from f1buddy_ai import render_chatbot_panel
st.set_page_config(page_title="F1 Buddy", page_icon="🏁", layout="centered")
st.title("F1 Buddy")
render_chatbot_panel(data_dir=Path(__file__).resolve().parents[1] / "web" / "public" / "data")
```

- [x] Build wheel with `python -m pip wheel --no-deps --no-build-isolation ../f1buddy-ai --wheel-dir chatbot_app/vendor`. Allowlist only this wheel in .gitignore. Add `./chatbot_app/vendor/f1buddy_ai-0.2.0-py3-none-any.whl` to both app requirements. All install/run commands execute from the Formula1 repository root.
- [x] Document artifact provenance/hash, separate Streamlit app deployment using chatbot_app/app.py, native app redeployment using streamlit_app/app.py, and Vercel NEXT_PUBLIC_F1BUDDY_URL configuration/rebuild. Do not create an invented hosted URL or publish a new repository.

## Task 4 — Verify, review, and handoff

- [x] Run full Python tests, Node chatbot tests, focused frontend lint, TypeScript, and production Next build. Investigate failures without modifying unrelated code.
- [ ] Run the real chatbot-only entrypoint locally against existing read-only outputs; embed it in local Next and verify a saved historical answer. Do not run ML training or refresh.
- [x] Compare protected SHA-256 hashes, inspect changed files, and review spec then code quality. Preserve unrelated untracked plans.
- [x] Commit only scoped changes locally on feature2. Check available deployment access read-only; if credentials, app URL selection, or public rollout authority are missing, report that separately from implementation and do not claim the live URLs changed.

## Acceptance checks

The launcher is visible on every Vercel route and works on narrow screens; the iframe does not load until requested; the standalone chat has no extra popup; existing Streamlit tests still pass; predictions are never regenerated; source files remain unchanged; unavailable deployment shows setup guidance; no unapproved production merge/publication occurs.

## Execution record — 2026-11-09

Implementation tasks 1–3 are complete. The frontend worker was unavailable, so
the parent implemented its portion locally. Both repositories remain on feature2.
The chatbot source release is commit `c351d19d77540e3ff962db5e6606fea7028e7821`;
artifact provenance is in `chatbot_app/vendor/README.md`.

Verification completed:

- 126 Python tests and 5 frontend tests pass; new regressions were observed failing
  before implementation. Existing native popup behavior remains covered.
- Focused ESLint, TypeScript and production Next.js build pass. Build required
  network access for the website's existing Google Fonts; no font code changed.
- The real chatbot entrypoint imports and answers from the built wheel. No-network
  pip dry-run resolves the exact wheel path. No model code was executed.
- All 109 tracked files under `ml`, `web/public/data` and `.github` match the
  pre-change SHA-256 baseline. `streamlit_app/app.py` is unchanged this turn.
- Browser verified the configured iframe loads the actual standalone chat,
  parent Escape returns focus, close/reopen, the unconfigured production fallback,
  and launcher presence on home and How F1 Works routes.
- At 375x480 the complete panel top moved from -70px (clipped) to +16px after
  the responsive fix. The frame shrinks inside the bounded panel.
- Direct browser interaction with the standalone app returned the actual Mexico
  2026 snapshot (as-of 2026-10-26, predicted grid) and the Mexico 2025 historical
  estimate with explicit timing/stage limitations.
- Spec review and independent code-quality review passed after metadata and
  responsive sizing fixes. Cross-origin Escape limitation is documented.

Remaining rollout checks (not implementation claims):

- Browser automation could inspect the iframe but its iframe input actions failed
  with detached-target errors. Direct standalone interactions passed. Manually
  verify typing/buttons and transcript retention inside the final hosted iframe.
- No public chatbot-only app URL or authenticated deployment project is configured.
  No push, merge, new public repository or production deployment was performed.
  Follow `chatbot_app/README.md` to deploy and configure the actual URL, rebuild
  Vercel, redeploy the native prediction app and verify both hosted sites.
- On 2026-11-10 the user requested removal of the website saved-output/wake-up
  notice and the standalone Streamlit read-only caption. Version 0.2.1 removes
  both; the website iframe now starts directly below the F1 Buddy header.
- Preserve the unrelated automatic-qualifying-refresh plan. Commit only this
  integration's files; do not stage or alter that earlier plan.
