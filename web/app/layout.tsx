import type { Metadata } from "next";
import "./globals.css";
import { horizon, holiday, jetbrainsMono, mokoto } from "./fonts";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "F1 Guidebook",
  description:
    "New here? Perfect. From “who’s that guy” to actual fan, fast — a beginner-friendly Formula 1 guide.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${horizon.variable} ${holiday.variable} ${jetbrainsMono.variable} ${mokoto.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-fg">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
