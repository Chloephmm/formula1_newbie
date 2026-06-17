import localFont from "next/font/local";
import { JetBrains_Mono } from "next/font/google";

// Display font (headers + nav) — Canva uses "Horizon". Self-hosted.
export const horizon = localFont({
  src: "./fonts/horizon/Horizon.woff2",
  variable: "--font-horizon",
  display: "swap",
});

// Handwritten script — Canva uses "Holiday". Self-hosted.
export const holiday = localFont({
  src: "./fonts/holiday/HolidayFree.otf",
  variable: "--font-holiday",
  display: "swap",
});

// Pixel / glitch titles — Canva uses "Mokoto Glitch". Self-hosted (Mark 1).
export const mokoto = localFont({
  src: "./fonts/mokoto/ttf/mokoto-mokoto-regular-glitch-mark-1-400.ttf",
  variable: "--font-mokoto",
  display: "swap",
});

// Body monospace — JetBrains Mono (Google Fonts).
export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jet",
  display: "swap",
});
