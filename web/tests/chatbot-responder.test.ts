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

test("named race details use the selected season's schedule fallback", async () => {
  const reply = await answerF1Question("Tell me about the Las Vegas 2026 race", {
    ...fixedDependencies,
    resolveRaceSnapshot: async (search, season) => {
      assert.equal(search, "las vegas");
      assert.equal(season, 2026);
      return {
        season: 2026,
        round: 21,
        name: "Las Vegas Grand Prix",
        circuit: "Las Vegas Strip Street Circuit",
        locality: "Las Vegas",
        country: "USA",
        date: "2026-11-22",
      };
    },
  });

  assert.equal(reply.heading, "Las Vegas Grand Prix");
  assert.match(textOf(reply), /Las Vegas Strip Street Circuit/);
  assert.match(textOf(reply), /November 22, 2026/);
});

test("race details do not present the latest completed race as the next race", async () => {
  const reply = await answerF1Question("When is the next F1 race?", {
    ...fixedDependencies,
    now: () => new Date("2026-11-11T12:00:00Z"),
    getNextRaceSnapshot: async () => null,
  });

  assert.equal(reply.heading, "Race details");
  assert.match(reply.body, /No upcoming race/i);
  assert.doesNotMatch(textOf(reply), /Mexico City Grand Prix/);
});

test("current standings show the published top three drivers and constructors", async () => {
  const reply = await answerF1Question("Show current standings", fixedDependencies);
  const rankings = reply.sections.filter((section) => section.kind === "ranking");

  assert.equal(reply.intent, "standings");
  assert.match(reply.body, /latest saved/i);
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

test("standings fall back to Jolpica only when saved standings are unavailable", async () => {
  const reply = await answerF1Question("Show current standings", {
    ...fixedDependencies,
    getSavedDriverStandings: () => ({ kind: "drivers", updatedAt: "", entries: [] }),
    getSavedConstructorStandings: () => ({
      kind: "constructors",
      updatedAt: "",
      entries: [],
    }),
    getLiveDriverStandings: async (season) => {
      assert.equal(season, "2026");
      return {
        live: true,
        data: [
          {
            position: 1,
            driverId: "norris",
            code: "NOR",
            givenName: "Lando",
            familyName: "Norris",
            nationality: "British",
            points: 400,
            wins: 8,
            constructorId: "mclaren",
            constructorName: "McLaren",
          },
        ],
      };
    },
    getLiveConstructorStandings: async (season) => {
      assert.equal(season, "2026");
      return {
        live: true,
        data: [
          {
            position: 1,
            constructorId: "mclaren",
            name: "McLaren",
            points: 700,
            wins: 12,
          },
        ],
      };
    },
  });

  assert.match(reply.body, /Jolpica fallback/i);
  assert.match(textOf(reply), /Lando Norris/);
  assert.match(textOf(reply), /McLaren/);
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
    {
      ...fixedDependencies,
      now: () => new Date("2026-11-03T12:00:00Z"),
    },
  );

  assert.equal(reply.intent, "predictions");
  assert.equal(reply.heading, "Brazilian Grand Prix prediction");
  assert.match(textOf(reply), /Max Verstappen/);
  assert.match(textOf(reply), /81\.4%/);
  assert.match(textOf(reply), /not guarantees/i);
  assert.match(textOf(reply), /2026-11-04/);
  assert.ok(reply.sections.some((section) => section.kind === "link"));
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Model Accuracy", "How Predictions Work", "Qualifying Predictions"],
  );
  assertReplyContract(reply);
});

test("latest prediction rejects a stale saved snapshot", async () => {
  const reply = await answerF1Question("Show the latest F1 Buddy prediction", {
    ...fixedDependencies,
    now: () => new Date("2026-11-11T12:00:00Z"),
  });

  assert.equal(reply.heading, "Prediction unavailable");
  assert.match(reply.body, /No compatible saved prediction/i);
  assert.doesNotMatch(textOf(reply), /Mexico City Grand Prix prediction/);
});

test("historical prediction uses a labelled unqualified saved estimate", async () => {
  const reply = await answerF1Question(
    "Show the Monaco 2025 prediction",
    fixedDependencies,
  );

  assert.match(reply.body, /qualifying stage and original forecast time not recorded/i);
  assert.match(textOf(reply), /Lando Norris/);
  assert.match(textOf(reply), /75\.7%/);
});

test("explicit historical qualifying prediction does not use an unqualified estimate", async () => {
  const reply = await answerF1Question(
    "Show the Monaco 2025 predicted qualifying",
    {
      ...fixedDependencies,
      getSessionResults: async () => ({ data: null, live: false }),
    },
  );

  assert.equal(reply.heading, "Prediction unavailable");
  assert.match(reply.body, /No compatible saved prediction/i);
  assert.doesNotMatch(textOf(reply), /75\.7%/);
});

test("missing historical qualifying prediction shows actual qualifying separately", async () => {
  const reply = await answerF1Question(
    "Show the Monaco 2025 predicted qualifying",
    {
      ...fixedDependencies,
      getSessionResults: async (season, round, session) => {
        assert.equal(season, 2025);
        assert.equal(round, 8);
        assert.equal(session, "qualifying");
        return {
          live: true,
          data: {
            raceName: "Monaco Grand Prix",
            season: 2025,
            round: 8,
            results: [
              {
                position: 1,
                driverId: "norris",
                code: "NOR",
                driverName: "Lando Norris",
                constructorName: "McLaren",
              },
            ],
          },
        };
      },
    },
  );

  assert.equal(reply.heading, "Prediction unavailable");
  assert.match(reply.body, /actual qualifying/i);
  assert.match(textOf(reply), /Lando Norris/);
  assert.match(textOf(reply), /Actual qualifying classification/);
  assert.doesNotMatch(textOf(reply), /Saved historical model estimate/);
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

test("previous race results resolve the latest completed event from the schedule", async () => {
  const reply = await answerF1Question("Show previous F1 race results", {
    ...fixedDependencies,
    now: () => new Date("2026-11-11T12:00:00Z"),
    getPreviousRaceFromSchedule: async () => ({
      season: 2026,
      round: 20,
      name: "São Paulo Grand Prix",
      date: "2026-11-08",
    }),
    getSessionResults: async (season, round) => {
      assert.equal(season, 2026);
      assert.equal(round, 20);
      return {
        live: true,
        data: {
          raceName: "São Paulo Grand Prix",
          season: 2026,
          round: 20,
          results: [
            {
              position: 1,
              driverId: "norris",
              code: "NOR",
              driverName: "Lando Norris",
              constructorName: "McLaren",
            },
          ],
        },
      };
    },
  });

  assert.match(reply.heading, /São Paulo Grand Prix/i);
  assert.match(textOf(reply), /Lando Norris/);
});

test("saved real qualifying is used before the Jolpica result fallback", async () => {
  const reply = await answerF1Question("Mexico 2026 qualifying results", {
    ...fixedDependencies,
    getSavedSessionResults: () => ({
      raceName: "Mexico City Grand Prix",
      season: 2026,
      round: 19,
      results: [
        {
          position: 1,
          driverId: "verstappen",
          code: "VER",
          driverName: "Max Verstappen",
          constructorName: "Red Bull",
        },
      ],
    }),
    getSessionResults: async () => {
      throw new Error("Jolpica should not be called when saved qualifying exists");
    },
  });

  assert.match(textOf(reply), /Max Verstappen/);
  assert.match(reply.body, /saved qualifying/i);
});

test("unsupported questions explain the five-topic scope", async () => {
  const reply = await answerF1Question("Explain DRS", fixedDependencies);

  assert.equal(reply.intent, "unsupported");
  assert.match(reply.body, /race details, standings, drivers, teams, and predictions/i);
  assertReplyContract(reply);
});
