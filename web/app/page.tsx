import Link from "next/link";
import Reveal from "@/components/Reveal";

export default function Home() {
  return (
    <section className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-6xl flex-col items-center overflow-hidden px-5 pt-10 sm:pt-14">
      {/* Headline */}
      <Reveal direction="down" once>
        <h1 className="mx-auto max-w-4xl text-center font-display text-3xl leading-tight tracking-tight sm:text-5xl">
          NEW HERE? PERFECT. WE&rsquo;LL GET YOU FROM &ldquo;WHO&rsquo;S THAT
          GUY&rdquo; TO ACTUAL FAN, FAST.
        </h1>
      </Reveal>

      {/* Car rising from smoke */}
      <div className="relative mt-4 flex w-full flex-1 items-end justify-center">
        {/* smoke around the base */}
        <img
          src="/images/smoke.png"
          alt=""
          aria-hidden
          className="pointer-events-none absolute bottom-16 left-1/2 w-[760px] max-w-[120%] -translate-x-1/2 opacity-50 mix-blend-screen"
        />
        {/* car */}
        <Reveal direction="up" once className="relative z-10">
          <img
            src="/images/car-front.png"
            alt="Formula 1 car"
            className="mx-auto w-[300px] drop-shadow-[0_0_70px_rgba(232,0,45,0.3)] sm:w-[440px]"
          />
        </Reveal>
      </div>

      {/* START HERE pixel button */}
      <Reveal direction="up" once className="relative z-20 -mt-2 pb-12">
        <Link
          href="/how-f1-works"
          className="pulse inline-flex items-center justify-center rounded-full bg-white px-12 py-3 text-center"
        >
          <span className="font-pixel text-2xl leading-none text-black">
            START
            <br />
            HERE
          </span>
        </Link>
      </Reveal>
    </section>
  );
}
