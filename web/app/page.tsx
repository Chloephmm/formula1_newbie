import Link from "next/link";
import Reveal from "@/components/Reveal";
import AuroraField from "@/components/AuroraField";
import WelcomeHeadline from "@/components/WelcomeHeadline";
import StatCounters from "@/components/StatCounters";
import { teams, drivers } from "@/lib/data";
import { getSchedule } from "@/lib/jolpica";
import { STREAMLIT_URL } from "@/lib/links";

export default async function Home() {
  const { data: schedule } = await getSchedule("2026");
  const raceCount = schedule.length >= 10 ? schedule.length : 24;
  const stats = [
    { label: "Drivers", value: drivers.length },
    { label: "Teams", value: teams.length },
    { label: "Races", value: raceCount },
  ];

  return (
    <>
      {/* Interactive Aurora Field shader — fullscreen background (Home only) */}
      <AuroraField heatColor="#ff5e1a" warmth={0.45} heatIntensity={0.9} />
      {/* Vignette scrim — frames the aurora toward the car and guarantees text contrast */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[1]"
        style={{
          background:
            "radial-gradient(120% 120% at 50% 38%, rgba(5,4,7,0) 30%, rgba(5,4,7,0.5) 66%, rgba(5,4,7,0.92) 100%)",
        }}
      />

      <section className="relative z-10 mx-auto max-w-6xl px-5 pb-16 pt-10 sm:pt-12">
        {/* Headline — rotates through a set of welcomes on each visit */}
        <Reveal direction="down" once>
          <WelcomeHeadline />
        </Reveal>

        {/* Car zooming toward the viewer, centered under the headline */}
        <div className="relative mt-4 flex flex-col items-center">
          <div className="relative flex w-full items-end justify-center">
            <Reveal scaleFrom={0.45} duration={1.4} once className="relative z-10 w-full">
              <img
                src="/images/car-front.png"
                alt="Formula 1 car"
                className="mx-auto w-[88%] max-w-[680px] drop-shadow-[0_0_90px_rgba(232,0,45,0.45)]"
              />
            </Reveal>
          </div>

          {/* CTA pair — primary START HERE on the car's nose + a quieter secondary */}
          <Reveal
            direction="up"
            once
            className="relative z-20 -mt-10 flex flex-col items-center gap-3 sm:-mt-14"
          >
            <Link
              href="/how-f1-works"
              className="pulse inline-flex items-center justify-center rounded-full bg-white px-10 py-3 text-center sm:px-12"
            >
              <span className="font-pixel text-xl leading-none text-black sm:text-2xl">
                START
                <br />
                HERE
              </span>
            </Link>
            <a
              href={STREAMLIT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-xs uppercase tracking-[0.18em] text-muted underline-offset-4 transition hover:text-fg hover:underline"
            >
              or jump to predictions ↗
            </a>
          </Reveal>

          {/* Animated stat counters */}
          <Reveal direction="up" once delay={0.1} className="mt-12">
            <StatCounters stats={stats} />
          </Reveal>
        </div>
      </section>
    </>
  );
}
