import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createFeedReader, validateConfirmedFeed } from "../lib/chatbot/prediction-feed";

const source = readFileSync(new URL("../public/data/prediction_feed.json", import.meta.url), "utf8");

test("reads the same confirmed current feed as Streamlit", async () => {
  let calls = 0;
  let now = 0;
  const reader = createFeedReader({
    nowMs: () => now,
    transport: async () => {
      calls += 1;
      return new Response(source, { status: 200, headers: { ETag: '"feed-1"' } });
    },
  });
  const first = await reader.readCurrent();
  assert.equal(first.available, true);
  if (!first.available) return;
  assert.equal(first.feed.current_event_id, "2026-21");
  assert.equal(first.feed.current?.publication.confirmed, true);
  now = 30_000;
  const second = await reader.readCurrent();
  assert.equal(second.available, true);
  assert.equal(calls, 1);
});

test("rejects changed revision, prediction, receipt, and event identity", () => {
  const valid = JSON.parse(source);
  const mutations: Array<(feed: Record<string, unknown>) => void> = [
    (feed) => { feed.revision = "0".repeat(64); },
    (feed) => { (feed.current as typeof valid.current).prediction.prediction_id = "0".repeat(64); },
    (feed) => { (feed.current as typeof valid.current).publication.checksum = "0".repeat(64); },
    (feed) => { (feed.current as typeof valid.current).publication.publication_id = "0".repeat(64); },
    (feed) => { feed.current_event_id = "2026-22"; },
  ];
  for (const mutate of mutations) {
    const feed = structuredClone(valid);
    mutate(feed);
    assert.throws(() => validateConfirmedFeed(JSON.stringify(feed)));
  }
});

test("a failed refresh uses only a validated last-good feed", async () => {
  let now = 0;
  let failing = false;
  const reader = createFeedReader({
    nowMs: () => now,
    transport: async () => failing ? new Response("unavailable", { status: 503 }) : new Response(source),
  });
  const first = await reader.readCurrent();
  assert.equal(first.available, true);
  now = 61_000;
  failing = true;
  const second = await reader.readCurrent();
  assert.deepEqual(second.available ? second.cached : false, true);
  const empty = createFeedReader({ transport: async () => new Response("unavailable", { status: 503 }) });
  assert.deepEqual(await empty.readCurrent(), { available: false });
});

test("archive paths cannot escape the Streamlit publication root", async () => {
  const reader = createFeedReader({ transport: async () => new Response(source) });
  await assert.rejects(reader.readArchiveArtifact("../predictions.json"));
  await assert.rejects(reader.readArchiveArtifact("predictions/2026-19.json?evil=1"));
});
