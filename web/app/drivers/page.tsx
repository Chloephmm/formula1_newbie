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
      <Reveal direction="up" className="text-center">
        <GlitchTitle className="mb-3">The Grid</GlitchTitle>
      </Reveal>
      <div className="mb-10 flex justify-center">
        <LiveBadge live={live} />
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {standings.map((d, i) => {
          const color = getTeam(d.constructorId)?.color ?? "#888888";
          return (
            <Reveal key={d.driverId} direction={i % 2 === 0 ? "left" : "right"} delay={(i % 3) * 0.04} className="h-full">
              <article
                className="group relative flex h-full min-h-[140px] gap-3 overflow-hidden rounded-xl border border-border py-3 pl-5 pr-4 transition duration-200 hover:-translate-y-1 hover:border-white/25 hover:shadow-[0_14px_36px_-20px_var(--tc)]"
                style={{ background: `linear-gradient(135deg, ${color}22, transparent)`, "--tc": color } as React.CSSProperties}
              >
                {/* team accent strip */}
                <span className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: color }} />

                {/* fixed-width number column → every name starts at the same x */}
                <span className="w-16 shrink-0 text-center font-display text-3xl leading-none tabular-nums text-white/85">
                  {d.position}
                </span>

                {/* right column — name, team, and stats all share this left edge */}
                <div className="flex min-w-0 flex-1 flex-col">
                  <div>
                    <h3 className="line-clamp-2 font-display text-[15px] uppercase leading-tight">
                      {d.givenName} {d.familyName}
                    </h3>
                    <p className="mt-0.5 truncate text-[11px] uppercase tracking-wider text-muted">
                      {d.constructorName}
                    </p>
                  </div>

                  <div className="mt-auto">
                    <div className="mb-2 border-t border-border/70" />
                    <div className="flex items-end gap-6 rounded-md bg-white/[0.04] px-2.5 py-1.5">
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.18em] text-muted">Points</div>
                        <div className="font-display text-xl leading-none">{d.points}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.18em] text-muted">Wins</div>
                        <div
                          className="font-display text-xl leading-none"
                          style={d.wins > 0 ? { color } : undefined}
                        >
                          {d.wins}
                        </div>
                      </div>
                    </div>
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
