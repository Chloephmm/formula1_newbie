import assert from "node:assert/strict";
import test from "node:test";
import {
  answerF1Question,
  defaultResponderDependencies,
} from "../lib/chatbot/responder";
import type { ChatReply } from "../lib/chatbot/types";

const fixedDependencies = {
  ...defaultResponderDependencies,
  now: () => new Date("2026-04-01T12:00:00Z"),
};

function textOf(reply: ChatReply): string {
  return JSON.stringify(reply);
}

function assertReplyContract(reply: ChatReply) {
  assert.ok(reply.heading);
  assert.ok(reply.body);
  assert.ok(reply.quickReplies.length <= 3);
  for (const quickReply of reply.quickReplies) {
    assert.ok(quickReply.label);
    assert.ok(quickReply.prompt);
  }
  for (const section of reply.sections) {
    assert.ok(["facts", "ranking", "paragraph", "link"].includes(section.kind));
  }
}

test("race details use the next saved race and approved follow-ups", async () => {
  const reply = await answerF1Question("When is the next F1 race?", fixedDependencies);

  assert.equal(reply.intent, "race");
  assert.equal(reply.heading, "Miami Grand Prix");
  assert.match(textOf(reply), /Miami International Autodrome/);
  assert.match(textOf(reply), /May 3, 2026/);
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Qualifying Schedule", "Circuit Details", "Previous Race Results"],
  );
  assertReplyContract(reply);
});

test("race details fall back to the latest saved event after the schedule ends", async () => {
  const reply = await answerF1Question("When is the next F1 race?", {
    ...fixedDependencies,
    now: () => new Date("2026-11-10T12:00:00Z"),
    getNextRaceSnapshot: async () => null,
  });

  assert.equal(reply.heading, "Mexico City Grand Prix");
  assert.match(reply.body, /latest completed event/i);
  assert.match(textOf(reply), /November 1, 2026/);
});

test("current standings show the published top three drivers and constructors", async () => {
  const reply = await answerF1Question("Show current standings", fixedDependencies);
  const rankings = reply.sections.filter((section) => section.kind === "ranking");

  assert.equal(reply.intent, "standings");
  assert.equal(rankings.length, 2);
  assert.deepEqual(rankings.map((section) => section.items.length), [3, 3]);
  assert.match(textOf(reply), /points/);
  assert.ok(reply.sourceUpdatedAt);
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Full Standings", "Constructor Standings", "How Does F1 Scoring Work?"],
  );
  assertReplyContract(reply);
});

test("named driver response reuses saved profile, stats, and image", async () => {
  const reply = await answerF1Question("Tell me about Lewis Hamilton", fixedDependencies);

  assert.equal(reply.intent, "drivers");
  assert.equal(reply.heading, "Lewis Hamilton");
  assert.match(textOf(reply), /Ferrari/);
  assert.match(textOf(reply), /British/);
  assert.match(textOf(reply), /106/);
  assert.match(reply.image?.src ?? "", /hamilton_ferrari\.png$/);
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Compare Drivers", "Career Statistics", "Current Season Performance"],
  );
  assertReplyContract(reply);
});

test("named team response reuses metadata, lineup, and standings", async () => {
  const reply = await answerF1Question("Tell me about Ferrari", fixedDependencies);

  assert.equal(reply.intent, "teams");
  assert.match(textOf(reply), /Maranello, Italy/);
  assert.match(textOf(reply), /Frédéric Vasseur/);
  assert.match(textOf(reply), /SF-26/);
  assert.match(textOf(reply), /Charles Leclerc/);
  assert.match(reply.image?.src ?? "", /ferrari\.jpg$/);
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Compare Teams", "Team History", "Season Performance"],
  );
  assertReplyContract(reply);
});

test("latest prediction exposes only published values and a disclaimer", async () => {
  const reply = await answerF1Question(
    "Show the latest F1 Buddy prediction",
    fixedDependencies,
  );

  assert.equal(reply.intent, "predictions");
  assert.equal(reply.heading, "Mexico City Grand Prix prediction");
  assert.match(textOf(reply), /Max Verstappen/);
  assert.match(textOf(reply), /71\.7%/);
  assert.match(textOf(reply), /not guarantees/i);
  assert.match(textOf(reply), /2026-10-26/);
  assert.ok(reply.sections.some((section) => section.kind === "link"));
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Model Accuracy", "How Predictions Work", "Qualifying Predictions"],
  );
  assertReplyContract(reply);
});

test("historical prediction requests never receive synthesized values", async () => {
  const reply = await answerF1Question(
    "Show the Monaco 2025 prediction",
    fixedDependencies,
  );

  assert.match(reply.body, /No saved prediction is available/i);
  assert.equal(
    reply.sections.some((section) => section.kind === "ranking"),
    false,
  );
});

test("model accuracy follow-up reads published metrics", async () => {
  const reply = await answerF1Question("Show model accuracy", fixedDependencies);

  assert.match(textOf(reply), /56\.6%/);
  assert.match(textOf(reply), /69\.8%/);
  assert.match(textOf(reply), /1,068/);
});

test("official-results outage becomes a friendly race response", async () => {
  const reply = await answerF1Question("Mexico 2026 race results", {
    ...fixedDependencies,
    getSessionResults: async () => ({ data: null, live: false }),
  });

  assert.equal(reply.intent, "race");
  assert.match(reply.body, /official results are temporarily unavailable/i);
  assertReplyContract(reply);
});

test("unsupported questions explain the five-topic scope", async () => {
  const reply = await answerF1Question("Explain DRS", fixedDependencies);

  assert.equal(reply.intent, "unsupported");
  assert.match(reply.body, /race details, standings, drivers, teams, and predictions/i);
  assertReplyContract(reply);
});
