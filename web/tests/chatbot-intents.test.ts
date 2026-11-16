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

test("prediction filler words are not mistaken for a race identity", () => {
  assert.equal(
    parseQuestion("Show the latest F1 Buddy prediction").searchTerm,
    undefined,
  );
  assert.equal(parseQuestion("Show the Mexico prediction").searchTerm, "mexico");
});

test("qualifying schedule wording stays a schedule request", () => {
  const parsed = parseQuestion(
    "Show the qualifying schedule for Mexico City Grand Prix 2026",
  );

  assert.equal(parsed.intent, "race");
  assert.equal(parsed.resultKind, "schedule");
  assert.equal(parsed.searchTerm, "mexico city");
});

test("next-race question words are not treated as a race identity", () => {
  const parsed = parseQuestion("What is the next F1 race?");

  assert.equal(parsed.intent, "race");
  assert.equal(parsed.resultKind, "schedule");
  assert.equal(parsed.searchTerm, undefined);
});

test("conversational next prediction requests select the current publication", () => {
  for (const message of [
    "Can you give me the next race prediction?",
    "Tell me anything about the latest prediction",
    "Please show the current F1 forecast",
  ]) {
    const parsed = parseQuestion(message);
    assert.equal(parsed.intent, "predictions", message);
    assert.equal(parsed.searchTerm, undefined, message);
  }
  assert.equal(parseQuestion("Show the Mexico 2026 prediction").searchTerm, "mexico");
});

test("prediction questions identify the requested published field", () => {
  assert.equal(parseQuestion("Who is predicted for pole at the next race?").predictionAspect, "qualifying");
  assert.equal(parseQuestion("Who has the best podium chance in the next race?").predictionAspect, "podium");
  assert.equal(parseQuestion("When was the next prediction updated?").predictionAspect, "updated");
  const driver = parseQuestion("What is Leclerc's podium chance in the next prediction?");
  assert.equal(driver.predictionAspect, "driver");
  assert.equal(driver.predictionDriverId, "leclerc");
  assert.equal(parseQuestion("Who will win the next race prediction?").predictionAspect, "winner");
  assert.equal(parseQuestion("Who is predicted for pole?").searchTerm, undefined);
  assert.equal(parseQuestion("When was the Mexico 2026 prediction updated?").searchTerm, "mexico");
  assert.equal(parseQuestion("What is Leclerc's podium chance for Mexico 2026?").searchTerm, "mexico");
  assert.equal(parseQuestion("What is Leclerc's prediction for the next race?").predictionAspect, "driver");
  assert.equal(parseQuestion("Who will win the next race?").predictionAspect, "winner");
  assert.equal(parseQuestion("Who is favored for the next race?").predictionAspect, "podium");
  assert.notEqual(parseQuestion("What is the chance of rain at the next race?").intent, "predictions");
});

test("a prediction follow-up uses only the selected race context", () => {
  const context = { raceName: "Las Vegas Grand Prix", season: 2026 };
  const driver = parseQuestion("What about Leclerc?", context);
  assert.equal(driver.intent, "predictions");
  assert.equal(driver.searchTerm, "Las Vegas Grand Prix");
  assert.equal(driver.season, 2026);
  assert.equal(driver.predictionAspect, "driver");
  assert.equal(driver.predictionDriverId, "leclerc");
  assert.equal(parseQuestion("When was it updated?", context).predictionAspect, "updated");
  assert.equal(parseQuestion("What about qualifying?", context).predictionAspect, "qualifying");
  assert.equal(parseQuestion("What about Leclerc?").intent, "drivers");
  assert.equal(parseQuestion("Tell me about Leclerc", context).intent, "drivers");
  assert.equal(parseQuestion("Show Mexico 2026 prediction", context).searchTerm, "mexico");
});
