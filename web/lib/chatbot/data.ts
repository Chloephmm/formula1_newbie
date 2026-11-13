import metricsData from "@/public/data/metrics.json";
import predictionData from "@/public/data/next_race_prediction.json";
import predictionArchive2026Round18 from "@/public/data/predictions/2026-18.json";
import predictionArchive2026Round19 from "@/public/data/predictions/2026-19.json";
import predictionArchive2026Round20 from "@/public/data/predictions/2026-20.json";
import predictionIndexData from "@/public/data/predictions/index.json";
import predictionsData from "@/public/data/predictions.json";
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
  RaceSessionResults,
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

interface SchemaV2PredictionRace {
  name: string;
  season: number;
  round: number;
  country: string;
  date: string;
  raceStartAt?: string;
  qualifyingStartAt?: string;
}

interface SchemaV2PredictionFile {
  schema_version: number;
  prediction_updated_at: string;
  race: SchemaV2PredictionRace;
  forecast: {
    error: string | null;
    asof: string;
    race?: SchemaV2PredictionRace;
    predictedQualifying: QualifyingRow[];
    preQualifyingPodium: PodiumRow[];
    hasActualQualifying: boolean;
    actualQualifyingPodium: PodiumRow[] | null;
    actualQualifying: QualifyingRow[] | null;
  };
}

type PredictionInput = PredictionFile | SchemaV2PredictionFile;

interface PredictionIndexFile {
  races: Array<{
    race_id: string;
    season: number;
    round: number;
    race_name: string;
    race_start_at: string;
  }>;
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
      source: "next-race-snapshot" | "historical-estimate";
      asof: string;
      generatedAt?: string;
      race: PredictionRace;
      predictedQualifying: QualifyingRow[];
      podium: PodiumRow[];
      qualifyingMode: "predicted" | "actual";
      predictionUrl: string;
    };

function normalizePredictionFile(input: PredictionInput): PredictionFile {
  if (!("schema_version" in input)) return input;

  const sourceRace = input.forecast.race ?? input.race;
  return {
    asof: input.forecast.asof,
    generatedAt: input.prediction_updated_at,
    race: {
      name: sourceRace.name,
      season: sourceRace.season,
      round: sourceRace.round,
      country: sourceRace.country,
      date: sourceRace.date,
      qualifyingDate: sourceRace.qualifyingStartAt?.slice(0, 10) ?? sourceRace.date,
    },
    forecast: {
      error: input.forecast.error,
      predictedQualifying: input.forecast.predictedQualifying,
      preQualifyingPodium: input.forecast.preQualifyingPodium,
      hasRealGrid: input.forecast.hasActualQualifying,
      realGridPodium: input.forecast.actualQualifyingPodium,
      realQualifying: input.forecast.actualQualifying,
    },
  };
}

const prediction = normalizePredictionFile(
  predictionData as unknown as PredictionInput,
);
const detailedPredictions = Array.from(
  new Map(
    [
      prediction,
      normalizePredictionFile(predictionArchive2026Round18 as SchemaV2PredictionFile),
      normalizePredictionFile(predictionArchive2026Round19 as SchemaV2PredictionFile),
      normalizePredictionFile(predictionArchive2026Round20 as SchemaV2PredictionFile),
    ].map((snapshot) => [
      `${snapshot.race.season}-${snapshot.race.round}`,
      snapshot,
    ]),
  ).values(),
).sort((a, b) => b.race.date.localeCompare(a.race.date));
const predictionIndex = predictionIndexData as PredictionIndexFile;
const historicalPredictions = predictionsData as Record<
  string,
  Array<{
    driver: string;
    driverName: string;
    team: string;
    podiumProbability: number;
  }>
>;
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

function predictionIndexSnapshots(): RaceSnapshot[] {
  return predictionIndex.races.map((race) => ({
    season: race.season,
    round: race.round,
    name: race.race_name,
    date: race.race_start_at.slice(0, 10),
  }));
}

function detailedPredictionForRace(race: Pick<RaceSnapshot, "season" | "round">) {
  return detailedPredictions.find(
    (snapshot) =>
      snapshot.race.season === race.season && snapshot.race.round === race.round,
  );
}

function utcDateKey(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export function findRaceSnapshot(search: string, season?: number): RaceSnapshot | null {
  const candidates: RaceSnapshot[] = [
    ...detailedPredictions.map((snapshot) => ({ ...snapshot.race })),
    ...predictionIndexSnapshots(),
    ...races.map((race: Race) => ({ ...race })),
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

export async function resolveRaceSnapshot(
  search: string,
  season?: number,
  scheduleProvider: typeof getSchedule = getSchedule,
): Promise<RaceSnapshot | null> {
  const selectedSeason = season ?? new Date().getUTCFullYear();
  const local = findRaceSnapshot(search, selectedSeason);
  if (local) return local;

  const schedule = await scheduleProvider(String(selectedSeason));
  const matches = schedule.data.filter(
    (race) =>
      race.season === selectedSeason &&
      (includesSearch(race.name, search) ||
        includesSearch(race.country ?? "", search) ||
        includesSearch(race.circuit ?? "", search)),
  );
  return matches.length === 1 ? scheduleRaceSnapshot(matches[0]) : null;
}

export async function getNextRaceSnapshot(
  now = new Date(),
  scheduleProvider: typeof getSchedule = getSchedule,
): Promise<RaceSnapshot | null> {
  const nowTime = now.getTime();
  const snapshot = predictionRaceSnapshot();
  const snapshotIsCompatible =
    prediction.asof === utcDateKey(now) &&
    new Date(`${snapshot.date}T23:59:59Z`).getTime() >= nowTime;
  if (snapshotIsCompatible) return snapshot;

  const schedule = await scheduleProvider(String(now.getUTCFullYear()));
  const fallback = [...schedule.data]
    .filter((race) => race.date >= utcDateKey(now))
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  return fallback ? scheduleRaceSnapshot(fallback) : null;
}

export function getPreviousRaceSnapshot(now = new Date()): RaceSnapshot | null {
  const nowTime = now.getTime();
  const previous = [
    ...races.map((race) => ({ ...race })),
    ...predictionIndexSnapshots(),
    ...detailedPredictions.map((snapshot) => ({ ...snapshot.race })),
  ]
    .filter((race) => new Date(`${race.date}T23:59:59Z`).getTime() < nowTime)
    .sort((a, b) => b.date.localeCompare(a.date))[0];
  return previous ?? null;
}

export async function getPreviousRaceFromSchedule(
  now = new Date(),
  scheduleProvider: typeof getSchedule = getSchedule,
): Promise<RaceSnapshot | null> {
  const schedule = await scheduleProvider(String(now.getUTCFullYear()));
  const previous = [...schedule.data]
    .filter((race) => race.date < utcDateKey(now))
    .sort((a, b) => b.date.localeCompare(a.date))[0];
  return previous ? scheduleRaceSnapshot(previous) : getPreviousRaceSnapshot(now);
}

export function getSavedSessionResults(
  race: RaceSnapshot,
  session: "results" | "qualifying",
  snapshot?: PredictionInput,
): RaceSessionResults | null {
  const selectedSnapshot = snapshot
    ? normalizePredictionFile(snapshot)
    : detailedPredictionForRace(race);
  if (
    !selectedSnapshot ||
    session !== "qualifying" ||
    selectedSnapshot.race.season !== race.season ||
    selectedSnapshot.race.round !== race.round ||
    !selectedSnapshot.forecast.hasRealGrid ||
    !selectedSnapshot.forecast.realQualifying?.length
  ) {
    return null;
  }

  return {
    raceName: selectedSnapshot.race.name,
    season: selectedSnapshot.race.season,
    round: selectedSnapshot.race.round,
    results: selectedSnapshot.forecast.realQualifying.map((row) => ({
      position: row.position,
      driverId: row.code.toLowerCase(),
      code: row.code,
      driverName: row.driverName,
      constructorName: row.team,
    })),
  };
}

function scheduleRaceSnapshot(race: ScheduleRace): RaceSnapshot {
  return { ...race };
}

export function getPublishedPrediction(
  search?: string,
  season?: number,
  now = new Date(),
  allowHistoricalEstimate = true,
): PublishedPrediction {
  if (!search && prediction.asof !== utcDateKey(now)) {
    return { available: false };
  }

  const selectedSnapshot = search
    ? detailedPredictions.find(
        (snapshot) =>
          (season === undefined || snapshot.race.season === season) &&
          (includesSearch(snapshot.race.name, search) ||
            includesSearch(snapshot.race.country, search)),
      )
    : prediction;

  if (!selectedSnapshot) {
    if (!search || season === undefined || !allowHistoricalEstimate) {
      return { available: false };
    }
    const race = findRaceSnapshot(search, season);
    if (!race) return { available: false };
    const rows = historicalPredictions[`${season}-${race.round}`];
    if (!rows?.length) return { available: false };
    return {
      available: true,
      source: "historical-estimate",
      asof: race.date,
      race: {
        name: race.name,
        season: race.season,
        round: race.round,
        country: race.country ?? "",
        date: race.date,
        qualifyingDate: race.qualifyingDate ?? race.date,
      },
      predictedQualifying: [],
      podium: rows.map((row) => ({
        code: row.driver,
        driverName: row.driverName,
        team: row.team,
        teamId: "",
        podiumProbability: row.podiumProbability,
      })),
      qualifyingMode: "predicted",
      predictionUrl: STREAMLIT_URL,
    };
  }

  if (selectedSnapshot.forecast.error) return { available: false };

  const useActual =
    selectedSnapshot.forecast.hasRealGrid &&
    Boolean(selectedSnapshot.forecast.realQualifying?.length) &&
    Boolean(selectedSnapshot.forecast.realGridPodium?.length);
  return {
    available: true,
    source: "next-race-snapshot",
    asof: selectedSnapshot.asof,
    generatedAt: selectedSnapshot.generatedAt,
    race: selectedSnapshot.race,
    predictedQualifying: useActual
      ? selectedSnapshot.forecast.realQualifying ?? []
      : selectedSnapshot.forecast.predictedQualifying,
    podium: useActual
      ? selectedSnapshot.forecast.realGridPodium ?? []
      : selectedSnapshot.forecast.preQualifyingPodium,
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
