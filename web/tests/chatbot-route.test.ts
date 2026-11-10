import assert from "node:assert/strict";
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

test("route returns a typed prediction response without caching", async () => {
  const response = await POST(
    request(JSON.stringify({ message: "Show the latest F1 Buddy prediction" })),
  );
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /application\/json/);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(body.intent, "predictions");
  assert.ok(Array.isArray(body.sections));
  assert.ok(Array.isArray(body.quickReplies));
});
