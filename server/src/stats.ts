// Private play-test stats: daily counts of visitors and what they did.
// Only anonymous hashes of player ids are stored, never the ids themselves.
// Read them at /admin (HTTP Basic auth, password in ADMIN_PASSWORD); nothing in
// the game links there.

import { createHash, timingSafeEqual } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { IncomingMessage } from "node:http";
import { config } from "./config.ts";

const dir = join(config.dataDir, "stats");
mkdirSync(dir, { recursive: true });

/** Events the game may report itself; everything else is recorded by the server. */
export const CLIENT_EVENTS = new Set(["visit", "rookie_start", "rookie_passed", "practice_start", "quali_start", "race_start", "garage_open", "pack_open_screen", "passes_open"]);

interface Day {
  day: string;
  counts: Record<string, number>;
  players: Record<string, string[]>; // event -> unique player hashes
  agents: Record<string, number>;
}
interface Recent {
  t: number;
  event: string;
  who: string;
  data?: string;
}

const days = new Map<string, Day>();
let firstSeen: Record<string, string> | null = null;
const recent: Recent[] = [];

const today = () => new Date().toISOString().slice(0, 10);
const hash = (player: string) => createHash("sha256").update(`pitwall-stats:${player}`).digest("hex").slice(0, 12);

function load(day: string): Day {
  let d = days.get(day);
  if (d) return d;
  const file = join(dir, `${day}.json`);
  d = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : { day, counts: {}, players: {}, agents: {} };
  days.set(day, d!);
  return d!;
}
function firstSeenMap(): Record<string, string> {
  if (!firstSeen) {
    const file = join(dir, "first_seen.json");
    firstSeen = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : {};
  }
  return firstSeen!;
}
function writeAtomic(file: string, data: unknown) {
  writeFileSync(file + ".tmp", JSON.stringify(data));
  renameSync(file + ".tmp", file);
}

let saveTimer: NodeJS.Timeout | null = null;
function saveSoon() {
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = null;
    try {
      mkdirSync(dir, { recursive: true });
      for (const d of days.values()) writeAtomic(join(dir, `${d.day}.json`), d);
      if (firstSeen) writeAtomic(join(dir, "first_seen.json"), firstSeen);
    } catch (err) {
      console.error("stats: could not save", (err as Error).message);
    }
  }, 2000);
  saveTimer.unref(); // never keeps the process (or a test) alive
}

/** A short browser/OS label from a user agent, e.g. "Chrome · Windows". */
function agentLabel(ua: string): string {
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Other";
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "Other";
  return `${browser} · ${os}`;
}

export function record(event: string, player: string | undefined, data?: string, ua?: string) {
  const day = load(today());
  day.counts[event] = (day.counts[event] ?? 0) + 1;
  const who = player ? hash(player) : "-";
  if (player) {
    const list = (day.players[event] ??= []);
    if (!list.includes(who)) list.push(who);
    const seen = firstSeenMap();
    seen[who] ??= day.day;
  }
  if (ua && event === "visit") {
    const label = agentLabel(ua);
    day.agents[label] = (day.agents[label] ?? 0) + 1;
  }
  recent.push({ t: Date.now(), event, who, data: data?.slice(0, 80) });
  if (recent.length > 200) recent.shift();
  saveSoon();
}

/** True when the request carries the admin password (HTTP Basic auth, any user name). */
export function isAdmin(req: IncomingMessage): boolean {
  const pass = process.env.ADMIN_PASSWORD ?? "";
  if (pass.length < 8) return false;
  const header = String(req.headers.authorization ?? "");
  if (!header.startsWith("Basic ")) return false;
  const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
  const given = Buffer.from(decoded.slice(decoded.indexOf(":") + 1));
  const want = Buffer.from(pass);
  return given.length === want.length && timingSafeEqual(given, want);
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

const ROWS: [string, string][] = [
  ["visit", "Opened the game"],
  ["rookie_start", "Started the Rookie Test"],
  ["rookie_passed", "Passed the Rookie Test"],
  ["practice_start", "Started Practice"],
  ["quali_start", "Started Qualifying"],
  ["lap_verified", "Verified laps (on Solana)"],
  ["race_start", "Started a race"],
  ["race_finished", "Finished races (verified)"],
  ["garage_open", "Opened the garage"],
  ["pack_opened", "Opened packs"],
  ["pass_bought", "Bought race passes"],
  ["account_created", "Created accounts"],
  ["wallet_linked", "Linked wallets"],
];

/** The private stats page. */
export function adminPage(extra: { timesheet: { name: string; us: number }[] }): string {
  const all = [...new Set([...days.keys(), today()])];
  // include saved days not loaded yet (last 7)
  for (let k = 0; k < 7; k++) {
    const d = new Date(Date.now() - k * 86400000).toISOString().slice(0, 10);
    if (existsSync(join(dir, `${d}.json`)) && !all.includes(d)) all.push(d);
  }
  const list = all.sort().reverse().slice(0, 7).map(load);
  const seen = firstSeenMap();
  const head = list.map((d) => `<th>${d.day}</th>`).join("");
  const rows = ROWS.map(([key, label]) => {
    const cells = list.map((d) => {
      const n = d.counts[key] ?? 0;
      const u = d.players[key]?.length ?? 0;
      return `<td>${n ? `<b>${u || n}</b>${u && n !== u ? ` <span>(${n}×)</span>` : ""}` : `<span>0</span>`}</td>`;
    });
    return `<tr><td>${label}</td>${cells.join("")}</tr>`;
  }).join("");
  const returning = list.map((d) => {
    const v = d.players.visit ?? [];
    return `<td>${v.filter((h) => seen[h] && seen[h] < d.day).length} of ${v.length}</td>`;
  }).join("");
  const agents = Object.entries(list[0]?.agents ?? {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<li>${esc(k)}: ${v}</li>`).join("") || "<li>none yet</li>";
  const feed = recent.slice(-40).reverse().map((r) => `<tr><td>${new Date(r.t).toISOString().slice(11, 19)}</td><td>${esc(r.event)}</td><td>${r.who}</td><td>${esc(r.data ?? "")}</td></tr>`).join("");
  const sheet = extra.timesheet.map((r, i) => `<li>${i + 1}. ${esc(r.name)}: ${(r.us / 1e6).toFixed(3)} s</li>`).join("") || "<li>no human laps yet</li>";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex"><title>Pit Wall stats</title>
<meta http-equiv="refresh" content="60">
<style>body{background:#141518;color:#f1efea;font:14px/1.4 system-ui,sans-serif;margin:24px}h1{color:#e8352b;margin:0 0 4px}
h2{font-size:15px;color:#a3a3ad;margin:26px 0 8px;text-transform:uppercase;letter-spacing:.08em}table{border-collapse:collapse}
td,th{border-bottom:1px solid #34363c;padding:6px 14px;text-align:left}th{color:#a3a3ad;font-weight:600}td span{color:#6e6f78}
b{color:#f1efea}ul{margin:0;padding-left:18px}.note{color:#6e6f78}</style></head><body>
<h1>Pit Wall · play-test stats</h1><div class="note">Unique players per day (total events in brackets). Refreshes every minute. Times in UTC.</div>
<h2>Last 7 days</h2><table><tr><th></th>${head}</tr>${rows}<tr><td>Returning players</td>${returning}</tr></table>
<h2>Today's browsers</h2><ul>${agents}</ul>
<h2>Today's qualifying timesheet (players)</h2><ul>${sheet}</ul>
<h2>Latest events</h2><table><tr><th>UTC</th><th>Event</th><th>Player (anon)</th><th>Detail</th></tr>${feed}</table>
</body></html>`;
}
