// Game content for the hackathon build: tracks, AI rival teams and their drivers.
// Fictional names only (no real F1 teams, drivers or circuits).

import type { Setup, Track } from "@pitwall/sim";

export const TRACKS: Track[] = [
  { id: "mtkvari", type: "mixed", laps: 24, baseLapMs: 72_000 },
  { id: "tbilisi-street", type: "street", laps: 24, baseLapMs: 92_000 },
  { id: "rustavi-speedway", type: "speed", laps: 24, baseLapMs: 84_000 },
  { id: "kutaisi-ring", type: "mixed", laps: 24, baseLapMs: 88_000 },
];

export const TRACK_NAMES: Record<string, string> = {
  mtkvari: "Mtkvari Circuit",
  "tbilisi-street": "Tbilisi Street Circuit",
  "rustavi-speedway": "Rustavi Speedway",
  "kutaisi-ring": "Kutaisi Ring",
};

export interface DriverSeed {
  driverId: number;
  name: string;
  rarity: number;
  pace: number;
  racecraft: number;
  tyreManagement: number;
  potential: number;
}

/** The player's starter driver. */
export const PLAYER_DRIVER: DriverSeed = { driverId: 1, name: "Nino Beridze", rarity: 0, pace: 64, racecraft: 72, tyreManagement: 68, potential: 82 };
export const PLAYER_TEAM = "Your Team";
/** Car colours in driven races (the client's Ui.TEAM_COLORS): the player is always brand red. */
export const PLAYER_COLOR = "#e8352b";

export interface Rival {
  team: string;
  driver: DriverSeed;
  /** Car colour on track. */
  color: string;
  /** How the AI picks a setup for a track type; deliberately imperfect. */
  pick: (trackType: Track["type"]) => Setup;
}

const best = { street: 0, speed: 2, mixed: 1 } as const;

export const RIVALS: Rival[] = [
  {
    team: "Kutaisi GP",
    color: "#f1efea",
    driver: { driverId: 101, name: "Giorgi Kapanadze", rarity: 1, pace: 76, racecraft: 60, tyreManagement: 52, potential: 85 },
    pick: () => ({ design: 2, tyre: 1, stops: 1, risk: 45 }), // always low drag
  },
  {
    team: "Batumi Motorsport",
    color: "#f2c230",
    driver: { driverId: 102, name: "Levan Tsereteli", rarity: 0, pace: 70, racecraft: 70, tyreManagement: 62, potential: 78 },
    pick: (t) => ({ design: best[t], tyre: 2, stops: 1, risk: 30 }), // right design, cautious
  },
  {
    team: "Rustavi Works",
    color: "#9aa0aa",
    driver: { driverId: 103, name: "Mariam Gelashvili", rarity: 0, pace: 66, racecraft: 58, tyreManagement: 76, potential: 74 },
    pick: () => ({ design: 0, tyre: 1, stops: 2, risk: 65 }), // aggressive downforce
  },
  {
    team: "Gori Autosport",
    color: "#c8a27a",
    driver: { driverId: 104, name: "Tamar Lomidze", rarity: 1, pace: 74, racecraft: 66, tyreManagement: 56, potential: 84 },
    pick: (t) => ({ design: 1, tyre: t === "speed" ? 1 : 0, stops: 2, risk: 50 }),
  },
  {
    team: "Mtskheta Racing",
    color: "#6f8fa8",
    driver: { driverId: 105, name: "Davit Abashidze", rarity: 0, pace: 60, racecraft: 76, tyreManagement: 80, potential: 70 },
    pick: () => ({ design: 1, tyre: 2, stops: 1, risk: 20 }), // steady
  },
];
