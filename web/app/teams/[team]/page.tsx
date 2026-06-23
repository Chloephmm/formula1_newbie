import { notFound } from "next/navigation";
import Link from "next/link";
import Reveal from "@/components/Reveal";
import { teams, getTeam, getDriversForTeam, shortTeamName } from "@/lib/data";
import { TEAM_META, teamLogo, LOGO_CFG } from "@/lib/teamMeta";
import { teamCar, driverPhoto, driverPhotoCutout, driverNumber, driverChampionships } from "@/lib/assets";
import { flagSrc } from "@/lib/flags";
import {
  getConstructorStandings,
  getDriverStandings,
  getSeasonStats,
  getDriverCareer,
  getCareerRevalidate,
} from "@/lib/jolpica";
import type { DriverCareer } from "@/lib/types";

export const revalidate = 3600;

export function generateStaticParams() {
  return teams.map((t) => ({ team: t.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ team: string }> }) {
  const { team } = await params;
  const t = getTeam(team);
  return { title: `${t?.name ?? "Team"} — F1 Guidebook` };
}

// Wireframe palette.
const LINE = "#2a2a31";
const DIM = "#7a7a84";
const VAL = "#f0f0f2";

const CELL = "#0b0b0e"; // near-black data cell

// Solid accent section header — folder "tab" that caps the table below it.
function Tab({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span
      className="relative z-10 inline-block px-4 py-1.5 text-sm font-bold uppercase tracking-[0.16em] text-white"
      style={{
        backgroundColor: color,
        clipPath: "polygon(0 0, 100% 0, 100% 60%, calc(100% - 11px) 100%, 0 100%)",
      }}
    >
      {children}
    </span>
  );
}

// Label + value stat block (wireframe style).
function Stat({
  label,
  value,
  accent,
  color,
  size = "text-2xl",
  upper,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
  color: string;
  size?: string;
  upper?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.13em]" style={{ color: DIM }}>
        {label}
      </div>
      <div
        className={`mt-1.5 font-bold leading-tight ${size} ${upper ? "uppercase" : ""}`}
        style={{ color: accent ? color : VAL }}
      >
        {value}
      </div>
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
  const car = teamCar(team);
  const drivers = getDriversForTeam(team);

  // Live data with static fallback
  const [{ data: constructors }, { data: driverStandings }, { data: seasonStats, live: statsLive }] =
    await Promise.all([getConstructorStandings(), getDriverStandings(), getSeasonStats()]);
  const live = constructors.find((c) => c.constructorId === team);
  const position = live?.position ?? constructors.findIndex((c) => c.constructorId === team) + 1;
  const teamPoints = live?.points ?? t.points;
  const teamWins = live?.wins ?? t.wins;

  // Per-driver season stats keyed by 3-letter code; team totals = sum of its drivers.
  const stat = (code: string) => seasonStats[code];
  const teamSum = (k: "podiums" | "poles" | "fastestLaps") =>
    drivers.reduce((s, d) => s + (stat(d.code)?.[k] ?? 0), 0);
  const teamPodiums = statsLive ? teamSum("podiums") : drivers.reduce((s, d) => s + d.podiums, 0);
  const teamPoles: string | number = statsLive ? teamSum("poles") : "—";
  const teamFastestLaps: string | number = statsLive ? teamSum("fastestLaps") : "—";

  // Whole-career driver totals (Section 2), keyed by our driver id. Ergast
  // driverId comes from the live standings. Career stats only change on race
  // day, so they're cached until just after the next Grand Prix.
  const careerRevalidate = await getCareerRevalidate();
  const careers: Record<string, DriverCareer | null> = {};
  for (const d of drivers) {
    const ds = driverStandings.find((s) => s.code === d.code);
    careers[d.id] = (await getDriverCareer(ds?.driverId ?? d.id, careerRevalidate)).data;
  }

  // Hero wordmark: scale font to keep any team name on a single line.
  const teamName = shortTeamName(t);
  const wmSize = `min(6rem, ${(95 / Math.max(teamName.length, 1)).toFixed(1)}vw)`;

  return (
    <div
      className="mx-auto max-w-6xl px-5 py-4"
      style={{ fontFamily: "var(--font-plex), ui-monospace, monospace" }}
    >
      {/* Label with small logo — matches the top-left lockup */}
      <Reveal direction="left" once>
        <div className="flex items-center gap-3">
          {logo && (
            <span
              className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full"
              style={{ backgroundColor: color }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={logo}
                alt={t.name}
                className="h-full w-full object-cover"
                style={{
                  objectPosition: LOGO_CFG[team]?.pos ?? "center",
                  transform: `scale(${LOGO_CFG[team]?.scale ?? 1})`,
                  transformOrigin: LOGO_CFG[team]?.pos ?? "center",
                }}
              />
            </span>
          )}
          <div className="border-l-4 pl-3" style={{ borderColor: color }}>
            <p className="font-mono text-sm font-bold uppercase tracking-wide">{meta.fullName}</p>
            <p className="font-mono text-xs text-muted">FORMULA 1 · 2026 SEASON</p>
          </div>
        </div>
      </Reveal>

      {/* Hero: the team name sits BEHIND the car, which slides in left → right */}
      <div className="relative my-3">
        <Reveal direction="up" once className="absolute left-1/2 top-0 z-0 w-full -translate-x-1/2">
          <h1
            className="whitespace-nowrap text-center font-display uppercase leading-none"
            style={{ color, fontSize: wmSize, textShadow: `0 0 40px ${color}66, 0 0 12px ${color}aa` }}
          >
            {teamName}
          </h1>
        </Reveal>
        {car && (
          <Reveal
            direction="left"
            once
            distance={420}
            duration={1.8}
            className="relative z-10 mx-auto block w-fit pt-10"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={car}
              alt={`${t.name} car`}
              className="pointer-events-none block max-h-[28vh] w-auto max-w-4xl"
            />
          </Reveal>
        )}
      </div>

      {/* Driver headshots — compact lockup under the car */}
      <Reveal direction="up" once className="-mt-2">
        <div className="flex justify-center gap-10 sm:gap-20">
          {drivers.map((d) => {
            const photo = driverPhotoCutout(d.id);
            const num = driverNumber(d.id);
            return (
              <div key={d.id} className="flex flex-col items-center">
                {photo && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={photo}
                    alt={d.name}
                    className="h-32 w-32 object-cover sm:h-[18vh] sm:w-[18vh]"
                  />
                )}
                <p className="mt-1.5 font-display text-sm uppercase tracking-wide sm:text-base">
                  {num != null && (
                    <span className="mr-2 font-bold" style={{ color }}>
                      {num}
                    </span>
                  )}
                  {d.name}
                </p>
              </div>
            );
          })}
        </div>
      </Reveal>

      {/* Team Information */}
      <div className="mt-4">
        <div>
          <Tab color={color}>Team Information</Tab>
        </div>
        <div
          className="grid grid-cols-2 gap-px border sm:grid-cols-4"
          style={{ borderColor: LINE, backgroundColor: LINE }}
        >
          {[
            ["BASE", meta.base],
            ["TEAM CHIEF", meta.chief],
            ["CHASSIS", meta.chassis],
            ["POWER UNIT", meta.powerUnit],
          ].map(([label, value]) => (
            <div key={label} className="px-5 py-2.5" style={{ backgroundColor: CELL }}>
              <Stat label={label} value={value} color={color} size="text-base sm:text-lg" upper />
            </div>
          ))}
        </div>
      </div>

      {/* 2026 Statistics — sits flush against the Team Information table above */}
      <div>
        <div>
          <Tab color={color}>2026 Statistics</Tab>
        </div>
        <div
          className="grid grid-cols-3 gap-px border sm:grid-cols-6"
          style={{ borderColor: LINE, backgroundColor: LINE }}
        >
          {(
            [
              ["Classification", position, true],
              ["Points", teamPoints, true],
              ["Wins", teamWins, false],
              ["Podiums", teamPodiums, false],
              ["Poles", teamPoles, false],
              ["Fastest Laps", teamFastestLaps, false],
            ] as [string, string | number, boolean][]
          ).map(([label, value, accent]) => (
            <div key={label} className="px-4 py-2.5" style={{ backgroundColor: CELL }}>
              <Stat label={label} value={value} accent={accent} color={color} size="text-xl sm:text-2xl" />
            </div>
          ))}
        </div>
      </div>

      {/* Section 2 · Drivers — stacked feature rows */}
      <div className="mt-10">
        <div className="h-[3px] opacity-75" style={{ backgroundColor: color }} />
        <div className="mt-6">
          <Tab color={color}>Drivers</Tab>
        </div>
        <div className="mt-6 flex flex-col gap-8">
          {drivers.map((d, i) => {
            const ds = driverStandings.find((s) => s.code === d.code);
            const career = careers[d.id];
            const champs = driverChampionships(d.id);
            const photo = driverPhoto(d.id);
            const num = driverNumber(d.id);
            const flag = flagSrc(d.nationality);
            const flip = i % 2 === 1;
            return (
              <Reveal key={d.id} direction={flip ? "right" : "left"}>
                <div
                  className={`flex flex-col items-center gap-8 sm:items-stretch ${
                    flip ? "sm:flex-row-reverse" : "sm:flex-row"
                  }`}
                >
                  {photo && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={photo}
                      alt={d.name}
                      className="h-56 w-56 shrink-0 object-cover sm:h-64 sm:w-64"
                      style={{ background: `linear-gradient(160deg, ${color}, ${color}55)` }}
                    />
                  )}
                  <div className="w-full flex-1">
                    <div className="flex items-center gap-4">
                      {num != null && (
                        <span className="text-5xl font-bold" style={{ color }}>
                          {num}
                        </span>
                      )}
                      {flag && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={flag}
                          alt={d.nationality}
                          title={d.nationality}
                          className="h-7 w-10 shrink-0 rounded-sm object-cover ring-1 ring-white/15"
                        />
                      )}
                      <span className="text-2xl font-bold uppercase tracking-wide">{d.name}</span>
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-x-7 gap-y-3">
                      {(
                        [
                          ["World Championships", champs, false],
                          ["Races", career?.races ?? "—", false],
                          ["Wins", career?.wins ?? "—", false],
                          ["Podiums", career?.podiums ?? "—", false],
                          ["Poles", career?.poles ?? "—", false],
                          ["Fastest Laps", career?.fastestLaps ?? "—", false],
                        ] as [string, string | number, boolean][]
                      ).map(([label, value, accent]) => (
                        <div key={label} className="border-t pt-3" style={{ borderColor: LINE }}>
                          <Stat label={label} value={value} accent={accent} color={color} size="text-3xl" />
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 border-t pt-3" style={{ borderColor: LINE }}>
                      <Stat
                        label="2026 Classification"
                        value={ds ? `P${ds.position}` : "—"}
                        accent
                        color={color}
                        size="text-3xl"
                      />
                    </div>
                  </div>
                </div>
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
