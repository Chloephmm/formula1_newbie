"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

type Direction = "left" | "right" | "up" | "down";

const offset: Record<Direction, { x?: number; y?: number }> = {
  left: { x: -64 },
  right: { x: 64 },
  up: { y: 48 },
  down: { y: -48 },
};

/** Slide-in / slide-out reveal wrapper matching the animations. */
export default function Reveal({
  children,
  direction = "up",
  delay = 0,
  className,
  once = true,
  distance,
  duration = 0.6,
}: {
  children: ReactNode;
  direction?: Direction;
  delay?: number;
  className?: string;
  once?: boolean;
  /** Override the slide distance (px) — e.g. a long left→right car entrance. */
  distance?: number;
  duration?: number;
}) {
  const start =
    distance == null
      ? offset[direction]
      : direction === "left"
        ? { x: -distance }
        : direction === "right"
          ? { x: distance }
          : direction === "up"
            ? { y: distance }
            : { y: -distance };

  const variants: Variants = {
    hidden: { opacity: 0, ...start },
    visible: {
      opacity: 1,
      x: 0,
      y: 0,
      transition: { duration, delay, ease: [0.22, 1, 0.36, 1] },
    },
  };

  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once, amount: 0.2 }}
      variants={variants}
    >
      {children}
    </motion.div>
  );
}
