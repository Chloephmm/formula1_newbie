// Per-constructor static metadata to fill the Ferrari-style team template for every team.
// Live position/points/wins come from Jolpica; these provide the design's other fields
// (base / chief / chassis / power unit) and the logo filename + accent color fallback.

export interface TeamMeta {
  fullName: string;
  base: string;
  chief: string;
  chassis: string;
  powerUnit: string;
  logo: string; // filename under /public/images/teams
}

export const TEAM_META: Record<string, TeamMeta> = {
  mercedes: { fullName: "Mercedes", base: "Brackley, UK", chief: "Toto Wolff", chassis: "W17", powerUnit: "Mercedes", logo: "mercedes.jpg" },
  ferrari: { fullName: "Scuderia Ferrari", base: "Maranello, Italy", chief: "Frédéric Vasseur", chassis: "SF-26", powerUnit: "Ferrari", logo: "ferrari.jpg" },
  mclaren: { fullName: "McLaren", base: "Woking, UK", chief: "Andrea Stella", chassis: "MCL40", powerUnit: "Mercedes", logo: "mclaren.jpg" },
  red_bull: { fullName: "Red Bull Racing", base: "Milton Keynes, UK", chief: "Laurent Mekies", chassis: "RB22", powerUnit: "Red Bull Ford", logo: "red_bull.png" },
  alpine: { fullName: "Alpine", base: "Enstone, UK", chief: "Flavio Briatore", chassis: "A526", powerUnit: "Mercedes", logo: "alpine.png" },
  rb: { fullName: "Racing Bulls", base: "Faenza, Italy", chief: "Alan Permane", chassis: "VCARB 03", powerUnit: "Red Bull Ford", logo: "rb.jpg" },
  williams: { fullName: "Williams", base: "Grove, UK", chief: "James Vowles", chassis: "FW48", powerUnit: "Mercedes", logo: "williams.jpg" },
  audi: { fullName: "Audi", base: "Hinwil, Switzerland", chief: "Jonathan Wheatley", chassis: "A26", powerUnit: "Audi", logo: "audi.png" },
  cadillac: { fullName: "Cadillac", base: "Silverstone, UK", chief: "Graeme Lowdon", chassis: "C26", powerUnit: "Ferrari", logo: "cadillac.jpg" },
  aston_martin: { fullName: "Aston Martin", base: "Silverstone, UK", chief: "Andy Cowell", chassis: "AMR26", powerUnit: "Honda", logo: "aston_martin.jpg" },
  haas: { fullName: "Haas", base: "Kannapolis, USA", chief: "Ayao Komatsu", chassis: "VF-26", powerUnit: "Ferrari", logo: "haas.jpg" },
};

export function teamLogo(id: string): string | null {
  const m = TEAM_META[id];
  return m ? `/images/teams/${m.logo}` : null;
}

// Per-team logo zoom/focal point for source images with extra padding or an
// off-centre mark. Used everywhere a logo sits in a circle (teams grid + the
// team-page lockup) so they stay consistent.
export const LOGO_CFG: Record<string, { scale?: number; pos?: string }> = {
  mercedes: { scale: 1.5 },
  alpine: { scale: 1.55, pos: "50% 58%" },
  aston_martin: { scale: 1.5 },
  cadillac: { scale: 1.5 },
};
