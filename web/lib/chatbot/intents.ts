import { drivers, teams } from "../data";
import type { ParsedQuestion, ResultKind } from "./types";

export function normalizeQuestion(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function hasTerm(normalized: string, terms: readonly string[]): boolean {
  const padded = ` ${normalized} `;
  return terms.some((term) => padded.includes(` ${term} `));
}

function findDriver(normalized: string): string | undefined {
  const tokens = new Set(normalized.split(" "));
  for (const driver of drivers) {
    const fullName = normalizeQuestion(driver.name);
    const surname = fullName.split(" ").at(-1) ?? fullName;
    if (
      normalized.includes(fullName) ||
      tokens.has(surname) ||
      tokens.has(driver.code.toLowerCase()) ||
      normalized.includes(normalizeQuestion(driver.id))
    ) {
      return driver.id;
    }
  }
  return undefined;
}

function findTeam(normalized: string): string | undefined {
  const padded = ` ${normalized} `;
  for (const team of teams) {
    const candidates = [
      normalizeQuestion(team.name),
      normalizeQuestion(team.name.replace(/\s*F1 Team$/i, "")),
      normalizeQuestion(team.id),
    ];
    if (candidates.some((candidate) => padded.includes(` ${candidate} `))) {
      return team.id;
    }
  }
  return undefined;
}

function resultKind(normalized: string): ResultKind | undefined {
  const asksForResult = hasTerm(normalized, [
    "result",
    "results",
    "winner",
    "finish",
    "finished",
  ]);
  if (
    hasTerm(normalized, ["schedule", "date", "time", "when"]) &&
    !asksForResult
  ) {
    return "schedule";
  }
  if (hasTerm(normalized, ["qualifying", "quali", "grid", "pole"])) {
    return "qualifying";
  }
  if (asksForResult) {
    return "race";
  }
  if (
    hasTerm(normalized, ["schedule", "date", "time", "next", "circuit", "where", "when"])
  ) {
    return "schedule";
  }
  return undefined;
}

const RACE_STOP_WORDS = new Set([
  "show",
  "tell",
  "me",
  "about",
  "for",
  "details",
  "the",
  "a",
  "an",
  "f1",
  "formula",
  "one",
  "grand",
  "prix",
  "gp",
  "race",
  "races",
  "result",
  "results",
  "qualifying",
  "quali",
  "schedule",
  "date",
  "time",
  "circuit",
  "winner",
  "finish",
  "finished",
  "next",
  "previous",
  "last",
  "latest",
  "buddy",
  "prediction",
  "predictions",
  "predict",
  "predicted",
  "forecast",
  "forecasts",
  "podium",
  "probability",
  "probabilities",
  "when",
  "what",
  "where",
  "is",
  "was",
]);

function raceSearchTerm(normalized: string, season?: number): string | undefined {
  const words = normalized
    .split(" ")
    .filter((word) => word !== String(season ?? ""))
    .filter((word) => !RACE_STOP_WORDS.has(word));
  return words.length ? words.join(" ") : undefined;
}

export function parseQuestion(message: string): ParsedQuestion {
  const normalized = normalizeQuestion(message);
  const seasonMatch = normalized.match(/\b(20\d{2})\b/);
  const season = seasonMatch ? Number(seasonMatch[1]) : undefined;
  const driver = findDriver(normalized);
  const team = findTeam(normalized);

  if (
    hasTerm(normalized, [
      "prediction",
      "predictions",
      "predict",
      "predicted",
      "forecast",
      "forecasts",
      "probability",
      "probabilities",
      "accuracy",
    ]) ||
    (hasTerm(normalized, ["podium"]) && !driver)
  ) {
    return {
      intent: "predictions",
      normalized,
      season,
      searchTerm: raceSearchTerm(normalized, season),
    };
  }

  if (hasTerm(normalized, ["standing", "standings", "championship", "leader"])) {
    return {
      intent: "standings",
      normalized,
      season,
      standingKind: hasTerm(normalized, ["constructor", "constructors", "team", "teams"])
        ? "constructors"
        : "drivers",
    };
  }

  if (team && (hasTerm(normalized, ["team", "teams", "drives", "lineup"]) || !driver)) {
    return { intent: "teams", normalized, season, searchTerm: team };
  }

  if (driver || hasTerm(normalized, ["driver", "drivers", "career", "stats", "statistics"])) {
    return { intent: "drivers", normalized, season, searchTerm: driver };
  }

  const session = resultKind(normalized);
  if (
    session ||
    hasTerm(normalized, ["race", "races", "grand prix", "gp", "weekend"])
  ) {
    return {
      intent: "race",
      normalized,
      season,
      searchTerm: raceSearchTerm(normalized, season),
      resultKind: session ?? "schedule",
    };
  }

  return { intent: "unsupported", normalized, season };
}
