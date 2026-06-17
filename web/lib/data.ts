// Static data loaders (lookup tables + offline fallback for the live Jolpica calls).
import teamsData from "@/public/data/teams.json";
import driversData from "@/public/data/drivers.json";
import racesData from "@/public/data/races.json";
import type { Team, Driver, Race } from "./types";

export const teams: Team[] = teamsData as Team[];
export const drivers: Driver[] = driversData as Driver[];
export const races: Race[] = racesData as Race[];

export function getTeam(id: string): Team | undefined {
  return teams.find((t) => t.id === id);
}
export function getDriverByCode(code: string): Driver | undefined {
  return drivers.find((d) => d.code === code);
}
export function getDriversForTeam(teamId: string): Driver[] {
  return drivers.filter((d) => d.team === teamId);
}
export function teamColor(teamId: string): string {
  return getTeam(teamId)?.color ?? "#888888";
}
