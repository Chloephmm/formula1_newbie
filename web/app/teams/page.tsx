import Link from "next/link";
import Reveal from "@/components/Reveal";
import { getTeam, shortTeamName } from "@/lib/data";
import { teamLogo, LOGO_CFG } from "@/lib/teamMeta";

export const metadata = { title: "Teams — F1 Guidebook" };

// Display order matches the layout: 6 on top, 5 on the second row.
const ORDER = [
  "mercedes", "ferrari", "mclaren", "red_bull", "alpine", "haas",
  "williams", "rb", "audi", "aston_martin", "cadillac",
];

export default function TeamsPage() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-12">
        {ORDER.map((id, i) => {
          const t = getTeam(id);
          if (!t) return null;
          const logo = teamLogo(id);
          return (
            <Reveal
              key={id}
              direction={i % 2 === 0 ? "left" : "right"}
              delay={(i % 6) * 0.04}
              className="w-[130px] sm:w-[150px] lg:w-40"
            >
              <Link href={`/teams/${id}`} className="group flex flex-col items-center">
                <span
                  className="flex h-28 w-28 items-center justify-center overflow-hidden rounded-full ring-2 ring-transparent transition group-hover:scale-105 group-hover:ring-white/40 sm:h-32 sm:w-32 lg:h-36 lg:w-36"
                  style={{ backgroundColor: t.color }}
                >
                  {logo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={logo}
                      alt={t.name}
                      className="h-full w-full object-cover"
                      style={{
                        objectPosition: LOGO_CFG[id]?.pos ?? "center",
                        transform: `scale(${LOGO_CFG[id]?.scale ?? 1})`,
                        transformOrigin: LOGO_CFG[id]?.pos ?? "center",
                      }}
                    />
                  ) : (
                    <span className="font-display text-3xl text-white">{t.name[0]}</span>
                  )}
                </span>
                <span className="mt-4 block w-full px-1 text-center font-display text-base uppercase leading-tight tracking-wide underline-offset-4 group-hover:underline sm:text-lg">
                  {shortTeamName(t)}
                </span>
              </Link>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}
