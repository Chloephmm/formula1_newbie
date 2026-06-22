import type { ReactNode } from "react";
import Reveal from "@/components/Reveal";
import GlitchTitle from "@/components/GlitchTitle";

export const metadata = { title: "History — F1 Guidebook" };

const calendar: { name: string; flag: string; hl?: boolean }[] = [
  { name: "AUSTRALIA", flag: "🇦🇺" },
  { name: "CHINA", flag: "🇨🇳" },
  { name: "JAPAN", flag: "🇯🇵", hl: true },
  { name: "BAHRAIN", flag: "🇧🇭" },
  { name: "SAUDI ARABIA", flag: "🇸🇦" },
  { name: "UNITED STATES (MIAMI)", flag: "🇺🇸" },
  { name: "CANADA", flag: "🇨🇦" },
  { name: "MONACO", flag: "🇲🇨", hl: true },
  { name: "SPAIN (BARCELONA)", flag: "🇪🇸" },
  { name: "AUSTRIA", flag: "🇦🇹" },
  { name: "GREAT BRITAIN", flag: "🇬🇧", hl: true },
  { name: "BELGIUM", flag: "🇧🇪" },
  { name: "HUNGARY", flag: "🇭🇺" },
  { name: "NETHERLANDS", flag: "🇳🇱" },
  { name: "ITALY", flag: "🇮🇹", hl: true },
  { name: "SPAIN (MADRID)", flag: "🇪🇸" },
  { name: "AZERBAIJAN", flag: "🇦🇿" },
  { name: "SINGAPORE", flag: "🇸🇬" },
  { name: "UNITED STATES (AUSTIN)", flag: "🇺🇸" },
  { name: "MEXICO", flag: "🇲🇽", hl: true },
  { name: "BRAZIL", flag: "🇧🇷", hl: true },
  { name: "UNITED STATES (LAS VEGAS)", flag: "🇺🇸" },
  { name: "QATAR", flag: "🇶🇦" },
  { name: "ABU DHABI", flag: "🇦🇪" },
];

// ---- Winding road timeline ----
const RW = 1608;
const RH = 900;
const ry = (x: number) => 470 + 105 * Math.sin((x / RW) * Math.PI * 2.4 - 0.5);
const roadPath = Array.from({ length: 161 }, (_, i) => {
  const x = (i / 160) * RW;
  return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${ry(x).toFixed(1)}`;
}).join(" ");

function Em({ children }: { children: ReactNode }) {
  return (
    <span className="underline decoration-yellow decoration-2 underline-offset-2">
      {children}
    </span>
  );
}

type Milestone = {
  year: string;
  dot: [number, number];
  year_at: [number, number];
  text_at: [number, number];
  text_w: number;
  node: ReactNode;
};

const M: Milestone[] = [
  {
    year: "1950",
    dot: [46, 255],
    year_at: [4, 200],
    text_at: [105, 178],
    text_w: 480,
    node: (
      <>
        THE <Em>FIRST</Em> FIA WORLD CHAMPIONSHIP IS HELD OVER SEVEN RACES, WITH
        NINO FARINA WINNING THE OPENER AT SILVERSTONE TO BECOME THE FIRST
        CHAMPION.
      </>
    ),
  },
  {
    year: "1994",
    dot: [670, 255],
    year_at: [632, 200],
    text_at: [735, 180],
    text_w: 380,
    node: (
      <>
        IMOLA BECOMES THE CATALYST FOR A SAFETY REVOLUTION THAT RESHAPED THE
        SPORT, DRIVING MAJOR REFORMS THAT PUT <Em>DRIVER SAFETY FIRST</Em> AND
        CONTINUE TO ADVANCE F1 TODAY.
      </>
    ),
  },
  {
    year: "2019",
    dot: [1220, 232],
    year_at: [1160, 180],
    text_at: [1272, 146],
    text_w: 330,
    node: (
      <>
        <Em>NETFLIX</Em>&rsquo;S DRIVE TO SURVIVE PREMIERES, BRINGING MILLIONS OF
        NEW FANS TO F1 THROUGH BEHIND THE SCENES ACCESS AND FUELING ITS MODERN
        POPULARITY BOOM.
      </>
    ),
  },
  {
    year: "1958",
    dot: [185, 620],
    year_at: [148, 672],
    text_at: [22, 710],
    text_w: 380,
    node: (
      <>
        THE FIRST CONSTRUCTORS&rsquo; CHAMPIONSHIP IS AWARDED, WON BY{" "}
        <Em>VANWALL</Em>, CREATING F1&rsquo;S TEAM COMPETITION.
      </>
    ),
  },
  {
    year: "1959",
    dot: [520, 690],
    year_at: [470, 740],
    text_at: [574, 720],
    text_w: 320,
    node: (
      <>
        COOPER&rsquo;S REAR MID ENGINE LAYOUT TAKES OVER AND COMES TO DOMINATE
        F1, MAKING FRONT ENGINED CARS OBSOLETE.
      </>
    ),
  },
  {
    year: "2014",
    dot: [1045, 624],
    year_at: [1000, 678],
    text_at: [1002, 720],
    text_w: 400,
    node: (
      <>
        THE <Em>HYBRID</Em> POWER UNIT ERA BEGINS, LAUNCHING MERCEDES&rsquo;
        RECORD EIGHT STRAIGHT CONSTRUCTORS&rsquo; TITLES.
      </>
    ),
  },
];

const px = (v: number, total: number) => `${(v / total) * 100}%`;

export default function HistoryPage() {
  return (
    <div>
      {/* ABOUT THE SEASON */}
      <section className="mx-auto max-w-6xl px-5 py-16">
        <Reveal direction="up">
          <GlitchTitle className="mb-14 text-center">About the Season</GlitchTitle>
        </Reveal>

        <div className="grid gap-12 md:grid-cols-2">
          <Reveal direction="left">
            <ul className="space-y-1.5">
              {calendar.map((c) => (
                <li key={c.name} className="flex items-center gap-3 text-base tracking-wide">
                  <span className="w-6 shrink-0 text-center text-lg">{c.flag}</span>
                  <span
                    className={
                      c.hl
                        ? "inline-block w-60 rounded-sm bg-yellow px-2 py-0.5 font-medium text-black"
                        : "py-0.5 text-fg"
                    }
                  >
                    {c.name}
                  </span>
                </li>
              ))}
            </ul>
          </Reveal>

          <Reveal direction="right" className="flex flex-col justify-center">
            <p className="max-w-md text-lg leading-relaxed text-white">
              A Formula 1 season usually has around{" "}
              <span className="font-script text-4xl text-accent">20-24 Races</span> held
              across different countries.
            </p>
            <p className="mt-10 max-w-md text-lg leading-relaxed text-white">
              9 months, from March to December.
            </p>
          </Reveal>
        </div>
      </section>

      {/* THE HISTORY — winding road timeline */}
      <section className="px-4 py-16">
        <Reveal direction="up">
          <div className="flex justify-center">
            <GlitchTitle className="mb-2 text-center">The History</GlitchTitle>
          </div>
        </Reveal>

        {/* Desktop: winding road (strict layout) */}
        <div
          className="relative mx-auto hidden w-full max-w-[1608px] lg:block"
          style={{ aspectRatio: `${RW} / ${RH}` }}
        >
          <svg viewBox={`0 0 ${RW} ${RH}`} className="absolute inset-0 h-full w-full">
            {/* road edge + surface */}
            <path d={roadPath} fill="none" stroke="#55555a" strokeWidth={86} strokeLinecap="round" />
            <path d={roadPath} fill="none" stroke="#333338" strokeWidth={78} strokeLinecap="round" />
            {/* dashed centre line */}
            <path d={roadPath} fill="none" stroke="#ffffff" strokeWidth={5} strokeDasharray="30 32" strokeLinecap="round" />
            {/* stems + pins */}
            {M.map((m) => (
              <g key={m.year}>
                <line
                  x1={m.dot[0]}
                  y1={m.dot[1]}
                  x2={m.dot[0]}
                  y2={ry(m.dot[0])}
                  stroke="#ffffff"
                  strokeOpacity={0.55}
                  strokeWidth={2}
                />
                <circle cx={m.dot[0]} cy={m.dot[1]} r={13} fill="var(--accent)" stroke="#000" strokeWidth={3} />
              </g>
            ))}
          </svg>

          {/* Year + text overlays */}
          {M.map((m) => (
            <div key={m.year}>
              <span
                className="font-script absolute text-4xl leading-none text-accent"
                style={{ left: px(m.year_at[0], RW), top: px(m.year_at[1], RH) }}
              >
                {m.year}
              </span>
              <p
                className="absolute font-mono text-[13px] uppercase leading-relaxed text-white"
                style={{
                  left: px(m.text_at[0], RW),
                  top: px(m.text_at[1], RH),
                  width: px(m.text_w, RW),
                }}
              >
                {m.node}
              </p>
            </div>
          ))}
        </div>

        {/* Mobile / tablet: vertical timeline */}
        <ol className="relative mx-auto max-w-md space-y-8 border-l-2 border-white/20 pl-6 lg:hidden">
          {M.slice()
            .sort((a, b) => Number(a.year) - Number(b.year))
            .map((m) => (
              <li key={m.year} className="relative">
                <span className="absolute -left-[31px] top-1.5 h-4 w-4 rounded-full border-2 border-black bg-accent" />
                <span className="font-script text-3xl text-accent">{m.year}</span>
                <p className="mt-1 font-mono text-xs uppercase leading-relaxed text-white">{m.node}</p>
              </li>
            ))}
        </ol>
      </section>
    </div>
  );
}
