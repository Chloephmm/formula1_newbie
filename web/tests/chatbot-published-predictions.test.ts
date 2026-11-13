import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createPublishedPredictionProvider } from "../lib/chatbot/published-predictions";
import type { ConfirmedFeed } from "../lib/chatbot/prediction-feed";

const feed = JSON.parse(readFileSync(new URL("../public/data/prediction_feed.json", import.meta.url), "utf8")) as ConfirmedFeed;
const index = JSON.parse(readFileSync(new URL("../public/data/predictions/index.json", import.meta.url), "utf8"));
const archive = JSON.parse(readFileSync(new URL("../public/data/predictions/2026-19.json", import.meta.url), "utf8"));
const unitedStates = JSON.parse(readFileSync(new URL("../public/data/predictions/2026-18.json", import.meta.url), "utf8"));
const brazil = JSON.parse(readFileSync(new URL("../public/data/prediction_snapshots/2026-20/feed.json", import.meta.url), "utf8"));

function provider(current: ConfirmedFeed = feed) {
  const requested: string[] = [];
  const lookup = createPublishedPredictionProvider({
    readCurrent: async () => ({ available: true as const, feed: current, cached: false }),
    readArchiveIndex: async () => index,
    readArchiveArtifact: async (path: string) => {
      requested.push(path);
      return path.endsWith("2026-18.json") ? unitedStates : path.endsWith("2026-20/feed.json") ? brazil : archive;
    },
  });
  return { lookup, requested };
}

test("generic next race uses the last confirmed Streamlit forecast across calendar days", async () => {
  const { lookup } = provider();
  const result = await lookup(undefined, undefined, new Date("2026-11-13T12:00:00Z"));
  assert.equal(result.available, true);
  if (!result.available) return;
  assert.equal(result.race.name, "Las Vegas Grand Prix");
  assert.equal(result.generatedAt, "2026-11-09T15:42:59Z");
  assert.match(result.publishedAt ?? "", /^2026-11-09/);
  assert.equal(result.predictedQualifying[0].driverName, "Charles Leclerc");
  assert.equal(result.podium[0].driverName, "Max Verstappen");
  assert.equal(result.source, "confirmed-feed");
});

test("a completed current event is unavailable as the next race", async () => {
  const { lookup } = provider();
  assert.deepEqual(await lookup(undefined, undefined, new Date("2026-11-23T12:00:00Z")), { available: false });
});

test("a feed without a confirmed current selection has no forecast", async () => {
  const missing = structuredClone(feed);
  missing.current = null;
  assert.deepEqual(await provider(missing).lookup(undefined, undefined, new Date("2026-11-13T12:00:00Z")), { available: false });
});

test("a named Streamlit archive can provide Mexico but an unrelated estimate cannot", async () => {
  const { lookup, requested } = provider();
  const mexico = await lookup("mexico", 2026, new Date("2026-11-13T12:00:00Z"));
  assert.equal(mexico.available, true);
  if (mexico.available) assert.equal(mexico.race.name, "Mexico City Grand Prix");
  assert.deepEqual(requested, ["predictions/2026-19.json"]);
  const usa = await lookup("united states", 2026, new Date("2026-11-13T12:00:00Z"));
  assert.equal(usa.available, true);
  if (usa.available) assert.equal(usa.race.name, "United States Grand Prix");
  const brazilResult = await lookup("brazil", 2026, new Date("2026-11-13T12:00:00Z"));
  assert.equal(brazilResult.available, true);
  if (brazilResult.available) assert.equal(brazilResult.race.name, "Brazilian Grand Prix");
  assert.deepEqual(await lookup("monaco", 2025, new Date("2026-11-13T12:00:00Z")), { available: false });
});

test("post-qualifying selection uses actual rows and restores rank order", async () => {
  const changed = structuredClone(feed);
  const current = changed.current!;
  current.prediction.mode = "actual_qualifying";
  const forecast = current.prediction.forecast as Record<string, unknown>;
  forecast.realQualifying = [
    { position: 2, driverName: "Second", gap: null },
    { position: 1, driverName: "First", gap: 0 },
  ];
  forecast.realGridPodium = [
    { rank: 2, driverName: "Second", podiumProbability: 0.4 },
    { rank: 1, driverName: "First", podiumProbability: 0.6 },
  ];
  const result = await provider(changed).lookup(undefined, undefined, new Date("2026-11-13T12:00:00Z"));
  assert.equal(result.available, true);
  if (!result.available) return;
  assert.equal(result.qualifyingMode, "actual");
  assert.equal(result.predictedQualifying[0].driverName, "First");
  assert.equal(result.predictedQualifying[1].gap, null);
  assert.equal(result.podium[0].driverName, "First");
});

test("a malformed dashboard archive is never substituted as a forecast", async () => {
  const lookup = createPublishedPredictionProvider({
    readCurrent: async () => ({ available: false as const }),
    readArchiveIndex: async () => index,
    readArchiveArtifact: async () => ({ ...archive, race_id: "2026-18" }),
  });
  assert.deepEqual(await lookup("mexico", 2026), { available: false });
});
