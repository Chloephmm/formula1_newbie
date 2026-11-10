import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ChatHeader from "../components/f1-buddy/ChatHeader";
import ChatInput from "../components/f1-buddy/ChatInput";
import ChatMessage from "../components/f1-buddy/ChatMessage";
import F1BuddyLauncher from "../components/f1-buddy/F1BuddyLauncher";
import F1BuddyPanel from "../components/f1-buddy/F1BuddyPanel";
import QuickReplies from "../components/f1-buddy/QuickReplies";
import TopicCards from "../components/f1-buddy/TopicCards";
import type { ChatReply } from "../lib/chatbot/types";

const noop = () => undefined;

test("launcher renders the approved car control and full tooltip", () => {
  const html = renderToStaticMarkup(
    createElement(F1BuddyLauncher, { open: false, onToggle: noop }),
  );

  assert.match(html, /f1-buddy-car\.jpg/);
  assert.match(html, /Red Formula 1 car/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-controls="f1buddy-panel"/);
  assert.match(html, /Hello, F1 fan!/);
  assert.match(html, /Need help with Formula 1\?/);
  assert.match(html, /Currently English only\./);
});

test("header exposes title, beta status, minimize, and close controls", () => {
  const html = renderToStaticMarkup(
    createElement(ChatHeader, { onMinimize: noop, onClose: noop }),
  );

  assert.match(html, />F1 Buddy</);
  assert.match(html, />Beta</);
  assert.match(html, /aria-label="Minimize F1 Buddy"/);
  assert.match(html, /aria-label="Close F1 Buddy"/);
});

test("welcome contains exactly five approved topic cards", () => {
  const html = renderToStaticMarkup(createElement(TopicCards, { onSubmit: noop }));

  assert.equal((html.match(/data-topic-card=/g) ?? []).length, 5);
  for (const label of ["Race details", "Standings", "Drivers", "Teams", "Predictions"]) {
    assert.match(html, new RegExp(`>${label}<`));
  }
  assert.doesNotMatch(html, /F1 basics/i);
});

test("input has the approved placeholder, limit, and send label", () => {
  const html = renderToStaticMarkup(
    createElement(ChatInput, {
      draft: "",
      pending: false,
      onDraftChange: noop,
      onSubmit: noop,
    }),
  );

  assert.match(html, /placeholder="Ask a question about Formula 1\.\.\."/);
  assert.match(html, /maxLength="500"/);
  assert.match(html, /aria-label="Send message"/);
});

test("assistant messages render structured content without raw HTML", () => {
  const reply: ChatReply = {
    intent: "race",
    heading: "Miami Grand Prix",
    body: "Race details",
    sections: [
      { kind: "facts", items: [{ label: "Circuit", value: "Miami International Autodrome" }] },
      {
        kind: "ranking",
        title: "Result",
        items: [{ rank: 1, label: "Driver", value: "Team" }],
      },
      { kind: "paragraph", text: "Published information." },
      { kind: "link", label: "View race", href: "/races" },
    ],
    quickReplies: [],
  };
  const html = renderToStaticMarkup(
    createElement(ChatMessage, {
      message: { id: "assistant-1", role: "assistant", reply },
      onQuickReply: noop,
    }),
  );

  assert.match(html, /Miami International Autodrome/);
  assert.match(html, /Published information\./);
  assert.match(html, /href="\/races"/);
  const source = readFileSync(
    new URL("../components/f1-buddy/ResponseSections.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/);
});

test("pending panel exposes an accessible typing indicator", () => {
  const html = renderToStaticMarkup(
    createElement(F1BuddyPanel, {
      messages: [],
      draft: "",
      pending: true,
      error: null,
      onDraftChange: noop,
      onSubmit: noop,
      onQuickReply: noop,
      onMinimize: noop,
      onClose: noop,
    }),
  );

  assert.match(html, /role="status"/);
  assert.match(html, /F1 Buddy is typing/);
});

test("quick reply buttons expose labels and submit their complete prompts", () => {
  const html = renderToStaticMarkup(
    createElement(QuickReplies, {
      items: [{ label: "Circuit Details", prompt: "Miami 2026 circuit details" }],
      onSelect: noop,
    }),
  );

  assert.match(html, />Circuit Details</);
  assert.match(html, /data-prompt="Miami 2026 circuit details"/);
  assert.match(html, /<button/);
});
