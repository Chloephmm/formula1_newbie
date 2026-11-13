import { STREAMLIT_URL } from "../links";
import { normalizeQuestion } from "./intents";
import { createFeedReader, type ConfirmedFeed } from "./prediction-feed";

type RecordValue = Record<string, unknown>;
type FeedReader = ReturnType<typeof createFeedReader>;
export type PublishedPrediction =
  | { available: false }
  | {
      available: true;
      source: "confirmed-feed" | "dashboard-archive";
      cached: boolean;
      generatedAt: string;
      publishedAt?: string;
      race: { name: string; season: number; round: number; country: string; date: string };
      predictedQualifying: Array<{ position: number; driverName: string; gap: number | null }>;
      podium: Array<{ driverName: string; podiumProbability: number }>;
      qualifyingMode: "predicted" | "actual";
      predictionUrl: string;
    };

const unavailable: PublishedPrediction = { available: false };
function record(value: unknown): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid dashboard prediction");
  return value as RecordValue;
}
function string(value: unknown): string {
  if (typeof value !== "string" || !value) throw new Error("Invalid dashboard text");
  return value;
}
function integer(value: unknown): number {
  if (!Number.isInteger(value) || Number(value) < 1) throw new Error("Invalid dashboard race number");
  return Number(value);
}
function matches(name: string, search: string): boolean {
  return normalizeQuestion(name).includes(normalizeQuestion(search));
}
function rows(forecast: RecordValue, mode: "predicted" | "actual") {
  const qualifying = mode === "actual" ? forecast.realQualifying ?? forecast.actualQualifying : forecast.predictedQualifying;
  const podium = mode === "actual" ? forecast.realGridPodium ?? forecast.actualQualifyingPodium : forecast.preQualifyingPodium;
  if (!Array.isArray(qualifying) || !Array.isArray(podium) || !podium.length) throw new Error("Missing dashboard forecast rows");
  const qualifyingRows = qualifying.map((value) => {
    const row = record(value);
    return { position: integer(row.position), driverName: string(row.driverName), gap: typeof row.gap === "number" && Number.isFinite(row.gap) ? row.gap : null };
  }).sort((a, b) => a.position - b.position);
  const podiumRows = podium.map((value, index) => {
    const row = record(value);
    const probability = row.podiumProbability;
    if (typeof probability !== "number" || !Number.isFinite(probability) || probability < 0 || probability > 1) {
      throw new Error("Invalid dashboard podium probability");
    }
    return { rank: typeof row.rank === "number" ? row.rank : index + 1, driverName: string(row.driverName), podiumProbability: probability };
  }).sort((a, b) => a.rank - b.rank || b.podiumProbability - a.podiumProbability);
  return { qualifyingRows, podiumRows };
}

function fromConfirmed(feed: ConfirmedFeed, cached: boolean): PublishedPrediction {
  if (!feed.current) return unavailable;
  const event = record(feed.event);
  const prediction = record(feed.current.prediction);
  const forecast = record(prediction.forecast);
  const mode = prediction.mode === "actual_qualifying" ? "actual" : "predicted";
  const { qualifyingRows, podiumRows } = rows(forecast, mode);
  const raceStart = string(event.race_start_at);
  return {
    available: true,
    source: "confirmed-feed",
    cached,
    generatedAt: string(prediction.generated_at),
    publishedAt: string(feed.current.publication.published_at),
    race: { name: string(event.race_name), season: integer(event.season), round: integer(event.round), country: string(event.country), date: raceStart.slice(0, 10) },
    predictedQualifying: qualifyingRows,
    podium: podiumRows,
    qualifyingMode: mode,
    predictionUrl: STREAMLIT_URL,
  };
}

function fromLegacy(value: unknown, raceId: string): PublishedPrediction {
  const artifact = record(value);
  if (artifact.schema_version !== 2 || artifact.race_id !== raceId) throw new Error("Archive race mismatch");
  const race = record(artifact.race);
  if (`${integer(race.season)}-${integer(race.round)}` !== raceId) throw new Error("Archive identity mismatch");
  const mode = artifact.input_mode === "actual_qualifying" ? "actual" : artifact.input_mode === "estimated_qualifying" ? "predicted" : null;
  if (!mode || typeof artifact.prediction_updated_at !== "string" || !Number.isFinite(Date.parse(artifact.prediction_updated_at))) {
    throw new Error("Invalid dashboard archive");
  }
  const forecast = record(artifact.forecast);
  if (forecast.error) throw new Error("Unavailable dashboard archive");
  const { qualifyingRows, podiumRows } = rows(forecast, mode);
  const sum = podiumRows.reduce((value, row) => value + row.podiumProbability, 0);
  if (Math.abs(sum - 3) > 0.02) throw new Error("Archive podium is not normalized");
  return {
    available: true,
    source: "dashboard-archive",
    cached: false,
    generatedAt: artifact.prediction_updated_at,
    race: { name: string(race.name), season: integer(race.season), round: integer(race.round), country: string(race.country), date: string(race.date) },
    predictedQualifying: qualifyingRows,
    podium: podiumRows,
    qualifyingMode: mode,
    predictionUrl: STREAMLIT_URL,
  };
}

export function createPublishedPredictionProvider(reader: FeedReader = createFeedReader()) {
  return async (search?: string, season?: number, now = new Date()): Promise<PublishedPrediction> => {
    const current = await reader.readCurrent();
    if (!search) {
      if (!current.available || !current.feed.current) return unavailable;
      const start = Date.parse(string(current.feed.event.race_start_at));
      if (!Number.isFinite(start) || start <= now.getTime()) return unavailable;
      try { return fromConfirmed(current.feed, current.cached); } catch { return unavailable; }
    }
    if (current.available && current.feed.current &&
        (season === undefined || season === current.feed.event.season) &&
        (matches(string(current.feed.event.race_name), search) || matches(string(current.feed.event.country), search))) {
      try { return fromConfirmed(current.feed, current.cached); } catch { return unavailable; }
    }
    try {
      const index = record(await reader.readArchiveIndex());
      if (index.schema_version !== 2 || !Array.isArray(index.races)) return unavailable;
      const matchesIndex = index.races.map(record).filter((entry) =>
        (season === undefined || entry.season === season) &&
        (matches(string(entry.race_name), search) || matches(string(entry.race_id), search)));
      if (matchesIndex.length !== 1) return unavailable;
      const entry = matchesIndex[0];
      const raceId = string(entry.race_id);
      if (raceId !== `${integer(entry.season)}-${integer(entry.round)}`) return unavailable;
      const path = string(entry.artifact_url);
      const artifact = await reader.readArchiveArtifact(path);
      if (path.endsWith("/feed.json")) {
        const feed = artifact as ConfirmedFeed;
        if (feed.current_event_id !== raceId) return unavailable;
        return fromConfirmed(feed, false);
      }
      return fromLegacy(artifact, raceId);
    } catch {
      return unavailable;
    }
  };
}

export const getPublishedPrediction = createPublishedPredictionProvider();
