// Driven races: the player drives a 5-lap race against the AI field in the Godot
// client (RaceSim, whole-number physics). Before the client gets the race, the
// server commits the seed on Solana and enters all six cars; after the race it
// re-drives the whole race from the player's inputs with headless Godot and
// settles the verified result on-chain: reveal the seed, post the result hash,
// settle every finishing position (XP for every driver).
//
// Everything that varies per race (the AI field, the grid, the seed) is fixed
// at the start and stored in config.dataDir/driven/<raceId>.json, so the
// re-drive runs exactly the race the client got. The chain calls, the re-drive
// and the player lookups are injectable (setDeps), so tests need neither
// Solana nor Godot; the live ones are loaded lazily for the same reason.

import { createHash, createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { PublicKey } from "@solana/web3.js";
import { TRACK_TYPES } from "@pitwall/sim";
import type { ChainSetup } from "./chain.ts";
import { config } from "./config.ts";
import { PLAYER_COLOR, PLAYER_DRIVER, PLAYER_TEAM, RIVALS } from "./content.ts";
import { awardRaceFinish, carSpec, type Spec } from "./parts.ts";
import type { DriveSetup, DriveStats } from "./quali.ts";
import { redrive } from "./redrive.ts";

export const DRIVEN = { track: "mtkvari", trackType: "mixed", laps: 5, baseLapMs: 65_000, lapKm: 3.245 } as const;
/** The client's Profile defaults, for a player without a qualifying setup today and for every AI car. */
export const DEFAULT_SETUP: DriveSetup = { front_wing: 6, rear_wing: 6, brake_bias: 57, differential: 6 };
const PLAYER_CREW = 70;
const TICKS_PER_SECOND = 120;
const REALTIME_SLACK_S = 5;
/**
 * Seconds from creating the race to the lock. Entering (a second transaction)
 * must land before it: create + enter take about 2 s to confirm on devnet, so a
 * 2 s lock would reject the entries. The seed is revealed only after the race,
 * minutes later, so a longer lock costs nothing.
 */
const LOCK_SECONDS = 10;
/** A race must be finished within this long of its start (the seed is known from the start). */
const RACE_TTL_MS = 60 * 60_000;
const MAX_INPUTS = 2_000_000;

// ---------------------------------------------------------------- types

/** One car in RaceSim's entries format (game/sim/race_sim.gd `_init`); index 0 is the player. */
export interface RaceEntry {
  setup: DriveSetup;
  stats: DriveStats;
  car: Partial<Spec>;
  /** Pit crew skill 0..100. */
  crew: number;
  /** Starting tyre: 0 soft, 1 medium, 2 hard. */
  compound: number;
  /** AI only: share of the circuit's speed profile (per mille), the lap it pits on and the tyre it fits. */
  pace?: number;
  pit_lap?: number;
  pit_compound?: number;
}
export interface DriverLike {
  name: string;
  pace: number;
  racecraft: number;
  tyreManagement: number;
}
export interface CarResult {
  /** Race time in microseconds with penalties, -1 if the car had not finished. */
  raceUs: number;
  penaltyS: number;
  pitStops: number;
  laps: number;
}
/** What res://sim/redrive.gd prints for a race. */
export interface RedriveResult {
  physicsVersion: number;
  ticks: number;
  finished: boolean;
  /** Entry indices, winner first. */
  order: number[];
  cars: CarResult[];
  inputHash: string;
}

export type DrivenStatus = "starting" | "racing" | "verified" | "finished" | "failed";
export interface DrivenRace {
  raceId: number;
  player: string;
  track: string;
  laps: number;
  /** Hex. Given to the client at the start; the on-chain commitment proves it was fixed before the race. */
  seed: string;
  commitment: string;
  lockTs: number;
  /** When the client got the race (ms): the real-time check counts from here. */
  startedAt: number;
  entries: RaceEntry[];
  /** Entry indices in starting order, pole first. */
  grid: number[];
  names: string[];
  drivers: string[];
  colors: string[];
  /** On-chain team names and driver ids, in entry (= on-chain slot) order. */
  teams: string[];
  driverIds: number[];
  accounts: string[];
  status: DrivenStatus;
  txs: Record<string, string>;
  result?: RedriveResult & { resultHash: string; verifiedAt: number };
  packsEarned?: unknown[];
  error?: string;
}

export class DrivenError extends Error {
  status: number;
  details: Record<string, unknown>;
  constructor(status: number, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

// ---------------------------------------------------------------- pure part

const sha256 = (b: Buffer | string) => createHash("sha256").update(b).digest();
/** Same derivation as races.ts seedFor: nothing secret is stored between commit and reveal. */
export const raceSeed = (raceId: number): Buffer => createHmac("sha256", config.seedSecret).update(`race:${raceId}`).digest();

/** AI pace (per mille of the circuit's speed profile) from the driver's pace stat. */
export const aiPace = (pace: number) => Math.min(975, Math.max(900, 925 + (pace - 60) * 3));
/** Pit crew skill per team, 45..85, fixed by the team name. */
export const crewSkill = (team: string) => 45 + (sha256(`crew:${team}`).readUInt16LE(0) % 41);
/** Pace drives braking and cornering, tyre management is traction, racecraft is energy use (as for the player). */
export const statsOf = (d: DriverLike): DriveStats => ({ braking: d.pace, cornering: d.pace, traction: d.tyreManagement, energy: d.racecraft });

/** The six cars in RaceSim's format: the player, then the rivals in RIVALS order. */
export function buildEntries(p: {
  seed: Buffer;
  setup: DriveSetup;
  stats: DriveStats;
  car: Partial<Spec>;
  compound: number;
  rivals: { team: string; driver: DriverLike }[];
}): RaceEntry[] {
  const player: RaceEntry = { setup: { ...p.setup }, stats: { ...p.stats }, car: { ...p.car }, crew: PLAYER_CREW, compound: p.compound };
  const ai = p.rivals.map((r, k): RaceEntry => {
    const compound = k % 2; // soft and medium alternate down the field
    return {
      setup: { ...DEFAULT_SETUP },
      stats: statsOf(r.driver),
      car: {},
      pace: aiPace(r.driver.pace),
      crew: crewSkill(r.team),
      compound,
      pit_lap: 2 + (p.seed[4 + k] & 1), // lap 2 or 3, from the race seed
      pit_compound: compound === 0 ? 1 : 0, // the other compound (two-compound rule)
    };
  });
  return [player, ...ai];
}

/** Qualifying order (quali.gridOrder: "you" or AI team names) to entry indices; 0..n-1 when it does not cover the field. */
export function gridFromQuali(order: string[], teams: string[] = RIVALS.map((r) => r.team)): number[] {
  const n = teams.length + 1;
  const grid = order.map((name) => (name === "you" ? 0 : teams.indexOf(name) + 1 || -1));
  const ok = grid.length === n && grid.every((i) => i >= 0) && new Set(grid).size === n;
  return ok ? grid : Array.from({ length: n }, (_, i) => i);
}

/** The hash posted on-chain: sha256 of the JSON of the physics version, finishing order, race times and input hash. */
export function resultHash(r: Pick<RedriveResult, "physicsVersion" | "order" | "cars" | "inputHash">): string {
  const json = JSON.stringify({ physicsVersion: r.physicsVersion, order: r.order, raceUs: r.cars.map((c) => c.raceUs), inputHash: r.inputHash });
  return sha256(json).toString("hex");
}

/** The on-chain entry for each car: the program's strategy fields, with the starting tyre. */
export const chainSetups = (entries: RaceEntry[], teams: string[], accounts: PublicKey[]): ChainSetup[] =>
  entries.map((e, i) => ({ driver: accounts[i], team: teams[i], design: 1, tyre: e.compound, stops: 1, risk: 0 }));

// ---------------------------------------------------------------- dependencies

export interface DrivenDeps {
  createRace(raceId: number, p: { trackType: number; laps: number; baseLapMs: number; commitment: Buffer; lockTs: number }): Promise<string>;
  enterAll(raceId: number, setups: ChainSetup[]): Promise<string>;
  revealSeed(raceId: number, seed: Buffer): Promise<string>;
  postResult(raceId: number, resultHash: Buffer): Promise<string>;
  settleAll(raceId: number, positions: { driver: PublicKey; position: number }[]): Promise<string>;
  driverAccount(driverId: number): PublicKey;
  /** On-chain driver stats (they grow with XP); null when the account does not exist. */
  fetchDriver(driverId: number): Promise<{ pace: number; racecraft: number; tyreManagement: number } | null>;
  playerStats(): Promise<DriveStats>;
  qualiSetup(player: string): DriveSetup | undefined;
  gridOrder(player: string): string[];
  carSpec(player: string): Partial<Spec>;
  redrive(job: object): Promise<RedriveResult>;
  awardRaceFinish(player: string, raceId: number, result: { km: number; won: boolean }): { pack?: unknown };
  now(): number;
  sleep(ms: number): Promise<void>;
}

async function liveDeps(): Promise<DrivenDeps> {
  const chain = await import("./chain.ts");
  const quali = await import("./quali.ts");
  return {
    createRace: chain.createRace,
    enterAll: chain.enterAll,
    revealSeed: chain.revealSeed,
    postResult: chain.postResult,
    settleAll: chain.settleAll,
    driverAccount: (id) => chain.pda.driver(id),
    fetchDriver: (id) => chain.fetchDriver(id),
    playerStats: async () => (await quali.driverStats()).stats,
    qualiSetup: quali.qualiSetup,
    gridOrder: quali.gridOrder,
    carSpec,
    // a whole race with six cars takes several seconds to re-drive
    redrive: (job) => redrive<RedriveResult>(job, 180_000),
    awardRaceFinish,
    now: () => Date.now(),
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  };
}

let deps: DrivenDeps | Promise<DrivenDeps> | undefined;
/** Replaces the chain, Godot and player lookups (tests); undefined goes back to the live ones. */
export function setDeps(d: DrivenDeps | undefined) {
  deps = d;
}
const getDeps = async () => (deps ??= liveDeps());

// ---------------------------------------------------------------- store

const dir = join(config.dataDir, "driven");
mkdirSync(join(dir, "inputs"), { recursive: true });
const races = new Map<number, DrivenRace>();

function save(s: DrivenRace) {
  races.set(s.raceId, s);
  writeFileSync(join(dir, `${s.raceId}.json`), JSON.stringify(s));
}

export function getDrivenRace(raceId: number): DrivenRace | undefined {
  if (!Number.isSafeInteger(raceId)) return undefined;
  const cached = races.get(raceId);
  if (cached) return cached;
  const file = join(dir, `${raceId}.json`);
  if (!existsSync(file)) return undefined;
  const s = JSON.parse(readFileSync(file, "utf8")) as DrivenRace;
  races.set(raceId, s);
  return s;
}

/** The player's recorded inputs of a verified race, so anyone can re-drive it. */
export function drivenInputs(raceId: number): string | undefined {
  const file = join(dir, "inputs", `${raceId}.txt`);
  return getDrivenRace(raceId)?.result && existsSync(file) ? readFileSync(file, "utf8") : undefined;
}

// ---------------------------------------------------------------- start

export async function startDrivenRace(player: string, opts: { compound?: unknown; name?: unknown } = {}) {
  if (!/^[0-9a-f]{16,64}$/.test(player)) throw new DrivenError(400, "bad player id");
  const compound = opts.compound === undefined || opts.compound === null ? 0 : Number(opts.compound);
  if (![0, 1, 2].includes(compound)) throw new DrivenError(400, "compound must be 0 (soft), 1 (medium) or 2 (hard)");
  const d = await getDeps();

  let raceId = d.now();
  while (getDrivenRace(raceId)) raceId++;
  const seed = raceSeed(raceId);
  const [stats, onChain] = await Promise.all([
    d.playerStats(),
    Promise.all(RIVALS.map((r) => d.fetchDriver(r.driver.driverId).catch(() => null))),
  ]);
  // rivals drive with their on-chain stats (they level up), or the starter values when offline
  const rivals = RIVALS.map((r, k) => {
    const c = onChain[k];
    return { team: r.team, driver: { name: r.driver.name, pace: c?.pace ?? r.driver.pace, racecraft: c?.racecraft ?? r.driver.racecraft, tyreManagement: c?.tyreManagement ?? r.driver.tyreManagement } };
  });
  const entries = buildEntries({ seed, setup: d.qualiSetup(player) ?? DEFAULT_SETUP, stats, car: d.carSpec(player), compound, rivals });
  const driverIds = [PLAYER_DRIVER.driverId, ...RIVALS.map((r) => r.driver.driverId)];
  const accounts = driverIds.map((id) => d.driverAccount(id));
  const teams = [PLAYER_TEAM, ...RIVALS.map((r) => r.team)];
  const name = typeof opts.name === "string" && opts.name.trim() ? opts.name.trim().slice(0, 24) : "You";
  const s: DrivenRace = {
    raceId,
    player,
    track: DRIVEN.track,
    laps: DRIVEN.laps,
    seed: seed.toString("hex"),
    commitment: sha256(seed).toString("hex"),
    lockTs: Math.floor(raceId / 1000) + LOCK_SECONDS,
    startedAt: 0,
    entries,
    grid: gridFromQuali(d.gridOrder(player)),
    names: [name, ...RIVALS.map((r) => r.team)],
    drivers: [PLAYER_DRIVER.name, ...RIVALS.map((r) => r.driver.name)],
    colors: [PLAYER_COLOR, ...RIVALS.map((r) => r.color)],
    teams,
    driverIds,
    accounts: accounts.map((a) => a.toBase58()),
    status: "starting",
    txs: {},
  };
  try {
    s.txs.create = await d.createRace(raceId, {
      trackType: TRACK_TYPES.indexOf(DRIVEN.trackType),
      laps: s.laps,
      baseLapMs: DRIVEN.baseLapMs,
      commitment: sha256(seed),
      lockTs: s.lockTs,
    });
    s.txs.enter = await d.enterAll(raceId, chainSetups(entries, teams, accounts));
  } catch (err) {
    s.status = "failed";
    s.error = String((err as Error).message ?? err).slice(0, 300);
    save(s);
    throw err;
  }
  s.startedAt = d.now();
  s.status = "racing";
  save(s);
  return {
    raceId,
    track: s.track,
    seed: s.seed,
    commitment: s.commitment,
    lockTs: s.lockTs,
    entries: s.entries,
    grid: s.grid,
    laps: s.laps,
    names: s.names,
    drivers: s.drivers,
    colors: s.colors,
    txs: { create: s.txs.create, enter: s.txs.enter },
  };
}

// ---------------------------------------------------------------- finish

function finishView(s: DrivenRace) {
  const r = s.result!;
  return {
    raceId: s.raceId,
    verified: true,
    physicsVersion: r.physicsVersion,
    ticks: r.ticks,
    order: r.order,
    cars: r.cars.map((c, i) => ({ entry: i, position: r.order.indexOf(i) + 1, name: s.names[i], driver: s.drivers[i], color: s.colors[i], ...c })),
    inputHash: r.inputHash,
    resultHash: r.resultHash,
    txs: { create: s.txs.create, enter: s.txs.enter, reveal: s.txs.reveal, result: s.txs.result, settle: s.txs.settle },
    packsEarned: s.packsEarned ?? [],
  };
}
export type FinishView = ReturnType<typeof finishView>;

const finishing = new Map<number, Promise<FinishView>>();

/**
 * Verifies a driven race from the player's input log and settles it on-chain.
 * Idempotent: once verified, the stored result stands (later logs are ignored),
 * a failed chain step is retried by calling again, and a finished race returns
 * its stored result.
 */
export function finishDrivenRace(raceId: number, inputs: unknown): Promise<FinishView> {
  const running = finishing.get(raceId);
  if (running) return running;
  const task = finish(raceId, inputs).finally(() => finishing.delete(raceId));
  finishing.set(raceId, task);
  return task;
}

async function finish(raceId: number, inputs: unknown): Promise<FinishView> {
  const s = getDrivenRace(raceId);
  if (!s) throw new DrivenError(404, "unknown race");
  if (s.status === "finished") return finishView(s);
  if (!s.startedAt) throw new DrivenError(409, `race did not start${s.error ? `: ${s.error}` : ""}`);
  const d = await getDeps();

  if (!s.result) {
    if (typeof inputs !== "string" || !inputs || inputs.length > MAX_INPUTS) throw new DrivenError(400, "bad inputs");
    const submittedAt = d.now();
    if (submittedAt - s.startedAt > RACE_TTL_MS) throw new DrivenError(400, "race expired");
    const out = await d.redrive({ track: s.track, kind: "race", seed: s.seed, inputs, entries: s.entries, grid: s.grid, laps: s.laps });
    // The race must have been driven in real time: no more ticks than seconds since the client got it
    const elapsedTicks = ((submittedAt - s.startedAt) / 1000 + REALTIME_SLACK_S) * TICKS_PER_SECOND;
    if (config.realtimeCheck && out.ticks > elapsedTicks) throw new DrivenError(400, "race is longer than the time since it started");
    if (!out.finished) throw new DrivenError(400, "the race was not finished in the input log");
    const { physicsVersion, ticks, finished, order, cars, inputHash } = out;
    s.result = { physicsVersion, ticks, finished, order, cars, inputHash, resultHash: resultHash(out), verifiedAt: d.now() };
    s.status = "verified";
    writeFileSync(join(dir, "inputs", `${raceId}.txt`), inputs);
    save(s);
  }
  const result = s.result;

  try {
    if (!s.txs.reveal) {
      s.txs.reveal = await revealWhenLocked(d, s);
      save(s);
    }
    if (!s.txs.result) {
      s.txs.result = await d.postResult(raceId, Buffer.from(result.resultHash, "hex"));
      save(s);
    }
    if (!s.txs.settle) {
      s.txs.settle = await d.settleAll(
        raceId,
        result.order.map((entry, i) => ({ driver: d.driverAccount(s.driverIds[entry]), position: i + 1 })),
      );
      save(s);
    }
  } catch (err) {
    s.error = String((err as Error).message ?? err).slice(0, 300);
    save(s);
    throw new DrivenError(502, `race verified, but settling it on Solana failed (finish again to retry): ${s.error}`, { verified: true, retry: true, order: result.order });
  }

  // finishing a race earns a development pack (and puts the race on the fitted parts)
  const award = d.awardRaceFinish(s.player, raceId, { km: Math.round(s.laps * DRIVEN.lapKm), won: result.order[0] === 0 });
  s.packsEarned = award.pack ? [award.pack] : [];
  s.status = "finished";
  delete s.error;
  save(s);
  console.log(`driven race ${raceId} finished: ${result.order.map((i) => s.names[i]).join(", ")}`);
  return finishView(s);
}

/** The program reveals only once the lock has passed, and the chain clock can trail ours a little. */
async function revealWhenLocked(d: DrivenDeps, s: DrivenRace): Promise<string> {
  const wait = (s.lockTs + 1) * 1000 - d.now();
  if (wait > 0) await d.sleep(wait);
  for (let attempt = 0; ; attempt++) {
    try {
      return await d.revealSeed(s.raceId, Buffer.from(s.seed, "hex"));
    } catch (err) {
      if (attempt >= 10 || !/RaceNotLocked|not locked/i.test(String((err as Error).message ?? err))) throw err;
      await d.sleep(2000);
    }
  }
}
