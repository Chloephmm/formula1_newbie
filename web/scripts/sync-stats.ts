/**
 * sync-stats — fetches all driver/team stats from Jolpica ONCE and writes them to
 * web/public/data/stats.json. Run by the scheduled GitHub Action (and manually via
 * `npm run sync-stats`). Requests are throttled + retried inside lib/jolpica; this
 * script fails (non-zero exit) without writing if any critical fetch fails, so a
 * partial/broken file is never produced.
 */
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  getConstructorStandings,
  getDriverStandings,
  getSeasonStats,
  getDriverCareer,
} from "../lib/jolpica";
import type { DriverCareer } from "../lib/types";

const OUT = resolve(process.cwd(), "public/data/stats.json");
const SEASON = "current";

async function main() {
  console.log("[sync-stats] constructor standings…");
  const { data: constructors, live: cLive } = await getConstructorStandings(SEASON);
  console.log("[sync-stats] driver standings…");
  const { data: drivers, live: dLive } = await getDriverStandings(SEASON);
  console.log("[sync-stats] season stats…");
  const { data: seasonStats, live: sLive } = await getSeasonStats(SEASON);

  if (!cLive || !dLive || !sLive || !constructors.length || !drivers.length) {
    throw new Error("standings/season fetch failed or empty — aborting without write");
  }

  console.log(`[sync-stats] career totals for ${drivers.length} drivers…`);
  const career: Record<string, DriverCareer> = {};
  for (const d of drivers) {
    if (!d.code) continue;
    const { data, live } = await getDriverCareer(d.driverId);
    if (!live || !data) throw new Error(`career fetch failed for ${d.driverId} — aborting`);
    career[d.code] = data;
    console.log(`  ${d.code} (${d.driverId}): ${data.races} races, ${data.wins} wins`);
  }

  const payload = {
    updatedAt: new Date().toISOString(),
    season: new Date().getUTCFullYear().toString(),
    constructors,
    drivers,
    seasonStats,
    career,
  };

  writeFileSync(OUT, JSON.stringify(payload, null, 2) + "\n");
  console.log(`[sync-stats] wrote ${OUT} — ${constructors.length} teams, ${drivers.length} drivers.`);
}

main().catch((err: unknown) => {
  console.error("[sync-stats] FAILED:", err instanceof Error ? err.message : err);
  process.exit(1);
});
