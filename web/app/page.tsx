import Link from "next/link";
import Reveal from "@/components/Reveal";

export default function Home() {
  return (
    <section className="relative mx-auto max-w-6xl overflow-hidden px-5 pb-16 pt-10 sm:pt-12">
      {/* Headline */}
      <Reveal direction="down" once>
        <h1 className="mx-auto max-w-3xl text-center font-display text-2xl leading-tight tracking-tight sm:text-4xl">
          NEW HERE? PERFECT! WE&rsquo;LL GET YOU FROM &ldquo;WHO&rsquo;S THAT
          GUY&rdquo; TO ACTUAL FAN, FAST.
        </h1>
      </Reveal>

      {/* Car rising from smoke — large, centered, just under the headline */}
      <div className="relative mt-4 flex flex-col items-center">
        <div className="relative flex w-full items-end justify-center">
          {/* smoke around the base */}
          <img
            src="/images/smoke.png"
            alt=""
            aria-hidden
            className="pointer-events-none absolute bottom-0 left-1/2 w-[120%] max-w-none -translate-x-1/2 opacity-60 mix-blend-screen"
          />
          {/* car */}
          <Reveal direction="up" once className="relative z-10 w-full">
            <img
              src="/images/car-front.png"
              alt="Formula 1 car"
              className="mx-auto w-[88%] max-w-[680px] drop-shadow-[0_0_90px_rgba(232,0,45,0.35)]"
            />
          </Reveal>
        </div>

        {/* START HERE pixel button — sits on the car's nose */}
        <Reveal direction="up" once className="relative z-20 -mt-10 sm:-mt-14">
          <Link
            href="/how-f1-works"
            className="pulse inline-flex items-center justify-center rounded-full bg-white px-10 py-3 text-center sm:px-12"
          >
            <span className="font-pixel text-xl leading-none text-black sm:text-2xl">
              START
              <br />
              HERE
            </span>
          </Link>
        </Reveal>
      </div>
    </section>
  );
}