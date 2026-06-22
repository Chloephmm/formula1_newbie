"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { STREAMLIT_URL } from "@/lib/links";

const links = [
  { href: "/", label: "HOME" },
  { href: "/how-f1-works", label: "HOW F1 WORKS" },
  { href: "/history", label: "HISTORY" },
  { href: "/teams", label: "TEAMS" },
  { href: "/drivers", label: "DRIVERS" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-bg/85 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
        {/* Mobile brand */}
        <Link href="/" className="font-nav text-base font-bold md:hidden">
          F1
        </Link>

        {/* Desktop nav — centered, Cooper Hewitt, red ellipse on active */}
        <ul className="hidden w-full items-center justify-center gap-12 md:flex">
          {links.map((l) => {
            const active = isActive(l.href);
            return (
              <li key={l.href} className="relative">
                {active && (
                  <span className="absolute left-1/2 top-1/2 -z-10 h-[2.2em] w-[calc(100%+3.5rem)] -translate-x-1/2 -translate-y-1/2 rounded-[50%] bg-accent" />
                )}
                <Link
                  href={l.href}
                  className="font-nav text-sm font-semibold tracking-wide underline-offset-4 transition-opacity hover:opacity-80"
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
          <li>
            <a
              href={STREAMLIT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="font-nav text-sm font-semibold tracking-wide underline-offset-4 hover:text-accent"
            >
              PREDICT ↗
            </a>
          </li>
        </ul>

        {/* Mobile toggle */}
        <button
          aria-label="Toggle menu"
          className="md:hidden"
          onClick={() => setOpen((v) => !v)}
        >
          <span className="block h-0.5 w-6 bg-fg" />
          <span className="mt-1.5 block h-0.5 w-6 bg-fg" />
          <span className="mt-1.5 block h-0.5 w-6 bg-fg" />
        </button>
      </nav>

      {open && (
        <ul className="flex flex-col gap-1 border-t border-border px-5 py-3 md:hidden">
          {links.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                onClick={() => setOpen(false)}
                className={`block py-2 font-nav text-sm font-semibold ${
                  isActive(l.href) ? "text-accent" : ""
                }`}
              >
                {l.label}
              </Link>
            </li>
          ))}
          <li>
            <a
              href={STREAMLIT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="block py-2 font-nav text-sm font-semibold hover:text-accent"
            >
              PREDICT ↗
            </a>
          </li>
        </ul>
      )}
    </header>
  );
}
