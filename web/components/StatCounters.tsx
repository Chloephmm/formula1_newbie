"use client";

import { Fragment, useEffect, useState } from "react";

function CountUp({ to, duration = 1200 }: { to: number; duration?: number }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setN(to);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min((t - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out
      setN(Math.round(eased * to));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, duration]);
  return <span className="tabular-nums">{n}</span>;
}

export default function StatCounters({
  stats,
}: {
  stats: { label: string; value: number }[];
}) {
  return (
    <div className="flex items-center justify-center gap-5 sm:gap-9">
      {stats.map((s, i) => (
        <Fragment key={s.label}>
          {i > 0 && <span className="h-9 w-px bg-white/15" aria-hidden />}
          <div className="text-center">
            <div
              className="font-display text-3xl leading-none sm:text-4xl"
              style={{ textShadow: "0 2px 14px rgba(0,0,0,0.85)" }}
            >
              <CountUp to={s.value} />
            </div>
            <div className="mt-1.5 text-[10px] uppercase tracking-[0.22em] text-muted">
              {s.label}
            </div>
          </div>
        </Fragment>
      ))}
    </div>
  );
}
