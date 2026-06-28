// Reads the pre-generated static stats (web/public/data/stats.json), produced by
// `npm run sync-stats` (the scheduled GitHub Action). Pages read these synchronous
// getters instead of calling Jolpica at render time. Falls back to the committed
// teams.json / drivers.json so a missing entry never renders "—" on core numbers.
import statsData from "@/public/data/stats.json";
import { teams, drivers as staticDrivers, getTeam } from "./data";
import type {
  ConstructorStanding,
  DriverStanding,
  SeasonDriverStat,
  DriverCareer,
} from "./types";

interface StatsFile {
  updatedAt: string;
  season: string;
  constructors: ConstructorStanding[];
  drivers: DriverStanding[];
  seasonStats: Record<string, SeasonDriverStat>;
  career: Record<string, DriverCareer>;
}

const stats = statsData as StatsFile;

export function statsUpdatedAt(): string {
  return stats.updatedAt;
}

export function getConstructorStandings(): ConstructorStanding[] {
  if (stats.constructors?.length) return stats.constructors;
  return [...teams]
    .sort((a, b) => b.points - a.points)
    .map((t, i) => ({
      position: i + 1,
      constructorId: t.id,
      name: t.name,
      points: t.points,
      wins: t.wins,
    }));
}

export function getDriverStandings(): DriverStanding[] {
  if (stats.drivers?.length) return stats.drivers;
  return [...staticDrivers]
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
    });
}

// Season aggregate for a driver (by 3-letter code).
export function seasonStat(code: string): SeasonDriverStat | undefined {
  return stats.seasonStats?.[code];
}

// Whole-career totals for a driver (by 3-letter code).
export function career(code: string): DriverCareer | null {
  return stats.career?.[code] ?? null;
}
