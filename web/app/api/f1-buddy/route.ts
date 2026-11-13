import { NextResponse } from "next/server";
import { answerF1Question } from "@/lib/chatbot/responder";

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

  try {
    const reply = await answerF1Question(message.trim());
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
