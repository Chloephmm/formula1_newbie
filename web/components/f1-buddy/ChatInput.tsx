import type { FormEvent, Ref } from "react";

interface ChatInputProps {
  draft: string;
  pending: boolean;
  onDraftChange: (draft: string) => void;
  onSubmit: (question: string) => void;
  inputRef?: Ref<HTMLInputElement>;
}

export default function ChatInput({
  draft,
  pending,
  onDraftChange,
  onSubmit,
  inputRef,
}: ChatInputProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || pending) return;
    onSubmit(question);
  }

  return (
    <form onSubmit={submit} className="flex shrink-0 gap-2 border-t border-[#343945] bg-[#0B0D12] p-3">
      <label htmlFor="f1buddy-input" className="sr-only">
        Ask a question about Formula 1
      </label>
      <input
        ref={inputRef}
        id="f1buddy-input"
        value={draft}
        maxLength={500}
        disabled={pending}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="Ask a question about Formula 1..."
        className="min-w-0 flex-1 rounded-xl border border-[#4B5261] bg-[#151820] px-3.5 py-3 font-nav text-sm text-white placeholder:text-[#777F8D] focus:border-[#E8002D] focus:outline-none disabled:opacity-60"
      />
      <button
        type="submit"
        aria-label="Send message"
        disabled={pending || !draft.trim()}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#E8002D] text-lg text-white shadow-lg shadow-[#E8002D]/20 transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:opacity-45"
      >
        <span aria-hidden="true">➤</span>
      </button>
    </form>
  );
}
