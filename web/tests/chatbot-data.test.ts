import assert from "node:assert/strict";
import test from "node:test";
import { getSessionResults } from "../lib/jolpica";
import {
  findDriverSnapshot,
  findRaceSnapshot,
  findTeamSnapshot,
  getModelMetricsSnapshot,
  getNextRaceSnapshot,
  getPublishedPrediction,
  getStandingsSnapshot,
} from "../lib/chatbot/data";

test("driver snapshots reuse saved standings, stats, career, and assets", () => {
  const driver = findDriverSnapshot("hamilton");

  assert.ok(driver);
  assert.equal(driver.name, "Lewis Hamilton");
  assert.equal(driver.team.name, "Ferrari");
  assert.equal(driver.standing?.position, 3);
  assert.equal(driver.standing?.points, 241);
  assert.equal(driver.seasonStats?.podiums, 6);
  assert.equal(driver.career?.wins, 106);
  assert.equal(driver.image, "/images/assets/ferrari/hamilton_ferrari.png");
});

test("team snapshots reuse metadata, standings, lineups, and logos", () => {
  const team = findTeamSnapshot("ferrari");

  assert.ok(team);
  assert.equal(team.meta.base, "Maranello, Italy");
  assert.equal(team.meta.chief, "Frédéric Vasseur");
  assert.deepEqual(
    team.drivers.map((driver) => driver.name),
    ["Charles Leclerc", "Lewis Hamilton"],
  );
  assert.equal(team.standing?.constructorId, "ferrari");
  assert.equal(team.logo, "/images/teams/ferrari.jpg");
});

test("standings snapshots come from the published stats file", () => {
  const drivers = getStandingsSnapshot("drivers");
  const constructors = getStandingsSnapshot("constructors");

  assert.equal(drivers.entries[0].position, 1);
  assert.equal(constructors.entries[0].position, 1);
  assert.match(drivers.updatedAt, /^20\d{2}-/);
  assert.equal(constructors.updatedAt, drivers.updatedAt);
});

test("race lookup can use the detailed published prediction identity", () => {
  const race = findRaceSnapshot("mexico", 2026);

  assert.ok(race);
  assert.equal(race.name, "Mexico City Grand Prix");
  assert.equal(race.round, 19);
  assert.equal(race.date, "2026-11-01");
});

test("next-race lookup uses saved races before a schedule fallback", async () => {
  let fallbackCalls = 0;
  const race = await getNextRaceSnapshot(new Date("2026-04-01T00:00:00Z"), async () => {
    fallbackCalls += 1;
    return { data: [], live: false };
  });

  assert.equal(race?.name, "Miami Grand Prix");
  assert.equal(fallbackCalls, 0);
});

test("published prediction exposes only validated detailed output", () => {
  const prediction = getPublishedPrediction("mexico", 2026);

  assert.equal(prediction.available, true);
  if (!prediction.available) return;
  assert.equal(prediction.race.name, "Mexico City Grand Prix");
  assert.equal(prediction.predictedQualifying[0].driverName, "Max Verstappen");
  assert.equal(prediction.podium[0].driverName, "Max Verstappen");
  assert.equal(prediction.qualifyingMode, "predicted");
  assert.equal(prediction.generatedAt, "2026-10-26");
});

test("missing historical prediction is explicit and never synthesized", () => {
  assert.deepEqual(getPublishedPrediction("unavailable race", 2026), {
    available: false,
  });
});

test("model metrics are read from the published metrics snapshot", () => {
  assert.deepEqual(getModelMetricsSnapshot(), {
    top1Accuracy: 0.566,
    top3Accuracy: 0.6981,
    rocAuc: 0.9346,
    testRows: 1068,
  });
});

test("official session results are mapped into the safe chat shape", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        MRData: {
          RaceTable: {
            Races: [
              {
                season: "2026",
                round: "19",
                raceName: "Mexico City Grand Prix",
                date: "2026-11-01",
                Circuit: { circuitName: "Autódromo Hermanos Rodríguez" },
                Results: [
                  {
                    position: "1",
                    Driver: {
                      driverId: "max_verstappen",
                      code: "VER",
                      givenName: "Max",
                      familyName: "Verstappen",
                      nationality: "Dutch",
                    },
                    Constructor: { constructorId: "red_bull", name: "Red Bull" },
                  },
                ],
              },
            ],
          },
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );

  try {
    const response = await getSessionResults(2026, 19, "results");
    assert.equal(response.live, true);
    assert.deepEqual(response.data?.results[0], {
      position: 1,
      driverId: "max_verstappen",
      code: "VER",
      driverName: "Max Verstappen",
      constructorName: "Red Bull",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
