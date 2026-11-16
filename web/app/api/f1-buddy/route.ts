import { NextResponse } from "next/server";
import { answerF1Question } from "@/lib/chatbot/responder";
import type { PredictionContext } from "@/lib/chatbot/types";

const BAD_REQUEST = "Please ask a Formula 1 question using 500 characters or fewer.";
export const runtime = "nodejs";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: BAD_REQUEST }, { status: 400 });
  }

  const message =
    typeof body === "object" && body !== null && "message" in body
      ? (body as { message?: unknown }).message
      : undefined;
  if (typeof message !== "string" || !message.trim() || message.trim().length > 500) {
    return NextResponse.json({ error: BAD_REQUEST }, { status: 400 });
  }

  const rawContext = typeof body === "object" && body !== null && "context" in body
    ? (body as { context?: unknown }).context
    : undefined;
  let context: PredictionContext | undefined;
  if (typeof rawContext === "object" && rawContext !== null && !Array.isArray(rawContext)) {
    const candidate = rawContext as Record<string, unknown>;
    if (typeof candidate.raceName === "string" && candidate.raceName.length > 0 &&
        candidate.raceName.length <= 100 && Number.isInteger(candidate.season) &&
        Number(candidate.season) >= 1950 && Number(candidate.season) <= 2100) {
      context = { raceName: candidate.raceName, season: Number(candidate.season) };
    }
  }

  try {
    const reply = await answerF1Question(message.trim(), undefined, context);
    return NextResponse.json(reply, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "F1 Buddy could not answer that right now. Please try again." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
