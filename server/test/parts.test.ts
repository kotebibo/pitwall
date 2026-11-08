// Parts economy: rolls, budgets, car spec, supply caps and the garage store.
// Runs on a temporary data dir and never touches the chain.

import { after, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

process.env.DATA_DIR = mkdtempSync(join(tmpdir(), "pitwall-parts-"));
after(() => rmSync(process.env.DATA_DIR!, { recursive: true, force: true }));
const { config } = await import("../src/config.ts");
const P = await import("../src/parts.ts");
const { catalog, SPEC_KEYS } = P;
type Spec = import("../src/parts.ts").Spec;
type ConceptDef = import("../src/parts.ts").ConceptDef;

const SECRET = "test-secret";
const DAY = 86_400_000;
const at = (week: number, day = 2) => P.weekStartMs(week) + day * DAY + 3_600_000;
const BASE_WEEK = P.weekOf(Date.UTC(2031, 0, 1));
let playerN = 0;
const newPlayer = () => (0x1000000000000000n + BigInt(++playerN)).toString(16);

test("a pack rolls the same parts every time from its id and the secret", () => {
  assert.deepEqual(P.rollPack("0123456789abcdef", SECRET), P.rollPack("0123456789abcdef", SECRET));
  assert.notDeepEqual(P.rollPack("0123456789abcdef", SECRET), P.rollPack("0123456789abcdee", SECRET));
  assert.notDeepEqual(P.rollPack("0123456789abcdef", SECRET), P.rollPack("0123456789abcdef", "other-secret"));
});

test("packs hold three parts and never three from one area", () => {
  for (let i = 0; i < 500; i++) {
    const parts = P.rollPack(`area-${i}`, SECRET);
    assert.equal(parts.length, catalog.packs.partsPerPack);
    for (const a of P.AREAS) assert.ok(parts.filter((p) => p.area === a).length <= catalog.packs.maxSameArea);
  }
});

test("every rolled part spends the same lap-time budget, inside its concept's ranges", () => {
  const rarities: Record<string, number> = {};
  let n = 0;
  for (let i = 0; i < 1000; i++) {
    for (const part of P.rollPack(`budget-${i}`, SECRET)) {
      n++;
      const def = catalog.areas[part.area].concepts[part.concept];
      const target = P.budgetTarget(part.rarity, part.traits);
      assert.ok(Math.abs(P.goodness(part.stats) - target) <= catalog.budget.tolerance, `${part.area}.${part.concept} ${P.goodness(part.stats)} vs ${target}`);
      assert.equal(part.points, P.goodness(part.stats));
      // base stats (without the traits) stay inside the concept's ranges; unlisted stats are zero
      const delta = P.traitDelta(part.traits);
      for (const k of SPEC_KEYS) {
        const base = part.stats[k] - delta[k];
        const [lo, hi] = def.stats[k] ?? [0, 0];
        assert.ok(base >= lo && base <= hi, `${part.concept}.${k} = ${base} outside ${lo}..${hi}`);
        assert.ok(Number.isInteger(part.stats[k]));
      }
      // traits: as many as the rarity gives, distinct, from the concept's list
      assert.equal(part.traits.length, Math.min(catalog.rarities[part.rarity].traits, def.traits.length));
      assert.equal(new Set(part.traits).size, part.traits.length);
      for (const t of part.traits) assert.ok(def.traits.includes(t));
      rarities[part.rarity] = (rarities[part.rarity] ?? 0) + 1;
    }
  }
  assert.equal(n, 3000);
  // weights 70/22/7/1: loose bounds for 3000 draws
  assert.ok(rarities.common / n > 0.65 && rarities.common / n < 0.75, JSON.stringify(rarities));
  assert.ok(rarities.rare / n > 0.18 && rarities.rare / n < 0.26, JSON.stringify(rarities));
  assert.ok((rarities.legendary ?? 0) / n < 0.025, JSON.stringify(rarities));
  assert.equal(rarities.starter, undefined);
});

test("rarity adds at most 5% budget", () => {
  for (const [id, r] of Object.entries(catalog.rarities)) {
    assert.ok(r.budgetBonus <= 0.05, id);
    assert.ok(P.budgetTarget(id, []) - P.budgetTarget("common", []) <= Math.ceil(catalog.budget.points * 0.05), id);
  }
});

// Upper bound of c.s over a concept's ranges with the budget held fixed (a one-constraint LP, solved greedily).
function lpMax(def: ConceptDef, c: Record<string, number>, target: number): number | null {
  const w = catalog.lapWeights.weights;
  const keys = Object.keys(def.stats) as (keyof Spec)[];
  const lo = keys.map((k) => def.stats[k]![0]);
  const hi = keys.map((k) => def.stats[k]![1]);
  const s = keys.map((k, i) => (c[k] > 0 ? hi[i] : c[k] < 0 ? lo[i] : (lo[i] + hi[i]) / 2));
  let need = target - s.reduce((a, v, i) => a + v * w[keys[i]], 0);
  const moves = keys
    .map((k, i) => {
      const dir = Math.sign(need) * Math.sign(w[k]);
      return { i, dir, room: dir > 0 ? hi[i] - s[i] : s[i] - lo[i], loss: (c[k] * dir) / Math.abs(w[k] || 1), w: Math.abs(w[k]) };
    })
    .filter((m) => m.w > 0 && m.room > 0)
    .sort((a, b) => b.loss - a.loss);
  for (const m of moves) {
    if (Math.abs(need) < 1e-9) break;
    const take = Math.min(m.room * m.w, Math.abs(need));
    s[m.i] += (m.dir * take) / m.w;
    need -= Math.sign(need) * take;
  }
  if (Math.abs(need) > 1e-6) return null;
  return s.reduce((a, v, i) => a + v * c[keys[i]], 0);
}
function combos(items: string[], n: number): string[][] {
  if (n === 0) return [[]];
  return items.flatMap((t, i) => combos(items.slice(i + 1), n - 1).map((c) => [t, ...c]));
}

test("the best and worst possible cars are within 2% of lap time on every track type", () => {
  const w = catalog.lapWeights.weights;
  for (const [type, tt] of Object.entries(catalog.trackTypes)) {
    const c = Object.fromEntries(SPEC_KEYS.map((k) => [k, w[k] * tt.multipliers[k]]));
    const neg = Object.fromEntries(SPEC_KEYS.map((k) => [k, -c[k]]));
    let best = 0;
    let worst = 0;
    for (const area of Object.values(catalog.areas)) {
      let hi = 0; // the starter part (all zeros) is always an option
      let lo = 0;
      for (const def of Object.values(area.concepts)) {
        for (const [rid, r] of Object.entries(catalog.rarities)) {
          if (!r.weight) continue;
          for (const traits of combos(def.traits, Math.min(r.traits, def.traits.length))) {
            const d = P.traitDelta(traits);
            const target = P.budgetTarget(rid, traits) - P.goodness(d) + catalog.budget.tolerance;
            const fromTraits = SPEC_KEYS.reduce((s, k) => s + d[k] * c[k], 0);
            const up = lpMax(def, c, target);
            const down = lpMax(def, neg, target - 2 * catalog.budget.tolerance);
            assert.ok(up !== null && down !== null, "budget must be reachable");
            hi = Math.max(hi, up + fromTraits);
            lo = Math.min(lo, -down + fromTraits);
          }
        }
      }
      best += hi;
      worst += lo;
    }
    for (const s of catalog.synergies) {
      const g = SPEC_KEYS.reduce((a, k) => a + (s.delta[k] ?? 0) * c[k], 0);
      if (g > 0) best += g;
      else worst += g;
    }
    const fs = catalog.traits.floor_synergy.conditional!.delta;
    best += 3 * SPEC_KEYS.reduce((a, k) => a + (fs[k] ?? 0) * c[k], 0);
    assert.ok(best - worst <= 2000, `${type}: parts swing ${(best - worst) / 1000}% of lap time`);
  }
});

test("no fitted car can exceed the physics clamps", () => {
  for (const k of SPEC_KEYS) {
    let up = 0;
    let down = 0;
    for (const area of Object.values(catalog.areas)) {
      let amax = 0;
      let amin = 0;
      for (const def of Object.values(area.concepts)) {
        const [lo, hi] = def.stats[k] ?? [0, 0];
        const t = def.traits.map((id) => catalog.traits[id].delta[k] ?? 0);
        amax = Math.max(amax, hi + t.filter((x) => x > 0).sort((a, b) => b - a).slice(0, 2).reduce((a, b) => a + b, 0));
        amin = Math.min(amin, lo + t.filter((x) => x < 0).sort((a, b) => a - b).slice(0, 2).reduce((a, b) => a + b, 0));
      }
      up += amax;
      down += amin;
    }
    for (const s of catalog.synergies) {
      const v = s.delta[k] ?? 0;
      if (v > 0) up += v;
      else down += v;
    }
    up += 3 * Math.max(0, catalog.traits.floor_synergy.conditional!.delta[k] ?? 0);
    const [cl, ch] = catalog.specKeys[k].physicsClamp;
    assert.ok(up <= ch && down >= cl, `${k}: ${down}..${up} vs clamp ${cl}..${ch}`);
  }
});

const spec = (s: Partial<Spec>): Spec => ({ ...P.zeroSpec(), ...s });
const part = (area: string, concept: string, stats: Partial<Spec>, traits: string[] = []) => ({ area, concept, traits, stats: spec(stats) });

test("car spec sums the fitted parts, conditional traits and synergies", () => {
  const fw = part("front_wing", "outwash", { downforce: 10, drag: 15, balance: 8 });
  const rwHigh = part("rear_wing", "highdf", { downforce: 12, drag: 25, balance: -6 });
  const floor = part("floor", "high_rake", { downforce: 14, drag: 12, balance: 5, grip: -2 });
  const pods = part("sidepods", "downwash", { downforce: 5, drag: 4 }, ["floor_synergy"]);
  const susp = part("suspension", "baseline", {});
  const pu = part("power_unit", "torque", { traction: 10, power: -2, harvest: -5 });

  const matched = P.carDetail([fw, rwHigh, floor, pods, susp, pu]);
  // parts + aero family (+10 downforce) + clean floor edge (-3 drag) + floor synergy trait (+4 downforce)
  assert.deepEqual(matched.spec, spec({ downforce: 10 + 12 + 14 + 5 + 10 + 4, drag: 15 + 25 + 12 + 4 - 3, balance: 8 - 6 + 5, grip: -2, traction: 10, power: -2, harvest: -5 }));
  assert.deepEqual(matched.synergies.map((s) => s.id).sort(), ["aero_family", "clean_floor_edge", "trait:floor_synergy:sidepods"]);
  assert.deepEqual(matched.looks, { front_wing: "outwash", rear_wing: "highdf", sidepods: "downwash", floor: "high_rake" });

  // a spoon rear wing behind an outwash front wing: no family bonus, and the wake mismatch
  const rwSpoon = part("rear_wing", "spoon", { downforce: -8, drag: -20, balance: 4 });
  const mismatched = P.carDetail([fw, rwSpoon, floor, pods, susp, pu]);
  assert.deepEqual(mismatched.synergies.map((s) => s.id).sort(), ["clean_floor_edge", "trait:floor_synergy:sidepods", "wake_mismatch"]);
  assert.equal(mismatched.spec.balance, 8 + 4 + 5 + 6);
  assert.equal(mismatched.spec.downforce, 10 - 8 + 14 + 5 - 4 + 4);

  // the floor synergy trait does nothing on a floor from another family; baseline parts have no family
  const venturi = part("floor", "venturi", { downforce: 12 });
  const other = P.carDetail([pods, venturi]);
  assert.deepEqual(other.spec, spec({ downforce: 5 + 12, drag: 4 }));
  assert.deepEqual(P.carDetail([part("front_wing", "baseline", {}), part("rear_wing", "baseline", {}), part("floor", "baseline", {})]).synergies, []);
});

test("the Merkle root commits to every part in order", () => {
  const h = (s: string) => P.partHash({ id: s, area: "floor", concept: "venturi", rarity: "common", stats: P.zeroSpec(), traits: [], serial: "#0001", week: 1 });
  assert.equal(P.merkleRoot([]), null);
  assert.equal(P.merkleRoot([h("a")]), h("a"));
  const r3 = P.merkleRoot([h("a"), h("b"), h("c")]);
  assert.notEqual(r3, P.merkleRoot([h("a"), h("b")]));
  assert.notEqual(r3, P.merkleRoot([h("b"), h("a"), h("c")]));
  assert.equal(r3, P.merkleRoot([h("a"), h("b"), h("c")]));
});

test("a new player starts with six starter parts fitted and a neutral car", () => {
  P.clock.now = () => at(BASE_WEEK);
  const player = newPlayer();
  const g = P.garage(player);
  assert.equal(g.inventory.length, P.AREAS.length);
  for (const x of g.inventory) {
    assert.equal(x.rarity, "starter");
    assert.equal(x.tradeable, false);
    assert.equal(x.equipped, true);
  }
  assert.deepEqual(Object.keys(g.equipped).sort(), [...P.AREAS].sort());
  assert.deepEqual(g.car, P.zeroSpec());
  assert.deepEqual(P.carSpec(player), P.zeroSpec());
  assert.deepEqual(g.looks, { front_wing: "outwash", rear_wing: "highdf", sidepods: "downwash", floor: "low_rake" });
  assert.equal(g.packs.unopened, 0);
  assert.throws(() => P.garage("not-a-player"), /bad player id/);
});

test("packs are earned once per rule and capped per player per week", () => {
  P.clock.now = () => at(BASE_WEEK + 1);
  const player = newPlayer();
  assert.equal(P.awardPack(player, "first_quali", "100").awarded, true);
  assert.equal(P.awardPack(player, "first_quali", "100").awarded, false);
  for (let day = 101; day < 100 + config.packsPerPlayerWeek; day++) assert.equal(P.awardPack(player, "first_quali", String(day)).awarded, true);
  const over = P.awardPack(player, "quali_top3", "101");
  assert.equal(over.awarded, false);
  assert.equal(over.why, "weekly pack limit reached");
  assert.equal(P.garage(player).packs.earnedThisWeek, config.packsPerPlayerWeek);
  P.clock.now = () => at(BASE_WEEK + 2);
  assert.equal(P.awardPack(player, "quali_top3", "101").awarded, true);
  assert.throws(() => P.awardPack(player, "bought_it", "1"), /unknown pack reason/);
});

test("opening a pack mints numbered parts, and the global weekly cap holds", () => {
  const week = BASE_WEEK + 10;
  P.clock.now = () => at(week);
  config.partsWeeklyCap = 6;
  config.partsPerActivePlayer = 0;
  const player = newPlayer();
  for (const day of ["1", "2", "3"]) P.awardPack(player, "first_quali", day);

  const first = P.openPack(player);
  assert.equal(first.parts.length, 3);
  assert.deepEqual(first.parts.map((x) => x.serial), ["#0001", "#0002", "#0003"]);
  for (const x of first.parts) {
    assert.equal(x.minted, "db");
    assert.equal(x.tradeable, true);
    assert.equal(x.week, week);
    assert.equal(x.hash, P.partHash(x));
    assert.ok(x.display.name && x.display.sprite?.startsWith("res://assets/sprites/parts/"));
  }
  // what the pack holds is exactly what the deterministic roll says
  assert.deepEqual(first.parts.map((x) => x.stats), P.rollPack(first.pack.id).map((r) => r.stats));
  const second = P.openPack(player);
  assert.deepEqual(second.parts.map((x) => x.serial), ["#0004", "#0005", "#0006"]);
  assert.equal(second.supply.minted, 6);
  assert.equal(second.supply.root, P.merkleRoot([...first.parts, ...second.parts].map((x) => x.hash!)));

  // the cap is reached: the third pack waits for next week
  assert.throws(
    () => P.openPack(player),
    (e: InstanceType<typeof P.PartsError>) => e.status === 409 && e.details.resetsAt === P.weekStartMs(week + 1) && /supply is used up/.test(e.message),
  );
  assert.equal(P.garage(player).packs.unopened, 1);
  P.clock.now = () => at(week + 1);
  assert.equal(P.openPack(player).parts[0].serial, "#0001");
  assert.equal(P.garage(player).inventory.length, P.AREAS.length + 9);
  assert.throws(() => P.openPack(player), /no unopened packs/);
  config.partsWeeklyCap = 3000;
});

test("weekly supply follows last week's active players, between the floor and the hard cap", () => {
  const week = BASE_WEEK + 20;
  config.partsPerActivePlayer = 3;
  config.partsWeeklyFloor = 5;
  config.partsWeeklyCap = 20;
  P.clock.now = () => at(week);
  for (let i = 0; i < 4; i++) P.awardPack(newPlayer(), "first_quali", "1");
  assert.equal(P.supplyInfo(week + 1).cap, 12); // 4 active x 3
  for (let i = 0; i < 10; i++) P.awardPack(newPlayer(), "first_quali", "2");
  assert.equal(P.supplyInfo(week + 2).cap, 5); // nobody active in week + 1: the floor
  P.clock.now = () => at(week + 3);
  for (let i = 0; i < 10; i++) P.awardPack(newPlayer(), "first_quali", "3");
  assert.equal(P.supplyInfo(week + 4).cap, 20); // 30 capped at the hard cap
  config.partsPerActivePlayer = 0;
  config.partsWeeklyCap = 3000;
});

test("equipping a part: one per area, refused under parc ferme", () => {
  P.clock.now = () => at(BASE_WEEK + 30);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const [p] = P.openPack(player).parts;
  const starter = P.garage(player).equipped[p.area];

  P.setEquipLockCheck(() => true);
  assert.throws(() => P.equip(player, p.id), (e: InstanceType<typeof P.PartsError>) => e.status === 409 && /Parc fermé/.test(e.message));
  assert.equal(P.garage(player).equipped[p.area], starter);
  assert.equal(P.garage(player).locked, true);

  P.setEquipLockCheck(() => false);
  const g = P.equip(player, p.id);
  assert.equal(g.equipped[p.area], p.id);
  assert.equal(g.inventory.filter((x) => x.equipped && x.area === p.area).length, 1);
  assert.deepEqual(P.carSpec(player), P.carDetail([{ ...p }]).spec);
  // back to the starter part
  assert.equal(P.equip(player, starter).equipped[p.area], starter);
  assert.throws(() => P.equip(player, "ffffffffffffffff"), (e: InstanceType<typeof P.PartsError>) => e.status === 404);
});

test("a race finish earns a pack and goes on the fitted parts' records", () => {
  P.clock.now = () => at(BASE_WEEK + 40);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const [p] = P.openPack(player).parts;
  P.equip(player, p.id);
  assert.equal(P.awardRaceFinish(player, 77, { km: 40, won: true }).awarded, true);
  assert.equal(P.awardRaceFinish(player, 77, { km: 40 }).awarded, false);
  const fitted = P.garage(player).inventory.find((x) => x.id === p.id)!;
  assert.equal(fitted.races, 1);
  assert.equal(fitted.wins, 1);
  assert.equal(fitted.km, 40);
  assert.ok(fitted.display.wear > 0 && fitted.display.wear < 1);
});

test("car spec sums the parts' weight in kg", () => {
  const fw = part("front_wing", "outwash", { downforce: 10, weight: 3 });
  const pu = part("power_unit", "efficiency", { harvest: 30, weight: 6 });
  const pod = part("sidepods", "zeropod", { drag: -10, weight: -4 });
  assert.equal(P.carDetail([fw, pu, pod]).spec.weight, 5);
  // parts rolled before weight existed count as 0 kg
  const old = { ...fw, stats: { downforce: 10 } as Spec };
  assert.equal(P.carDetail([old]).spec.weight, 0);
});

test("wear: full effect to 70% of a part's life, then down to 60% at the end; starters never wear", () => {
  const life = catalog.areas.front_wing.lifeKm;
  const effect = (km: number, rarity = "common") => P.wearEffect({ area: "front_wing", rarity, km });
  assert.equal(effect(0), 1000);
  assert.equal(effect(life * 0.7), 1000);
  assert.equal(effect(life * 0.85), 800);
  assert.equal(effect(life), 600);
  assert.equal(effect(life * 3), 600);
  assert.equal(effect(life * 3, "starter"), 1000);
  // a worn part gives less of every stat and never ends up worse than the standard part
  let checked = 0;
  for (let i = 0; i < 400; i++) {
    for (const p of P.rollPack(`wear-${i}`, SECRET)) {
      const full = P.goodness(p.stats);
      const lifeKm = catalog.areas[p.area].lifeKm;
      for (const f of [0.8, 0.9, 1]) {
        const e = P.wearEffect({ ...p, km: lifeKm * f });
        const worn = P.carDetail([{ ...p, km: lifeKm * f }]).spec;
        for (const k of SPEC_KEYS) {
          assert.ok(Math.abs(worn[k]) <= Math.abs(p.stats[k]), `${p.concept}.${k} grew with wear`);
          assert.ok(Math.abs(worn[k] - (p.stats[k] * e) / 1000) < 1, `${p.concept}.${k} ${worn[k]} vs ${p.stats[k]} x ${e}`);
        }
        if (full > 0) {
          assert.ok(P.goodness(worn) >= (full * e) / 1000 - 1e-9, `${p.concept} worn ${P.goodness(worn)} vs ${full} x ${e}`);
          assert.ok(P.goodness(worn) >= 0);
        }
        checked++;
      }
    }
  }
  assert.equal(checked, 3600);
});

test("verified driving wears the fitted parts, and the car spec fades with them", () => {
  P.clock.now = () => at(BASE_WEEK + 50);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const [p] = P.openPack(player).parts;
  P.equip(player, p.id);
  const starters = P.garage(player).inventory.filter((x) => x.rarity === "starter");
  // km to a tenth, starters unchanged
  P.addDistance(player, 3.2449);
  let g = P.garage(player);
  assert.equal(g.inventory.find((x) => x.id === p.id)!.km, 3.2);
  for (const s of starters) assert.equal(g.inventory.find((x) => x.id === s.id)!.km, 0);
  P.addDistance(player, 3.2449);
  assert.equal(P.garage(player).inventory.find((x) => x.id === p.id)!.km, 6.4);
  // only the named parts (an attempt's), and only if still in the garage
  P.addDistance(player, 100, [starters[0].id, "ffffffffffffffff"]);
  assert.equal(P.garage(player).inventory.find((x) => x.id === p.id)!.km, 6.4);
  // 85% of its life: 80% effect, in the garage view and the physics spec
  const life = catalog.areas[p.area].lifeKm;
  P.addDistance(player, life * 0.85 - 6.4, [p.id]);
  g = P.garage(player);
  const worn = g.inventory.find((x) => x.id === p.id)!;
  assert.equal(worn.display.effect, 800);
  assert.equal(worn.display.kmLeft, Math.round(life * 0.15 * 10) / 10);
  assert.equal(worn.display.retired, false);
  assert.deepEqual(P.carSpec(player), P.carDetail([{ ...p, km: worn.km }]).spec);
  assert.deepEqual(g.car, P.carSpec(player));
  for (const k of SPEC_KEYS) assert.ok(Math.abs(g.car[k] - p.stats[k] * 0.8) < 1, k);
});

test("a part at the end of its life is retired: unfitted, starter back, kept in the garage", () => {
  P.clock.now = () => at(BASE_WEEK + 51);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const [p, q] = P.openPack(player).parts;
  P.equip(player, p.id);
  const starter = P.garage(player).inventory.find((x) => x.area === p.area && x.rarity === "starter")!;
  const life = catalog.areas[p.area].lifeKm;
  assert.deepEqual(P.addDistance(player, life - 1).retired, []);
  assert.deepEqual(P.addDistance(player, 1).retired, [p.id]);
  const g = P.garage(player);
  assert.equal(g.equipped[p.area], starter.id);
  const r = g.inventory.find((x) => x.id === p.id)!;
  assert.equal(r.retired, true);
  assert.equal(r.retiredAt, at(BASE_WEEK + 51));
  assert.equal(r.equipped, false);
  assert.equal(r.display.retired, true);
  assert.equal(r.display.effect, 600);
  assert.equal(r.display.kmLeft, 0);
  assert.equal(g.inventory[g.inventory.length - 1].id, p.id, "retired parts sort last");
  assert.deepEqual(g.car, P.zeroSpec());
  assert.throws(() => P.equip(player, p.id), (e: InstanceType<typeof P.PartsError>) => e.status === 400 && /worn out/.test(e.message));
  // a retired part wears no further
  P.equip(player, q.id);
  P.addDistance(player, 50, [p.id, q.id]);
  assert.equal(P.garage(player).inventory.find((x) => x.id === p.id)!.km, life);
  assert.equal(P.garage(player).inventory.find((x) => x.id === q.id)!.km, 50);
});

test("race finishes wear the fitted parts and retire them too", () => {
  P.clock.now = () => at(BASE_WEEK + 52);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const [p] = P.openPack(player).parts;
  P.equip(player, p.id);
  const life = catalog.areas[p.area].lifeKm;
  P.addDistance(player, life - 10);
  P.awardRaceFinish(player, 900, { km: 16, won: false });
  const g = P.garage(player);
  const r = g.inventory.find((x) => x.id === p.id)!;
  assert.equal(r.races, 1);
  assert.equal(r.km, life + 6);
  assert.equal(r.retired, true);
  assert.notEqual(g.equipped[p.area], p.id);
  // the next race does not count on the retired part
  P.awardRaceFinish(player, 901, { km: 16, won: true });
  assert.equal(P.garage(player).inventory.find((x) => x.id === p.id)!.races, 1);
});

test("scrapping a part gives R&D credits by rarity; fitted and starter parts cannot be scrapped", () => {
  assert.deepEqual(["common", "rare", "epic", "legendary"].map((r) => catalog.rarities[r].scrapCredits), [10, 25, 60, 150]);
  P.clock.now = () => at(BASE_WEEK + 53);
  const player = newPlayer();
  P.awardPack(player, "first_quali", "1");
  const parts = P.openPack(player).parts;
  assert.equal(P.garage(player).credits, 0);
  P.equip(player, parts[0].id);
  assert.throws(() => P.scrapPart(player, parts[0].id), (e: InstanceType<typeof P.PartsError>) => e.status === 400 && /unfit it first/.test(e.message));
  const starter = P.garage(player).inventory.find((x) => x.rarity === "starter")!;
  assert.throws(() => P.scrapPart(player, starter.id), (e: InstanceType<typeof P.PartsError>) => e.status === 400);
  assert.throws(() => P.scrapPart(player, "ffffffffffffffff"), (e: InstanceType<typeof P.PartsError>) => e.status === 404);
  let total = 0;
  for (const p of parts.slice(1)) {
    const res = P.scrapPart(player, p.id);
    total += catalog.rarities[p.rarity].scrapCredits;
    assert.deepEqual(res.scrapped, { id: p.id, credits: catalog.rarities[p.rarity].scrapCredits });
    assert.equal(res.credits, total);
    assert.equal(res.inventory.find((x) => x.id === p.id), undefined);
  }
  assert.equal(P.garage(player).credits, total);
  assert.equal(P.garage(player).inventory.length, P.AREAS.length + 1);
});
