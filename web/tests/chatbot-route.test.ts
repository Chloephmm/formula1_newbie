import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { POST } from "../app/api/f1-buddy/route";

function request(body: string): Request {
  return new Request("http://localhost/api/f1-buddy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

test("route rejects malformed JSON", async () => {
  const response = await POST(request("{"));
  assert.equal(response.status, 400);
});

test("route rejects missing, blank, and oversized messages", async () => {
  for (const body of [
    {},
    { message: "   " },
    { message: "x".repeat(501) },
  ]) {
    const response = await POST(request(JSON.stringify(body)));
    assert.equal(response.status, 400);
  }
});

test("route returns a typed prediction response without caching", async (context) => {
  context.mock.timers.enable({ apis: ["Date"], now: new Date("2026-11-13T12:00:00Z") });
  const originalFetch = globalThis.fetch;
  const feed = readFileSync(new URL("../public/data/prediction_feed.json", import.meta.url), "utf8");
  globalThis.fetch = async () => new Response(feed, { status: 200 });
  let response: Response;
  try {
    response = await POST(
      request(JSON.stringify({ message: "Show the latest F1 Buddy prediction" })),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /application\/json/);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(body.intent, "predictions");
  assert.equal(body.heading, "Las Vegas Grand Prix prediction");
  assert.match(JSON.stringify(body), /Charles Leclerc/);
  assert.match(JSON.stringify(body), /Max Verstappen/);
  assert.ok(Array.isArray(body.sections));
  assert.ok(Array.isArray(body.quickReplies));
});

test("route reads a named forecast from the Streamlit archive", async () => {
  const originalFetch = globalThis.fetch;
  const data = (path: string) => readFileSync(new URL(`../public/data/${path}`, import.meta.url), "utf8");
  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url.endsWith("predictions/index.json")) return new Response(data("predictions/index.json"));
    if (url.endsWith("predictions/2026-19.json")) return new Response(data("predictions/2026-19.json"));
    return new Response(data("prediction_feed.json"));
  };
  let response: Response;
  try {
    response = await POST(request(JSON.stringify({ message: "Mexico 2026 prediction" })));
  } finally {
    globalThis.fetch = originalFetch;
  }
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.heading, "Mexico City Grand Prix prediction");
  assert.match(body.body, /Streamlit dashboard archive/);
  assert.match(JSON.stringify(body), /Max Verstappen/);
});
