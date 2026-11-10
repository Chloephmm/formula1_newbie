import Image from "next/image";
import type { Ref } from "react";

interface F1BuddyLauncherProps {
  open: boolean;
  onToggle: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}

export default function F1BuddyLauncher({
  open,
  onToggle,
  buttonRef,
}: F1BuddyLauncherProps) {
  return (
    <div className="group relative ml-auto w-fit">
      <div
        role="tooltip"
        className="pointer-events-none absolute right-0 bottom-[calc(100%+0.9rem)] w-72 translate-y-2 rounded-2xl border border-[#E8002D]/25 bg-white p-4 text-left text-[#111521] opacity-0 shadow-[0_18px_45px_rgba(0,0,0,.38)] transition duration-200 group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100 motion-reduce:transform-none motion-reduce:transition-none"
      >
        <p className="font-nav text-base font-bold">Hello, F1 fan! 🏁</p>
        <p className="mt-1.5 text-xs leading-5">
          Need help with Formula 1? Ask me about races, drivers, standings, and predictions!
        </p>
        <p className="mt-2 text-[11px] font-semibold italic text-[#E8002D]">
          Currently English only.
        </p>
        <span className="absolute -bottom-2 right-6 h-4 w-4 rotate-45 border-r border-b border-[#E8002D]/25 bg-white" />
      </div>

      <button
        ref={buttonRef}
        type="button"
        aria-label={open ? "Minimize F1 Buddy" : "Open F1 Buddy"}
        aria-expanded={open}
        aria-controls="f1buddy-panel"
        onClick={onToggle}
        className="relative grid h-16 w-16 place-items-center overflow-hidden rounded-full border-2 border-[#E8002D] bg-white p-1 shadow-[0_0_0_5px_rgba(232,0,45,.10),0_0_28px_rgba(232,0,45,.55)] transition-transform duration-200 hover:scale-105 focus-visible:scale-105 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white motion-reduce:transform-none motion-reduce:transition-none sm:h-[72px] sm:w-[72px]"
      >
        <Image
          src="/images/f1-buddy-car.jpg"
          alt="Red Formula 1 car — open F1 Buddy"
          width={768}
          height={768}
          priority={false}
          className="h-full w-full rounded-full object-cover"
        />
      </button>
    </div>
  );
}
