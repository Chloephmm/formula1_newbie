import assert from "node:assert/strict";
import test from "node:test";
import {
  answerF1Question,
  defaultResponderDependencies,
} from "../lib/chatbot/responder";
import type { ChatReply } from "../lib/chatbot/types";
import type { PublishedPrediction } from "../lib/chatbot/published-predictions";

const publishedPrediction = {
  available: true,
  source: "confirmed-feed",
  cached: false,
  generatedAt: "2026-11-09T15:42:59Z",
  publishedAt: "2026-11-09T15:43:03Z",
  race: { name: "Las Vegas Grand Prix", season: 2026, round: 21, country: "USA", date: "2026-11-22" },
  predictedQualifying: [{ position: 1, driverName: "Charles Leclerc", gap: 0 }],
  podium: [{ driverName: "Max Verstappen", podiumProbability: 0.766389 }],
  qualifyingMode: "predicted",
  predictionUrl: "https://f1forecast.streamlit.app/",
} satisfies PublishedPrediction;

const fixedDependencies = {
  ...defaultResponderDependencies,
  now: () => new Date("2026-04-01T12:00:00Z"),
  getPublishedPrediction: async () => ({ available: false as const, reason: "not-found" as const }),
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
      now: () => new Date("2026-11-13T12:00:00Z"),
      getPublishedPrediction: async () => publishedPrediction,
    },
  );

  assert.equal(reply.intent, "predictions");
  assert.equal(reply.heading, "Las Vegas Grand Prix prediction");
  assert.match(textOf(reply), /Charles Leclerc/);
  assert.match(textOf(reply), /Max Verstappen/);
  assert.match(textOf(reply), /76\.6%/);
  assert.match(textOf(reply), /not guarantees/i);
  assert.match(textOf(reply), /2026-11-09/);
  assert.ok(reply.sections.some((section) => section.kind === "link"));
  assert.deepEqual(
    reply.quickReplies.map((item) => item.label),
    ["Model Accuracy", "How Predictions Work", "Qualifying Predictions"],
  );
  assertReplyContract(reply);
});

test("next-race prediction variants read the current published forecast", async () => {
  const calls: Array<[string | undefined, number | undefined]> = [];
  for (const message of [
    "Can you give me the next race prediction?",
    "Tell me anything about the latest prediction",
  ]) {
    const reply = await answerF1Question(message, {
      ...fixedDependencies,
      getPublishedPrediction: async (search, season) => {
        calls.push([search, season]);
        return publishedPrediction;
      },
    });
    assert.equal(reply.heading, "Las Vegas Grand Prix prediction");
  }
  assert.deepEqual(calls, [[undefined, undefined], [undefined, undefined]]);
});

test("specific prediction questions show only the published field requested", async () => {
  const dependencies = {
    ...fixedDependencies,
    getPublishedPrediction: async () => publishedPrediction,
  };
  const qualifying = await answerF1Question("Who is predicted for pole at the next race?", dependencies);
  assert.match(JSON.stringify(qualifying.sections), /Charles Leclerc/);
  assert.doesNotMatch(JSON.stringify(qualifying.sections), /76\.6%/);

  const podium = await answerF1Question("Who has the best podium chance in the next race?", dependencies);
  assert.match(JSON.stringify(podium.sections), /76\.6%/);
  assert.doesNotMatch(JSON.stringify(podium.sections), /Charles Leclerc/);

  const updated = await answerF1Question("When was the next prediction updated?", dependencies);
  assert.match(JSON.stringify(updated.sections), /2026-11-09T15:43:03Z/);
  assert.equal(updated.sections.some((section) => section.kind === "ranking"), false);

  const winner = await answerF1Question("Who will win the next race prediction?", dependencies);
  assert.match(winner.body, /winner probability is not published/i);
  assert.doesNotMatch(winner.body, /76\.6%/);
});

test("driver prediction question uses that driver's published podium probability", async () => {
  const reply = await answerF1Question("What is Leclerc's podium chance in the next prediction?", {
    ...fixedDependencies,
    getPublishedPrediction: async () => ({
      ...publishedPrediction,
      podium: [...publishedPrediction.podium, { driverName: "Charles Leclerc", podiumProbability: 0.42 }],
    }),
  });
  assert.match(JSON.stringify(reply.sections), /42\.0%/);
  assert.doesNotMatch(JSON.stringify(reply.sections), /76\.6%/);
});

test("a selected prediction answers a driver follow-up for the same race", async () => {
  const context = { raceName: "Las Vegas Grand Prix", season: 2026 };
  const calls: Array<[string | undefined, number | undefined]> = [];
  const dependencies = {
    ...fixedDependencies,
    getPublishedPrediction: async (search?: string, season?: number) => {
      calls.push([search, season]);
      return {
        ...publishedPrediction,
        podium: [...publishedPrediction.podium, { driverName: "Charles Leclerc", podiumProbability: 0.42 }],
      };
    },
  };
  const initial = await answerF1Question("Show the latest prediction", dependencies);
  assert.deepEqual(initial.context, context);
  const followUp = await answerF1Question("What about Leclerc?", dependencies, initial.context);
  assert.equal(followUp.intent, "predictions");
  assert.match(JSON.stringify(followUp.sections), /42\.0%/);
  assert.deepEqual(calls, [[undefined, undefined], ["Las Vegas Grand Prix", 2026]]);
});

test("a historical forecast's qualifying follow-up stays on that race", async () => {
  const reply = await answerF1Question("Show the Mexico 2026 prediction", {
    ...fixedDependencies,
    getPublishedPrediction: async () => ({
      ...publishedPrediction,
      source: "dashboard-archive" as const,
      race: { ...publishedPrediction.race, name: "Mexico City Grand Prix", round: 19 },
    }),
  });
  const qualifying = reply.quickReplies.find((item) => item.label === "Qualifying Predictions");
  assert.match(qualifying?.prompt ?? "", /Mexico City Grand Prix 2026/);
});

test("cached confirmed prediction remains clearly labelled", async () => {
  const reply = await answerF1Question("Show the latest F1 Buddy prediction", {
    ...fixedDependencies,
    now: () => new Date("2026-11-13T12:00:00Z"),
    getPublishedPrediction: async () => ({ ...publishedPrediction, cached: true }),
  });

  assert.equal(reply.heading, "Las Vegas Grand Prix prediction");
  assert.match(reply.body, /last validated cached publication/i);
  assert.match(reply.body, /2026-11-09T15:43:03Z/);
});

test("historical prediction without a Streamlit publication is unavailable", async () => {
  const reply = await answerF1Question(
    "Show the Monaco 2025 prediction",
    { ...fixedDependencies, getSessionResults: async () => ({ data: null, live: false }) },
  );

  assert.equal(reply.heading, "Prediction unavailable");
  assert.doesNotMatch(textOf(reply), /75\.7%/);
});

test("next prediction explains why the published forecast is unavailable", async () => {
  const cases = [
    ["not-published", /not been published/i],
    ["invalid-publication", /failed validation/i],
    ["source-unavailable", /temporarily unavailable/i],
    ["past-event", /already started/i],
  ] as const;
  for (const [reason, expected] of cases) {
    const reply = await answerF1Question("Show the next race prediction", {
      ...fixedDependencies,
      getPublishedPrediction: async () => ({ available: false, reason }),
    });
    assert.equal(reply.heading, "Prediction unavailable");
    assert.match(reply.body, expected, reason);
  }
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
