"use client";

import { useEffect, useReducer, useRef } from "react";
import type { ChatReply } from "@/lib/chatbot/types";
import F1BuddyLauncher from "./f1-buddy/F1BuddyLauncher";
import F1BuddyPanel from "./f1-buddy/F1BuddyPanel";
import { chatReducer, initialChatState } from "./f1-buddy/chatReducer";

const FRIENDLY_ERROR = "F1 Buddy could not answer that right now. Please try again.";

export default function F1Buddy() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const requestVersion = useRef(0);
  const open = state.mode === "open";

  function openOrRestore() {
    dispatch({ type: state.mode === "closed" ? "OPEN" : "RESTORE" });
  }

  function minimize() {
    dispatch({ type: "MINIMIZE" });
    launcherRef.current?.focus();
  }

  function close() {
    requestVersion.current += 1;
    dispatch({ type: "CLOSE" });
    window.setTimeout(() => launcherRef.current?.focus(), 0);
  }

  function returnHome() {
    requestVersion.current += 1;
    dispatch({ type: "RETURN_HOME" });
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function submit(question: string) {
    const text = question.trim();
    if (!text || state.pending) return;

    const version = ++requestVersion.current;
    dispatch({ type: "SUBMIT", id: crypto.randomUUID(), text });
    try {
      const response = await fetch("/api/f1-buddy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!response.ok) throw new Error("request failed");
      const reply = (await response.json()) as ChatReply;
      if (version !== requestVersion.current) return;
      dispatch({ type: "SUCCEED", id: crypto.randomUUID(), reply });
    } catch {
      if (version !== requestVersion.current) return;
      dispatch({ type: "FAIL", error: FRIENDLY_ERROR });
    }
  }

  useEffect(() => {
    if (!open) return;
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 0);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth",
    });
    if (!state.pending && state.messages.length) inputRef.current?.focus();
  }, [open, state.error, state.messages, state.pending]);

  return (
    <aside aria-label="F1 Buddy chatbot" className="fixed right-3 bottom-3 z-[60] sm:right-4 sm:bottom-4">
      {open ? (
        <F1BuddyPanel
          messages={state.messages}
          draft={state.draft}
          pending={state.pending}
          error={state.error}
          onDraftChange={(draft) => dispatch({ type: "SET_DRAFT", draft })}
          onSubmit={submit}
          onQuickReply={submit}
          onBack={returnHome}
          onMinimize={minimize}
          onClose={close}
          inputRef={inputRef}
          messagesRef={messagesRef}
        />
      ) : null}
      <F1BuddyLauncher
        open={open}
        onToggle={open ? minimize : openOrRestore}
        buttonRef={launcherRef}
      />
    </aside>
  );
}
