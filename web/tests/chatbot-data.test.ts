import assert from "node:assert/strict";
import test from "node:test";
import { getSessionResults } from "../lib/jolpica";
import {
  findDriverSnapshot,
  findRaceSnapshot,
  findTeamSnapshot,
  getModelMetricsSnapshot,
  getNextRaceSnapshot,
  getPreviousRaceSnapshot,
  getPreviousRaceFromSchedule,
  getPublishedPrediction,
  getSavedSessionResults,
  resolveRaceSnapshot,
  getStandingsSnapshot,
} from "../lib/chatbot/data";

test("driver snapshots reuse saved standings, stats, career, and assets", () => {
  const driver = findDriverSnapshot("hamilton");

  assert.ok(driver);
  assert.equal(driver.name, "Lewis Hamilton");
  assert.equal(driver.team.name, "Ferrari");
  assert.equal(driver.standing?.position, 4);
  assert.equal(driver.standing?.points, 261);
  assert.equal(driver.seasonStats?.podiums, 7);
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

test("named race lookup falls back to the selected season's Jolpica schedule", async () => {
  const requestedSeasons: string[] = [];
  const race = await resolveRaceSnapshot("abu dhabi", 2026, async (season) => {
    requestedSeasons.push(season ?? "");
    return {
      live: true,
      data: [
        {
          season: 2026,
          round: 22,
          name: "Abu Dhabi Grand Prix",
          circuit: "Yas Marina Circuit",
          locality: "Abu Dhabi",
          country: "UAE",
          date: "2026-12-06",
        },
      ],
    };
  });

  assert.deepEqual(requestedSeasons, ["2026"]);
  assert.equal(race?.name, "Abu Dhabi Grand Prix");
  assert.equal(race?.round, 22);
});

test("next-race lookup uses a compatible prediction snapshot before Jolpica", async () => {
  let fallbackCalls = 0;
  const race = await getNextRaceSnapshot(new Date("2026-11-09T12:00:00Z"), async () => {
    fallbackCalls += 1;
    return { data: [], live: false };
  });

  assert.equal(race?.name, "Las Vegas Grand Prix");
  assert.equal(fallbackCalls, 0);
});

test("next-race lookup rejects a stale snapshot and asks Jolpica for the selected year", async () => {
  const requestedSeasons: string[] = [];
  const race = await getNextRaceSnapshot(new Date("2026-11-11T12:00:00Z"), async (season) => {
    requestedSeasons.push(season ?? "");
    return {
      live: true,
      data: [
        {
          season: 2026,
          round: 21,
          name: "Las Vegas Grand Prix",
          circuit: "Las Vegas Strip Street Circuit",
          locality: "Las Vegas",
          country: "USA",
          date: "2026-11-22",
          time: "04:00:00Z",
        },
      ],
    };
  });

  assert.deepEqual(requestedSeasons, ["2026"]);
  assert.equal(race?.name, "Las Vegas Grand Prix");
  assert.equal(race?.date, "2026-11-22");
});

test("next-race schedule keeps an event on its calendar date", async () => {
  const race = await getNextRaceSnapshot(
    new Date("2026-11-22T12:00:00Z"),
    async () => ({
      live: true,
      data: [
        {
          season: 2026,
          round: 21,
          name: "Las Vegas Grand Prix",
          circuit: "Las Vegas Strip Street Circuit",
          date: "2026-11-22",
          time: "04:00:00Z",
        },
      ],
    }),
  );

  assert.equal(race?.name, "Las Vegas Grand Prix");
});

test("previous-race lookup is deterministic from saved dates", () => {
  const race = getPreviousRaceSnapshot(new Date("2026-04-01T00:00:00Z"));

  assert.equal(race?.name, "Japanese Grand Prix");
  assert.equal(race?.round, 3);
});

test("previous-race lookup includes the newer published prediction identity", () => {
  const race = getPreviousRaceSnapshot(new Date("2026-11-10T00:00:00Z"));

  assert.equal(race?.name, "Brazilian Grand Prix");
  assert.equal(race?.round, 20);
});

test("previous-race schedule lookup selects the latest completed event", async () => {
  const race = await getPreviousRaceFromSchedule(
    new Date("2026-11-11T12:00:00Z"),
    async () => ({
      live: true,
      data: [
        { season: 2026, round: 19, name: "Mexico City Grand Prix", circuit: "Autódromo Hermanos Rodríguez", date: "2026-11-01" },
        { season: 2026, round: 20, name: "São Paulo Grand Prix", circuit: "Interlagos", date: "2026-11-08" },
        { season: 2026, round: 21, name: "Las Vegas Grand Prix", circuit: "Las Vegas Strip Street Circuit", date: "2026-11-22" },
      ],
    }),
  );

  assert.equal(race?.name, "São Paulo Grand Prix");
  assert.equal(race?.round, 20);
});

test("published prediction exposes only validated detailed output", () => {
  const prediction = getPublishedPrediction("mexico", 2026);

  assert.equal(prediction.available, true);
  if (!prediction.available) return;
  assert.equal(prediction.race.name, "Mexico City Grand Prix");
  assert.equal(prediction.predictedQualifying[0].driverName, "Max Verstappen");
  assert.equal(prediction.podium[0].driverName, "Max Verstappen");
  assert.equal(prediction.qualifyingMode, "predicted");
  assert.equal(prediction.generatedAt, "2026-10-30T18:00:43Z");
});

test("schema-v2 saved qualifying is normalized without changing published data", () => {
  const saved = getSavedSessionResults(
    {
      season: 2026,
      round: 21,
      name: "Las Vegas Grand Prix",
      date: "2026-11-22",
    },
    "qualifying",
    {
      schema_version: 2,
      prediction_updated_at: "2026-11-21T12:00:00Z",
      race: {
        name: "Las Vegas Grand Prix",
        season: 2026,
        round: 21,
        country: "USA",
        date: "2026-11-22",
        raceStartAt: "2026-11-22T04:00:00Z",
        qualifyingStartAt: "2026-11-21T04:00:00Z",
      },
      forecast: {
        error: null,
        asof: "2026-11-21",
        race: {
          name: "Las Vegas Grand Prix",
          season: 2026,
          round: 21,
          country: "USA",
          date: "2026-11-22",
          raceStartAt: "2026-11-22T04:00:00Z",
          qualifyingStartAt: "2026-11-21T04:00:00Z",
        },
        predictedQualifying: [],
        preQualifyingPodium: [],
        hasActualQualifying: true,
        actualQualifyingPodium: [],
        actualQualifying: [
          {
            position: 1,
            code: "NOR",
            driverName: "Lando Norris",
            team: "McLaren",
            teamId: "mclaren",
            gap: 0,
          },
        ],
      },
    },
  );

  assert.equal(saved?.raceName, "Las Vegas Grand Prix");
  assert.equal(saved?.results[0].driverName, "Lando Norris");
});

test("generic current prediction rejects a snapshot from a different as-of date", () => {
  assert.deepEqual(
    getPublishedPrediction(undefined, undefined, new Date("2026-11-11T12:00:00Z")),
    { available: false },
  );
  assert.deepEqual(
    getPublishedPrediction(undefined, 2026, new Date("2026-11-11T12:00:00Z")),
    { available: false },
  );
});

test("missing historical prediction is explicit and never synthesized", () => {
  assert.deepEqual(getPublishedPrediction("unavailable race", 2026), {
    available: false,
  });
});

test("named historical prediction can use the unqualified saved estimate", () => {
  const prediction = getPublishedPrediction(
    "monaco",
    2025,
    new Date("2026-11-11T12:00:00Z"),
  );

  assert.equal(prediction.available, true);
  if (!prediction.available) return;
  assert.equal(prediction.source, "historical-estimate");
  assert.equal(prediction.race.name, "Monaco Grand Prix");
  assert.equal(prediction.podium[0].driverName, "Lando Norris");
  assert.equal(prediction.predictedQualifying.length, 0);
});

test("unqualified historical estimate cannot satisfy an explicit stage request", () => {
  assert.deepEqual(
    getPublishedPrediction(
      "monaco",
      2025,
      new Date("2026-11-11T12:00:00Z"),
      false,
    ),
    { available: false },
  );
});

test("model metrics are read from the published metrics snapshot", () => {
  assert.deepEqual(getModelMetricsSnapshot(), {
    top1Accuracy: 0.566,
    top3Accuracy: 0.6981,
    rocAuc: 0.9346,
    testRows: 1068,
  });
});

test("saved real qualifying is preferred only for the matching race", () => {
  const saved = getSavedSessionResults(
    {
      season: 2026,
      round: 21,
      name: "Las Vegas Grand Prix",
      date: "2026-11-22",
    },
    "qualifying",
    {
      asof: "2026-11-21",
      generatedAt: "2026-11-21",
      race: {
        name: "Las Vegas Grand Prix",
        season: 2026,
        round: 21,
        country: "USA",
        date: "2026-11-22",
        qualifyingDate: "2026-11-21",
      },
      forecast: {
        error: null,
        predictedQualifying: [],
        preQualifyingPodium: [],
        hasRealGrid: true,
        realGridPodium: [],
        realQualifying: [
          {
            position: 1,
            code: "NOR",
            driverName: "Lando Norris",
            team: "McLaren",
            teamId: "mclaren",
            gap: 0,
          },
        ],
      },
    },
  );

  assert.equal(saved?.raceName, "Las Vegas Grand Prix");
  assert.equal(saved?.results[0].driverName, "Lando Norris");
  assert.equal(saved?.results[0].constructorName, "McLaren");
  assert.equal(
    getSavedSessionResults(
      { season: 2026, round: 20, name: "São Paulo Grand Prix", date: "2026-11-08" },
      "qualifying",
    ),
    null,
  );
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
