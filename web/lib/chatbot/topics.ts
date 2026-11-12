export const CHAT_TOPICS = [
  {
    id: "race",
    title: "Race details",
    description: "Schedule, results, circuit info",
    prompt: "When is the next F1 race?",
    icon: "flag",
  },
  {
    id: "standings",
    title: "Standings",
    description: "Driver and team rankings",
    prompt: "Show the current driver standings.",
    icon: "chart",
  },
  {
    id: "drivers",
    title: "Drivers",
    description: "Stats and career information",
    prompt: "Tell me about Max Verstappen.",
    icon: "driver",
  },
  {
    id: "teams",
    title: "Teams",
    description: "Performance and lineups",
    prompt: "Tell me about Ferrari.",
    icon: "shield",
  },
  {
    id: "predictions",
    title: "Predictions",
    description: "Published qualifying and podium forecasts",
    prompt: "Show the latest F1 Buddy prediction.",
    icon: "trend",
  },
] as const;

export type ChatTopic = (typeof CHAT_TOPICS)[number];
