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
