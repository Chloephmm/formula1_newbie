import assert from "node:assert/strict";
import test from "node:test";
import { getChatbotUrl } from "../lib/chatbot";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import F1Buddy from "../components/F1Buddy";
import { readFileSync } from "node:fs";

test("missing and malformed URLs never embed", () => {
  for (const value of [undefined, "", "  ", "not a url", "javascript:alert(1)", "//example.streamlit.app"]) {
    assert.equal(getChatbotUrl(value, false), null);
  }
});

test("public Streamlit URLs use embed mode and preserve options", () => {
  assert.equal(getChatbotUrl("https://f1-example.streamlit.app/?embed=false&embed_options=dark_theme", false),
    "https://f1-example.streamlit.app/?embed=true&embed_options=dark_theme");
});

test("rejects credentials, untrusted hosts, ports and insecure production embeds", () => {
  for (const value of ["https://user:pass@demo.streamlit.app", "https://evil.com", "https://demo.streamlit.app.evil.com",
    "https://streamlit.app", "http://demo.streamlit.app", "https://demo.streamlit.app:444", "https://a.b.streamlit.app"]) {
    assert.equal(getChatbotUrl(value, false), null);
  }
});

test("loopback HTTP embeds are development-only", () => {
  for (const host of ["localhost", "127.0.0.1"]) {
    assert.equal(getChatbotUrl(`http://${host}:8519`, true), `http://${host}:8519/?embed=true`);
    assert.equal(getChatbotUrl(`http://${host}:8519`, false), null);
  }
  assert.equal(getChatbotUrl("http://192.168.1.2:8501", true), null);
});

test("launcher initially renders closed and never loads an iframe eagerly", () => {
  const previous = process.env.NEXT_PUBLIC_F1BUDDY_URL;
  try {
    process.env.NEXT_PUBLIC_F1BUDDY_URL = "https://demo.streamlit.app";
    const html = renderToStaticMarkup(createElement(F1Buddy));
    assert.match(html, /Ask F1 Buddy/);
    assert.match(html, /aria-expanded="false"/);
    assert.doesNotMatch(html, /<iframe/);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_F1BUDDY_URL;
    else process.env.NEXT_PUBLIC_F1BUDDY_URL = previous;
  }
});

test("website panel omits the saved-output and wake-up notice", () => {
  const source = readFileSync(new URL("../components/F1Buddy.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /Saved outputs, not live model runs/);
  assert.doesNotMatch(source, /open chatbot in a new tab/);
});
