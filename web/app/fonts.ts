import localFont from "next/font/local";
import { JetBrains_Mono, IBM_Plex_Mono } from "next/font/google";

// Display font (headers + nav), Self-hosted.
export const horizon = localFont({
  src: "./fonts/horizon/Horizon.woff2",
  variable: "--font-horizon",
  display: "swap",
});

// Handwritten script, Self-hosted.
export const holiday = localFont({
  src: "./fonts/holiday/HolidayFree.otf",
  variable: "--font-holiday",
  display: "swap",
});

// Pixel / glitch titles, Self-hosted (Mark 1).
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

// Team-page monospace — IBM Plex Mono (matches the team-tab wireframe).
export const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-plex",
  display: "swap",
});

// Navigation font — Cooper Hewitt. Self-hosted.
export const cooperHewitt = localFont({
  src: [
    { path: "./fonts/cooper-hewitt/CooperHewitt-Book.otf", weight: "400", style: "normal" },
    { path: "./fonts/cooper-hewitt/CooperHewitt-Medium.otf", weight: "500", style: "normal" },
    { path: "./fonts/cooper-hewitt/CooperHewitt-Semibold.otf", weight: "600", style: "normal" },
    { path: "./fonts/cooper-hewitt/CooperHewitt-Bold.otf", weight: "700", style: "normal" },
  ],
  variable: "--font-cooper",
  display: "swap",
});
