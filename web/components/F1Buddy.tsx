"use client";

import React, { useEffect, useRef, useState } from "react";
import { getChatbotUrl } from "../lib/chatbot";

export default function F1Buddy() {
  const [open, setOpen] = useState(false);
  const [started, setStarted] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const url = getChatbotUrl(process.env.NEXT_PUBLIC_F1BUDDY_URL, process.env.NODE_ENV === "development");

  function close() {
    setOpen(false);
    launcher.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        launcher.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <aside aria-label="F1 Buddy chatbot" className="fixed bottom-4 right-4 z-[60]">
      {started ? (
        <section
          id="f1buddy-panel"
          role="dialog"
          aria-modal="false"
          aria-labelledby="f1buddy-heading"
          hidden={!open}
          className={`absolute bottom-16 right-0 ${open ? "flex" : "hidden"} h-[min(80dvh,48rem)] max-h-[calc(100dvh-6rem)] w-[calc(100vw-2rem)] max-w-[26rem] flex-col overflow-hidden rounded-2xl border border-border bg-bg shadow-2xl`}
        >
          <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
            <h2 id="f1buddy-heading" className="font-nav font-semibold">F1 Buddy</h2>
            <button ref={closeButton} onClick={close} aria-label="Close F1 Buddy"
              className="rounded-lg px-3 py-2 text-sm hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-accent">
              Close ✕
            </button>
          </header>
          {url ? (
            <iframe src={url} title="F1 Buddy chat" className="block min-h-0 w-full flex-1 border-0 bg-bg"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
              referrerPolicy="no-referrer" />
          ) : (
            <p className="p-5 text-sm leading-relaxed text-muted">
              F1 Buddy is not connected yet. The site owner needs to deploy the chatbot-only Streamlit app,
              set NEXT_PUBLIC_F1BUDDY_URL to its public address, and rebuild this website.
            </p>
          )}
        </section>
      ) : null}
      <button ref={launcher} type="button" aria-expanded={open} aria-controls={started ? "f1buddy-panel" : undefined}
        onClick={() => { if (open) close(); else { setStarted(true); setOpen(true); } }}
        className="rounded-full border border-white/20 bg-accent px-5 py-3 font-nav text-sm font-semibold text-white shadow-lg hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">
        💬 Ask F1 Buddy
      </button>
    </aside>
  );
}
