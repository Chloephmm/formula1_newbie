import Reveal from "@/components/Reveal";
import GlitchTitle from "@/components/GlitchTitle";

export const metadata = { title: "How F1 Works — F1 Guidebook" };

const points = [
  ["1st", "25 pts"], ["2nd", "18 pts"], ["3rd", "15 pts"], ["4th", "12 pts"], ["5th", "10 pts"],
  ["6th", "8 pts"], ["7th", "6 pts"], ["8th", "4 pts"], ["9th", "2 pts"], ["10th", "1 pts"],
];

const tyres = [
  { name: "SOFT", desc: "Fastest, wear out quickly", img: "/images/assets/tires/soft.jpg" },
  { name: "MEDIUM", desc: "Balanced option", img: "/images/assets/tires/medium.jpg" },
  { name: "HARD", desc: "Slowest, longest lasting", img: "/images/assets/tires/hard.jpg" },
  { name: "INTERMEDIATE", desc: "Best for damp / wet conditions", img: "/images/assets/tires/intermediate.jpg" },
  { name: "FULL WET", desc: "Used in heavy rain", img: "/images/assets/tires/wet.jpg" },
];

const flags = [
  { name: "GREEN FLAG", desc: "Clear track, go!", swatch: "#00c000" },
  { name: "RED FLAG", desc: "Session stopped, return to pit lane", swatch: "#ff0000" },
  { name: "YELLOW FLAG", desc: "Hazard ahead. Slow down", swatch: "#ffe000" },
  { name: "BLACK FLAG", desc: "Driver disqualified", swatch: "#0a0a0a" },
  { name: "BLUE FLAG", desc: "A faster car needs to overtake", swatch: "#1a1aff" },
  { name: "WHITE FLAG", desc: "Slow vehicle ahead", swatch: "#ffffff" },
  { name: "CHEQUERED FLAG", desc: "End of the race", swatch: "chequered" },
  { name: "BLACK & ORANGE FLAG", desc: "Car damage", swatch: "dot" },
];

function Day({ day, text, indent }: { day: string; text: string; indent?: boolean }) {
  return (
    <div className={indent ? "sm:pl-[18%]" : ""}>
      <h3 className="font-display text-2xl sm:text-3xl">{day}</h3>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-white">{text}</p>
    </div>
  );
}

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
  const redStreak = "/images/red-streak.jpg";

  return (
    <div>
      {/* RACE WEEK + SESSIONS — one continuous red-streak background */}
      <section
        className="bg-black bg-no-repeat"
        style={{ backgroundImage: `url(${redStreak})`, backgroundSize: "100% 100%" }}
      >
        <div className="mx-auto max-w-6xl px-5 py-20">
          <Reveal direction="up">
            <GlitchTitle className="mb-14 text-center">Typical Race Week</GlitchTitle>
          </Reveal>

          {/* Thursday + Saturday */}
          <div className="grid gap-x-10 gap-y-12 sm:grid-cols-2">
            <Reveal direction="left"><Day day="THURSDAY" text="Media responsibilities & driver activities" /></Reveal>
            <Reveal direction="right"><Day day="SATURDAY" text="Free Practice 3 + Qualifying: one last practice, then qualifying sets the starting grid. Fastest lap earns the front spot." /></Reveal>
          </div>

          {/* Animated road */}
          <div className="road-line my-14" />

          {/* Friday + Sunday (staggered right) */}
          <div className="grid gap-x-10 gap-y-12 sm:grid-cols-2">
            <Reveal direction="left"><Day day="FRIDAY" text="Free Practice 1 & 2: 1-hour sessions that allow drivers to train on the track." indent /></Reveal>
            <Reveal direction="right"><Day day="SUNDAY" text="Race Day / Grand Prix: the main event, where drivers battle for points and the podium." indent /></Reveal>
          </div>
        </div>

        {/* QUALIFYING / SPRINT / RACE DAY — continues on the same streak */}
        <div className="mx-auto grid max-w-6xl gap-x-12 gap-y-16 px-5 py-24 sm:grid-cols-2">
          {/* Left column: Qualifying (top) + Sprint Races (bottom) */}
          <div className="flex flex-col gap-24">
            <Reveal direction="left">
              <GlitchTitle>Qualifying</GlitchTitle>
              <p className="mt-4 text-sm leading-relaxed text-white">Split into three stages:</p>
              <ul className="mt-2 space-y-1 text-sm text-white">
                <li>• Q1 (18 min) — slowest 5 drivers knocked out</li>
                <li>• Q2 (15 min) — another 5 eliminated</li>
                <li>• Q3 (12 min) — decides pole position</li>
              </ul>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-white">
                The driver with the fastest lap takes pole — first on the grid. The slower your
                time, the further back you start.
              </p>
            </Reveal>

            <Reveal direction="left">
              <GlitchTitle>Sprint Races</GlitchTitle>
              <ul className="mt-4 space-y-1 text-sm text-white">
                <li>• A sprint is a mini race before the main Grand Prix, around 100km.</li>
                <li>• It matters less than Sunday&rsquo;s race — fewer points to fewer drivers (1ˢᵗ = 8 pts, 8ᵗʰ = 1 pt).</li>
                <li>
                  • It changes the weekend schedule:
                  <ul className="mt-1 space-y-1 pl-5">
                    <li>○ Friday: 1 practice + Sprint Qualifying</li>
                    <li>○ Saturday: Sprint race + Sunday-race qualifying</li>
                  </ul>
                </li>
              </ul>
            </Reveal>
          </div>

          {/* Right column: Race Day, vertically centered */}
          <div className="flex sm:items-center">
            <Reveal direction="right">
              <GlitchTitle>Race Day / Grand Prix</GlitchTitle>
              <ul className="mt-4 space-y-1 text-sm text-white">
                <li>• The number of laps changes per track — each race covers roughly 305 km total.</li>
                <li>• Drivers complete a formation lap beforehand to warm up their tyres.</li>
                <li>• The first 3 across the chequered flag earn a podium.</li>
                <li>• The top 10 finishers score points.</li>
                <li>• Pit stops and tyre strategy can make or break the result.</li>
              </ul>
            </Reveal>
          </div>
        </div>
      </section>

      {/* THE CHAMPIONSHIPS — black */}
      <section className="px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up">
            <GlitchTitle className="mb-16 text-center">The Championships</GlitchTitle>
          </Reveal>

          <Reveal direction="up">
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <h2 className="font-display text-3xl uppercase sm:text-5xl">Drivers&rsquo; Championship</h2>
              <span className="font-script text-3xl text-accent sm:text-4xl">Best Driver</span>
            </div>
            <ul className="mt-5 max-w-2xl space-y-1 text-sm text-white">
              <li>• The title awarded to the driver who scores the most points during the season.</li>
              <li>• This award changes the winner&rsquo;s number to 1 for the following year.</li>
            </ul>
          </Reveal>

          <Reveal direction="up" className="mt-16 sm:pl-[8%]">
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <h2 className="font-display text-3xl uppercase sm:text-5xl">Constructors&rsquo; Championship</h2>
              <span className="font-script text-3xl text-accent sm:text-4xl">Best Team</span>
            </div>
            <ul className="mt-5 max-w-3xl space-y-1 text-sm text-white">
              <li>• Team championship — the title awarded to the team scoring the most points.</li>
              <li>• Both drivers&rsquo; points are combined to decide it.</li>
              <li>• A team can win the constructors&rsquo; even if its driver doesn&rsquo;t win the drivers&rsquo;.</li>
            </ul>
          </Reveal>

          {/* points table */}
          <div className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {points.map(([pos, pts]) => (
              <div
                key={pos}
                className="flex items-center justify-between rounded-md border border-accent/70 px-4 py-3"
              >
                <span className="font-display text-lg">{pos}</span>
                <span className="text-sm text-white">{pts}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TIRES — black, two columns */}
      <section className="px-5 py-20">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up">
            <GlitchTitle className="mb-12 sm:pl-[14%]">Tires</GlitchTitle>
          </Reveal>

          <div className="grid gap-x-12 gap-y-12 sm:grid-cols-2">
            {/* Left: tyre list */}
            <div className="space-y-6">
              {tyres.map((t, i) => (
                <Reveal key={t.name} direction="left" delay={i * 0.04}>
                  <div className="flex items-center gap-6">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={t.img}
                      alt={`${t.name} tyre`}
                      className="h-20 w-20 shrink-0 object-contain sm:h-24 sm:w-24"
                    />
                    <div>
                      <h3 className="font-display text-2xl sm:text-3xl">{t.name}</h3>
                      <p className="text-sm text-white">{t.desc}</p>
                    </div>
                  </div>
                </Reveal>
              ))}
            </div>

            {/* Right: notes */}
            <Reveal direction="right" className="relative flex flex-col justify-between">
              <div>
                <span className="font-script inline-block -rotate-6 text-3xl leading-tight text-accent sm:text-4xl">
                  Only 3 dry tire compounds
                </span>
                <p className="mt-3 font-display text-lg uppercase tracking-wide text-white">
                  (Soft, Medium, Hard)
                </p>
              </div>
              <p className="mt-12 max-w-sm text-sm leading-relaxed text-white sm:ml-auto sm:text-right">
                Sometimes the rain can change everything and turns the race into complete chaos!
              </p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* FLAGS */}
      <section className="bg-gradient-to-r from-[#e8002d] via-[#ff8a00] to-yellow px-5 py-20 text-black">
        <div className="mx-auto max-w-6xl">
          <Reveal direction="up">
            <GlitchTitle className="mb-12 sm:pl-[14%]">Flags</GlitchTitle>
          </Reveal>
          <div className="grid gap-x-12 gap-y-10 sm:grid-cols-2">
            {flags.map((f) => (
            <Reveal key={f.name} direction="up">
              <div className="flex items-center gap-6">
                <FlagSwatch kind={f.swatch} />
                <div>
                  <h3 className="font-display text-2xl sm:text-3xl">{f.name}</h3>
                  <p className="text-sm opacity-80 text-white">{f.desc}</p>
                </div>
              </div>
            </Reveal>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
