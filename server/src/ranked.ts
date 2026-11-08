// Ranked (first version: daily board and medals; the ladder is being built on feat/ranked-server).
// A free daily time trial in the standard car with your own setup. Laps are verified like
// qualifying laps (re-driven by the server). No stake and no wallet: guests and accounts alike.

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { config } from "./config.ts";

const DAY_MS = 86_400_000;
export const MEDALS = { gold: 65_000_000, silver: 66_500_000, bronze: 68_500_000 }; // microseconds

interface Entry {
  name: string;
  best: { us: number; attempt: string; at: number };
  laps: number;
}
interface Day {
  day: number;
  players: Record<string, Entry>;
}

const dir = join(config.dataDir, "ranked");
mkdirSync(dir, { recursive: true });
const days = new Map<number, Day>();

const today = () => Math.floor(Date.now() / DAY_MS);
function load(day: number): Day {
  let d = days.get(day);
  if (d) return d;
  const file = join(dir, `${day}.json`);
  d = existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as Day) : { day, players: {} };
  days.set(day, d);
  return d;
}
function save(d: Day) {
  const file = join(dir, `${d.day}.json`);
  writeFileSync(file + ".tmp", JSON.stringify(d));
  renameSync(file + ".tmp", file);
}

export function medalFor(us: number): "gold" | "silver" | "bronze" | null {
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
  if (!e) d.players[player] = { name: name.slice(0, 24) || "Player", best: { ...lap, at: Date.now() }, laps: 1 };
  else {
    e.laps += 1;
    if (name) e.name = name.slice(0, 24);
    if (personalBest) e.best = { ...lap, at: Date.now() };
  }
  save(d);
  const s = standings(d);
  const me = s.find((r) => r.player === player)!;
  return { rank: me.rank, of: s.length, us: me.best.us, medal: medalFor(me.best.us), personalBest };
}

export function rankedInfo(player: string) {
  const d = load(today());
  const s = standings(d);
  const me = s.find((r) => r.player === player);
  const leader = s.find((r) => r.player !== player);
  return {
    day: d.day,
    closesAt: (d.day + 1) * DAY_MS,
    medals: MEDALS,
    drivers: s.length,
    leaderboard: s.slice(0, 12).map((r) => ({ rank: r.rank, name: r.name, us: r.best.us, medal: medalFor(r.best.us), you: r.player === player })),
    you: me ? { rank: me.rank, us: me.best.us, medal: medalFor(me.best.us), laps: me.laps } : null,
    ghost: leader ? { attempt: leader.best.attempt, name: leader.name, us: leader.best.us } : null,
  };
}
