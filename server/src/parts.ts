// Parts: unique car parts earned in packs by racing. Each part is rolled from a
// concept in game/data/parts.json and spends the same lap-time budget, so parts
// are different, not better. Parts live in the game database (hash-committed,
// one Merkle root per week) until a player trades or withdraws one; minting
// on-chain happens then, paid by the player. See docs/ECONOMY.md.
//
// The pure part (rolling, budgets, car spec, Merkle roots) needs nothing but the
// catalogue; the store keeps each player's garage in config.dataDir/parts/.

import { createHash, createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { config } from "./config.ts";

// ---------------------------------------------------------------- catalogue

/** Car spec keys: per-mille changes, kW for power, kg for weight (see specKeys in game/data/parts.json). */
export const SPEC_KEYS = ["downforce", "drag", "balance", "power", "harvest", "grip", "traction", "weight"] as const;
export type SpecKey = (typeof SPEC_KEYS)[number];
export type Spec = Record<SpecKey, number>;
export type Range = [number, number];

export interface ConceptDef {
  name: string;
  family: string | null;
  description: string;
  stats: Partial<Record<SpecKey, Range>>;
  traits: string[];
  sprite: string;
  carLayer: string | null;
}
export interface AreaDef {
  name: string;
  lifeKm: number;
  carLayer: boolean;
  baseline: { name: string; look: string | null; description: string };
  concepts: Record<string, ConceptDef>;
}
export interface TraitDef {
  name: string;
  description: string;
  delta: Partial<Spec>;
  budgetCost?: number;
  conditional?: { when: "floor_family_matches"; delta: Partial<Spec> };
}
export interface RarityDef {
  name: string;
  weight: number;
  budgetBonus: number;
  traits: number;
  flair: string;
  scrapCredits: number;
  color: string;
}
export interface SynergyDef {
  id: string;
  name: string;
  description: string;
  when: { sameFamily?: string[]; concepts?: Record<string, string> };
  delta: Partial<Spec>;
}
/** A way to earn packs. `odds` (rarity -> weight) replaces the rarity weights for its packs; `medal` marks ranked medal packs. */
export interface EarnRule {
  name: string;
  packs: number;
  per: string;
  odds?: Record<string, number>;
  medal?: "bronze" | "silver" | "gold";
}
export interface Catalog {
  version: number;
  specKeys: Record<SpecKey, { unit: string; label: string; description: string; physicsClamp: Range }>;
  lapWeights: { weights: Spec };
  trackTypes: Record<string, { name: string; multipliers: Spec }>;
  budget: { points: number; tolerance: number };
  rarities: Record<string, RarityDef>;
  families: Record<string, { name: string }>;
  areas: Record<string, AreaDef>;
  traits: Record<string, TraitDef>;
  synergies: SynergyDef[];
  packs: { partsPerPack: number; maxSameArea: number; earn: Record<string, EarnRule> };
}

export const catalogPath = config.partsCatalog || join(config.gameDir, "data", "parts.json");
export const catalog: Catalog = JSON.parse(readFileSync(catalogPath, "utf8"));
export const AREAS = Object.keys(catalog.areas);

/** Livery colours players can pick (game/data/livery.json): cosmetic only, never part of the car spec. */
export interface Livery {
  primary: string;
  secondary: string;
}
interface LiveryPalette {
  default: Livery;
  primary: { hex: string; name: string }[];
  secondary: { hex: string; name: string }[];
}
export const liveryPalette: LiveryPalette = JSON.parse(readFileSync(join(config.gameDir, "data", "livery.json"), "utf8"));

export const zeroSpec = (): Spec => ({ downforce: 0, drag: 0, balance: 0, power: 0, harvest: 0, grip: 0, traction: 0, weight: 0 });
export function addSpec(a: Spec, b: Partial<Spec>): Spec {
  const out = { ...a };
  for (const k of SPEC_KEYS) out[k] += b[k] ?? 0;
  return out;
}

/** Lap-time points of a set of stats (1 point = 0.001% of lap time, positive = faster), optionally for a track type. */
export function goodness(stats: Partial<Spec>, trackType = "mixed"): number {
  const w = catalog.lapWeights.weights;
  const m = catalog.trackTypes[trackType]?.multipliers;
  let g = 0;
  for (const k of SPEC_KEYS) g += (stats[k] ?? 0) * w[k] * (m ? m[k] : 1);
  return g;
}

/** The lap-time points a rolled part must hit: the budget, its rarity bonus, minus what its traits cost. */
export function budgetTarget(rarity: string, traits: string[]): number {
  const bonus = catalog.rarities[rarity]?.budgetBonus ?? 0;
  const cost = traits.reduce((c, t) => c + (catalog.traits[t]?.budgetCost ?? 0), 0);
  return Math.round(catalog.budget.points * (1 + bonus)) - cost;
}

export function traitDelta(traits: string[]): Spec {
  return traits.reduce((s, t) => addSpec(s, catalog.traits[t]?.delta ?? {}), zeroSpec());
}

// ---------------------------------------------------------------- rolling

/** Deterministic random stream from a 32-byte seed: sha256(seed || counter) blocks. */
export class Rng {
  #seed: Buffer;
  #counter = 0;
  #buf = Buffer.alloc(0);
  #pos = 0;
  constructor(seed: Buffer) {
    this.#seed = seed;
  }
  u32(): number {
    if (this.#pos + 4 > this.#buf.length) {
      this.#buf = createHash("sha256").update(this.#seed).update(String(this.#counter++)).digest();
      this.#pos = 0;
    }
    const v = this.#buf.readUInt32LE(this.#pos);
    this.#pos += 4;
    return v;
  }
  /** Whole number in lo..hi inclusive. */
  int(lo: number, hi: number): number {
    return lo + (this.u32() % (hi - lo + 1));
  }
  pick<T>(items: readonly T[]): T {
    return items[this.u32() % items.length];
  }
  weighted<T>(items: readonly [T, number][]): T {
    const total = items.reduce((s, [, w]) => s + w, 0);
    let r = this.u32() % total;
    for (const [item, w] of items) {
      if (r < w) return item;
      r -= w;
    }
    return items[items.length - 1][0];
  }
}

export interface PartRoll {
  area: string;
  concept: string;
  rarity: string;
  /** Effective stats: rolled base plus the traits' deltas. */
  stats: Spec;
  traits: string[];
  /** Lap-time points the part ended on and how far from its target (always within the tolerance for a sound catalogue). */
  points: number;
  budgetError: number;
}

/**
 * Rolls a concept's stats so the part's lap-time points hit the target. Each stat
 * is drawn within its range, then stats are nudged (randomly chosen, inside their
 * ranges) until the total matches, then a small exhaustive search closes the gap.
 */
export function rollStats(rng: Rng, def: ConceptDef, traits: string[], target: number): { stats: Spec; error: number } {
  const w = catalog.lapWeights.weights;
  const keys = (Object.keys(def.stats) as SpecKey[]).filter((k) => def.stats[k]);
  const base = zeroSpec();
  for (const k of keys) base[k] = rng.int(def.stats[k]![0], def.stats[k]![1]);
  const delta = traitDelta(traits);
  const adjustable = keys.filter((k) => w[k] !== 0 && def.stats[k]![0] !== def.stats[k]![1]);
  let err = target - goodness(addSpec(base, delta));
  const tol = catalog.budget.tolerance;

  for (let guard = 0; guard < 64 && Math.abs(err) > tol; guard++) {
    const options = adjustable.filter((k) => {
      const want = Math.round(err / w[k]);
      const [lo, hi] = def.stats[k]!;
      return want !== 0 && (want > 0 ? base[k] < hi : base[k] > lo);
    });
    if (!options.length) break;
    const k = rng.pick(options);
    const [lo, hi] = def.stats[k]!;
    const next = Math.min(hi, Math.max(lo, base[k] + Math.round(err / w[k])));
    err -= (next - base[k]) * w[k];
    base[k] = next;
  }

  if (Math.abs(err) > 0 && adjustable.length) {
    // Close the last few points: try every small change of the adjustable stats
    let best = { err, cost: 0, d: adjustable.map(() => 0) };
    const d = adjustable.map(() => -4);
    for (;;) {
      let ok = true;
      let change = 0;
      let cost = 0;
      adjustable.forEach((k, i) => {
        const v = base[k] + d[i];
        if (v < def.stats[k]![0] || v > def.stats[k]![1]) ok = false;
        change += d[i] * w[k];
        cost += Math.abs(d[i]);
      });
      if (ok) {
        const e = err - change;
        if (Math.abs(e) < Math.abs(best.err) || (Math.abs(e) === Math.abs(best.err) && cost < best.cost)) best = { err: e, cost, d: [...d] };
      }
      let i = 0;
      while (i < d.length && d[i] === 4) d[i++] = -4;
      if (i === d.length) break;
      d[i]++;
    }
    adjustable.forEach((k, i) => (base[k] += best.d[i]));
    err = best.err;
  }
  return { stats: addSpec(base, delta), error: err };
}

/** Rarity weights for a pack: the earn rule's odds when it has them, otherwise the catalogue's rarity weights. */
export function packOdds(reason?: string): [string, number][] {
  const odds = reason ? catalog.packs.earn[reason]?.odds : undefined;
  return Object.entries(catalog.rarities)
    .map(([id, r]) => [id, odds ? Math.max(0, Math.round(odds[id] ?? 0)) : r.weight] as [string, number])
    .filter(([id, w]) => w > 0 && id !== "starter");
}

/**
 * The three parts in a pack. Reproducible from the pack id and the season's seed secret
 * (and the rarity weights: `odds`, from the pack's earn rule; the catalogue's weights by default).
 */
export function rollPack(packId: string, secret = config.seedSecret, odds?: [string, number][]): PartRoll[] {
  const rng = new Rng(createHmac("sha256", secret).update(`pack:${packId}`).digest());
  const rarities = odds?.length ? odds : packOdds();
  const out: PartRoll[] = [];
  for (let i = 0; i < catalog.packs.partsPerPack; i++) {
    const room = AREAS.filter((a) => out.filter((p) => p.area === a).length < catalog.packs.maxSameArea);
    const area = rng.pick(room);
    const rarity = rng.weighted(rarities);
    const concept = rng.pick(Object.keys(catalog.areas[area].concepts));
    const def = catalog.areas[area].concepts[concept];
    const pool = [...def.traits];
    const traits: string[] = [];
    const count = Math.min(catalog.rarities[rarity].traits, pool.length);
    while (traits.length < count) traits.push(pool.splice(rng.u32() % pool.length, 1)[0]);
    const target = budgetTarget(rarity, traits);
    const { stats, error } = rollStats(rng, def, traits, target);
    out.push({ area, concept, rarity, stats, traits, points: goodness(stats), budgetError: error });
  }
  return out;
}

// ---------------------------------------------------------------- car spec

export interface PartLike {
  area: string;
  concept: string;
  traits: string[];
  stats: Spec;
  /** For wear: starter parts never wear; others fade over the last 30% of their area's lifeKm. */
  rarity?: string;
  km?: number;
}

const familyOf = (p: PartLike | undefined) => (p ? (catalog.areas[p.area]?.concepts[p.concept]?.family ?? null) : null);

/** Wear starts to cost performance at this share of a part's life. */
export const WEAR_FADE_FROM = 0.7;
/** Per-mille effect left at the end of a part's life: a worn part is never worse than the standard part. */
export const WEAR_MIN_EFFECT = 600;

/** Per-mille share of a part's stats it still gives: 1000 until 70% of its life, then down to 600 at 100%. */
export function wearEffect(p: { area: string; rarity?: string; km?: number }): number {
  const life = catalog.areas[p.area]?.lifeKm ?? 0;
  if (p.rarity === "starter" || !(life > 0)) return 1000;
  const used = (p.km ?? 0) / life;
  if (used <= WEAR_FADE_FROM) return 1000;
  const fade = Math.min(1, (used - WEAR_FADE_FROM) / (1 - WEAR_FADE_FROM));
  return Math.round(1000 - (1000 - WEAR_MIN_EFFECT) * fade);
}

/**
 * Stats scaled by a per-mille effect. Each is rounded toward the faster side
 * (lap weights), so a worn part keeps at least its share of its lap-time points
 * and a part that was better than the standard one never ends up worse.
 */
function scaleSpec(stats: Partial<Spec>, effect: number): Spec {
  const w = catalog.lapWeights.weights;
  const out = zeroSpec();
  for (const k of SPEC_KEYS) {
    const v = stats[k] ?? 0;
    const x = (v * effect) / 1000;
    out[k] = effect === 1000 ? v : (w[k] ?? 0) > 0 ? Math.ceil(x) : (w[k] ?? 0) < 0 ? Math.floor(x) : Math.sign(x) * Math.round(Math.abs(x));
  }
  return out;
}

/** Sum of the fitted parts plus conditional traits and synergies, and what the car looks like. */
export function carDetail(fitted: PartLike[]) {
  const byArea: Record<string, PartLike> = {};
  for (const p of fitted) byArea[p.area] = p;
  let spec = zeroSpec();
  const synergies: { id: string; name: string; description: string; delta: Partial<Spec> }[] = [];
  for (const p of fitted) {
    // a worn part gives less of everything it changes (wearEffect)
    const effect = wearEffect(p);
    spec = addSpec(spec, scaleSpec(p.stats, effect));
    for (const t of p.traits) {
      const c = catalog.traits[t]?.conditional;
      if (c?.when === "floor_family_matches" && p.area !== "floor" && familyOf(p) && familyOf(p) === familyOf(byArea.floor)) {
        const delta = effect === 1000 ? c.delta : scaleSpec(c.delta, effect);
        spec = addSpec(spec, delta);
        synergies.push({ id: `trait:${t}:${p.area}`, name: catalog.traits[t].name, description: catalog.traits[t].description, delta });
      }
    }
  }
  for (const s of catalog.synergies) {
    let on = true;
    if (s.when.sameFamily) {
      const fams = s.when.sameFamily.map((a) => familyOf(byArea[a]));
      on &&= fams.every((f) => f && f === fams[0]);
    }
    if (s.when.concepts) on &&= Object.entries(s.when.concepts).every(([a, c]) => byArea[a]?.concept === c);
    if (on) {
      spec = addSpec(spec, s.delta);
      synergies.push({ id: s.id, name: s.name, description: s.description, delta: s.delta });
    }
  }
  const looks: Record<string, string> = {};
  for (const [a, def] of Object.entries(catalog.areas)) {
    if (!def.carLayer) continue;
    const p = byArea[a];
    const look = p && p.concept !== "baseline" ? p.concept : def.baseline.look;
    if (look) looks[a] = look;
  }
  return { spec, synergies, looks };
}

// ---------------------------------------------------------------- supply proofs

/** Hash committed for a part: its immutable fields in a fixed order (weight only for parts rolled with one, so older hashes still verify). */
export function partHash(p: { id: string; area: string; concept: string; rarity: string; stats: Spec; traits: string[]; serial: string | null; week: number | null }): string {
  const keys = p.stats.weight === undefined ? SPEC_KEYS.filter((k) => k !== "weight") : SPEC_KEYS;
  const body = JSON.stringify([p.id, p.area, p.concept, p.rarity, keys.map((k) => p.stats[k]), p.traits, p.serial, p.week]);
  return createHash("sha256").update(`pitwall-part:${body}`).digest("hex");
}

/** Merkle root of the week's part hashes: pairs hashed as sha256(0x01 | left | right), an odd node moves up as is. */
export function merkleRoot(leaves: string[]): string | null {
  if (!leaves.length) return null;
  let level = leaves.map((h) => Buffer.from(h, "hex"));
  while (level.length > 1) {
    const next: Buffer[] = [];
    for (let i = 0; i < level.length; i += 2) {
      next.push(i + 1 < level.length ? createHash("sha256").update(Buffer.from([1])).update(level[i]).update(level[i + 1]).digest() : level[i]);
    }
    level = next;
  }
  return level[0].toString("hex");
}

// ---------------------------------------------------------------- time

const DAY_MS = 86_400_000;
/** Overridable in tests. */
export const clock = { now: () => Date.now() };
/** Weeks start on Monday 00:00 UTC. */
export const weekOf = (ms: number) => Math.floor((Math.floor(ms / DAY_MS) + 3) / 7);
export const weekStartMs = (week: number) => (week * 7 - 3) * DAY_MS;
/** ISO week label, e.g. "2026-W45". */
export function weekLabel(week: number): string {
  const thursday = new Date(weekStartMs(week) + 3 * DAY_MS);
  const year = thursday.getUTCFullYear();
  const n = 1 + Math.floor((thursday.getTime() - Date.UTC(year, 0, 1)) / DAY_MS / 7);
  return `${year}-W${String(n).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- store

export interface Part {
  id: string;
  area: string;
  concept: string;
  rarity: string;
  stats: Spec;
  traits: string[];
  /** Number within the week's supply, e.g. "#0412"; null for starter parts. */
  serial: string | null;
  week: number | null;
  /** "db" until minted on-chain (then the asset id). */
  minted: string;
  createdAt: number;
  races: number;
  wins: number;
  km: number;
  tradeable: boolean;
  packId: string | null;
  hash: string | null;
  /** Worn out (km reached the area's lifeKm): unfitted and kept in the garage, greyed. */
  retired?: boolean;
  retiredAt?: number;
}
export interface Pack {
  id: string;
  reason: string;
  key: string;
  week: number;
  earnedAt: number;
  openedAt?: number;
  parts?: string[];
}
interface PlayerParts {
  player: string;
  createdAt: number;
  inventory: Part[];
  equipped: Record<string, string>;
  packs: Pack[];
  /** `${reason}:${key}` -> pack id, so each award is given once. */
  awards: Record<string, string>;
  /** Races already added to the fitted parts' records. */
  raced?: Record<string, number>;
  /** R&D credits from scrapping parts. */
  credits?: number;
  /** Car colours (hex, from the livery palette); the default livery when unset. */
  livery?: Livery;
}
interface Supply {
  week: number;
  cap: number;
  minted: number;
  packsOpened: number;
  leaves: string[];
  /** Players who earned a pack this week (sets next week's supply). */
  active: string[];
}

export class PartsError extends Error {
  status: number;
  details: Record<string, unknown>;
  constructor(status: number, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

const players = new Map<string, PlayerParts>();
const supplies = new Map<number, Supply>();
const storeDir = (sub: string) => {
  const d = join(config.dataDir, "parts", sub);
  mkdirSync(d, { recursive: true });
  return d;
};

/** Set by quali.ts: true while the player's qualifying setup is locked (parc fermé covers parts too). */
let lockCheck: (player: string) => boolean = () => false;
export function setEquipLockCheck(fn: (player: string) => boolean) {
  lockCheck = fn;
}

function checkPlayer(player: string) {
  if (!/^[0-9a-f]{16,64}$/.test(player)) throw new PartsError(400, "bad player id");
}

function starterParts(player: string, now: number): Part[] {
  return AREAS.map((area) => ({
    id: createHash("sha256").update(`starter:${player}:${area}`).digest("hex").slice(0, 16),
    area,
    concept: "baseline",
    rarity: "starter",
    stats: zeroSpec(),
    traits: [],
    serial: null,
    week: null,
    minted: "db",
    createdAt: now,
    races: 0,
    wins: 0,
    km: 0,
    tradeable: false,
    packId: null,
    hash: null,
  }));
}

function loadPlayer(player: string): PlayerParts {
  checkPlayer(player);
  const cached = players.get(player);
  if (cached) return cached;
  const file = join(storeDir("players"), `${player}.json`);
  let p: PlayerParts;
  if (existsSync(file)) p = JSON.parse(readFileSync(file, "utf8"));
  else {
    const now = clock.now();
    const inventory = starterParts(player, now);
    p = { player, createdAt: now, inventory, equipped: Object.fromEntries(inventory.map((x) => [x.area, x.id])), packs: [], awards: {} };
    writeFileSync(file, JSON.stringify(p));
  }
  players.set(player, p);
  return p;
}
function savePlayer(p: PlayerParts) {
  writeFileSync(join(storeDir("players"), `${p.player}.json`), JSON.stringify(p));
}

/** This week's supply = parts per active player last week, between the floor and the hard cap; frozen when the week starts. */
function weeklyCap(week: number): number {
  const hard = config.partsWeeklyCap;
  if (!(config.partsPerActivePlayer > 0)) return hard;
  const prevFile = join(storeDir("supply"), `${week - 1}.json`);
  const prevActive = supplies.get(week - 1)?.active.length ?? (existsSync(prevFile) ? (JSON.parse(readFileSync(prevFile, "utf8")) as Supply).active.length : 0);
  return Math.min(hard, Math.max(Math.min(config.partsWeeklyFloor, hard), Math.round(config.partsPerActivePlayer * prevActive)));
}

function loadSupply(week: number): Supply {
  const cached = supplies.get(week);
  if (cached) return cached;
  const file = join(storeDir("supply"), `${week}.json`);
  let s: Supply;
  if (existsSync(file)) s = JSON.parse(readFileSync(file, "utf8"));
  else {
    s = { week, cap: weeklyCap(week), minted: 0, packsOpened: 0, leaves: [], active: [] };
    writeFileSync(file, JSON.stringify(s));
  }
  supplies.set(week, s);
  return s;
}
function saveSupply(s: Supply) {
  writeFileSync(join(storeDir("supply"), `${s.week}.json`), JSON.stringify(s));
}

/** The week's supply as shown to players; `root` commits to every part minted so far. */
export function supplyInfo(week = weekOf(clock.now())) {
  const s = loadSupply(week);
  return { week, label: weekLabel(week), cap: s.cap, minted: s.minted, remaining: Math.max(0, s.cap - s.minted), resetsAt: weekStartMs(week + 1), root: merkleRoot(s.leaves) };
}

export function partView(part: Part, equipped = false) {
  const area = catalog.areas[part.area];
  const def = area.concepts[part.concept];
  const rarity = catalog.rarities[part.rarity];
  const lookConcept = def ? part.concept : area.baseline.look;
  const look = lookConcept ? area.concepts[lookConcept] : undefined;
  return {
    ...part,
    equipped,
    display: {
      name: def ? def.name : area.baseline.name,
      label: part.serial ? `${def ? def.name : area.baseline.name} ${part.serial}` : area.baseline.name,
      area: area.name,
      description: def ? def.description : area.baseline.description,
      family: def?.family ?? null,
      familyName: def?.family ? catalog.families[def.family].name : null,
      rarity: rarity.name,
      rarityColor: rarity.color,
      flair: rarity.flair,
      sprite: look?.sprite ?? null,
      carLayer: area.carLayer && lookConcept ? `${part.area}_${lookConcept}` : null,
      week: part.week === null ? null : weekLabel(part.week),
      lifeKm: part.rarity === "starter" ? null : area.lifeKm,
      wear: part.rarity === "starter" ? 0 : Math.min(1, part.km / area.lifeKm),
      /** Per-mille of the part's stats it still gives (wearEffect). */
      effect: wearEffect(part),
      kmLeft: part.rarity === "starter" ? null : Math.max(0, Math.round((area.lifeKm - part.km) * 10) / 10),
      retired: Boolean(part.retired),
      traits: part.traits.map((t) => ({ id: t, name: catalog.traits[t].name, description: catalog.traits[t].description })),
    },
  };
}

/** A once-per-account bonus pack (signup): outside the weekly limit, which is for packs earned by driving. */
const isBonusPack = (reason: string) => catalog.packs.earn[reason]?.per === "account";

const packView = (p: Pack) => {
  const medal = catalog.packs.earn[p.reason]?.medal;
  return { id: p.id, reason: p.reason, reasonName: catalog.packs.earn[p.reason]?.name ?? p.reason, earnedAt: p.earnedAt, openedAt: p.openedAt ?? null, ...(medal ? { medal } : {}) };
};

function packSummary(p: PlayerParts) {
  const week = weekOf(clock.now());
  const unopened = p.packs.filter((x) => !x.openedAt);
  return {
    unopened: unopened.length,
    pending: unopened.map(packView),
    earnedThisWeek: p.packs.filter((x) => x.week === week && !isBonusPack(x.reason)).length,
    weeklyCap: config.packsPerPlayerWeek,
    maxUnopened: config.maxUnopenedPacks,
  };
}

const fittedParts = (p: PlayerParts) => AREAS.map((a) => p.inventory.find((x) => x.id === p.equipped[a])).filter((x): x is Part => Boolean(x));

/** Ids of the parts fitted now (an attempt keeps them, so its distance goes on the parts that drove it). */
export function fittedPartIds(player: string): string[] {
  return fittedParts(loadPlayer(player)).map((x) => x.id);
}

const roundKm = (km: number) => Math.round(km * 10) / 10;

/** Adds km to parts (not starters, not retired) and retires the ones that reach their life; returns the parts retired. Does not save. */
function wearParts(p: PlayerParts, parts: Part[], km: number): Part[] {
  const add = Math.max(0, Number.isFinite(km) ? km : 0);
  const retired: Part[] = [];
  for (const part of parts) {
    if (part.rarity === "starter" || part.retired) continue;
    part.km = roundKm(part.km + add);
    if (part.km >= catalog.areas[part.area].lifeKm) {
      part.retired = true;
      part.retiredAt = clock.now();
      retired.push(part);
      if (p.equipped[part.area] === part.id) {
        // the area falls back to its starter part, which never leaves the garage
        const starter = p.inventory.find((x) => x.area === part.area && x.rarity === "starter");
        if (starter) p.equipped[part.area] = starter.id;
      }
    }
  }
  return retired;
}

/**
 * Verified driving wears the parts that drove it: km on every fitted part, or
 * on the named parts (the ones fitted when a qualifying attempt started) that
 * are still in the garage. A part at the end of its life is retired: unfitted
 * (its area gets the starter part back) and kept in the garage, greyed.
 */
export function addDistance(player: string, km: number, partIds?: string[]) {
  const p = loadPlayer(player);
  const parts = partIds ? partIds.map((id) => p.inventory.find((x) => x.id === id)).filter((x): x is Part => Boolean(x)) : fittedParts(p);
  const retired = wearParts(p, parts, km);
  savePlayer(p);
  return { km: roundKm(Math.max(0, km)), retired: retired.map((x) => x.id) };
}

/** The car spec the physics drives with: the sum of the fitted parts, traits and synergies. */
export function carSpec(player: string): Spec {
  return carDetail(fittedParts(loadPlayer(player))).spec;
}

export function garage(player: string) {
  const p = loadPlayer(player);
  const fitted = new Set(Object.values(p.equipped));
  const detail = carDetail(fittedParts(p));
  const inventory = p.inventory
    .map((x) => partView(x, fitted.has(x.id)))
    .sort((a, b) => Number(b.equipped) - Number(a.equipped) || Number(a.display.retired) - Number(b.display.retired) || b.createdAt - a.createdAt || AREAS.indexOf(a.area) - AREAS.indexOf(b.area));
  return {
    player,
    inventory,
    equipped: p.equipped,
    credits: p.credits ?? 0,
    car: detail.spec,
    synergies: detail.synergies,
    looks: detail.looks,
    locked: lockCheck(player),
    packs: packSummary(p),
    supply: supplyInfo(),
    livery: p.livery ?? { ...liveryPalette.default },
  };
}

/**
 * Gives a pack for an earn rule (catalogue packs.earn), once per (reason, key):
 * key is the event id for daily rules, the race id for race finishes.
 */
export function awardPack(player: string, reason: string, key: string): { awarded: boolean; pack?: ReturnType<typeof packView>; why?: string } {
  if (!catalog.packs.earn[reason]) throw new PartsError(400, `unknown pack reason ${reason}`);
  const p = loadPlayer(player);
  const awardKey = `${reason}:${key}`;
  if (p.awards[awardKey]) return { awarded: false, why: "already earned" };
  const now = clock.now();
  const week = weekOf(now);
  if (!isBonusPack(reason) && p.packs.filter((x) => x.week === week && !isBonusPack(x.reason)).length >= config.packsPerPlayerWeek) return { awarded: false, why: "weekly pack limit reached" };
  if (!isBonusPack(reason) && p.packs.filter((x) => !x.openedAt).length >= config.maxUnopenedPacks) return { awarded: false, why: "too many unopened packs" };
  // The pack id follows from who earned it and why, so the server cannot re-roll a pack by picking ids
  const id = createHash("sha256").update(`pack:${player}:${awardKey}`).digest("hex").slice(0, 16);
  const pack: Pack = { id, reason, key, week, earnedAt: now };
  p.packs.push(pack);
  p.awards[awardKey] = id;
  savePlayer(p);
  const s = loadSupply(week);
  if (!s.active.includes(player)) {
    s.active.push(player);
    saveSupply(s);
  }
  return { awarded: true, pack: packView(pack) };
}

/** For the race flow: a pack for finishing, and the race on the fitted parts' records. */
export function awardRaceFinish(player: string, raceId: string | number, result: { km?: number; won?: boolean } = {}) {
  const p = loadPlayer(player);
  const key = String(raceId);
  p.raced ??= {};
  if (!p.raced[key]) {
    p.raced[key] = clock.now();
    const fitted = fittedParts(p).filter((part) => part.rarity !== "starter" && !part.retired);
    for (const part of fitted) {
      part.races += 1;
      if (result.won) part.wins += 1;
    }
    wearParts(p, fitted, Math.max(0, Math.round(result.km ?? 0)));
    savePlayer(p);
  }
  return awardPack(player, "race_finish", key);
}

/** Opens the player's oldest unopened pack (or the one named), if this week's supply has room. */
export function openPack(player: string, packId?: string) {
  const p = loadPlayer(player);
  const pack = p.packs.find((x) => !x.openedAt && (!packId || x.id === packId));
  if (!pack) throw new PartsError(400, packId ? "no such unopened pack" : "no unopened packs");
  const now = clock.now();
  const week = weekOf(now);
  const s = loadSupply(week);
  const n = catalog.packs.partsPerPack;
  if (s.minted + n > s.cap) {
    const resetsAt = weekStartMs(week + 1);
    throw new PartsError(409, `This week's part supply is used up (${s.minted} of ${s.cap} parts). Your pack keeps; it opens when the new week starts on ${new Date(resetsAt).toISOString().slice(0, 10)}.`, {
      resetsAt,
      cap: s.cap,
      minted: s.minted,
      week: weekLabel(week),
    });
  }
  const parts: Part[] = rollPack(pack.id, config.seedSecret, packOdds(pack.reason)).map((r, i) => {
    s.minted += 1;
    const part: Part = {
      id: createHash("sha256").update(`part:${pack.id}:${i}`).digest("hex").slice(0, 16),
      area: r.area,
      concept: r.concept,
      rarity: r.rarity,
      stats: r.stats,
      traits: r.traits,
      serial: `#${String(s.minted).padStart(4, "0")}`,
      week,
      minted: "db",
      createdAt: now,
      races: 0,
      wins: 0,
      km: 0,
      tradeable: true,
      packId: pack.id,
      hash: null,
    };
    part.hash = partHash(part);
    s.leaves.push(part.hash);
    return part;
  });
  s.packsOpened += 1;
  pack.openedAt = now;
  pack.parts = parts.map((x) => x.id);
  p.inventory.push(...parts);
  saveSupply(s);
  savePlayer(p);
  return { pack: packView(pack), parts: parts.map((x) => partView(x)), packs: packSummary(p), supply: supplyInfo(week) };
}

/** Fits a part in its area. Refused while the qualifying setup is locked (parc fermé). */
export function equip(player: string, partId: string) {
  const p = loadPlayer(player);
  const part = p.inventory.find((x) => x.id === partId);
  if (!part) throw new PartsError(404, "that part is not in your garage");
  if (p.equipped[part.area] !== part.id) {
    if (lockCheck(player)) throw new PartsError(409, "Parc fermé: parts are locked after your first qualifying run until the event closes.");
    if (part.retired || (part.rarity !== "starter" && part.km >= catalog.areas[part.area].lifeKm)) throw new PartsError(400, "that part is worn out");
    p.equipped[part.area] = part.id;
    savePlayer(p);
  }
  return garage(player);
}

/** Scraps a part for R&D credits by rarity (catalogue scrapCredits). Starter and fitted parts cannot be scrapped. */
export function scrapPart(player: string, partId: string) {
  const p = loadPlayer(player);
  const i = p.inventory.findIndex((x) => x.id === partId);
  if (i < 0) throw new PartsError(404, "that part is not in your garage");
  const part = p.inventory[i];
  if (part.rarity === "starter") throw new PartsError(400, "starter parts cannot be scrapped");
  if (p.equipped[part.area] === part.id) throw new PartsError(400, "that part is fitted: unfit it first");
  const credits = catalog.rarities[part.rarity]?.scrapCredits ?? 0;
  p.inventory.splice(i, 1);
  p.credits = (p.credits ?? 0) + credits;
  savePlayer(p);
  return { ...garage(player), scrapped: { id: part.id, credits } };
}

/** Sets the car's colours: each must be one of the livery palette's (game/data/livery.json), as "#rrggbb" or "rrggbb". */
export function setLivery(player: string, primary: unknown, secondary: unknown): { livery: Livery } {
  const pick = (raw: unknown, options: { hex: string }[], which: string) => {
    const hex = typeof raw === "string" ? `#${raw.trim().replace(/^#/, "").toLowerCase()}` : "";
    if (!options.some((o) => o.hex === hex)) throw new PartsError(400, `${which} must be one of the livery palette's colours`);
    return hex;
  };
  const livery = { primary: pick(primary, liveryPalette.primary, "primary"), secondary: pick(secondary, liveryPalette.secondary, "secondary") };
  const p = loadPlayer(player);
  p.livery = livery;
  savePlayer(p);
  return { livery };
}
