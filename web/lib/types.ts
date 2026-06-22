// Shared types for the F1 Guidebook frontend.

export interface Team {
  id: string;
  name: string;
  color: string;
  points: number;
  wins: number;
  drivers: string[]; // driver codes
}

export interface Driver {
  id: string;
  name: string;
  code: string;
  team: string; // team id
  nationality: string;
  wins: number;
  podiums: number;
  points: number;
}

export interface Race {
  season: number;
  round: number;
  name: string;
  circuit: string;
  date: string;
}

export interface ConstructorStanding {
  position: number;
  constructorId: string;
  name: string;
  points: number;
  wins: number;
}

export interface DriverStanding {
  position: number;
  driverId: string;
  code: string;
  givenName: string;
  familyName: string;
  nationality: string;
  points: number;
  wins: number;
  constructorId: string;
  constructorName: string;
}

export interface ScheduleRace {
  season: number;
  round: number;
  name: string;
  circuit: string;
  locality?: string;
  country?: string;
  date: string;
  time?: string;
}

// ---- Raw Jolpica/Ergast response shapes (only the fields we read) ----

interface ErgastDriver {
  driverId: string;
  code?: string;
  givenName: string;
  familyName: string;
  nationality: string;
}
interface ErgastConstructor {
  constructorId: string;
  name: string;
}
export interface ErgastConstructorStanding {
  position: string;
  points: string;
  wins: string;
  Constructor: ErgastConstructor;
}
export interface ErgastDriverStanding {
  position: string;
  points: string;
  wins: string;
  Driver: ErgastDriver;
  Constructors: ErgastConstructor[];
}
export interface ErgastResult {
  position: string;
  grid?: string;
  Driver: ErgastDriver;
  Constructor: ErgastConstructor;
  FastestLap?: { rank?: string };
}
export interface ErgastQualifying {
  position: string;
  Driver: ErgastDriver;
}
export interface ErgastRace {
  season: string;
  round: string;
  raceName: string;
  date: string;
  time?: string;
  Circuit: { circuitName: string; Location?: { locality?: string; country?: string } };
  Results?: ErgastResult[];
  QualifyingResults?: ErgastQualifying[];
}
export interface ErgastResponse {
  MRData: {
    total?: string;
    StandingsTable?: {
      StandingsLists?: Array<{
        ConstructorStandings?: ErgastConstructorStanding[];
        DriverStandings?: ErgastDriverStanding[];
      }>;
    };
    RaceTable?: { Races?: ErgastRace[] };
  };
}

// Aggregated per-driver season stats (keyed by 3-letter code).
export interface SeasonDriverStat {
  races: number;
  wins: number;
  podiums: number;
  poles: number;
  fastestLaps: number;
}

// Whole-career totals for a single driver.
export interface DriverCareer {
  races: number;
  wins: number;
  podiums: number;
  poles: number;
  fastestLaps: number;
}
