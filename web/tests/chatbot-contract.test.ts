import assert from "node:assert/strict";
import test from "node:test";
import { CHAT_TOPICS } from "../lib/chatbot/topics";

test("F1 Buddy exposes exactly the five approved topics", () => {
  assert.deepEqual(
    CHAT_TOPICS.map((topic) => topic.id),
    ["race", "standings", "drivers", "teams", "predictions"],
  );
  assert.equal(new Set(CHAT_TOPICS.map((topic) => topic.id)).size, 5);
});

test("each topic has complete display and submission data", () => {
  for (const topic of CHAT_TOPICS) {
    assert.ok(topic.title.trim());
    assert.ok(topic.description.trim());
    assert.ok(topic.prompt.trim());
    assert.ok(topic.icon.trim());
  }
});

test("the approved default prompts remain stable", () => {
  assert.deepEqual(
    CHAT_TOPICS.map((topic) => topic.prompt),
    [
      "When is the next F1 race?",
      "Show the current driver standings.",
      "Tell me about Max Verstappen.",
      "Tell me about Ferrari.",
      "Show the latest F1 Buddy prediction.",
    ],
  );
});
