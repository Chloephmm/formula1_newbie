export type ChatIntent =
  | "race"
  | "standings"
  | "drivers"
  | "teams"
  | "predictions"
  | "unsupported";

export type ResultKind = "schedule" | "race" | "qualifying";
export type PredictionAspect = "summary" | "qualifying" | "podium" | "driver" | "updated" | "winner";
export interface PredictionContext {
  raceName: string;
  season: number;
}

export type ChatSection =
  | { kind: "facts"; items: Array<{ label: string; value: string }> }
  | {
      kind: "ranking";
      title: string;
      items: Array<{
        rank: number;
        label: string;
        value: string;
        image?: string;
      }>;
    }
  | { kind: "paragraph"; text: string }
  | { kind: "link"; label: string; href: string };

export interface QuickReply {
  label: string;
  prompt: string;
}

export interface ChatReply {
  intent: ChatIntent;
  heading: string;
  body: string;
  sections: ChatSection[];
  quickReplies: QuickReply[];
  sourceUpdatedAt?: string;
  image?: { src: string; alt: string };
  context?: PredictionContext;
}

export interface ChatRequest {
  message: string;
  context?: PredictionContext;
}

export interface ParsedQuestion {
  intent: ChatIntent;
  normalized: string;
  season?: number;
  searchTerm?: string;
  resultKind?: ResultKind;
  standingKind?: "drivers" | "constructors";
  predictionAspect?: PredictionAspect;
  predictionDriverId?: string;
}
