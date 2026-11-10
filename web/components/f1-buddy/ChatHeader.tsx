import type { Ref } from "react";

interface ChatHeaderProps {
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: Ref<HTMLButtonElement>;
}

export default function ChatHeader({
  onMinimize,
  onClose,
  closeButtonRef,
}: ChatHeaderProps) {
  return (
    <header className="flex shrink-0 items-center justify-between border-b border-[#343945] bg-[linear-gradient(180deg,#10131A_0%,#0B0D12_100%)] px-4 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <span aria-hidden="true" className="font-display text-lg font-black italic text-[#E8002D]">
          F1
        </span>
        <span className="h-6 w-px bg-[#343945]" />
        <h2 id="f1buddy-heading" className="truncate font-nav text-lg font-bold italic text-white">
          F1 Buddy
        </h2>
        <span className="rounded-full border border-white/15 bg-white/10 px-2 py-0.5 font-nav text-[10px] font-semibold text-[#F4F6F8]">
          Beta
        </span>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-label="Minimize F1 Buddy"
          onClick={onMinimize}
          className="grid h-9 w-9 place-items-center rounded-lg text-xl text-[#F4F6F8] transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-[#E8002D]"
        >
          <span aria-hidden="true">−</span>
        </button>
        <button
          ref={closeButtonRef}
          type="button"
          aria-label="Close F1 Buddy"
          onClick={onClose}
          className="grid h-9 w-9 place-items-center rounded-lg text-xl text-[#F4F6F8] transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-[#E8002D]"
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </header>
  );
}
