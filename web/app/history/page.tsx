import Reveal from "@/components/Reveal";
import GlitchTitle from "@/components/GlitchTitle";

export const metadata = { title: "History — F1 Guidebook" };

const calendar = [
  "AUSTRALIA", "CHINA", "JAPAN", "BAHRAIN", "SAUDI ARABIA",
  "UNITED STATES (MIAMI)", "CANADA", "MONACO", "SPAIN (BARCELONA)", "AUSTRIA",
  "GREAT BRITAIN", "BELGIUM", "HUNGARY", "NETHERLANDS", "ITALY",
  "SPAIN (MADRID)", "AZERBAIJAN", "SINGAPORE", "UNITED STATES (AUSTIN)", "MEXICO",
  "BRAZIL", "UNITED STATES (LAS VEGAS)", "QATAR", "ABU DHABI",
];

const highlighted = new Set([
  "JAPAN", "MONACO", "GREAT BRITAIN", "ITALY", "MEXICO", "BRAZIL",
]);

export default function HistoryPage() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <Reveal direction="up">
        <GlitchTitle className="mb-14 text-center">About the Season</GlitchTitle>
      </Reveal>

      <div className="grid gap-12 md:grid-cols-2">
        {/* Calendar list */}
        <Reveal direction="left">
          <ul className="space-y-1">
            {calendar.map((c) => {
              const hl = highlighted.has(c);
              return (
                <li
                  key={c}
                  className={`w-fit px-2 py-0.5 text-base tracking-wide ${
                    hl ? "bg-yellow font-medium text-black" : "text-fg"
                  }`}
                >
                  {c}
                </li>
              );
            })}
          </ul>
        </Reveal>

        {/* Facts */}
        <Reveal direction="right" className="flex flex-col justify-center">
          <div className="relative">
            <p className="max-w-md text-lg leading-relaxed text-muted">
              A Formula 1 season usually has around{" "}
              <span className="font-script text-4xl text-accent">20-24 Races</span> held
              across different countries.
            </p>
            <p className="mt-10 max-w-md text-lg leading-relaxed text-muted">
              9 months, from March to December.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
