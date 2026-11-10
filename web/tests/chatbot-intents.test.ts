import assert from "node:assert/strict";
import test from "node:test";
import { parseQuestion } from "../lib/chatbot/intents";

test("classifies the five supported topics before unsupported questions", () => {
  const cases = [
    ["When is the next F1 race?", "race"],
    ["Show the Mexico 2026 race result", "race"],
    ["Who leads the constructor standings?", "standings"],
    ["Tell me about Lewis Hamilton", "drivers"],
    ["Who drives for Ferrari?", "teams"],
    ["Show the latest podium prediction", "predictions"],
    ["Explain DRS", "unsupported"],
  ] as const;

  for (const [message, expected] of cases) {
    assert.equal(parseQuestion(message).intent, expected, message);
  }
});

test("extracts a historical qualifying-result target", () => {
  assert.deepEqual(parseQuestion("Mexico 2026 qualifying results"), {
    intent: "race",
    normalized: "mexico 2026 qualifying results",
    season: 2026,
    searchTerm: "mexico",
    resultKind: "qualifying",
  });
});

test("recognizes constructor standings separately", () => {
  assert.equal(
    parseQuestion("Show constructor standings").standingKind,
    "constructors",
  );
  assert.equal(parseQuestion("Show driver standings").standingKind, "drivers");
});

test("resolves names, surnames, codes, and teams from site data", () => {
  assert.equal(parseQuestion("How is HAM doing?").searchTerm, "hamilton");
  assert.equal(parseQuestion("Tell me about McLaren").searchTerm, "mclaren");
});

test("prediction language wins over generic race language", () => {
  assert.equal(
    parseQuestion("What is the race podium prediction?").intent,
    "predictions",
  );
});
