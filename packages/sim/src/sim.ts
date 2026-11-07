// Pit Wall race simulation.
//
// A race is a pure function of (track, entries, seed). Integer maths only
// (milliseconds, per-mille), a seeded PRNG and no clocks, so every machine
// produces the same result. Bump SIM_VERSION whenever an output can change:
// old races must always be re-run with the version they were raced on.

import { createHash } from "node:crypto";

export const SIM_VERSION = "1.0.0";
export const REPLAY_VERSION = 1;

export type TrackType = "street" | "speed" | "mixed";
export const TRACK_TYPES: readonly TrackType[] = ["street", "speed", "mixed"];

/** Car designs, indexed the same way they are stored on-chain (u8). */
export const DESIGNS = ["high_downforce", "balanced", "low_drag"] as const;
/** Tyre compounds, indexed the same way they are stored on-chain (u8). */
export const TYRES = ["soft", "medium", "hard"] as const;

export interface Track {
  id: string;
  type: TrackType;
  laps: number;
  baseLapMs: number;
}

/** Driver skills, 0..100. */
export interface DriverStats {
  pace: number;
  racecraft: number;
  tyreManagement: number;
}

/** A setup as stored on-chain: every field is a small integer. */
export interface Setup {
  design: number; // index into DESIGNS
  tyre: number; // index into TYRES
  stops: number; // 1 or 2
  risk: number; // 0..100
}

export interface Entry {
  team: string;
  driver: DriverStats;
  setup: Setup;
}

export interface RaceInput {
  track: Track;
  entries: Entry[];
  /** 32-byte seed as 64 hex characters. */
  seedHex: string;
  /** Starting order from qualifying (entry indices, pole first). Omitted: everyone starts level. */
  grid?: number[];
}

/** Gap between grid slots at the start, in race milliseconds. */
export const GRID_GAP_MS = 300;

export type RaceEvent =
  | { lap: number; type: "pit"; team: number }
  | { lap: number; type: "overtake"; team: number; passed: number }
  | { lap: number; type: "retired"; team: number };

export interface Replay {
  replayVersion: number;
  simVersion: string;
  track: Track;
  teams: string[];
  /** laps[team][lap] = cumulative race time in ms after that lap; null once retired. */
  laps: (number | null)[][];
  /** Lap numbers (1-based) on which each team pits. */
  pitLaps: number[][];
  events: RaceEvent[];
  /** Team indices in finishing order (retired teams last, by laps completed). */
  order: number[];
  /** SHA-256 over the canonical result; posted on-chain. */
  resultHash: string;
}

// Lap-time effect of each design on each track type, ms per lap (negative = faster).
const DESIGN_FIT: Record<TrackType, readonly [number, number, number]> = {
  street: [-900, -300, 400],
  speed: [500, -250, -950],
  mixed: [-200, -450, -150],
};
// Per compound: base pace offset and wear added per lap of tyre age, ms.
const TYRE_PACE = [-700, 0, 550] as const;
const TYRE_WEAR = [95, 55, 30] as const;
const PIT_LOSS_MS = 21_000;

export function sha256Hex(data: string | Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

/** The commitment posted on-chain before setups lock: sha256 of the raw seed bytes. */
export function commitmentFor(seedHex: string): string {
  return sha256Hex(hexToBytes(seedHex));
}

export function hexToBytes(hex: string): Uint8Array {
  if (!/^[0-9a-f]{64}$/i.test(hex)) throw new Error("seed must be 32 bytes as 64 hex characters");
  return Uint8Array.from(hex.match(/../g)!.map((b) => parseInt(b, 16)));
}

/** xoshiro128** seeded from sha256(seed). Returns integers in [0, max). */
function makeRng(seedHex: string): (max: number) => number {
  const h = createHash("sha256").update("pitwall-rng").update(hexToBytes(seedHex)).digest();
  const s = new Uint32Array([h.readUInt32LE(0), h.readUInt32LE(4), h.readUInt32LE(8), h.readUInt32LE(12)]);
  const rotl = (x: number, k: number) => ((x << k) | (x >>> (32 - k))) >>> 0;
  return (max: number) => {
    const result = Math.imul(rotl(Math.imul(s[1], 5) >>> 0, 7), 9) >>> 0;
    const t = (s[1] << 9) >>> 0;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = rotl(s[3], 11);
    return result % max;
  };
}

export function pitLapsFor(stops: number, laps: number): number[] {
  return stops === 2 ? [Math.round(laps / 3), Math.round((2 * laps) / 3)] : [Math.round(laps / 2)];
}

function validate(input: RaceInput): void {
  const { track, entries } = input;
  if (!TRACK_TYPES.includes(track.type)) throw new Error(`unknown track type ${track.type}`);
  if (!Number.isInteger(track.laps) || track.laps < 1) throw new Error("laps must be a positive integer");
  if (entries.length < 2) throw new Error("a race needs at least 2 entries");
  for (const e of entries) {
    const { design, tyre, stops, risk } = e.setup;
    if (!(design in DESIGNS) || !(tyre in TYRES)) throw new Error(`invalid setup for ${e.team}`);
    if (stops !== 1 && stops !== 2) throw new Error(`stops must be 1 or 2 for ${e.team}`);
    if (!Number.isInteger(risk) || risk < 0 || risk > 100) throw new Error(`risk must be 0..100 for ${e.team}`);
  }
}

export function simulate(input: RaceInput): Replay {
  validate(input);
  const { track, entries, seedHex } = input;
  const next = makeRng(seedHex);
  const n = entries.length;
  const laps: (number | null)[][] = entries.map(() => []);
  const pitLaps = entries.map((e) => pitLapsFor(e.setup.stops, track.laps));
  const total = new Array<number>(n).fill(0);
  if (input.grid) {
    if (input.grid.length !== n || new Set(input.grid).size !== n || input.grid.some((i) => !(i >= 0 && i < n)))
      throw new Error("grid must list every entry once");
    input.grid.forEach((team, slot) => (total[team] = slot * GRID_GAP_MS));
  }
  const tyreAge = new Array<number>(n).fill(0);
  const retiredOn = new Array<number>(n).fill(0);
  const events: RaceEvent[] = [];
  let prevOrder = input.grid ? [...input.grid] : entries.map((_, i) => i);

  for (let lap = 1; lap <= track.laps; lap++) {
    for (let i = 0; i < n; i++) {
      if (retiredOn[i]) {
        laps[i].push(null);
        continue;
      }
      const { driver, setup } = entries[i];
      const wearMul = 1000 - driver.tyreManagement * 4; // better tyre management, less wear
      let t = track.baseLapMs;
      t -= driver.pace * 12;
      t += DESIGN_FIT[track.type][setup.design];
      t += TYRE_PACE[setup.tyre] + Math.floor((TYRE_WEAR[setup.tyre] * tyreAge[i] * wearMul) / 1000);
      t -= setup.risk * 6; // pushing is faster...
      t += next(400 + (100 - driver.racecraft) * 4); // ...racecraft keeps laps consistent
      if (next(1000) < Math.floor(setup.risk / 15)) {
        // ...but risk can end the race
        retiredOn[i] = lap;
        laps[i].push(null);
        events.push({ lap, type: "retired", team: i });
        continue;
      }
      if (pitLaps[i].includes(lap)) {
        t += PIT_LOSS_MS;
        tyreAge[i] = 0;
        events.push({ lap, type: "pit", team: i });
      } else {
        tyreAge[i]++;
      }
      total[i] += t;
      laps[i].push(total[i]);
    }
    const order = runningOrder(total, retiredOn, lap);
    for (let pos = 0; pos < order.length; pos++) {
      const team = order[pos];
      const before = prevOrder.indexOf(team);
      if (before > pos && !retiredOn[team]) {
        const passed = prevOrder[pos];
        if (!retiredOn[passed] || retiredOn[passed] === lap) events.push({ lap, type: "overtake", team, passed });
      }
    }
    prevOrder = order;
  }

  const order = runningOrder(total, retiredOn, track.laps + 1);
  const resultHash = sha256Hex(JSON.stringify({ simVersion: SIM_VERSION, order, laps }));
  return {
    replayVersion: REPLAY_VERSION,
    simVersion: SIM_VERSION,
    track,
    teams: entries.map((e) => e.team),
    laps,
    pitLaps,
    events,
    order,
    resultHash,
  };
}

/** Running teams by total time; retired teams after them, the later retirement first. */
function runningOrder(total: number[], retiredOn: number[], lap: number): number[] {
  const idx = total.map((_, i) => i);
  return idx.sort((a, b) => {
    const ra = retiredOn[a] && retiredOn[a] <= lap ? retiredOn[a] : 0;
    const rb = retiredOn[b] && retiredOn[b] <= lap ? retiredOn[b] : 0;
    if (!ra !== !rb) return ra ? 1 : -1;
    if (ra && rb) return rb - ra || a - b;
    return total[a] - total[b] || a - b;
  });
}
