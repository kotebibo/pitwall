// Qualifying: players drive laps in the Godot client; the server re-drives each
// run from its input log with the same physics (headless Godot), keeps every
// player's verified best lap and records it on Solana.

import { createHash, createHmac, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { accountName, isAccountName } from "./accounts.ts";
import * as chain from "./chain.ts";
import { config } from "./config.ts";
import { PLAYER_DRIVER, RIVALS } from "./content.ts";
import { awardPack, carSpec, setEquipLockCheck, zeroSpec, type Spec } from "./parts.ts";
import { hasOpenPass, recordPassLap } from "./passes.ts";
import { redrive } from "./redrive.ts";

export const CIRCUIT = { id: "mtkvari", name: "Mtkvari Circuit", index: 0 };
const DAY_MS = 86_400_000;
const ATTEMPT_TTL_MS = 30 * 60_000;
const TICKS_PER_SECOND = 120;

export interface DriveSetup {
  front_wing: number;
  rear_wing: number;
  brake_bias: number;
  differential: number;
}
export interface DriveStats {
  braking: number;
  cornering: number;
  traction: number;
  energy: number;
}
interface Lap {
  lap: number;
  us: number;
  valid: boolean;
  sectors: number[];
  ticks: number[];
}
interface Attempt {
  id: string;
  player: string;
  session: "practice" | "qualifying" | "pass";
  seed: string;
  setup: DriveSetup;
  stats: DriveStats;
  /** Parts spec at the start of the attempt (parts.ts carSpec); missing on attempts made before parts existed. */
  car?: Spec;
  createdAt: number;
  best?: Lap;
}
interface PlayerBest {
  name: string;
  setup?: DriveSetup;
  /** Parts spec frozen at the first qualifying run (parc fermé); practice uses the current garage. */
  car?: Record<string, number>;
  best?: { us: number; sectors: number[]; attempt: string; lap: number; inputHash: string; at: number };
  tx?: string;
  chainError?: string;
  laps: number;
}
interface EventState {
  eventId: number;
  players: Record<string, PlayerBest>;
  attempts: Record<string, Attempt>;
}

const dir = join(config.dataDir, "quali");
mkdirSync(join(dir, "inputs"), { recursive: true });
const events = new Map<number, EventState>();

export const currentEventId = () => Math.floor(Date.now() / DAY_MS);

/** Parc fermé: true once the player's first qualifying run of today's event has locked their setup (and parts). */
export const setupLocked = (player: string) => Boolean(load(currentEventId()).players[player]?.setup);
/** The setup the player locked for today's qualifying, if they have run qualifying (races use it too). */
export const qualiSetup = (player: string): DriveSetup | undefined => load(currentEventId()).players[player]?.setup;
// Parts can be swapped any time and tried in practice; qualifying keeps the car frozen at the first run.
setEquipLockCheck(() => false);

function load(eventId: number): EventState {
  const cached = events.get(eventId);
  if (cached) return cached;
  const file = join(dir, `${eventId}.json`);
  const s: EventState = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : { eventId, players: {}, attempts: {} };
  events.set(eventId, s);
  return s;
}
function save(s: EventState) {
  writeFileSync(join(dir, `${s.eventId}.json`), JSON.stringify(s));
}

export function validateDriveSetup(s: Partial<DriveSetup> | undefined): DriveSetup {
  const pick = (v: unknown, lo: number, hi: number, name: string) => {
    const n = Number(v);
    if (!Number.isInteger(n) || n < lo || n > hi) throw new Error(`${name} must be ${lo}..${hi}`);
    return n;
  };
  return {
    front_wing: pick(s?.front_wing ?? 6, 1, 11, "front_wing"),
    rear_wing: pick(s?.rear_wing ?? 6, 1, 11, "rear_wing"),
    brake_bias: pick(s?.brake_bias ?? 57, 50, 64, "brake_bias"),
    differential: pick(s?.differential ?? 6, 1, 11, "differential"),
  };
}
const sameSetup = (a: DriveSetup, b: DriveSetup) =>
  a.front_wing === b.front_wing && a.rear_wing === b.rear_wing && a.brake_bias === b.brake_bias && a.differential === b.differential;

/** Driving stats come from the driver's on-chain record. */
let statsCache: { at: number; stats: DriveStats; name: string; address: string; level: number } | undefined;
export async function driverStats() {
  if (statsCache && Date.now() - statsCache.at < 60_000) return statsCache;
  let pace = PLAYER_DRIVER.pace;
  let racecraft = PLAYER_DRIVER.racecraft;
  let tyre = PLAYER_DRIVER.tyreManagement;
  let level = 1;
  try {
    const d = await chain.fetchDriver(PLAYER_DRIVER.driverId);
    if (d) ({ pace, racecraft, tyreManagement: tyre, level } = d);
  } catch {
    // offline: starter values
  }
  statsCache = {
    at: Date.now(),
    name: PLAYER_DRIVER.name,
    address: chain.pda.driver(PLAYER_DRIVER.driverId).toBase58(),
    level,
    // Pace drives braking and cornering; tyre management is traction; racecraft is energy use.
    stats: { braking: pace, cornering: pace, traction: tyre, energy: racecraft },
  };
  return statsCache;
}

const playerKey = (player: string) => createHash("sha256").update(`pitwall-player:${player}`).digest();

export async function startAttempt(player: string, name: string, session: string, setupIn: Partial<DriveSetup>) {
  if (!/^[0-9a-f]{16,64}$/.test(player)) throw new Error("bad player id");
  const s = load(currentEventId());
  const setup = validateDriveSetup(setupIn);
  const kind = session === "practice" ? "practice" : session === "pass" ? "pass" : "qualifying";
  if (kind === "pass" && !hasOpenPass(player)) {
    throw Object.assign(new Error("buy a race pass first"), { status: 409 });
  }
  // Account players run under their account name; guests under the team name their client sends
  name = accountName(player) ?? name.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  const p = (s.players[player] ??= { name: name.slice(0, 24) || "Player", laps: 0 });
  if (name) p.name = name.slice(0, 24);
  if (kind === "qualifying") {
    // Parc fermé: the first qualifying run locks the setup for the weekend
    if (p.setup && !sameSetup(p.setup, setup)) {
      const err = new Error("setup locked for qualifying") as Error & { status?: number; setup?: DriveSetup };
      err.status = 409;
      err.setup = p.setup;
      throw err;
    }
    p.setup = setup;
  }
  const id = randomBytes(8).toString("hex");
  const seed = createHmac("sha256", config.seedSecret).update(`attempt:${id}`).digest("hex");
  const { stats } = await driverStats();
  // race passes are run on equal cars: the standard car for everyone
  let car = kind === "pass" ? zeroSpec() : carSpec(player);
  if (kind === "qualifying") {
    p.car ??= car;
    car = p.car;
  }
  s.attempts[id] = { id, player, session: kind, seed, setup, stats, car, createdAt: Date.now() };
  save(s);
  return { attempt: id, seed, setup, stats, car, eventId: s.eventId };
}

export async function submitRun(attemptId: string, inputs: string) {
  const s = load(currentEventId());
  const a = s.attempts[attemptId];
  if (!a) throw new Error("unknown attempt");
  if (Date.now() - a.createdAt > ATTEMPT_TTL_MS) throw new Error("attempt expired");
  if (typeof inputs !== "string" || inputs.length > 2_000_000) throw new Error("bad inputs");
  const result = await redrive<{ physicsVersion: number; ticks: number; laps: Lap[]; inputHash: string }>({ track: CIRCUIT.id, setup: a.setup, stats: a.stats, car: a.car ?? zeroSpec(), seed: a.seed, inputs, kind: a.session === "pass" ? "qualifying" : a.session });
  // A run must have been driven in real time: no more ticks than seconds since the seed was issued
  const elapsedTicks = ((Date.now() - a.createdAt) / 1000 + 3) * TICKS_PER_SECOND;
  if (config.realtimeCheck && result.ticks > elapsedTicks) throw new Error("run is longer than the time since it started");

  const valid = result.laps.filter((l) => l.valid);
  const best = valid.sort((x, y) => x.us - y.us)[0];
  const p = s.players[a.player];
  let personalBest = false;
  if (best && (!a.best || best.us < a.best.us)) a.best = best;
  if (best && a.session === "qualifying") {
    p.laps += valid.length;
    if (!p.best || best.us < p.best.us) {
      personalBest = true;
      p.best = { us: best.us, sectors: best.sectors, attempt: a.id, lap: best.lap, inputHash: result.inputHash, at: Date.now() };
      writeFileSync(join(dir, "inputs", `${a.id}.txt`), inputs);
      recordOnChain(s, a.player, p, result.physicsVersion);
    }
  }
  let pass: ReturnType<typeof recordPassLap> = [];
  if (best && a.session === "pass") {
    pass = recordPassLap(a.player, { us: best.us, attempt: a.id, inputHash: result.inputHash });
    writeFileSync(join(dir, "inputs", `${a.id}.txt`), inputs);
  }
  save(s);
  const position = leaderboard(s).findIndex((r) => r.player === a.player) + 1;
  // Packs are earned by verified driving: the first qualifying run of the day that
  // completes a lap, and a top-3 qualifying time (each once per event)
  const packsEarned: unknown[] = [];
  if (a.session === "qualifying" && result.laps.length > 0) {
    const first = awardPack(a.player, "first_quali", String(s.eventId));
    if (first.pack) packsEarned.push(first.pack);
    if (best && position > 0 && position <= 3) {
      const top = awardPack(a.player, "quali_top3", String(s.eventId));
      if (top.pack) packsEarned.push(top.pack);
    }
  }
  return {
    verified: true,
    physicsVersion: result.physicsVersion,
    laps: result.laps,
    best: best ?? null,
    personalBest,
    position,
    packsEarned,
    pass,
  };
}

function recordOnChain(s: EventState, player: string, p: PlayerBest, physicsVersion: number) {
  const best = p.best!;
  chain
    .submitLap(s.eventId, playerKey(player), {
      circuit: CIRCUIT.index,
      physicsVersion,
      lapUs: best.us,
      inputHash: Buffer.from(best.inputHash, "hex"),
    })
    .then((tx) => {
      if (p.best === best) {
        p.tx = tx;
        p.chainError = undefined;
        save(s);
      }
    })
    .catch((err) => {
      p.chainError = String((err as Error).message ?? err).slice(0, 200);
      save(s);
      console.error("submitLap failed:", p.chainError);
    });
}

/** AI rivals set a qualifying time from their pace, slightly different each day. */
function rivalTimes(eventId: number) {
  return RIVALS.map((r) => {
    const h = createHash("sha256").update(`rival:${eventId}:${r.team}`).digest();
    // Calibrated to the physics (v3): a tidy lap of Mtkvari is 1:04 to 1:06.
    const us = 65_400_000 - (r.driver.pace - 60) * 60_000 + (h.readUInt16LE(0) % 700) * 1000;
    return { player: `ai:${r.team}`, name: r.driver.name, team: r.team, us, ai: true };
  });
}

/** Account players show their account name; a guest using an account's name is marked as a guest. */
function displayName(player: string, stored: string): string {
  return accountName(player) ?? (isAccountName(stored) ? `${stored} (guest)` : stored);
}

/** The timesheet with player ids (server side only: a guest's id is all it takes to act as that guest). */
export function leaderboard(s: EventState) {
  const humans = Object.entries(s.players)
    .filter(([, p]) => p.best)
    .map(([player, p]) => {
      const name = displayName(player, p.name);
      return { player, name, team: name, us: p.best!.us, sectors: p.best!.sectors, attempt: p.best!.attempt, tx: p.tx, ai: false };
    });
  return [...humans, ...rivalTimes(s.eventId)].sort((a, b) => a.us - b.us).map((r, i) => ({ position: i + 1, ...r }));
}

/** A timesheet row as the API shows it: `you` marks the asking player's row instead of a player id (AI rows keep theirs). */
function publicRow(r: ReturnType<typeof leaderboard>[number], player: string) {
  if (r.ai) return { ...r, you: false };
  const { player: id, ...row } = r;
  return { ...row, you: player !== "" && id === player };
}

/** The player id an attempt belongs to (today's event), if the attempt exists. */
export const attemptPlayer = (attemptId: string): string | undefined => load(currentEventId()).attempts[attemptId]?.player;

export async function eventInfo(player: string) {
  const s = load(currentEventId());
  const driver = await driverStats();
  const p = s.players[player];
  const board = leaderboard(s);
  return {
    eventId: s.eventId,
    circuit: CIRCUIT.id,
    circuitName: CIRCUIT.name,
    closesAt: (s.eventId + 1) * DAY_MS,
    driver: { name: driver.name, address: driver.address, level: driver.level, stats: driver.stats },
    you: {
      setupLocked: Boolean(p?.setup),
      setup: p?.setup ?? null,
      bestUs: p?.best?.us ?? null,
      position: board.findIndex((r) => r.player === player) + 1 || null,
      tx: p?.tx ?? null,
      chainError: p?.chainError ?? null,
    },
    leaderboard: board.slice(0, 12).map((r) => publicRow(r, player)),
  };
}

/** Everything needed to re-drive a lap in the client and show it as a ghost. */
export function ghost(attemptId: string) {
  const s = load(currentEventId());
  const a = s.attempts[attemptId];
  const file = join(dir, "inputs", `${attemptId}.txt`);
  if (!a || !existsSync(file)) throw new Error("no ghost for that attempt");
  return { setup: a.setup, stats: a.stats, car: a.car ?? zeroSpec(), seed: a.seed, inputs: readFileSync(file, "utf8"), lap: a.best ?? null, name: displayName(a.player, s.players[a.player]?.name ?? "") };
}

/** Grid for the race: qualifying order of the player and the AI teams. */
export function gridOrder(player: string | undefined): string[] {
  const s = load(currentEventId());
  return leaderboard(s)
    .filter((r) => r.ai || r.player === player)
    .map((r) => (r.ai ? r.team : "you"));
}
