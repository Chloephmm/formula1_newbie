import metricsData from "@/public/data/metrics.json";
import predictionData from "@/public/data/next_race_prediction.json";
import { driverPhoto } from "../assets";
import { drivers, getDriversForTeam, getTeam, races, teams } from "../data";
import { getSchedule } from "../jolpica";
import { STREAMLIT_URL } from "../links";
import {
  career,
  getConstructorStandings,
  getDriverStandings,
  seasonStat,
  statsUpdatedAt,
} from "../stats";
import { TEAM_META, teamLogo, type TeamMeta } from "../teamMeta";
import type {
  ConstructorStanding,
  Driver,
  DriverCareer,
  DriverStanding,
  Race,
  ScheduleRace,
  SeasonDriverStat,
} from "../types";
import { normalizeQuestion } from "./intents";

interface PredictionRace {
  name: string;
  season: number;
  round: number;
  country: string;
  date: string;
  qualifyingDate: string;
}

interface QualifyingRow {
  position: number;
  code: string;
  driverName: string;
  team: string;
  teamId: string;
  gap: number;
}

interface PodiumRow {
  code: string;
  driverName: string;
  team: string;
  teamId: string;
  podiumProbability: number;
}

interface PredictionFile {
  asof: string;
  generatedAt: string;
  race: PredictionRace;
  forecast: {
    error: string | null;
    predictedQualifying: QualifyingRow[];
    preQualifyingPodium: PodiumRow[];
    hasRealGrid: boolean;
    realGridPodium: PodiumRow[] | null;
    realQualifying: QualifyingRow[] | null;
  };
}

interface MetricsFile {
  podium: {
    top1Accuracy: number;
    top3Accuracy: number;
    rocAuc: number;
    testRows: number;
  };
}

export interface DriverSnapshot {
  id: string;
  name: string;
  code: string;
  nationality: string;
  team: { id: string; name: string };
  standing?: DriverStanding;
  seasonStats?: SeasonDriverStat;
  career: DriverCareer | null;
  image: string | null;
}

export interface TeamSnapshot {
  id: string;
  name: string;
  color: string;
  meta: TeamMeta;
  drivers: Driver[];
  standing?: ConstructorStanding;
  logo: string | null;
}

export interface RaceSnapshot {
  season: number;
  round: number;
  name: string;
  circuit?: string;
  locality?: string;
  country?: string;
  date: string;
  time?: string;
  qualifyingDate?: string;
}

export type PublishedPrediction =
  | { available: false }
  | {
      available: true;
      asof: string;
      generatedAt: string;
      race: PredictionRace;
      predictedQualifying: QualifyingRow[];
      podium: PodiumRow[];
      qualifyingMode: "predicted" | "actual";
      predictionUrl: string;
    };

const prediction = predictionData as PredictionFile;
const metrics = metricsData as MetricsFile;

function includesSearch(value: string, search: string): boolean {
  return normalizeQuestion(value).includes(normalizeQuestion(search));
}

export function findDriverSnapshot(search: string): DriverSnapshot | null {
  const normalized = normalizeQuestion(search);
  const driver = drivers.find((candidate) => {
    const name = normalizeQuestion(candidate.name);
    return (
      candidate.id === normalized ||
      candidate.code.toLowerCase() === normalized ||
      name === normalized ||
      name.split(" ").includes(normalized)
    );
  });
  if (!driver) return null;

  const team = getTeam(driver.team);
  const standing = getDriverStandings().find(
    (candidate) => candidate.driverId === driver.id || candidate.code === driver.code,
  );
  return {
    id: driver.id,
    name: driver.name,
    code: driver.code,
    nationality: driver.nationality,
    team: { id: driver.team, name: team?.name ?? standing?.constructorName ?? driver.team },
    standing,
    seasonStats: seasonStat(driver.code),
    career: career(driver.code),
    image: driverPhoto(driver.id),
  };
}

export function findTeamSnapshot(search: string): TeamSnapshot | null {
  const normalized = normalizeQuestion(search);
  const team = teams.find((candidate) => {
    const name = normalizeQuestion(candidate.name);
    return (
      normalizeQuestion(candidate.id) === normalized ||
      name === normalized ||
      normalizeQuestion(candidate.name.replace(/\s*F1 Team$/i, "")) === normalized
    );
  });
  if (!team) return null;
  const meta = TEAM_META[team.id];
  if (!meta) return null;

  return {
    id: team.id,
    name: team.name,
    color: team.color,
    meta,
    drivers: getDriversForTeam(team.id),
    standing: getConstructorStandings().find(
      (candidate) => candidate.constructorId === team.id,
    ),
    logo: teamLogo(team.id),
  };
}

export function getStandingsSnapshot(kind: "drivers"): {
  kind: "drivers";
  updatedAt: string;
  entries: DriverStanding[];
};
export function getStandingsSnapshot(kind: "constructors"): {
  kind: "constructors";
  updatedAt: string;
  entries: ConstructorStanding[];
};
export function getStandingsSnapshot(kind: "drivers" | "constructors") {
  return kind === "drivers"
    ? { kind, updatedAt: statsUpdatedAt(), entries: getDriverStandings() }
    : { kind, updatedAt: statsUpdatedAt(), entries: getConstructorStandings() };
}

function predictionRaceSnapshot(): RaceSnapshot {
  return { ...prediction.race };
}

export function findRaceSnapshot(search: string, season?: number): RaceSnapshot | null {
  const candidates: RaceSnapshot[] = [
    ...races.map((race: Race) => ({ ...race })),
    predictionRaceSnapshot(),
  ];
  return (
    candidates.find(
      (race) =>
        (season === undefined || race.season === season) &&
        (includesSearch(race.name, search) ||
          includesSearch(race.country ?? "", search) ||
          includesSearch(race.circuit ?? "", search)),
    ) ?? null
  );
}

export async function getNextRaceSnapshot(
  now = new Date(),
  scheduleProvider: typeof getSchedule = getSchedule,
): Promise<RaceSnapshot | null> {
  const nowTime = now.getTime();
  const local = races
    .map((race) => ({ ...race }))
    .filter((race) => new Date(`${race.date}T23:59:59Z`).getTime() >= nowTime)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  if (local) return local;

  const schedule = await scheduleProvider("current");
  const fallback = [...schedule.data]
    .filter((race) => new Date(`${race.date}T${race.time ?? "23:59:59Z"}`).getTime() >= nowTime)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  return fallback ? scheduleRaceSnapshot(fallback) : null;
}

export function getPreviousRaceSnapshot(now = new Date()): RaceSnapshot | null {
  const nowTime = now.getTime();
  const previous = races
    .map((race) => ({ ...race }))
    .filter((race) => new Date(`${race.date}T23:59:59Z`).getTime() < nowTime)
    .sort((a, b) => b.date.localeCompare(a.date))[0];
  return previous ?? null;
}

function scheduleRaceSnapshot(race: ScheduleRace): RaceSnapshot {
  return { ...race };
}

export function getPublishedPrediction(
  search?: string,
  season?: number,
): PublishedPrediction {
  if (prediction.forecast.error) return { available: false };
  if (season !== undefined && prediction.race.season !== season) {
    return { available: false };
  }
  if (
    search &&
    !includesSearch(prediction.race.name, search) &&
    !includesSearch(prediction.race.country, search)
  ) {
    return { available: false };
  }

  const useActual =
    prediction.forecast.hasRealGrid &&
    Boolean(prediction.forecast.realQualifying?.length) &&
    Boolean(prediction.forecast.realGridPodium?.length);
  return {
    available: true,
    asof: prediction.asof,
    generatedAt: prediction.generatedAt,
    race: prediction.race,
    predictedQualifying: useActual
      ? prediction.forecast.realQualifying ?? []
      : prediction.forecast.predictedQualifying,
    podium: useActual
      ? prediction.forecast.realGridPodium ?? []
      : prediction.forecast.preQualifyingPodium,
    qualifyingMode: useActual ? "actual" : "predicted",
    predictionUrl: STREAMLIT_URL,
  };
}

export function getModelMetricsSnapshot() {
  return {
    top1Accuracy: metrics.podium.top1Accuracy,
    top3Accuracy: metrics.podium.top3Accuracy,
    rocAuc: metrics.podium.rocAuc,
    testRows: metrics.podium.testRows,
  };
}
