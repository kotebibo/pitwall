// Race lifecycle: create on-chain with a seed commitment, enter setups, then after
// the lock reveal the seed, simulate, post the result hash and settle positions.

import { createHash, createHmac } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { simulate, SIM_VERSION, TRACK_TYPES, type Entry, type Replay, type Setup, type Track } from "@pitwall/sim";
import * as chain from "./chain.ts";
import { config } from "./config.ts";
import { PLAYER_DRIVER, PLAYER_TEAM, RIVALS, TRACKS, TRACK_NAMES } from "./content.ts";
import { awardRaceFinish } from "./parts.ts";
import { gridOrder } from "./quali.ts";

export type RaceStatus = "open" | "locked" | "revealed" | "finished" | "failed";

export interface RaceState {
  raceId: number;
  trackId: string;
  trackName: string;
  lockTs: number;
  commitment: string;
  status: RaceStatus;
  teams: string[];
  setups: Setup[];
  playerSlot: number;
  txs: Record<string, string>;
  replay?: Replay;
  error?: string;
  /** Who raced (for packs) and the starting order from qualifying (entry slots, pole first). */
  player?: string;
  grid?: number[];
}

const races = new Map<number, RaceState>();
const dir = join(config.dataDir, "races");
mkdirSync(dir, { recursive: true });

function save(s: RaceState) {
  races.set(s.raceId, s);
  writeFileSync(join(dir, `${s.raceId}.json`), JSON.stringify(s));
}

export function getRace(raceId: number): RaceState | undefined {
  if (races.has(raceId)) return races.get(raceId);
  const file = join(dir, `${raceId}.json`);
  if (!existsSync(file)) return undefined;
  const s = JSON.parse(readFileSync(file, "utf8")) as RaceState;
  races.set(raceId, s);
  return s;
}

/** Seeds come from a server secret, so nothing has to be stored between commit and reveal. */
export function seedFor(raceId: number): Buffer {
  return createHmac("sha256", config.seedSecret).update(`race:${raceId}`).digest();
}
const sha256 = (b: Buffer) => createHash("sha256").update(b).digest();

/** On first run: Config account plus every driver used in races. */
export async function bootstrap(): Promise<void> {
  await chain.ensureConfig();
  await chain.ensureDriver(PLAYER_DRIVER, chain.authority.publicKey);
  for (const r of RIVALS) await chain.ensureDriver(r.driver, chain.authority.publicKey);
}

export function validateSetup(s: Partial<Setup>): Setup {
  const setup = { design: Number(s.design), tyre: Number(s.tyre), stops: Number(s.stops), risk: Number(s.risk) };
  const ok =
    [0, 1, 2].includes(setup.design) &&
    [0, 1, 2].includes(setup.tyre) &&
    [1, 2].includes(setup.stops) &&
    Number.isInteger(setup.risk) &&
    setup.risk >= 0 &&
    setup.risk <= 100;
  if (!ok) throw new Error("invalid setup");
  return setup;
}

export async function startRace(trackId: string, playerSetup: Setup, player?: string): Promise<RaceState> {
  const track = TRACKS.find((t) => t.id === trackId) ?? TRACKS[0];
  const raceId = Date.now();
  const seed = seedFor(raceId);
  const lockTs = Math.floor(Date.now() / 1000) + config.lockSeconds;
  const state: RaceState = {
    raceId,
    trackId: track.id,
    trackName: TRACK_NAMES[track.id],
    lockTs,
    commitment: sha256(seed).toString("hex"),
    status: "open",
    teams: [],
    setups: [],
    playerSlot: 0,
    txs: {},
  };
  state.txs.create = await chain.createRace(raceId, {
    trackType: TRACK_TYPES.indexOf(track.type),
    laps: track.laps,
    baseLapMs: track.baseLapMs,
    commitment: sha256(seed),
    lockTs,
  });

  const setups: chain.ChainSetup[] = [
    { driver: chain.pda.driver(PLAYER_DRIVER.driverId), team: PLAYER_TEAM, ...playerSetup },
    ...RIVALS.map((r) => ({ driver: chain.pda.driver(r.driver.driverId), team: r.team, ...r.pick(track.type) })),
  ];
  state.txs.enter = await chain.enterAll(raceId, setups);
  state.teams = setups.map((s) => s.team);
  state.setups = setups.map(({ design, tyre, stops, risk }) => ({ design, tyre, stops, risk }));
  // Start where qualifying put everyone (your verified lap against the AI teams' times)
  if (player) {
    state.player = player;
    const grid = gridOrder(player).map((name) => (name === "you" ? state.playerSlot : state.teams.indexOf(name)));
    if (grid.length === state.teams.length && grid.every((i) => i >= 0)) state.grid = grid;
  }
  save(state);

  const wait = Math.max(0, lockTs * 1000 - Date.now()) + 1500;
  setTimeout(() => void finishRace(raceId), wait);
  return state;
}

/** Rebuilds the sim input purely from on-chain data: anyone can do this. */
export async function raceInputFromChain(raceId: number) {
  const race = await chain.fetchRace(raceId);
  if (!race) throw new Error(`race ${raceId} not found on-chain`);
  const entries = await chain.fetchEntries(raceId);
  const track: Track = {
    id: TRACK_TYPES[race.trackType],
    type: TRACK_TYPES[race.trackType],
    laps: race.laps,
    baseLapMs: race.baseLapMs,
  };
  const simEntries: Entry[] = entries.map((e) => ({
    team: chain.bytesToName(e.teamName),
    driver: { pace: e.pace, racecraft: e.racecraft, tyreManagement: e.tyreManagement },
    setup: { design: e.design, tyre: e.tyre, stops: e.stops, risk: e.risk },
  }));
  return { race, entries, track, simEntries };
}

async function finishRace(raceId: number, attempt = 0): Promise<void> {
  const state = getRace(raceId);
  if (!state || state.status === "finished") return;
  try {
    if (state.status === "open") {
      state.status = "locked";
      const seed = seedFor(raceId);
      state.txs.reveal = await chain.revealSeed(raceId, seed);
      state.status = "revealed";
      save(state);
    }
    const { entries, track, simEntries } = await raceInputFromChain(raceId);
    const replay = simulate({ track: { ...track, id: state.trackId }, entries: simEntries, seedHex: seedFor(raceId).toString("hex"), grid: state.grid });
    state.txs.result = await chain.postResult(raceId, Buffer.from(replay.resultHash, "hex"));
    state.txs.settle = await chain.settleAll(
      raceId,
      replay.order.map((slot, i) => ({ driver: entries[slot].driver, position: i + 1 })),
    );
    state.replay = replay;
    state.status = "finished";
    if (state.player) {
      // finishing a race earns a development pack (and mileage on the fitted parts)
      const finished = !(replay.laps[state.playerSlot] ?? []).includes(null);
      if (finished) awardRaceFinish(state.player, raceId, { km: Math.round(track.laps * 3.245), won: replay.order[0] === state.playerSlot });
    }
    save(state);
    console.log(`race ${raceId} finished: ${replay.order.map((s) => replay.teams[s]).join(", ")}`);
  } catch (err) {
    const msg = String((err as Error).message ?? err);
    // The chain clock can trail ours by a second or two; retry the reveal.
    if (attempt < 10 && /RaceNotLocked|not locked/i.test(msg)) {
      state.status = "open";
      setTimeout(() => void finishRace(raceId, attempt + 1), 2000);
      return;
    }
    state.status = "failed";
    state.error = msg;
    save(state);
    console.error(`race ${raceId} failed:`, msg);
  }
}

export interface Verification {
  raceId: number;
  simVersion: string;
  seedMatchesCommitment: boolean;
  onChainResultHash: string;
  recomputedResultHash: string;
  verified: boolean;
}

/** Re-runs a race from on-chain data only and compares it with the posted result. */
export async function verifyRace(raceId: number): Promise<Verification> {
  const { race, track, simEntries } = await raceInputFromChain(raceId);
  const seed = Buffer.from(race.seed);
  const seedMatchesCommitment = sha256(seed).equals(Buffer.from(race.commitment));
  const replay = simulate({ track, entries: simEntries, seedHex: seed.toString("hex"), grid: getRace(raceId)?.grid });
  const onChainResultHash = Buffer.from(race.resultHash).toString("hex");
  return {
    raceId,
    simVersion: SIM_VERSION,
    seedMatchesCommitment,
    onChainResultHash,
    recomputedResultHash: replay.resultHash,
    verified: seedMatchesCommitment && onChainResultHash === replay.resultHash,
  };
}
