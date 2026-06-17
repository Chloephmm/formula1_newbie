import Link from "next/link";
import Reveal from "@/components/Reveal";
import { teams } from "@/lib/data";
import { teamLogo } from "@/lib/teamMeta";

export const metadata = { title: "Teams — F1 Guidebook" };

export default function TeamsPage() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <div className="grid grid-cols-2 gap-x-6 gap-y-12 sm:grid-cols-3">
        {teams.map((t, i) => {
          const logo = teamLogo(t.id);
          return (
            <Reveal key={t.id} direction={i % 2 === 0 ? "left" : "right"} delay={(i % 3) * 0.05}>
              <Link href={`/teams/${t.id}`} className="group flex flex-col items-center">
                <span
                  className="flex h-32 w-32 items-center justify-center overflow-hidden rounded-full ring-2 ring-transparent transition group-hover:scale-105 group-hover:ring-white/40 sm:h-40 sm:w-40"
                  style={{ backgroundColor: t.color }}
                >
                  {logo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={logo} alt={t.name} className="h-full w-full object-cover" />
                  ) : (
                    <span className="font-display text-3xl text-white">{t.name[0]}</span>
                  )}
                </span>
                <span className="mt-4 text-center font-display text-xl uppercase tracking-wide underline-offset-4 group-hover:underline sm:text-2xl">
                  {t.name}
                </span>
              </Link>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}
