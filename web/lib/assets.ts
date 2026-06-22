// Maps team ids -> side-view car image, and driver ids -> driver photo.
// Files live under public/images/assets/<folder>/ (folder names mirror the team,
// except Racing Bulls whose folder is "racingbull" while the team id is "rb").

const A = "/images/assets";

export const TEAM_CAR: Record<string, string> = {
  mercedes: `${A}/mercedes/mercedes_car.avif`,
  ferrari: `${A}/ferrari/ferrari_car.avif`,
  mclaren: `${A}/mclaren/mclaren_car.avif`,
  red_bull: `${A}/red_bull/redbull_car.avif`,
  alpine: `${A}/alpine/alpine_car.avif`,
  rb: `${A}/racingbull/racingbulls_car.avif`,
  williams: `${A}/williams/williams_car.avif`,
  audi: `${A}/audi/audi_car.avif`,
  cadillac: `${A}/cadillac/cadillac_car.avif`,
  aston_martin: `${A}/astonmartin/astonmartin_car.avif`,
  haas: `${A}/haas/haas_car.avif`,
};

export const DRIVER_PHOTO: Record<string, string> = {
  antonelli: `${A}/mercedes/kimi_mercedes.png`,
  russell: `${A}/mercedes/mercedes_george.png`,
  leclerc: `${A}/ferrari/charles_ferrari.png`,
  hamilton: `${A}/ferrari/hamilton_ferrari.png`,
  norris: `${A}/mclaren/norris_mclaren.png`,
  piastri: `${A}/mclaren/piastri_mclaren.png`,
  max_verstappen: `${A}/red_bull/max_redbull.webp`,
  hadjar: `${A}/red_bull/hadjar_redbull.webp`,
  gasly: `${A}/alpine/gasly_alpine.webp`,
  colapinto: `${A}/alpine/colapinto_alpine.webp`,
  bearman: `${A}/haas/bearman_haas.webp`,
  ocon: `${A}/haas/ocon_haas.webp`,
  lawson: `${A}/racingbull/lawson_racingbulls.webp`,
  arvid_lindblad: `${A}/racingbull/lindblad_racingbulls.webp`,
  sainz: `${A}/williams/carloz_williams.webp`,
  albon: `${A}/williams/albon_williams.webp`,
  bortoleto: `${A}/audi/Bortoleto_audi.webp`,
  hulkenberg: `${A}/audi/hulkenberg_audi.webp`,
  bottas: `${A}/cadillac/bottas_cadillac.webp`,
  perez: `${A}/cadillac/perez_cadillac.webp`,
  stroll: `${A}/astonmartin/lanstroll_aston.png`,
  alonso: `${A}/astonmartin/alonso_aston.png`,
};

// Permanent car numbers (2026 grid). Drivers without a confirmed number are
// omitted, and the UI falls back to showing just the name.
export const DRIVER_NUMBER: Record<string, number> = {
  antonelli: 12,
  russell: 63,
  leclerc: 16,
  hamilton: 44,
  norris: 4,
  piastri: 81,
  max_verstappen: 33,
  hadjar: 6,
  gasly: 10,
  colapinto: 43,
  bearman: 87,
  ocon: 31,
  lawson: 30,
  arvid_lindblad: 41,
  sainz: 55,
  albon: 23,
  bortoleto: 5,
  hulkenberg: 27,
  bottas: 77,
  perez: 11,
  stroll: 18,
  alonso: 14,
};

// Career World Drivers' Championships (official F1 records). Jolpica can't be
// queried for all-season standings without a season param, so this is curated;
// drivers not listed have 0.
export const DRIVER_CHAMPIONSHIPS: Record<string, number> = {
  hamilton: 7,
  max_verstappen: 4,
  alonso: 2,
};

export function driverChampionships(driverId: string): number {
  return DRIVER_CHAMPIONSHIPS[driverId] ?? 0;
}

export function teamCar(teamId: string): string | null {
  return TEAM_CAR[teamId] ?? null;
}
export function driverPhoto(driverId: string): string | null {
  return DRIVER_PHOTO[driverId] ?? null;
}
// Background-removed transparent cutout (used for the Section 1 hero headshots).
export function driverPhotoCutout(driverId: string): string | null {
  const p = DRIVER_PHOTO[driverId];
  return p ? p.replace(/\.[a-z0-9]+$/i, "_nobg.png") : null;
}
export function driverNumber(driverId: string): number | null {
  return DRIVER_NUMBER[driverId] ?? null;
}
