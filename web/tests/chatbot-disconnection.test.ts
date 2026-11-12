import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const repoRoot = fileURLToPath(new URL("../../", import.meta.url));

function read(relativePath: string): string {
  return readFileSync(resolve(repoRoot, relativePath), "utf8");
}

test("the prediction dashboard has no F1 Buddy Python hook", () => {
  const streamlitApp = read("streamlit_app/app.py");

  assert.doesNotMatch(streamlitApp, /f1buddy_ai|render_chatbot/);
});

test("the prediction dashboard has no chatbot wheel dependency", () => {
  const requirements = read("streamlit_app/requirements.txt");

  assert.doesNotMatch(requirements, /f1buddy_ai|chatbot_app/);
});

test("the standalone Streamlit chatbot copy is removed", () => {
  assert.equal(existsSync(resolve(repoRoot, "chatbot_app")), false);
});

test("gitignore has no chatbot wheel exception", () => {
  const gitignore = read(".gitignore");

  assert.doesNotMatch(gitignore, /f1buddy_ai.*\.whl/);
});
