import assert from "node:assert/strict";
import test from "node:test";
import { getConstructorStandings } from "../lib/jolpica";

test("stats sync can fetch standings when Jolpica requires an identifiable client", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, init) => {
    const userAgent = new Headers(init?.headers).get("User-Agent");
    if (!userAgent) return new Response(null, { status: 403 });
    return Response.json({
      MRData: {
        StandingsTable: {
          StandingsLists: [{
            ConstructorStandings: [{
              position: "1",
              points: "100",
              wins: "2",
              Constructor: { constructorId: "ferrari", name: "Ferrari" },
            }],
          }],
        },
      },
    });
  };

  try {
    const standings = await getConstructorStandings("current");
    assert.equal(standings.live, true);
    assert.equal(standings.data[0]?.constructorId, "ferrari");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
