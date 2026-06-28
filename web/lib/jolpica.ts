// Live F1 data from Jolpica with ISR + graceful static fallback.
import { teams, drivers, races, getTeam } from "./data";
import type {
  ConstructorStanding,
  DriverStanding,
  ScheduleRace,
  ErgastResponse,
  SeasonDriverStat,
  DriverCareer,
} from "./types";

const BASE = "https://api.jolpi.ca/ergast/f1";
const REVALIDATE_SECONDS = 3600;
const HOUR = 3600;
const DAY = 86400;

// Politeness gate: ensure a minimum spacing between Jolpica requests so the
// sync script (and any runtime caller) never bursts past the rate limit.
const MIN_INTERVAL_MS = 500;
let gateChain: Promise<void> = Promise.resolve();
function throttle(): Promise<void> {
  const wait = gateChain.then(() => new Promise<void>((r) => setTimeout(r, MIN_INTERVAL_MS)));
  gateChain = wait;
  return gateChain;
}

async function jget(
  path: string,
  revalidate = REVALIDATE_SECONDS,
  tries = 5
): Promise<ErgastResponse> {
  for (let attempt = 0; ; attempt++) {
    await throttle();
    const res = await fetch(`${BASE}/${path}`, { next: { revalidate } });
    if (res.ok) return (await res.json()) as ErgastResponse;
    // Retry transient rate-limit (429) / server errors with backoff.
    if ((res.status === 429 || res.status >= 500) && attempt < tries - 1) {
      await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
      continue;
    }
    throw new Error(`Jolpica ${path} -> ${res.status}`);
  }
}

/**
 * Seconds until career data should refresh — just after the next race finishes,
 * since whole-career stats only change on race day. Off-season (no upcoming
 * race) falls back to ~7 days. Clamped to [1h, 30d].
 */
export async function getCareerRevalidate(season = "current"): Promise<number> {
  try {
    const { data } = await getSchedule(season);
    const now = Date.now();
    const next = data
      .map((r) => new Date(`${r.date}T${r.time ?? "14:00:00Z"}`).getTime() + 4 * HOUR * 1000)
      .filter((end) => end > now)
      .sort((a, b) => a - b)[0];
    if (!next) return 7 * DAY;
    const secs = Math.round((next - now) / 1000);
    return Math.min(Math.max(secs, HOUR), 30 * DAY);
  } catch {
    return DAY;
  }
}

export async function getConstructorStandings(
  season = "current"
): Promise<{ data: ConstructorStanding[]; live: boolean }> {
  try {
    const json = await jget(`${season}/constructorstandings/`);
    const list = json.MRData.StandingsTable?.StandingsLists?.[0]?.ConstructorStandings ?? [];
    if (!list.length) throw new Error("empty");
    return {
      live: true,
      data: list.map((c) => ({
        position: Number(c.position),
        constructorId: c.Constructor.constructorId,
        name: c.Constructor.name,
        points: Number(c.points),
        wins: Number(c.wins),
      })),
    };
  } catch {
    return {
      live: false,
      data: [...teams]
        .sort((a, b) => b.points - a.points)
        .map((t, i) => ({
          position: i + 1,
          constructorId: t.id,
          name: t.name,
          points: t.points,
          wins: t.wins,
        })),
    };
  }
}

export async function getDriverStandings(
  season = "current"
): Promise<{ data: DriverStanding[]; live: boolean }> {
  try {
    const json = await jget(`${season}/driverstandings/`);
    const list = json.MRData.StandingsTable?.StandingsLists?.[0]?.DriverStandings ?? [];
    if (!list.length) throw new Error("empty");
    return {
      live: true,
      data: list.map((d) => ({
        position: Number(d.position),
        driverId: d.Driver.driverId,
        code: d.Driver.code ?? "",
        givenName: d.Driver.givenName,
        familyName: d.Driver.familyName,
        nationality: d.Driver.nationality,
        points: Number(d.points),
        wins: Number(d.wins),
        constructorId: d.Constructors[0]?.constructorId ?? "",
        constructorName: d.Constructors[0]?.name ?? "",
      })),
    };
  } catch {
    return {
      live: false,
      data: [...drivers]
        .sort((a, b) => b.points - a.points)
        .map((d, i) => {
          const [givenName, ...rest] = d.name.split(" ");
          return {
            position: i + 1,
            driverId: d.id,
            code: d.code,
            givenName,
            familyName: rest.join(" "),
            nationality: d.nationality,
            points: d.points,
            wins: d.wins,
            constructorId: d.team,
            constructorName: getTeam(d.team)?.name ?? d.team,
          };
        }),
    };
  }
}

/**
 * Aggregates real per-driver season stats (races, wins, podiums, fastest laps
 * from race results; poles from qualifying) for the given season, keyed by the
 * driver's 3-letter code. A few cached, season-wide calls shared by every team page.
 */
export async function getSeasonStats(
  season = "current"
): Promise<{ data: Record<string, SeasonDriverStat>; live: boolean }> {
  try {
    const stats: Record<string, SeasonDriverStat> = {};
    const slot = (code: string) =>
      (stats[code] ??= { races: 0, wins: 0, podiums: 0, poles: 0, fastestLaps: 0 });

    // Race results across every round (paginated) -> races / wins / podiums / fastest laps.
    const limit = 100;
    let offset = 0;
    let total = Infinity;
    while (offset < total) {
      const json = await jget(`${season}/results/?limit=${limit}&offset=${offset}`);
      total = Number(json.MRData.total ?? 0);
      const racesPage = json.MRData.RaceTable?.Races ?? [];
      if (!racesPage.length) break;
      for (const r of racesPage) {
        for (const res of r.Results ?? []) {
          const code = res.Driver.code;
          if (!code) continue;
          const s = slot(code);
          s.races += 1;
          const pos = Number(res.position);
          if (pos === 1) s.wins += 1;
          if (pos <= 3) s.podiums += 1;
          if (res.FastestLap?.rank === "1") s.fastestLaps += 1;
        }
      }
      offset += limit;
    }

    // Poles = qualifying P1 per round.
    const q = await jget(`${season}/qualifying/1/?limit=100`);
    for (const r of q.MRData.RaceTable?.Races ?? []) {
      const code = r.QualifyingResults?.[0]?.Driver.code;
      if (code) slot(code).poles += 1;
    }

    if (!Object.keys(stats).length) throw new Error("empty");
    return { live: true, data: stats };
  } catch {
    return { live: false, data: {} };
  }
}

/**
 * Whole-career totals for a driver (by Ergast driverId). Each value is the
 * `total` count of a filtered results/qualifying query, fetched in parallel.
 * Podiums = finishes P1 + P2 + P3.
 */
export async function getDriverCareer(
  driverId: string,
  revalidate?: number
): Promise<{ data: DriverCareer | null; live: boolean }> {
  try {
    const totalOf = async (path: string) =>
      Number((await jget(path, revalidate)).MRData.total ?? 0);
    // Serial (not Promise.all) to avoid bursting Jolpica's rate limit.
    const races = await totalOf(`drivers/${driverId}/results/?limit=1`);
    const p1 = await totalOf(`drivers/${driverId}/results/1/?limit=1`);
    const p2 = await totalOf(`drivers/${driverId}/results/2/?limit=1`);
    const p3 = await totalOf(`drivers/${driverId}/results/3/?limit=1`);
    const poles = await totalOf(`drivers/${driverId}/qualifying/1/?limit=1`);
    const fastestLaps = await totalOf(`drivers/${driverId}/fastest/1/results/?limit=1`);
    return {
      live: true,
      data: { races, wins: p1, podiums: p1 + p2 + p3, poles, fastestLaps },
    };
  } catch {
    return { live: false, data: null };
  }
}

export async function getSchedule(
  season = "current"
): Promise<{ data: ScheduleRace[]; live: boolean }> {
  try {
    const json = await jget(`${season}/races/`);
    const list = json.MRData.RaceTable?.Races ?? [];
    if (!list.length) throw new Error("empty");
    return {
      live: true,
      data: list.map((r) => ({
        season: Number(r.season),
        round: Number(r.round),
        name: r.raceName,
        circuit: r.Circuit.circuitName,
        locality: r.Circuit.Location?.locality,
        country: r.Circuit.Location?.country,
        date: r.date,
        time: r.time,
      })),
    };
  } catch {
    const latestSeason = Math.max(...races.map((r) => r.season));
    return {
      live: false,
      data: races
        .filter((r) => r.season === latestSeason)
        .sort((a, b) => a.round - b.round)
        .map((r) => ({
          season: r.season,
          round: r.round,
          name: r.name,
          circuit: r.circuit,
          date: r.date,
        })),
    };
  }
}
