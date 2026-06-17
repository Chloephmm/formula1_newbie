import Reveal from "@/components/Reveal";
import GlitchTitle from "@/components/GlitchTitle";
import LiveBadge from "@/components/LiveBadge";
import { getDriverStandings } from "@/lib/jolpica";
import { getTeam } from "@/lib/data";

export const revalidate = 3600;
export const metadata = { title: "Drivers — F1 Guidebook" };

export default async function DriversPage() {
  const { data: standings, live } = await getDriverStandings();

  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <Reveal direction="up">
        <GlitchTitle className="mb-3 text-center">The Grid</GlitchTitle>
      </Reveal>
      <div className="mb-10 flex justify-center">
        <LiveBadge live={live} />
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {standings.map((d, i) => {
          const color = getTeam(d.constructorId)?.color ?? "#888888";
          return (
            <Reveal key={d.driverId} direction={i % 2 === 0 ? "left" : "right"} delay={(i % 3) * 0.04}>
              <article
                className="flex items-center gap-4 rounded-xl border border-border p-5"
                style={{ background: `linear-gradient(135deg, ${color}22, transparent)` }}
              >
                <span className="font-display text-4xl text-muted">{d.position}</span>
                <span className="h-12 w-1.5 rounded" style={{ backgroundColor: color }} />
                <div className="min-w-0 flex-1">
                  <h3 className="font-display text-base uppercase leading-tight">
                    {d.givenName} {d.familyName}
                  </h3>
                  <p className="truncate text-xs text-muted">{d.constructorName}</p>
                  <div className="mt-2 flex gap-4 text-sm">
                    <span><span className="font-display text-lg">{d.points}</span> <span className="text-muted">pts</span></span>
                    <span><span className="font-display text-lg">{d.wins}</span> <span className="text-muted">wins</span></span>
                  </div>
                </div>
              </article>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}
