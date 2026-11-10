import { CHAT_TOPICS } from "@/lib/chatbot/topics";

interface TopicCardsProps {
  onSubmit: (prompt: string) => void;
}

function TopicIcon({ icon }: { icon: (typeof CHAT_TOPICS)[number]["icon"] }) {
  const symbols = {
    flag: "🏁",
    chart: "▥",
    driver: "◉",
    shield: "⬡",
    trend: "↗",
  } as const;
  return (
    <span aria-hidden="true" className="text-xl font-bold text-[#E8002D]">
      {symbols[icon]}
    </span>
  );
}

export default function TopicCards({ onSubmit }: TopicCardsProps) {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {CHAT_TOPICS.map((topic) => (
        <button
          key={topic.id}
          type="button"
          data-topic-card={topic.id}
          onClick={() => onSubmit(topic.prompt)}
          className={`group/card flex min-h-20 items-center gap-3 rounded-xl border border-[#343945] bg-[#151820] px-3 py-3 text-left transition hover:-translate-y-0.5 hover:border-[#E8002D]/75 hover:bg-[#1A1E27] focus-visible:outline-2 focus-visible:outline-[#E8002D] motion-reduce:transform-none ${topic.id === "predictions" ? "col-span-2" : ""}`}
        >
          <TopicIcon icon={topic.icon} />
          <span className="min-w-0 flex-1">
            <span className="block font-nav text-sm font-bold text-[#F4F6F8]">{topic.title}</span>
            <span className="mt-0.5 block text-[10px] leading-4 text-[#A6ADB8]">
              {topic.description}
            </span>
          </span>
          <span aria-hidden="true" className="text-lg text-[#E8002D] transition-transform group-hover/card:translate-x-0.5 motion-reduce:transform-none">
            ›
          </span>
        </button>
      ))}
    </div>
  );
}
