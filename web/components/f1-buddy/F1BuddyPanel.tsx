import type { Ref } from "react";
import type { ConversationMessage } from "./chatReducer";
import ChatHeader from "./ChatHeader";
import ChatInput from "./ChatInput";
import ChatMessage from "./ChatMessage";
import TopicCards from "./TopicCards";

interface F1BuddyPanelProps {
  messages: ConversationMessage[];
  draft: string;
  pending: boolean;
  error: string | null;
  onDraftChange: (draft: string) => void;
  onSubmit: (question: string) => void;
  onQuickReply: (prompt: string) => void;
  onBack?: () => void;
  onMinimize: () => void;
  onClose: () => void;
  inputRef?: Ref<HTMLInputElement>;
  closeButtonRef?: Ref<HTMLButtonElement>;
  messagesRef?: Ref<HTMLDivElement>;
}

export default function F1BuddyPanel({
  messages,
  draft,
  pending,
  error,
  onDraftChange,
  onSubmit,
  onQuickReply,
  onBack,
  onMinimize,
  onClose,
  inputRef,
  closeButtonRef,
  messagesRef,
}: F1BuddyPanelProps) {
  const showBack = Boolean(onBack) && (messages.length > 0 || pending || Boolean(error));
  const welcome = !showBack;
  return (
    <section
      id="f1buddy-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="f1buddy-heading"
      className="absolute right-0 bottom-[5.25rem] flex h-[min(550px,calc(100dvh-7rem))] w-[min(400px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-[22px] border border-[#E8002D]/75 bg-[#0B0D12] shadow-[0_24px_80px_rgba(0,0,0,.62),0_0_28px_rgba(232,0,45,.18)]"
    >
      <ChatHeader
        showBack={showBack}
        onBack={onBack}
        onMinimize={onMinimize}
        onClose={onClose}
        closeButtonRef={closeButtonRef}
      />
      <div ref={messagesRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 [scrollbar-color:#4B5261_transparent]">
        {welcome ? (
          <div>
            <div className="mb-4 flex items-start gap-3 rounded-2xl bg-[#F4F6F8] p-4 text-[#171B24]">
              <span aria-hidden="true" className="text-xl">👋</span>
              <div>
                <h3 className="font-nav text-lg font-bold">Hello!</h3>
                <p className="mt-1 text-xs leading-5">
                  I&apos;m <strong>F1 Buddy</strong>, your Formula 1 assistant.
                </p>
                <p className="mt-1 text-xs leading-5 text-[#4A5360]">
                  Ask me about races, drivers, teams, standings, or our predictions!
                </p>
              </div>
            </div>
            <p className="mb-2.5 font-nav text-xs font-bold uppercase tracking-[0.14em] text-[#F4F6F8]">
              Try asking me about
            </p>
            <TopicCards onSubmit={onSubmit} />
          </div>
        ) : null}

        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} onQuickReply={onQuickReply} />
        ))}

        {pending ? (
          <div role="status" aria-label="F1 Buddy is typing" className="flex items-center gap-2.5">
            <span className="h-8 w-8 rounded-full border border-[#E8002D] bg-white" />
            <span className="flex gap-1 rounded-2xl rounded-tl-md bg-[#F4F6F8] px-4 py-3">
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#E8002D] motion-reduce:animate-none"
                  style={{ animationDelay: `${dot * 120}ms` }}
                />
              ))}
              <span className="sr-only">F1 Buddy is typing</span>
            </span>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="rounded-xl border border-[#E8002D]/50 bg-[#E8002D]/10 p-3 font-nav text-xs leading-5 text-[#FFD6DE]">
            {error}
          </p>
        ) : null}
        <div aria-live="polite" className="sr-only">
          {pending ? "F1 Buddy is typing" : error ?? (messages.length ? "F1 Buddy response ready" : "")}
        </div>
      </div>
      <ChatInput
        draft={draft}
        pending={pending}
        onDraftChange={onDraftChange}
        onSubmit={onSubmit}
        inputRef={inputRef}
      />
    </section>
  );
}
