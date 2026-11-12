import type { QuickReply } from "@/lib/chatbot/types";

interface QuickRepliesProps {
  items: QuickReply[];
  onSelect: (prompt: string) => void;
}

export default function QuickReplies({ items, onSelect }: QuickRepliesProps) {
  if (!items.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2" aria-label="Follow-up suggestions">
      {items.map((item) => (
        <button
          key={`${item.label}-${item.prompt}`}
          type="button"
          data-prompt={item.prompt}
          onClick={() => onSelect(item.prompt)}
          className="rounded-full border border-[#4B5261] bg-[#151820] px-3 py-1.5 font-nav text-[11px] font-semibold text-[#F4F6F8] transition hover:border-[#E8002D] hover:text-white focus-visible:outline-2 focus-visible:outline-[#E8002D]"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
