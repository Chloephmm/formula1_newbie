// Maps an F1 nationality (Ergast demonym) to a local flag SVG under
// /public/images/flags/<iso>.svg.

const NATIONALITY_ISO: Record<string, string> = {
  Argentine: "ar",
  Argentinian: "ar",
  Australian: "au",
  Brazilian: "br",
  British: "gb",
  Canadian: "ca",
  Dutch: "nl",
  Finnish: "fi",
  French: "fr",
  German: "de",
  Italian: "it",
  Mexican: "mx",
  Monegasque: "mc",
  "New Zealander": "nz",
  Spanish: "es",
  Thai: "th",
};

export function flagSrc(nationality: string): string | null {
  const iso = NATIONALITY_ISO[nationality];
  return iso ? `/images/flags/${iso}.svg` : null;
}
