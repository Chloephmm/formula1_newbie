import { notFound } from "next/navigation";
import Link from "next/link";
import Reveal from "@/components/Reveal";
import { teams, getTeam, getDriversForTeam } from "@/lib/data";
import { TEAM_META, teamLogo } from "@/lib/teamMeta";
import { getConstructorStandings, getDriverStandings } from "@/lib/jolpica";

export const revalidate = 3600;

export function generateStaticParams() {
  return teams.map((t) => ({ team: t.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ team: string }> }) {
  const { team } = await params;
  const t = getTeam(team);
  return { title: `${t?.name ?? "Team"} — F1 Guidebook` };
}

function Stat({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="border-l-2 pl-3" style={{ borderColor: color }}>
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="font-display text-3xl">{value}</p>
    </div>
  );
}

export default async function TeamDetailPage({
  params,
}: {
  params: Promise<{ team: string }>;
}) {
  const { team } = await params;
  const t = getTeam(team);
  const meta = TEAM_META[team];
  if (!t || !meta) notFound();

  const color = t.color;
  const logo = teamLogo(team);
  const drivers = getDriversForTeam(team);

  // Live data with static fallback
  const [{ data: constructors }, { data: driverStandings }] = await Promise.all([
    getConstructorStandings(),
    getDriverStandings(),
  ]);
  const live = constructors.find((c) => c.constructorId === team);
  const position = live?.position ?? constructors.findIndex((c) => c.constructorId === team) + 1;
  const teamPoints = live?.points ?? t.points;
  const teamWins = live?.wins ?? t.wins;
  const teamPodiums = drivers.reduce((s, d) => s + d.podiums, 0);

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      {/* Logo */}
      {logo && (
        <Reveal direction="down" once className="flex justify-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={logo}
            alt={t.name}
            className="h-24 w-24 overflow-hidden rounded-full object-cover"
            style={{ backgroundColor: color }}
          />
        </Reveal>
      )}

      {/* Label */}
      <Reveal direction="left" once className="mt-8">
        <div className="w-fit border-l-4 pl-3" style={{ borderColor: color }}>
          <p className="font-mono text-sm font-bold uppercase tracking-wide">{meta.fullName}</p>
          <p className="font-mono text-xs text-muted">FORMULA 1 · 2026 SEASON</p>
        </div>
      </Reveal>

      {/* Giant glowing team name */}
      <Reveal direction="up" once>
        <h1
          className="my-6 font-display text-6xl uppercase leading-none sm:text-[9rem]"
          style={{ color, textShadow: `0 0 40px ${color}66, 0 0 12px ${color}aa` }}
        >
          {t.name}
        </h1>
      </Reveal>

      {/* Info bar */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-4">
        {[
          ["BASE", meta.base],
          ["TEAM CHIEF", meta.chief],
          ["CHASSIS", meta.chassis],
          ["POWER UNIT", meta.powerUnit],
        ].map(([label, value]) => (
          <div key={label} className="bg-black p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
            <p className="mt-1 font-display text-lg">{value}</p>
          </div>
        ))}
      </div>

      {/* Season statistics */}
      <div className="mt-10">
        <span
          className="inline-block rounded px-3 py-1 font-mono text-xs font-bold uppercase tracking-widest text-white"
          style={{ backgroundColor: color }}
        >
          2026 Statistics
        </span>
        <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Classification" value={`${position}`} color={color} />
          <Stat label="Points" value={teamPoints} color={color} />
          <Stat label="Wins" value={teamWins} color={color} />
          <Stat label="Podiums" value={teamPodiums} color={color} />
        </div>
      </div>

      {/* Drivers */}
      <div className="mt-16">
        <div
          className="mb-8 rounded px-4 py-2 font-display text-2xl uppercase tracking-wide text-white"
          style={{ backgroundColor: color }}
        >
          Drivers
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          {drivers.map((d, i) => {
            const ds = driverStandings.find((s) => s.code === d.code);
            return (
              <Reveal key={d.id} direction={i % 2 === 0 ? "left" : "right"}>
                <article
                  className="rounded-xl border border-border p-6"
                  style={{ background: `linear-gradient(135deg, ${color}22, transparent)` }}
                >
                  <h3 className="font-display text-2xl uppercase">{d.name}</h3>
                  <p className="text-xs text-muted">{d.nationality}</p>
                  <div className="mt-5 grid grid-cols-2 gap-4">
                    <Stat label="Classification" value={ds ? `P${ds.position}` : "—"} color={color} />
                    <Stat label="Points" value={d.points} color={color} />
                    <Stat label="Wins" value={d.wins} color={color} />
                    <Stat label="Podiums" value={d.podiums} color={color} />
                  </div>
                </article>
              </Reveal>
            );
          })}
        </div>
      </div>

      <div className="mt-12">
        <Link href="/teams" className="font-display text-lg underline underline-offset-4 hover:text-accent">
          ← All teams
        </Link>
      </div>
    </div>
  );
}
