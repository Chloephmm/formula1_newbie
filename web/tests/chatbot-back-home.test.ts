import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ChatHeader from "../components/f1-buddy/ChatHeader";
import F1BuddyPanel from "../components/f1-buddy/F1BuddyPanel";
import {
  chatReducer,
  initialChatState,
  type ChatState,
} from "../components/f1-buddy/chatReducer";

const noop = () => undefined;

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
