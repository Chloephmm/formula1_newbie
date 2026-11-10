import assert from "node:assert/strict";
import test from "node:test";
import {
  chatReducer,
  initialChatState,
  type ChatState,
} from "../components/f1-buddy/chatReducer";
import type { ChatReply } from "../lib/chatbot/types";

const reply: ChatReply = {
  intent: "race",
  heading: "Miami Grand Prix",
  body: "Round 6",
  sections: [],
  quickReplies: [],
};

test("initial state is closed and empty", () => {
  assert.deepEqual(initialChatState, {
    mode: "closed",
    messages: [],
    draft: "",
    pending: false,
    error: null,
  });
});

test("open shows the welcome state", () => {
  assert.equal(chatReducer(initialChatState, { type: "OPEN" }).mode, "open");
});

test("submit appends the user message and enters pending state", () => {
  const state = chatReducer(
    { ...initialChatState, mode: "open", draft: "question" },
    { type: "SUBMIT", id: "user-1", text: "question" },
  );

  assert.deepEqual(state.messages, [
    { id: "user-1", role: "user", text: "question" },
  ]);
  assert.equal(state.pending, true);
  assert.equal(state.draft, "");
});

test("success appends the assistant reply and leaves pending state", () => {
  const pending: ChatState = {
    ...initialChatState,
    mode: "open",
    pending: true,
    messages: [{ id: "user-1", role: "user", text: "question" }],
  };
  const state = chatReducer(pending, {
    type: "SUCCEED",
    id: "assistant-1",
    reply,
  });

  assert.deepEqual(state.messages[1], {
    id: "assistant-1",
    role: "assistant",
    reply,
  });
  assert.equal(state.pending, false);
  assert.equal(state.error, null);
});

test("failure preserves history and exposes a friendly error", () => {
  const pending: ChatState = {
    ...initialChatState,
    mode: "open",
    pending: true,
    messages: [{ id: "user-1", role: "user", text: "question" }],
  };
  const state = chatReducer(pending, {
    type: "FAIL",
    error: "Please try again.",
  });

  assert.equal(state.messages, pending.messages);
  assert.equal(state.pending, false);
  assert.equal(state.error, "Please try again.");
});

test("minimize and restore preserve conversation and draft", () => {
  const open: ChatState = {
    ...initialChatState,
    mode: "open",
    draft: "unfinished",
    messages: [{ id: "user-1", role: "user", text: "question" }],
  };
  const minimized = chatReducer(open, { type: "MINIMIZE" });
  const restored = chatReducer(minimized, { type: "RESTORE" });

  assert.equal(minimized.mode, "minimized");
  assert.equal(minimized.messages, open.messages);
  assert.equal(minimized.draft, "unfinished");
  assert.equal(restored.mode, "open");
  assert.equal(restored.messages, open.messages);
});

test("close resets the complete conversation", () => {
  const active: ChatState = {
    mode: "open",
    draft: "unfinished",
    pending: true,
    error: "error",
    messages: [{ id: "user-1", role: "user", text: "question" }],
  };

  assert.deepEqual(chatReducer(active, { type: "CLOSE" }), initialChatState);
});

test("a second submit is ignored while pending", () => {
  const pending: ChatState = {
    ...initialChatState,
    mode: "open",
    pending: true,
    messages: [{ id: "user-1", role: "user", text: "first" }],
  };

  assert.equal(
    chatReducer(pending, { type: "SUBMIT", id: "user-2", text: "second" }),
    pending,
  );
});
