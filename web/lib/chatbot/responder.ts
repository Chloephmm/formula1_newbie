import {
  findDriverSnapshot,
  findTeamSnapshot,
  getModelMetricsSnapshot,
  getNextRaceSnapshot,
  getPreviousRaceFromSchedule,
  getSavedSessionResults,
  getStandingsSnapshot,
  resolveRaceSnapshot,
  type RaceSnapshot,
} from "./data";
import { getPublishedPrediction, type PublishedPrediction } from "./published-predictions";
import { parseQuestion } from "./intents";
import {
  getConstructorStandings as getLiveConstructorStandings,
  getDriverStandings as getLiveDriverStandings,
  getSessionResults,
} from "../jolpica";
import type {
  ConstructorStanding,
  DriverStanding,
  RaceSessionResults,
} from "../types";
import type { ChatReply, QuickReply } from "./types";

export interface ResponderDependencies {
  now: () => Date;
  getSessionResults: typeof getSessionResults;
  getNextRaceSnapshot: typeof getNextRaceSnapshot;
  resolveRaceSnapshot: typeof resolveRaceSnapshot;
  getSavedDriverStandings: () => DriverStandingsSnapshot;
  getSavedConstructorStandings: () => ConstructorStandingsSnapshot;
  getLiveDriverStandings: typeof getLiveDriverStandings;
  getLiveConstructorStandings: typeof getLiveConstructorStandings;
  getSavedSessionResults: typeof getSavedSessionResults;
  getPreviousRaceFromSchedule: typeof getPreviousRaceFromSchedule;
  getPublishedPrediction: (
    search?: string,
    season?: number,
    now?: Date,
  ) => Promise<PublishedPrediction>;
}

type DriverStandingsSnapshot = {
  kind: "drivers";
  updatedAt: string;
  entries: DriverStanding[];
};

type ConstructorStandingsSnapshot = {
  kind: "constructors";
  updatedAt: string;
  entries: ConstructorStanding[];
};

export const defaultResponderDependencies: ResponderDependencies = {
  now: () => new Date(),
  getSessionResults,
  getNextRaceSnapshot,
  resolveRaceSnapshot,
  getSavedDriverStandings: () => getStandingsSnapshot("drivers"),
  getSavedConstructorStandings: () => getStandingsSnapshot("constructors"),
  getLiveDriverStandings,
  getLiveConstructorStandings,
  getSavedSessionResults,
  getPreviousRaceFromSchedule,
  getPublishedPrediction,
};

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "long",
  timeZone: "UTC",
});

function formatDate(date: string): string {
  return dateFormatter.format(new Date(`${date}T12:00:00Z`));
}

function quick(label: string, prompt: string): QuickReply {
  return { label, prompt };
}

function raceQuickReplies(race: RaceSnapshot): QuickReply[] {
  return [
    quick(
      "Qualifying Schedule",
      `Show the qualifying schedule for ${race.name} ${race.season}`,
    ),
    quick("Circuit Details", `${race.name} ${race.season} circuit details`),
    quick(
      "Previous Race Results",
      "Show previous F1 race results",
    ),
  ];
}

async function answerRace(
  message: string,
  dependencies: ResponderDependencies,
): Promise<ChatReply> {
  const parsed = parseQuestion(message);
  const now = dependencies.now();

  if (parsed.resultKind === "race" || parsed.resultKind === "qualifying") {
    const race = parsed.searchTerm
      ? await dependencies.resolveRaceSnapshot(parsed.searchTerm, parsed.season)
      : await dependencies.getPreviousRaceFromSchedule(now);
    if (!race) {
      return {
        intent: "race",
        heading: "Race results",
        body: "I could not match that request to a saved Grand Prix.",
        sections: [{ kind: "paragraph", text: "Try including the race name and season." }],
        quickReplies: [],
      };
    }
    const session = parsed.resultKind === "qualifying" ? "qualifying" : "results";
    const saved = dependencies.getSavedSessionResults(race, session);
    if (saved) {
      return resultReply(saved, session, race, "saved");
    }
    const official = await dependencies.getSessionResults(race.season, race.round, session);
    if (!official.data) {
      return {
        intent: "race",
        heading: `${race.name} ${session === "qualifying" ? "qualifying" : "results"}`,
        body: "The official results are temporarily unavailable. Please try again later.",
        sections: [],
        quickReplies: raceQuickReplies(race),
      };
    }
    return resultReply(official.data, session, race, "jolpica");
  }

  const race = parsed.searchTerm
    ? await dependencies.resolveRaceSnapshot(parsed.searchTerm, parsed.season)
    : await dependencies.getNextRaceSnapshot(now);
  if (!race) {
    return {
      intent: "race",
      heading: "Race details",
      body: "No upcoming race is available in the saved schedule right now.",
      sections: [],
      quickReplies: [],
    };
  }

  const location = [race.locality, race.country].filter(Boolean).join(", ");
  const facts = [
    { label: "Date", value: formatDate(race.date) },
    ...(race.time ? [{ label: "Start", value: `${race.time} (source timezone)` }] : []),
    ...(race.circuit ? [{ label: "Circuit", value: race.circuit }] : []),
    ...(location ? [{ label: "Location", value: location }] : []),
    ...(race.qualifyingDate
      ? [{ label: "Qualifying", value: formatDate(race.qualifyingDate) }]
      : []),
  ];
  return {
    intent: "race",
    heading: race.name,
    body: `Round ${race.round} of the ${race.season} season.`,
    sections: [{ kind: "facts", items: facts }],
    quickReplies: raceQuickReplies(race),
  };
}

function resultReply(
  data: RaceSessionResults,
  session: "results" | "qualifying",
  race: RaceSnapshot,
  source: "saved" | "jolpica",
): ChatReply {
  const label = session === "qualifying" ? "Qualifying" : "Race result";
  return {
    intent: "race",
    heading: `${data.raceName} ${label.toLowerCase()}`,
    body:
      source === "saved"
        ? `${label} from the matching saved qualifying snapshot for the ${data.season} event.`
        : `${label} from Jolpica for the ${data.season} event.`,
    sections: [
      {
        kind: "ranking",
        title: label,
        items: data.results.slice(0, 5).map((result) => ({
          rank: result.position,
          label: result.driverName,
          value: result.constructorName,
        })),
      },
    ],
    quickReplies: raceQuickReplies(race),
  };
}

async function answerStandings(
  message: string,
  dependencies: ResponderDependencies,
): Promise<ChatReply> {
  const normalized = parseQuestion(message).normalized;
  if (normalized.includes("scoring")) {
    return {
      intent: "standings",
      heading: "How F1 scoring works",
      body: "Drivers and constructors earn points from race finishing positions; sprint weekends can add sprint points too.",
      sections: [
        {
          kind: "paragraph",
          text: "A standard Grand Prix awards 25 points for first, then 18, 15, 12, 10, 8, 6, 4, 2 and 1 through tenth place.",
        },
      ],
      quickReplies: standingsQuickReplies(),
    };
  }

  let savedDrivers: DriverStandingsSnapshot | null = null;
  let savedConstructors: ConstructorStandingsSnapshot | null = null;
  try {
    savedDrivers = dependencies.getSavedDriverStandings();
  } catch {
    savedDrivers = null;
  }
  try {
    savedConstructors = dependencies.getSavedConstructorStandings();
  } catch {
    savedConstructors = null;
  }

  const season = String(dependencies.now().getUTCFullYear());
  const liveDrivers = savedDrivers?.entries.length
    ? null
    : await dependencies.getLiveDriverStandings(season);
  const liveConstructors = savedConstructors?.entries.length
    ? null
    : await dependencies.getLiveConstructorStandings(season);
  const driverEntries = savedDrivers?.entries.length
    ? savedDrivers.entries
    : liveDrivers?.live
      ? liveDrivers.data
      : [];
  const constructorEntries = savedConstructors?.entries.length
    ? savedConstructors.entries
    : liveConstructors?.live
      ? liveConstructors.data
      : [];
  if (!driverEntries.length || !constructorEntries.length) {
    return {
      intent: "standings",
      heading: "Championship standings",
      body: "The saved standings are unavailable, and the Jolpica fallback could not provide them right now.",
      sections: [],
      quickReplies: standingsQuickReplies(),
    };
  }
  const usedLive = Boolean(liveDrivers?.live || liveConstructors?.live);
  return {
    intent: "standings",
    heading: "Current championship standings",
    body: usedLive
      ? "The saved standings were unavailable, so these standings use the Jolpica fallback."
      : "Here are the top three latest saved driver and constructor standings.",
    sections: [
      {
        kind: "ranking",
        title: "Drivers",
        items: driverEntries.slice(0, 3).map((entry) => ({
          rank: entry.position,
          label: `${entry.givenName} ${entry.familyName}`,
          value: `${entry.points} points`,
        })),
      },
      {
        kind: "ranking",
        title: "Constructors",
        items: constructorEntries.slice(0, 3).map((entry) => ({
          rank: entry.position,
          label: entry.name,
          value: `${entry.points} points`,
        })),
      },
    ],
    quickReplies: standingsQuickReplies(),
    sourceUpdatedAt: usedLive ? undefined : savedDrivers?.updatedAt,
  };
}

function standingsQuickReplies(): QuickReply[] {
  return [
    quick("Full Standings", "Show the full F1 standings"),
    quick("Constructor Standings", "Show the F1 constructor standings"),
    quick("How Does F1 Scoring Work?", "How does F1 standings scoring work?"),
  ];
}

function answerDriver(message: string): ChatReply {
  const parsed = parseQuestion(message);
  const driver = parsed.searchTerm ? findDriverSnapshot(parsed.searchTerm) : null;
  if (!driver) {
    return {
      intent: "drivers",
      heading: "Driver information",
      body: "Tell me a current driver name, such as Max Verstappen or Lewis Hamilton.",
      sections: [],
      quickReplies: [quick("Career Statistics", "Show Lewis Hamilton career statistics")],
    };
  }

  const facts = [
    { label: "Nationality", value: driver.nationality },
    { label: "Team", value: driver.team.name },
    ...(driver.standing
      ? [
          { label: "Championship", value: `P${driver.standing.position}` },
          { label: "Points", value: String(driver.standing.points) },
        ]
      : []),
    ...(driver.seasonStats
      ? [
          { label: "Season wins", value: String(driver.seasonStats.wins) },
          { label: "Season podiums", value: String(driver.seasonStats.podiums) },
        ]
      : []),
    ...(driver.career
      ? [
          { label: "Career wins", value: String(driver.career.wins) },
          { label: "Career podiums", value: String(driver.career.podiums) },
          { label: "Career poles", value: String(driver.career.poles) },
        ]
      : []),
  ];
  return {
    intent: "drivers",
    heading: driver.name,
    body: `${driver.name} currently drives for ${driver.team.name}.`,
    sections: [{ kind: "facts", items: facts }],
    quickReplies: [
      quick("Compare Drivers", `Compare ${driver.name} with another F1 driver`),
      quick("Career Statistics", `Show ${driver.name} career statistics`),
      quick("Current Season Performance", `Show ${driver.name} current season performance`),
    ],
    image: driver.image ? { src: driver.image, alt: driver.name } : undefined,
  };
}

function answerTeam(message: string): ChatReply {
  const parsed = parseQuestion(message);
  const team = parsed.searchTerm ? findTeamSnapshot(parsed.searchTerm) : null;
  if (!team) {
    return {
      intent: "teams",
      heading: "Team information",
      body: "Tell me a current team name, such as Ferrari or McLaren.",
      sections: [],
      quickReplies: [quick("Season Performance", "Show Ferrari season performance")],
    };
  }

  const facts = [
    { label: "Headquarters", value: team.meta.base },
    { label: "Team principal", value: team.meta.chief },
    { label: "Chassis", value: team.meta.chassis },
    { label: "Power unit", value: team.meta.powerUnit },
    { label: "Drivers", value: team.drivers.map((driver) => driver.name).join(" · ") },
    ...(team.standing
      ? [
          { label: "Championship", value: `P${team.standing.position}` },
          { label: "Points", value: String(team.standing.points) },
          { label: "Wins", value: String(team.standing.wins) },
        ]
      : []),
  ];
  return {
    intent: "teams",
    heading: team.meta.fullName,
    body: `${team.meta.fullName} competes with ${team.meta.chassis}.`,
    sections: [{ kind: "facts", items: facts }],
    quickReplies: [
      quick("Compare Teams", `Compare ${team.meta.fullName} with another F1 team`),
      quick("Team History", `Show ${team.meta.fullName} team history`),
      quick("Season Performance", `Show ${team.meta.fullName} season performance`),
    ],
    image: team.logo ? { src: team.logo, alt: `${team.meta.fullName} logo` } : undefined,
  };
}

function predictionQuickReplies(): QuickReply[] {
  return [
    quick("Model Accuracy", "Show F1 prediction model accuracy"),
    quick("How Predictions Work", "How do F1 Buddy predictions work?"),
    quick("Qualifying Predictions", "Show the latest qualifying predictions"),
  ];
}

async function answerPrediction(
  message: string,
  dependencies: ResponderDependencies,
): Promise<ChatReply> {
  const parsed = parseQuestion(message);
  if (parsed.normalized.includes("accuracy")) {
    const metrics = getModelMetricsSnapshot();
    return {
      intent: "predictions",
      heading: "Published model accuracy",
      body: "These are the evaluation metrics already published by the prediction website.",
      sections: [
        {
          kind: "facts",
          items: [
            { label: "Top-1 accuracy", value: `${(metrics.top1Accuracy * 100).toFixed(1)}%` },
            { label: "Top-3 accuracy", value: `${(metrics.top3Accuracy * 100).toFixed(1)}%` },
            { label: "ROC AUC", value: metrics.rocAuc.toFixed(3) },
            { label: "Evaluation rows", value: metrics.testRows.toLocaleString("en-US") },
          ],
        },
      ],
      quickReplies: predictionQuickReplies(),
    };
  }
  if (parsed.normalized.includes("how") && parsed.normalized.includes("work")) {
    return {
      intent: "predictions",
      heading: "How predictions work",
      body: "F1 Buddy reads the prediction website's already-published model output; it never runs or retrains the model from chat.",
      sections: [
        {
          kind: "paragraph",
          text: "Published probabilities express model uncertainty and are not guarantees of a finishing position.",
        },
      ],
      quickReplies: predictionQuickReplies(),
    };
  }

  const prediction = await dependencies.getPublishedPrediction(
    parsed.searchTerm,
    parsed.season,
    dependencies.now(),
  );
  if (!prediction.available) {
    if (parsed.searchTerm) {
      const race = await dependencies.resolveRaceSnapshot(
        parsed.searchTerm,
        parsed.season,
      );
      if (race) {
        const session = parsed.normalized.includes("qualifying")
          ? "qualifying"
          : "results";
        const official = await dependencies.getSessionResults(
          race.season,
          race.round,
          session,
        );
        if (official.data) {
          const label =
            session === "qualifying"
              ? "Actual qualifying classification"
              : "Actual race result";
          return {
            intent: "predictions",
            heading: "Prediction unavailable",
            body: `No compatible saved prediction is available. The ${label.toLowerCase()} is shown separately and is not a replacement prediction.`,
            sections: [
              {
                kind: "ranking",
                title: label,
                items: official.data.results.slice(0, 5).map((result) => ({
                  rank: result.position,
                  label: result.driverName,
                  value: result.constructorName,
                })),
              },
              ...(session === "qualifying"
                ? [
                    {
                      kind: "paragraph" as const,
                      text: "Qualifying classification may differ from the final starting grid after penalties.",
                    },
                  ]
                : []),
            ],
            quickReplies: predictionQuickReplies(),
          };
        }
      }
    }
    return {
      intent: "predictions",
      heading: "Prediction unavailable",
      body: "No compatible saved prediction is available for that race and date. I will not substitute real results or create a new forecast.",
      sections: [],
      quickReplies: predictionQuickReplies(),
    };
  }
  const sections: ChatReply["sections"] = [];
  if (prediction.predictedQualifying.length) {
    sections.push({
      kind: "ranking",
      title: "Qualifying",
      items: prediction.predictedQualifying.slice(0, 3).map((row) => ({
        rank: row.position,
        label: row.driverName,
        value: row.position === 1 ? "Pole" : row.gap === null ? "Gap unavailable" : `+${row.gap.toFixed(3)}s`,
      })),
    });
  }
  sections.push(
    {
      kind: "ranking",
      title: "Podium probabilities",
      items: prediction.podium.slice(0, 3).map((row, index) => ({
        rank: index + 1,
        label: row.driverName,
        value: `${(row.podiumProbability * 100).toFixed(1)}%`,
      })),
    },
    {
      kind: "paragraph",
      text: "Probabilities are not guarantees; race incidents and conditions can change the result.",
    },
    { kind: "link", label: "Open the full prediction", href: prediction.predictionUrl },
  );

  return {
    intent: "predictions",
    heading: `${prediction.race.name} prediction`,
    body: `${prediction.source === "dashboard-archive" ? "Saved Streamlit dashboard archive. " : ""}${prediction.cached ? "Using the last validated cached publication. " : ""}${prediction.publishedAt ? `Published ${prediction.publishedAt}; ` : ""}generated ${prediction.generatedAt} using ${prediction.qualifyingMode === "actual" ? "post-qualifying" : "predicted qualifying"} data.`,
    sections,
    quickReplies: predictionQuickReplies(),
    sourceUpdatedAt: prediction.generatedAt,
  };
}

function unsupportedReply(): ChatReply {
  return {
    intent: "unsupported",
    heading: "I can help with F1",
    body: "I currently support race details, standings, drivers, teams, and predictions.",
    sections: [
      {
        kind: "paragraph",
        text: "Try one of the topics below, or include a race, driver, or team name in your question.",
      },
    ],
    quickReplies: [
      quick("Race details", "When is the next F1 race?"),
      quick("Standings", "Show the current F1 standings"),
      quick("Drivers", "Tell me about Max Verstappen"),
    ],
  };
}

export async function answerF1Question(
  message: string,
  dependencies: ResponderDependencies = defaultResponderDependencies,
): Promise<ChatReply> {
  const parsed = parseQuestion(message);
  switch (parsed.intent) {
    case "race":
      return answerRace(message, dependencies);
    case "standings":
      return answerStandings(message, dependencies);
    case "drivers":
      return answerDriver(message);
    case "teams":
      return answerTeam(message);
    case "predictions":
      return answerPrediction(message, dependencies);
    default:
      return unsupportedReply();
  }
}
