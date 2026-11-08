// Ranked: a ladder of one-lap races in the standard car with your own setup (docs/RANKED_CONTRACT.md).
// Starting a ranked attempt starts a race against the 5 opponents nearest your hidden rating
// (humans with a ranked lap this week, AI benchmark drivers filling in); the first completed
// lap of the attempt, verified by the server's re-drive, decides it. On top of the ladder is a
// daily board of the day's best ranked lap with medals, and each medal earns a pack once a day.
// No stake and no wallet: guests and accounts alike.
//
// Stored in config.dataDir/ranked/: <day>.json (daily boards), ladder.json (every player's
// ladder state and their open race) and races/<attempt>.json (a resolved race's result, so
// a race is resolved once and asking again returns the same answer).

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { accountName, isAccountName } from "./accounts.ts";
import { config } from "./config.ts";
import { awardPack } from "./parts.ts";

const DAY_MS = 86_400_000;
export const MEDALS = { gold: 65_000_000, silver: 66_500_000, bronze: 68_500_000 }; // microseconds
export type Medal = "gold" | "silver" | "bronze";

/** Time source (tests move it). */
export const clock = { now: () => Date.now() };

// ---------------------------------------------------------------- rules

export const TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"] as const;
/** Divisions from the lowest to the highest: a tier's ladder points run IV 0-99, III 100-199, II 200-299, I 300-399. */
export const DIVISIONS = ["IV", "III", "II", "I"] as const;
export const ALL_TIERS = [...TIERS, "MASTER", "GRANDMASTER", "CHALLENGER"] as const;
export const MASTER_LADDER = TIERS.length * 400; // 2800
export const START_MMR = 1200;
export const PLACEMENTS = 5;
export const K_PLACEMENT = 64;
export const K = 32;
export const OPPONENTS = 5;
export const CHALLENGERS = 3;
export const GRANDMASTERS = 7;
/** Humans count as opponents with a ranked lap this recent. */
export const HUMAN_WINDOW_DAYS = 7;
/** An open race not resolved by then is a forfeit (the attempt expires then too). */
export const RACE_TTL_MS = 30 * 60_000;
/** A run submitted just before the attempt expires is still being re-driven for up to a minute: the sweep waits that long. */
const REDRIVE_GRACE_MS = 60_000;
export const SEASON = { id: 1, name: "SEASON 1", endsAt: Number(process.env.RANKED_SEASON_ENDS_AT ?? Date.UTC(2027, 0, 1)) };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Elo expectation of beating an opponent. */
export const expectedScore = (mmr: number, oppMmr: number) => 1 / (1 + 10 ** ((oppMmr - mmr) / 400));

/** Where placements put a player: ladder = clamp((mmr - 800) * 1.75, 0, 3200). */
export const placementLadder = (mmr: number) => Math.round(clamp((mmr - 800) * 1.75, 0, 3200));

/** The MMR a ladder position stands for. */
export const ladderMmr = (ladder: number) => 800 + ladder / 1.75;

/**
 * RP applied to a ladder position: 100 RP promotes (the rest carries over), below 0 demotes to
 * 75 RP of the division below; Iron IV stops at 0. MASTER counts RP up from 2800 and drops to
 * Diamond I 75 below it.
 */
export function applyRp(ladder: number, change: number): { ladder: number; promoted: boolean; demoted: boolean } {
  const base = ladder >= MASTER_LADDER ? MASTER_LADDER : Math.floor(ladder / 100) * 100;
  const next = ladder + change;
  if (next < base) {
    if (base === 0) return { ladder: 0, promoted: false, demoted: false };
    return { ladder: base - 25, promoted: false, demoted: true };
  }
  return { ladder: next, promoted: base < MASTER_LADDER && next >= base + 100, demoted: false };
}

export interface RankView {
  tier: string;
  /** "" for UNRANKED and MASTER+, which have no divisions. */
  division: string;
  rp: number;
  ladder: number;
  placementsLeft: number;
}

/** Tier, division and RP of a ladder position (`apex` is GRANDMASTER or CHALLENGER for the top MASTER players). */
export function rankFromLadder(ladder: number, placementsLeft = 0, apex?: string): RankView {
  if (placementsLeft > 0) return { tier: "UNRANKED", division: "", rp: 0, ladder: 0, placementsLeft };
  if (ladder >= MASTER_LADDER) return { tier: apex ?? "MASTER", division: "", rp: ladder - MASTER_LADDER, ladder, placementsLeft: 0 };
  const t = Math.floor(ladder / 400);
  return { tier: TIERS[t], division: DIVISIONS[Math.floor((ladder - t * 400) / 100)], rp: ladder % 100, ladder, placementsLeft: 0 };
}

export interface Opponent {
  name: string;
  mmr: number;
  us: number;
  ai: boolean;
  tier: string;
  division: string;
}
export interface LadderState {
  mmr: number;
  ladder: number;
  placementsLeft: number;
}

/**
 * One race scored: 1 for each opponent your lap beats (a forfeit beats nobody), Elo on the hidden
 * MMR, RP on the ladder once placements are done; the 5th placement race places you.
 */
export function scoreRace(state: LadderState, opponents: { mmr: number; us: number }[], us: number | null) {
  const n = opponents.length || 1;
  const beat = opponents.map((o) => us !== null && us < o.us);
  const sum = opponents.reduce((s, o, i) => s + (beat[i] ? 1 : 0) - expectedScore(state.mmr, o.mmr), 0);
  const placing = state.placementsLeft > 0;
  const mmr = Math.round((state.mmr + ((placing ? K_PLACEMENT : K) * sum) / n) * 100) / 100;
  let { ladder, placementsLeft } = state;
  let rpChange = 0;
  let promoted = false;
  let demoted = false;
  let placed = false;
  if (placing) {
    placementsLeft -= 1;
    if (placementsLeft === 0) {
      ladder = placementLadder(mmr);
      placed = true;
    }
  } else {
    rpChange = Math.round((40 * sum) / n + clamp((mmr - ladderMmr(ladder)) / 40, -8, 8));
    ({ ladder, promoted, demoted } = applyRp(ladder, rpChange));
  }
  return { beat, wins: beat.filter(Boolean).length, mmr, ladder, placementsLeft, rpChange, promoted, demoted, placed };
}

// ---------------------------------------------------------------- AI benchmark drivers

const AI_NAMES = ["Rookie Ruslan", "Steady Salome", "Late-Braker Luka", "Apex Ana", "Kerb-Hopper Koba", "Smooth Sopho", "Trail-Brake Tornike", "Slipstream Shorena", "Flatout Fridon", "Benchmark Bachana"];
/** 10 AI drivers, one per 200 MMR from 700 to 2500: us(mmr) = 72_000_000 - (mmr - 700) * 4278, with ±150 ms daily jitter. */
export function aiDrivers(day: number): Opponent[] {
  return AI_NAMES.map((name, i) => {
    const mmr = 700 + i * 200;
    const jitter = (createHash("sha256").update(`ranked-ai:${day}:${i}`).digest().readUInt32LE(0) % 300_001) - 150_000;
    const rank = rankFromLadder(placementLadder(mmr));
    return { name, mmr, us: 72_000_000 - (mmr - 700) * 4278 + jitter, ai: true, tier: rank.tier, division: rank.division };
  });
}

/** The 5 candidates nearest the MMR (humans first on a tie), fastest first. */
export function pickOpponents(mmr: number, candidates: Opponent[], count = OPPONENTS): Opponent[] {
  return [...candidates]
    .sort((a, b) => Math.abs(a.mmr - mmr) - Math.abs(b.mmr - mmr) || Number(a.ai) - Number(b.ai) || a.us - b.us)
    .slice(0, count)
    .sort((a, b) => a.us - b.us);
}

// ---------------------------------------------------------------- store

interface Entry {
  name: string;
  best: { us: number; attempt: string; at: number };
  laps: number;
}
interface Day {
  day: number;
  players: Record<string, Entry>;
}
interface OpenRace {
  attempt: string;
  createdAt: number;
  opponents: Opponent[];
}
interface Recent {
  at: number;
  attempt: string;
  rpChange: number;
  wins: number;
  of: number;
  us: number | null;
  forfeit: boolean;
}
interface LadderPlayer extends LadderState {
  name: string;
  wins: number;
  losses: number;
  races: number;
  recent: Recent[];
  pending: OpenRace | null;
  createdAt: number;
  updatedAt: number;
}
interface Ladder {
  players: Record<string, LadderPlayer>;
}

const dir = join(config.dataDir, "ranked");
mkdirSync(join(dir, "races"), { recursive: true });
const days = new Map<number, Day>();

function writeAtomic(file: string, data: unknown) {
  writeFileSync(file + ".tmp", JSON.stringify(data));
  renameSync(file + ".tmp", file);
}

export const today = () => Math.floor(clock.now() / DAY_MS);
function load(day: number): Day {
  let d = days.get(day);
  if (d) return d;
  const file = join(dir, `${day}.json`);
  d = existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as Day) : { day, players: {} };
  days.set(day, d);
  return d;
}
function save(d: Day) {
  writeAtomic(join(dir, `${d.day}.json`), d);
}

const ladderFile = join(dir, "ladder.json");
let ladderState: Ladder | undefined;
function ladder(): Ladder {
  ladderState ??= existsSync(ladderFile) ? (JSON.parse(readFileSync(ladderFile, "utf8")) as Ladder) : { players: {} };
  return ladderState;
}
const saveLadder = () => writeAtomic(ladderFile, ladder());
/** Every player's ladder record, live (tests and admin tools; not for the API: it holds player ids and MMR). */
export const ladderStore = () => ladder().players;

const raceFile = (attempt: string) => join(dir, "races", `${attempt.replace(/[^0-9a-f]/g, "")}.json`);
interface StoredRace {
  player: string;
  ranked: RankedResult;
  /** The whole run response (quali.ts submitRun), once a run resolved the race. */
  run?: unknown;
}
function storedRace(attempt: string): StoredRace | undefined {
  const file = raceFile(attempt);
  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as StoredRace) : undefined;
}

/** Account players show their account name; a guest using an account's name is marked as a guest. */
function shownName(player: string, stored: string): string {
  return accountName(player) ?? (isAccountName(stored) ? `${stored} (guest)` : stored);
}

function newPlayer(name: string): LadderPlayer {
  const now = clock.now();
  return { name, mmr: START_MMR, ladder: 0, placementsLeft: PLACEMENTS, wins: 0, losses: 0, races: 0, recent: [], pending: null, createdAt: now, updatedAt: now };
}

// ---------------------------------------------------------------- daily board and medals

export function medalFor(us: number): Medal | null {
  if (us <= MEDALS.gold) return "gold";
  if (us <= MEDALS.silver) return "silver";
  if (us <= MEDALS.bronze) return "bronze";
  return null;
}

function standings(d: Day) {
  return Object.entries(d.players)
    .sort((a, b) => a[1].best.us - b[1].best.us || a[1].best.at - b[1].best.at)
    .map(([player, e], i) => ({ rank: i + 1, player, ...e }));
}

/** A verified ranked lap: keeps the player's best of the day. */
export function recordRanked(player: string, name: string, lap: { us: number; attempt: string }) {
  const d = load(today());
  const e = d.players[player];
  const personalBest = !e || lap.us < e.best.us;
  const now = clock.now();
  if (!e) d.players[player] = { name: name.slice(0, 24) || "Player", best: { ...lap, at: now }, laps: 1 };
  else {
    e.laps += 1;
    if (name) e.name = name.slice(0, 24);
    if (personalBest) e.best = { ...lap, at: now };
  }
  save(d);
  const s = standings(d);
  const me = s.find((r) => r.player === player)!;
  return { rank: me.rank, of: s.length, us: me.best.us, medal: medalFor(me.best.us), personalBest };
}

const MEDAL_ORDER: Medal[] = ["bronze", "silver", "gold"];
/** Each medal tier reached today earns its pack once per UTC day; gold also brings silver and bronze. */
export function awardMedalPacks(player: string, medal: Medal | null, day = today()): unknown[] {
  if (!medal) return [];
  const earned: unknown[] = [];
  for (const m of MEDAL_ORDER.slice(0, MEDAL_ORDER.indexOf(medal) + 1)) {
    try {
      const r = awardPack(player, `ranked_${m}`, String(day));
      if (r.awarded && r.pack) earned.push(r.pack);
    } catch (err) {
      console.error(`ranked ${m} pack:`, (err as Error).message);
    }
  }
  return earned;
}

// ---------------------------------------------------------------- ladder

/** CHALLENGER (top 3) and GRANDMASTER (next 7) among MASTER+ players, by ladder. */
function apexTiers(): Map<string, string> {
  const top = Object.entries(ladder().players)
    .filter(([, p]) => p.placementsLeft === 0 && p.ladder >= MASTER_LADDER)
    .sort((a, b) => b[1].ladder - a[1].ladder || b[1].mmr - a[1].mmr || a[0].localeCompare(b[0]));
  return new Map(top.slice(0, CHALLENGERS + GRANDMASTERS).map(([id], i) => [id, i < CHALLENGERS ? "CHALLENGER" : "GRANDMASTER"]));
}

function rankOf(player: string, apex = apexTiers()): RankView {
  const p = ladder().players[player];
  if (!p) return rankFromLadder(0, PLACEMENTS);
  return rankFromLadder(p.ladder, p.placementsLeft, apex.get(player));
}

/** Humans with a ranked lap in the last 7 days: their best lap and their MMR. */
function humanOpponents(except: string): Opponent[] {
  const best = new Map<string, { us: number; name: string }>();
  const t = today();
  for (let day = t - HUMAN_WINDOW_DAYS + 1; day <= t; day++) {
    for (const [player, e] of Object.entries(load(day).players)) {
      if (player === except) continue;
      const b = best.get(player);
      if (!b || e.best.us < b.us) best.set(player, { us: e.best.us, name: e.name });
    }
  }
  const apex = apexTiers();
  return [...best].map(([player, b]) => {
    const p = ladder().players[player];
    const rank = rankOf(player, apex);
    return { name: shownName(player, p?.name ?? b.name), mmr: p?.mmr ?? START_MMR, us: b.us, ai: false, tier: rank.tier, division: rank.division };
  });
}

export interface RankedResult {
  counted: boolean;
  forfeit: boolean;
  us: number | null;
  opponents: { name: string; us: number; beat: boolean; ai: boolean; tier: string; division: string }[];
  wins: number;
  of: number;
  rpChange: number;
  rank: RankView;
  promoted: boolean;
  demoted: boolean;
  placed: boolean;
  medal: Medal | null;
  packsEarned: unknown[];
  daily: { rank: number | null; of: number };
}

/** Resolves the player's open race with this lap (null = forfeit). */
function resolve(player: string, lap: { us: number; valid: boolean } | null): RankedResult {
  const p = ladder().players[player];
  const race = p.pending!;
  const forfeit = !lap || !lap.valid;
  const us = forfeit ? null : lap.us;
  const r = scoreRace(p, race.opponents, us);
  Object.assign(p, { mmr: r.mmr, ladder: r.ladder, placementsLeft: r.placementsLeft });
  p.races += 1;
  // a race is won by beating most of the field (3 of 5)
  if (r.wins * 2 > race.opponents.length) p.wins += 1;
  else p.losses += 1;
  const now = clock.now();
  p.recent = [{ at: now, attempt: race.attempt, rpChange: r.rpChange, wins: r.wins, of: race.opponents.length, us, forfeit }, ...p.recent].slice(0, 10);
  p.pending = null;
  p.updatedAt = now;
  saveLadder();
  // the daily board takes the race lap; each medal reached today earns its pack
  let daily: { rank: number | null; of: number };
  let medal: Medal | null;
  let packsEarned: unknown[] = [];
  if (us !== null) {
    const d = recordRanked(player, p.name, { us, attempt: race.attempt });
    daily = { rank: d.rank, of: d.of };
    medal = d.medal;
    packsEarned = awardMedalPacks(player, medal);
  } else {
    const s = standings(load(today()));
    const me = s.find((x) => x.player === player);
    daily = { rank: me?.rank ?? null, of: s.length };
    medal = me ? medalFor(me.best.us) : null;
  }
  const result: RankedResult = {
    counted: true,
    forfeit,
    us,
    opponents: race.opponents.map((o, i) => ({ name: o.name, us: o.us, beat: r.beat[i], ai: o.ai, tier: o.tier, division: o.division })),
    wins: r.wins,
    of: race.opponents.length,
    rpChange: r.rpChange,
    rank: rankOf(player),
    promoted: r.promoted,
    demoted: r.demoted,
    placed: r.placed,
    medal,
    packsEarned,
    daily,
  };
  writeAtomic(raceFile(race.attempt), { player, ranked: result } satisfies StoredRace);
  return result;
}

/** Open races older than 30 minutes are forfeits. */
export function sweepRanked() {
  const now = clock.now();
  for (const [player, p] of Object.entries(ladder().players)) {
    if (p.pending && now - p.pending.createdAt > RACE_TTL_MS + REDRIVE_GRACE_MS) resolve(player, null);
  }
}

/**
 * A ranked attempt starts a race: an earlier race left open is a forfeit, then the 5 opponents
 * nearest the player's MMR are fixed for this attempt.
 */
export function startRankedRace(player: string, name: string, attempt: string) {
  const l = ladder();
  const p = (l.players[player] ??= newPlayer(name.slice(0, 24) || "Player"));
  if (name) p.name = name.slice(0, 24);
  if (p.pending) resolve(player, null);
  const opponents = pickOpponents(p.mmr, [...humanOpponents(player), ...aiDrivers(today())]);
  p.pending = { attempt, createdAt: clock.now(), opponents };
  p.updatedAt = clock.now();
  saveLadder();
  return { opponents: opponents.map((o) => ({ name: o.name, tier: o.tier, division: o.division, us: o.us, ai: o.ai })) };
}

/**
 * Resolves an attempt's race with its first completed lap (null when the run completed none),
 * once: later calls, and a race already forfeited, return the stored result.
 */
export function resolveRankedRace(player: string, attempt: string, firstLap: { us: number; valid: boolean } | null): RankedResult | null {
  const stored = storedRace(attempt);
  if (stored) return stored.ranked;
  const p = ladder().players[player];
  if (!p?.pending || p.pending.attempt !== attempt) return null;
  return resolve(player, firstLap);
}

/** The stored run response of an attempt whose race a run resolved. */
export const rankedRun = (attempt: string): unknown => storedRace(attempt)?.run;
/** Keeps an attempt's run response (the first one) so asking again returns it unchanged. */
export function saveRankedRun(attempt: string, run: unknown) {
  const stored = storedRace(attempt);
  if (stored && stored.run === undefined) writeAtomic(raceFile(attempt), { ...stored, run });
}

// ---------------------------------------------------------------- GET /api/ranked

export function rankedInfo(player: string) {
  sweepRanked();
  const d = load(today());
  const s = standings(d);
  const me = s.find((r) => r.player === player);
  const leader = s.find((r) => r.player !== player);
  const apex = apexTiers();
  const ranked = Object.entries(ladder().players)
    .filter(([, p]) => p.placementsLeft === 0)
    .sort((a, b) => b[1].ladder - a[1].ladder || b[1].mmr - a[1].mmr || a[0].localeCompare(b[0]));
  const lp = player ? ladder().players[player] : undefined;
  const rank = rankOf(player, apex);
  return {
    season: SEASON,
    you: player
      ? {
          tier: rank.tier,
          division: rank.division,
          rp: rank.rp,
          ladder: rank.ladder,
          placementsLeft: rank.placementsLeft,
          wins: lp?.wins ?? 0,
          losses: lp?.losses ?? 0,
          races: lp?.races ?? 0,
          recent: (lp?.recent ?? []).slice(0, 5).map((r) => ({ at: r.at, rpChange: r.rpChange, wins: r.wins, of: r.of, us: r.us, forfeit: r.forfeit })),
        }
      : null,
    ladder: ranked.slice(0, 20).map(([id, p], i) => {
      const r = rankFromLadder(p.ladder, 0, apex.get(id));
      return { rank: i + 1, name: shownName(id, p.name), tier: r.tier, division: r.division, rp: r.rp, you: id === player };
    }),
    daily: {
      day: d.day,
      closesAt: (d.day + 1) * DAY_MS,
      medals: MEDALS,
      drivers: s.length,
      leaderboard: s.slice(0, 20).map((r) => ({ rank: r.rank, name: shownName(r.player, r.name), us: r.best.us, medal: medalFor(r.best.us), you: r.player === player })),
      you: me ? { rank: me.rank, us: me.best.us, medal: medalFor(me.best.us), laps: me.laps } : null,
      ghost: leader ? { attempt: leader.best.attempt, name: shownName(leader.player, leader.name), us: leader.best.us } : null,
    },
    tiers: ALL_TIERS,
  };
}
