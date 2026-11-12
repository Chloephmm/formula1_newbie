import type { ChatSection } from "@/lib/chatbot/types";

function safeHref(href: string): string | null {
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  try {
    const url = new URL(href);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export default function ResponseSections({ sections }: { sections: ChatSection[] }) {
  return (
    <div className="mt-3 space-y-3">
      {sections.map((section, index) => {
        if (section.kind === "facts") {
          return (
            <dl key={index} className="space-y-1.5">
              {section.items.map((item) => (
                <div key={`${item.label}-${item.value}`} className="grid grid-cols-[6rem_1fr] gap-2 text-xs leading-5">
                  <dt className="font-nav font-bold text-[#222936]">{item.label}</dt>
                  <dd className="text-[#303744]">{item.value}</dd>
                </div>
              ))}
            </dl>
          );
        }
        if (section.kind === "ranking") {
          return (
            <section key={index} aria-label={section.title}>
              <h4 className="mb-1.5 font-nav text-xs font-bold uppercase tracking-wide text-[#222936]">
                {section.title}
              </h4>
              <ol className="space-y-1.5">
                {section.items.map((item) => (
                  <li key={`${item.rank}-${item.label}`} className="grid grid-cols-[1.5rem_1fr_auto] items-center gap-2 rounded-lg bg-black/[.055] px-2 py-1.5 text-xs">
                    <span className="font-mono font-bold text-[#E8002D]">{item.rank}</span>
                    <span className="font-nav font-semibold text-[#202631]">{item.label}</span>
                    <span className="text-right text-[#525B69]">{item.value}</span>
                  </li>
                ))}
              </ol>
            </section>
          );
        }
        if (section.kind === "paragraph") {
          return <p key={index} className="text-xs leading-5 text-[#444D5B]">{section.text}</p>;
        }
        const href = safeHref(section.href);
        return href ? (
          <a
            key={index}
            href={href}
            target={href.startsWith("https:") ? "_blank" : undefined}
            rel={href.startsWith("https:") ? "noreferrer" : undefined}
            className="inline-flex rounded-lg border border-[#E8002D] px-3 py-2 font-nav text-xs font-bold text-[#B00023] transition hover:bg-[#E8002D] hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#E8002D]"
          >
            {section.label} ↗
          </a>
        ) : null;
      })}
    </div>
  );
}
