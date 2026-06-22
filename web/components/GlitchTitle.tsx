import type { ReactNode } from "react";

// Pixel/glitch section title (Mokoto Glitch → Handjet substitute + glitch effect).
export default function GlitchTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      className={`glitch font-pixel text-2xl uppercase leading-none sm:text-3xl ${className}`}
    >
      {children}
    </h2>
  );
}
