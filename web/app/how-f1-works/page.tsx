import Reveal from "@/components/Reveal";
import GlitchTitle from "@/components/GlitchTitle";

export const metadata = { title: "How F1 Works — F1 Guidebook" };

const week = [
  { day: "THURSDAY", text: "Media responsibilities & driver activities", dir: "left" as const },
  { day: "FRIDAY", text: "Free Practice 1 & 2: 1-hour sessions that let drivers train on the track.", dir: "left" as const },
  { day: "SATURDAY", text: "Free Practice 3 + Qualifying: one last practice, then qualifying sets the starting grid. Fastest lap earns the front spot.", dir: "right" as const },
  { day: "SUNDAY", text: "Race day / Grand Prix: the main event, where drivers battle for points and the podium.", dir: "right" as const },
];

const points = [
  ["1st", "25 pts"], ["2nd", "18 pts"], ["3rd", "15 pts"], ["4th", "12 pts"], ["5th", "10 pts"],
  ["6th", "8 pts"], ["7th", "6 pts"], ["8th", "4 pts"], ["9th", "2 pts"], ["10th", "1 pts"],
];

const tyres = [
  { name: "SOFT", desc: "Fastest, wears out quickly", color: "#ff1e1e" },
  { name: "MEDIUM", desc: "Balanced option", color: "#ffe23d" },
  { name: "HARD", desc: "Slowest, longest lasting", color: "#ffffff" },
  { name: "INTERMEDIATE", desc: "Best for damp / wet conditions", color: "#37d35a" },
  { name: "FULL WET", desc: "Used in heavy rain", color: "#1f6fff" },
];

const flags = [
  { name: "RED FLAG", desc: "Session stopped, return to pit lane", swatch: "#ff0000" },
  { name: "GREEN FLAG", desc: "Clear track, go!", swatch: "#00c000" },
  { name: "YELLOW FLAG", desc: "Hazard ahead. Slow down", swatch: "#ffe000" },
  { name: "BLACK FLAG", desc: "Driver disqualified", swatch: "#0a0a0a" },
  { name: "BLUE FLAG", desc: "A faster car needs to overtake", swatch: "#1a1aff" },
  { name: "WHITE FLAG", desc: "Slow vehicle ahead", swatch: "#ffffff" },
  { name: "CHEQUERED FLAG", desc: "End of the race", swatch: "chequered" },
  { name: "BLACK & ORANGE FLAG", desc: "Car damage", swatch: "dot" },
];

function FlagSwatch({ kind }: { kind: string }) {
  if (kind === "chequered")
    return (
      <div
        className="h-24 w-36 shrink-0 rounded-sm"
        style={{
          backgroundImage:
            "conic-gradient(#000 90deg, #fff 90deg 180deg, #000 180deg 270deg, #fff 270deg)",
          backgroundSize: "24px 24px",
        }}
      />
    );
  if (kind === "dot")
    return (
      <div className="flex h-24 w-36 shrink-0 items-center justify-center rounded-sm bg-[#0a0a0a]">
        <span className="h-12 w-12 rounded-full bg-accent" />
      </div>
    );
  return (
    <div
      className="h-24 w-36 shrink-0 rounded-sm border border-white/10"
      style={{ backgroundColor: kind }}
    />
  );
}

export default function HowF1WorksPage() {
  return (
    <div>
      {/* TYPICAL RACE WEEK */}
      <section className="relative overflow-hidden bg-gradient-to-b from-[#1a0000] via-[#2a0606] to-black px-5 py-20">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up">
            <GlitchTitle className="mb-12 text-center">Typical Race Week</GlitchTitle>
          </Reveal>
          <div className="grid gap-x-10 gap-y-12 sm:grid-cols-2">
            {week.map((w) => (
              <Reveal key={w.day} direction={w.dir}>
                <h3 className="font-display text-4xl sm:text-5xl">{w.day}</h3>
                <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">{w.text}</p>
              </Reveal>
            ))}
          </div>
          <div className="road-line mt-16" />
        </div>
      </section>

      {/* QUALIFYING + SPRINT + RACE DAY over red streak */}
      <section
        className="relative bg-black bg-cover bg-center px-5 py-24"
        style={{ backgroundImage: "linear-gradient(to bottom, rgba(0,0,0,.55), rgba(0,0,0,.85)), url(/images/red-streak.jpg)" }}
      >
        <div className="mx-auto max-w-3xl space-y-20">
          <Reveal direction="left">
            <GlitchTitle>Qualifying</GlitchTitle>
            <p className="mt-4 text-sm leading-relaxed text-muted">Split into three stages:</p>
            <ul className="mt-2 space-y-1 text-sm text-muted">
              <li>• Q1 (18 min) — slowest 5 drivers knocked out</li>
              <li>• Q2 (15 min) — another 5 eliminated</li>
              <li>• Q3 (12 min) — decides pole position</li>
            </ul>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              The driver with the fastest lap takes pole — first on the grid. The slower your
              time, the further back you start.
            </p>
          </Reveal>

          <Reveal direction="right">
            <GlitchTitle>Sprint Races</GlitchTitle>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              A sprint is a mini race before the main Grand Prix, around 100km. It matters less
              than Sunday&rsquo;s race — fewer points to fewer drivers (1st = 8 pts, 8th = 1 pt).
              It changes the weekend: Friday has 1 practice + Sprint Qualifying; Saturday has the
              Sprint race + Sunday-race qualifying.
            </p>
          </Reveal>

          <Reveal direction="left">
            <GlitchTitle>Race Day / Grand Prix</GlitchTitle>
            <ul className="mt-4 space-y-1 text-sm text-muted">
              <li>• Laps vary per track — each race covers roughly 305 km total.</li>
              <li>• Drivers complete a formation lap to warm up their tyres.</li>
              <li>• The first 3 across the chequered flag earn a podium.</li>
              <li>• The top 10 finishers score points.</li>
              <li>• Pit stops and tyre strategy can make or break the result.</li>
            </ul>
          </Reveal>
        </div>
      </section>

      {/* CHAMPIONSHIPS */}
      <section className="px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up" className="relative inline-block">
            <h2 className="font-display text-4xl sm:text-6xl">DRIVERS&rsquo; CHAMPIONSHIP</h2>
            <span className="font-script absolute -right-8 -top-6 text-4xl text-accent sm:text-5xl">
              Best Driver
            </span>
          </Reveal>
          <ul className="mt-6 max-w-2xl space-y-1 text-sm text-muted">
            <li>• The title awarded to the driver who scores the most points during the season.</li>
            <li>• This award changes the winner&rsquo;s number to 1 for the following year.</li>
          </ul>

          <Reveal direction="up" className="relative mt-16 inline-block">
            <h2 className="font-display text-4xl sm:text-6xl">CONSTRUCTORS&rsquo; CHAMPIONSHIP</h2>
            <span className="font-script absolute -right-6 -top-6 text-4xl text-accent sm:text-5xl">
              Best Team
            </span>
          </Reveal>
          <ul className="mt-6 max-w-3xl space-y-1 text-sm text-muted">
            <li>• Team championship — the title awarded to the team scoring the most points.</li>
            <li>• Both drivers&rsquo; points are combined to decide it.</li>
            <li>• A team can win the constructors&rsquo; even if its driver doesn&rsquo;t win the drivers&rsquo;.</li>
          </ul>

          {/* points table */}
          <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {points.map(([pos, pts]) => (
              <div
                key={pos}
                className="flex items-center justify-between rounded-md border border-accent/70 px-4 py-3"
              >
                <span className="font-display text-lg">{pos}</span>
                <span className="text-sm text-muted">{pts}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TYRES */}
      <section className="px-5 py-20">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up">
            <GlitchTitle className="mb-12">Tyres</GlitchTitle>
          </Reveal>
          <div className="space-y-6">
            {tyres.map((t, i) => (
              <Reveal key={t.name} direction="left" delay={i * 0.04}>
                <div className="flex items-center gap-6">
                  <span
                    className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-[6px] bg-neutral-900"
                    style={{ borderColor: t.color }}
                  >
                    <span className="h-6 w-6 rounded-full bg-neutral-700" />
                  </span>
                  <div>
                    <h3 className="font-display text-2xl sm:text-3xl">{t.name}</h3>
                    <p className="text-sm text-muted">{t.desc}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
          <p className="mt-10 max-w-md text-sm text-muted">
            Only 3 dry compounds (Soft, Medium, Hard) are picked per weekend — and rain can turn
            the race into complete chaos!
          </p>
        </div>
      </section>

      {/* FLAGS */}
      <section className="bg-gradient-to-r from-yellow via-[#ff8a00] to-[#ff3b00] px-5 py-20 text-black">
        <div className="mx-auto grid max-w-6xl gap-x-12 gap-y-10 sm:grid-cols-2">
          {flags.map((f) => (
            <Reveal key={f.name} direction="up">
              <div className="flex items-center gap-6">
                <FlagSwatch kind={f.swatch} />
                <div>
                  <h3 className="font-display text-2xl sm:text-3xl">{f.name}</h3>
                  <p className="text-sm opacity-80">{f.desc}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  );
}
