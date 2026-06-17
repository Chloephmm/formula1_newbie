// Live F1 data from Jolpica (Ergast successor) with ISR + graceful static fallback.
import { teams, drivers, races, getTeam } from "./data";
import type {
  ConstructorStanding,
  DriverStanding,
  ScheduleRace,
  ErgastResponse,
} from "./types";

const BASE = "https://api.jolpi.ca/ergast/f1";
const REVALIDATE_SECONDS = 3600;

async function jget(path: string): Promise<ErgastResponse> {
  const res = await fetch(`${BASE}/${path}`, {
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!res.ok) throw new Error(`Jolpica ${path} -> ${res.status}`);
  return (await res.json()) as ErgastResponse;
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
