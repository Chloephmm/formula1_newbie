import { createHash } from "node:crypto";

export const FEED_URL = "https://raw.githubusercontent.com/Chloephmm/formula1_newbie/main/web/public/data/prediction_feed.json";
export const DATA_BASE_URL = FEED_URL.slice(0, -"prediction_feed.json".length);
const MAX_BYTES = 1_048_576;
const NUMBER_MARKER = "__f1_feed_number_lexeme__";
const ARTIFACT_PATH = /^(?:prediction_snapshots\/[1-9]\d*-[1-9]\d*\/feed\.json|predictions\/[1-9]\d*-[1-9]\d*\.json)$/;

type JsonObject = Record<string, unknown>;
export type ConfirmedSelection = { event: JsonObject; prediction: JsonObject; publication: JsonObject };
export type ConfirmedFeed = {
  schema_version: 1;
  current_event_id: string;
  feed_updated_at: string;
  event: JsonObject;
  status: JsonObject;
  current: ConfirmedSelection | null;
  previous: ConfirmedSelection | null;
  initial: ConfirmedSelection | null;
  revision: string;
};
export type FeedRead = { available: true; feed: ConfirmedFeed; cached: boolean } | { available: false };
export type FeedTransport = (url: string, init: RequestInit) => Promise<Response>;

function object(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid prediction feed object");
  return value as JsonObject;
}

function identity(value: JsonObject): string {
  const season = value.season;
  const round = value.round;
  if (!Number.isInteger(season) || !Number.isInteger(round) || Number(season) < 1 || Number(round) < 1) {
    throw new Error("Invalid prediction event identity");
  }
  return `${season}-${round}`;
}

function time(value: unknown): number {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) throw new Error("Invalid prediction timestamp");
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) throw new Error("Invalid prediction timestamp");
  return timestamp;
}

// The publisher hashes Python's canonical JSON. Keep numeric source tokens (0.0
// versus 0) while building the same canonical projections in JavaScript.
function lossless(raw: string): unknown {
  let transformed = "";
  let quoted = false;
  let escaped = false;
  for (let i = 0; i < raw.length; i += 1) {
    const character = raw[i];
    if (quoted) {
      transformed += character;
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') quoted = false;
      continue;
    }
    if (character === '"') {
      quoted = true;
      transformed += character;
      continue;
    }
    if (character === "-" || /[0-9]/.test(character)) {
      const match = raw.slice(i).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
      if (!match) throw new Error("Invalid number in prediction feed");
      transformed += `{"${NUMBER_MARKER}":"${match[0]}"}`;
      i += match[0].length - 1;
      continue;
    }
    transformed += character;
  }
  return JSON.parse(transformed);
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 1 && entries[0][0] === NUMBER_MARKER) return String(entries[0][1]);
    return `{${entries.sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

const PREDICTION_FIELDS = [
  "schema_version", "season", "round", "mode", "model_version", "model_manifest",
  "training_cutoff", "training_data_hash", "training_manifest", "qualifying_source_version",
  "qualifying_manifest", "input_hash", "feature_input_hash", "feature_policy_version",
  "probability_policy_version", "event_schedule_hash", "roster_version",
];

function predictionSemantic(prediction: JsonObject): JsonObject {
  const result: JsonObject = {};
  for (const field of PREDICTION_FIELDS) result[field] = prediction[field] ?? null;
  const forecast = { ...object(prediction.forecast) };
  for (const field of ["predictedQualifying", "preQualifyingPodium", "realQualifying", "realGridPodium"]) {
    const rows = forecast[field];
    if (Array.isArray(rows)) forecast[field] = [...rows].sort((a, b) =>
      String(object(a).driver_id ?? "").localeCompare(String(object(b).driver_id ?? "")));
  }
  result.forecast = forecast;
  return result;
}

function validateSelection(selection: unknown, event: JsonObject, rawSelection: unknown): void {
  if (selection === null) return;
  const item = object(selection);
  const raw = object(rawSelection);
  const selectedEvent = object(item.event);
  const prediction = object(item.prediction);
  const publication = object(item.publication);
  const rawPrediction = object(raw.prediction);
  const rawPublication = object(raw.publication);
  const eventId = identity(event);
  if (identity(selectedEvent) !== eventId || identity(prediction) !== eventId ||
      identity(publication) !== eventId || prediction.schema_version !== 2 ||
      publication.schema_version !== 1 || publication.confirmed !== true) {
    throw new Error("Prediction publication belongs to another event");
  }
  const mode = prediction.mode;
  if (mode !== "predicted_qualifying" && mode !== "actual_qualifying") throw new Error("Invalid prediction mode");
  const forecast = object(prediction.forecast);
  if (forecast.error !== null || forecast.mode !== mode || identity(object(forecast.race)) !== eventId) {
    throw new Error("Invalid published forecast");
  }
  const predictionId = prediction.prediction_id;
  if (typeof predictionId !== "string" || !/^[a-f0-9]{64}$/.test(predictionId) ||
      digest(canonical(predictionSemantic(rawPrediction))) !== predictionId ||
      publication.prediction_id !== predictionId) {
    throw new Error("Prediction ID does not match published content");
  }
  if (digest(`${canonical(rawPrediction)}\n`) !== publication.checksum) throw new Error("Invalid publication checksum");
  const receipt = { ...rawPublication };
  delete receipt.publication_id;
  if (digest(canonical(receipt)) !== publication.publication_id) throw new Error("Invalid publication ID");
  const generated = time(prediction.generated_at);
  const published = time(publication.published_at);
  const cutoff = time(publication.cutoff_at);
  if (generated > published || published >= cutoff) throw new Error("Publication missed the cutoff");
  if (mode === "predicted_qualifying" && published >= time(publication.qualifying_start_at)) {
    throw new Error("Initial forecast was published after qualifying");
  }
}

export function validateConfirmedFeed(raw: string): ConfirmedFeed {
  const feed = object(JSON.parse(raw));
  const lexical = object(lossless(raw));
  const revision = feed.revision;
  const withoutRevision = { ...lexical };
  delete withoutRevision.revision;
  if (feed.schema_version !== 1 || typeof revision !== "string" || digest(canonical(withoutRevision)) !== revision) {
    throw new Error("Invalid prediction feed revision");
  }
  const event = object(feed.event);
  object(feed.status);
  if (feed.current_event_id !== identity(event)) throw new Error("Invalid current prediction event");
  time(feed.feed_updated_at);
  for (const field of ["current", "previous", "initial"] as const) {
    validateSelection(feed[field] ?? null, event, lexical[field] ?? null);
  }
  const initial = feed.initial;
  if (initial && object(object(initial).prediction).mode !== "predicted_qualifying") throw new Error("Invalid initial forecast");
  return feed as ConfirmedFeed;
}

async function readText(response: Response): Promise<string> {
  if (!response.ok) throw new Error(`Prediction feed HTTP ${response.status}`);
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_BYTES) throw new Error("Prediction feed exceeds size limit");
  if (!response.body) throw new Error("Prediction feed has no body");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BYTES) {
      await reader.cancel();
      throw new Error("Prediction feed exceeds size limit");
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

export function createFeedReader(options: { transport?: FeedTransport; nowMs?: () => number; ttlMs?: number } = {}) {
  const transport = options.transport ?? ((url: string, init: RequestInit) => fetch(url, init));
  const nowMs = options.nowMs ?? Date.now;
  const ttlMs = options.ttlMs ?? 60_000;
  let cached: { feed: ConfirmedFeed; checkedAt: number; etag: string | null } | null = null;

  async function fetchPath(relative: string, etag?: string | null): Promise<Response> {
    const url = new URL(relative, DATA_BASE_URL);
    if (url.origin !== new URL(DATA_BASE_URL).origin || !url.href.startsWith(DATA_BASE_URL)) throw new Error("Invalid prediction URL");
    const response = await transport(url.href, {
      signal: AbortSignal.timeout(5_000),
      redirect: "error",
      headers: { Accept: "application/json", ...(etag ? { "If-None-Match": etag } : {}) },
      cache: "no-store",
    });
    if (response.url && new URL(response.url).origin !== url.origin) throw new Error("Prediction source redirected");
    return response;
  }

  return {
    async readCurrent(): Promise<FeedRead> {
      const now = nowMs();
      if (cached && now - cached.checkedAt < ttlMs) return { available: true, feed: cached.feed, cached: false };
      try {
        const response = await fetchPath("prediction_feed.json", cached?.etag);
        if (response.status === 304 && cached) {
          cached.checkedAt = now;
          return { available: true, feed: cached.feed, cached: false };
        }
        const feed = validateConfirmedFeed(await readText(response));
        if (cached && cached.feed.current_event_id === feed.current_event_id &&
            time(feed.feed_updated_at) < time(cached.feed.feed_updated_at)) {
          cached.checkedAt = now;
          return { available: true, feed: cached.feed, cached: true };
        }
        cached = { feed, checkedAt: now, etag: response.headers.get("ETag") };
        return { available: true, feed, cached: false };
      } catch {
        return cached ? { available: true, feed: cached.feed, cached: true } : { available: false };
      }
    },
    async readArchiveIndex(): Promise<unknown> {
      return JSON.parse(await readText(await fetchPath("predictions/index.json")));
    },
    async readArchiveArtifact(relative: string): Promise<unknown> {
      if (!ARTIFACT_PATH.test(relative)) throw new Error("Invalid archive path");
      const raw = await readText(await fetchPath(relative));
      return relative.endsWith("/feed.json") ? validateConfirmedFeed(raw) : JSON.parse(raw);
    },
  };
}
