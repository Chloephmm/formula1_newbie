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

/** Slide-in / slide-out reveal wrapper matching the Canva animations. */
export default function Reveal({
  children,
  direction = "up",
  delay = 0,
  className,
  once = true,
}: {
  children: ReactNode;
  direction?: Direction;
  delay?: number;
  className?: string;
  once?: boolean;
}) {
  const variants: Variants = {
    hidden: { opacity: 0, ...offset[direction] },
    visible: {
      opacity: 1,
      x: 0,
      y: 0,
      transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] },
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
