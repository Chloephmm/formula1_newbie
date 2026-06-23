"use client";

import { useEffect, useState } from "react";

// Rotating welcome lines — a different one each time the site is opened.
const WELCOMES = [
  "New here? Perfect! We'll get you from “who's that guy” to actual fan, fast.",
  "Step in. By the end you'll know why people lose their minds every Sunday.",
  "Welcome aboard. No experience needed, just a little curiosity and good timing.",
  "Come learn F1 from zero. Soon the races will actually make sense, promise.",
  "Buckle up. You're about to fall for a sport you barely understand yet.",
];

export default function WelcomeHeadline() {
  // Server + first client render use index 0 (stable → no hydration mismatch);
  // a random line is chosen on mount, while the parent Reveal is still faded in.
  const [i, setI] = useState(0);
  useEffect(() => {
    setI(Math.floor(Math.random() * WELCOMES.length));
  }, []);

  return (
    <h1
      className="mx-auto max-w-3xl text-center font-display text-2xl uppercase leading-tight tracking-tight sm:text-4xl"
      style={{ textShadow: "0 2px 20px rgba(0,0,0,0.9), 0 0 8px rgba(0,0,0,0.8)" }}
    >
      {WELCOMES[i]}
    </h1>
  );
}
