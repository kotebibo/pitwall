// Ranked (docs/RANKED_CONTRACT.md): the Elo/RP maths, placements, promotion and demotion,
// opponents, forfeits, resolving once, the daily medal packs and their odds, and the API
// shapes. The Godot re-drive is replaced by a fake (quali.ts setRedrive) and the Solana RPC
// by one that knows no accounts: never touches Solana or Godot.

import { after, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Keypair } from "@solana/web3.js";

const dataDir = mkdtempSync(join(tmpdir(), "pitwall-ranked-"));
process.env.DATA_DIR = dataDir;
process.env.REALTIME_CHECK = "0";
process.env.PASSES_SETTLE = "off";
process.env.PACKS_PER_PLAYER_WEEK = "50";
process.env.MAX_UNOPENED_PACKS = "50";
process.env.POSTS_PER_MINUTE = "0";
process.env.GETS_PER_MINUTE = "0";
const authorityFile = join(dataDir, "authority.json");
writeFileSync(authorityFile, JSON.stringify([...Keypair.generate().secretKey]));
process.env.AUTHORITY_KEYPAIR = authorityFile;

// every RPC call answers "no such account"
const rpc = createServer((req, res) => {
  let text = "";
  req.on("data", (c) => (text += c));
  req.on("end", () => {
    const calls = JSON.parse(text);
    const answer = (c: { id: unknown }) => ({ jsonrpc: "2.0", id: c.id, result: { context: { slot: 1 }, value: null } });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(Array.isArray(calls) ? calls.map(answer) : answer(calls)));
  });
});
await new Promise<void>((resolve) => rpc.listen(0, "127.0.0.1", resolve));
process.env.RPC_URL = `http://127.0.0.1:${(rpc.address() as AddressInfo).port}`;

const R = await import("../src/ranked.ts");
const Q = await import("../src/quali.ts");
const P = await import("../src/parts.ts");
const { config } = await import("../src/config.ts");
const { server } = await import("../src/index.ts");
await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(() => {
  server.close();
  rpc.close();
  rmSync(dataDir, { recursive: true, force: true });
});

const DAY = 86_400_000;
const MIN = 60_000;
// ranked and parts run on a test clock; each test moves to its own days so boards do not mix
let now = Date.UTC(2031, 0, 6, 12);
R.clock.now = () => now;
P.clock.now = () => now;
const nextWeek = () => (now = (Math.floor(now / DAY) + 14) * DAY + 12 * 3_600_000);
let playerN = 0;
const newPlayer = () => (0xe000000000000000n + BigInt(++playerN)).toString(16);

// the fake re-drive: the laps the next run completes
type Lap = { lap: number; us: number; valid: boolean; sectors: number[]; ticks: number[] };
let redrives = 0;
let nextLaps: Lap[] = [];
Q.setRedrive(async () => {
  redrives++;
  return { physicsVersion: 3, ticks: 9000, laps: nextLaps, inputHash: "00".repeat(32), metres: 3245 };
});
const lap = (us: number, valid = true, n = 1): Lap => ({ lap: n, us, valid, sectors: [us / 4, us / 2, us / 4], ticks: [0, Math.round(us / 8333)] });

/** One ranked race through quali.ts: start the attempt, drive these laps, submit. */
async function race(player: string, laps: Lap[], name = "Driver") {
  const start = await Q.startAttempt(player, name, "ranked", {});
  nextLaps = laps;
  const run = await Q.submitRun(start.attempt, "AAAA");
  return { start, run, ranked: run.ranked! };
}

const opps = (mmr: number, us = 70_000_000) => Array.from({ length: 5 }, () => ({ mmr, us }));

// ---------------------------------------------------------------- maths

test("Elo: expected score, the MMR change with K, and the RP change with the ladder pull", () => {
  assert.equal(R.expectedScore(1200, 1200), 0.5);
  assert.ok(Math.abs(R.expectedScore(1200, 1600) - 1 / 11) < 1e-12);
  assert.ok(Math.abs(R.expectedScore(1600, 1200) + R.expectedScore(1200, 1600) - 1) < 1e-12);

  // placements: K = 64, no RP
  const p = R.scoreRace({ mmr: 1200, ladder: 0, placementsLeft: 5 }, opps(1200), 60_000_000);
  assert.equal(p.wins, 5);
  assert.equal(p.mmr, 1200 + (64 * 2.5) / 5);
  assert.equal(p.rpChange, 0);
  assert.equal(p.placementsLeft, 4);

  // ranked: K = 32; 3 of 5 against equals at the ladder's own MMR
  const field = [65e6, 66e6, 67e6, 68e6, 69e6].map((us) => ({ mmr: 1200, us }));
  const r = R.scoreRace({ mmr: 1200, ladder: 700, placementsLeft: 0 }, field, 66_500_000);
  assert.deepEqual(r.beat, [false, false, true, true, true]);
  assert.equal(r.wins, 3);
  assert.equal(R.ladderMmr(700), 1200);
  assert.equal(r.mmr, 1200 + (32 * 0.5) / 5);
  assert.equal(r.rpChange, Math.round((40 * 0.5) / 5 + (r.mmr - 1200) / 40));
  assert.equal(r.ladder, 700 + r.rpChange);

  // the pull towards your MMR is clamped to ±8
  const high = R.scoreRace({ mmr: 2000, ladder: 0, placementsLeft: 0 }, opps(2000), null);
  assert.equal(high.mmr, 2000 - (32 * 2.5) / 5);
  assert.equal(high.rpChange, Math.round((40 * -2.5) / 5 + 8));
  const low = R.scoreRace({ mmr: 900, ladder: 2000, placementsLeft: 0 }, opps(900), 1);
  assert.equal(low.rpChange, Math.round((40 * 2.5) / 5 - 8));

  // a tie is not a win; typical changes are ±10 to 30
  assert.equal(R.scoreRace({ mmr: 1200, ladder: 700, placementsLeft: 0 }, opps(1200, 66e6), 66e6).wins, 0);
  const all = R.scoreRace({ mmr: 1200, ladder: 700, placementsLeft: 0 }, opps(1200), 1).rpChange;
  const none = R.scoreRace({ mmr: 1200, ladder: 700, placementsLeft: 0 }, opps(1200), null).rpChange;
  assert.ok(all >= 10 && all <= 30 && none <= -10 && none >= -30, `${all} ${none}`);
});

test("ladder points map to tiers and divisions (IV lowest), MASTER from 2800", () => {
  const at = (l: number) => {
    const r = R.rankFromLadder(l);
    return `${r.tier} ${r.division} ${r.rp}`.replace("  ", " ");
  };
  assert.equal(at(0), "IRON IV 0");
  assert.equal(at(99), "IRON IV 99");
  assert.equal(at(100), "IRON III 0");
  assert.equal(at(399), "IRON I 99");
  assert.equal(at(400), "BRONZE IV 0");
  assert.equal(at(1442), "GOLD II 42");
  assert.equal(at(2799), "DIAMOND I 99");
  assert.equal(at(2800), "MASTER 0");
  assert.equal(at(3200), "MASTER 400");
  assert.deepEqual(R.rankFromLadder(500, 3), { tier: "UNRANKED", division: "", rp: 0, ladder: 0, placementsLeft: 3 });
  assert.equal(R.placementLadder(700), 0);
  assert.equal(R.placementLadder(1200), 700);
  assert.equal(R.placementLadder(2800), 3200);
});

test("promotion and demotion at the boundaries; Iron IV never drops below 0", () => {
  assert.deepEqual(R.applyRp(195, 10), { ladder: 205, promoted: true, demoted: false }); // III 95 -> II 5
  assert.deepEqual(R.applyRp(150, 49), { ladder: 199, promoted: false, demoted: false });
  assert.deepEqual(R.applyRp(150, 50), { ladder: 200, promoted: true, demoted: false });
  assert.deepEqual(R.applyRp(200, 0), { ladder: 200, promoted: false, demoted: false });
  assert.deepEqual(R.applyRp(200, -1), { ladder: 175, promoted: false, demoted: true }); // to 75 of the division below
  assert.deepEqual(R.applyRp(205, -30), { ladder: 175, promoted: false, demoted: true });
  assert.deepEqual(R.applyRp(395, 10), { ladder: 405, promoted: true, demoted: false }); // Iron I -> Bronze IV 5
  assert.deepEqual(R.applyRp(402, -5), { ladder: 375, promoted: false, demoted: true }); // Bronze IV -> Iron I 75
  assert.deepEqual(R.applyRp(2790, 20), { ladder: 2810, promoted: true, demoted: false }); // into MASTER
  assert.deepEqual(R.applyRp(3000, 40), { ladder: 3040, promoted: false, demoted: false }); // MASTER counts on
  assert.deepEqual(R.applyRp(2805, -10), { ladder: 2775, promoted: false, demoted: true }); // to Diamond I 75
  // Iron IV floor
  assert.deepEqual(R.applyRp(10, -30), { ladder: 0, promoted: false, demoted: false });
  assert.deepEqual(R.applyRp(0, -30), { ladder: 0, promoted: false, demoted: false });
  assert.deepEqual(R.applyRp(110, -30), { ladder: 75, promoted: false, demoted: true }); // Iron III -> Iron IV 75
});

// ---------------------------------------------------------------- opponents

test("AI benchmark drivers: 10, one per 200 MMR from 700 to 2500, with ±150 ms daily jitter", () => {
  const day = Math.floor(now / DAY);
  const ai = R.aiDrivers(day);
  assert.equal(ai.length, 10);
  assert.deepEqual(ai.map((a) => a.mmr), [700, 900, 1100, 1300, 1500, 1700, 1900, 2100, 2300, 2500]);
  for (const a of ai) {
    assert.equal(a.ai, true);
    assert.ok(Math.abs(a.us - (72_000_000 - (a.mmr - 700) * 4278)) <= 150_000, `${a.name} ${a.us}`);
    assert.equal(a.tier, R.rankFromLadder(R.placementLadder(a.mmr)).tier);
  }
  assert.equal(ai[0].tier, "IRON");
  assert.equal(ai[9].tier, "MASTER");
  assert.deepEqual(R.aiDrivers(day), ai);
  assert.notDeepEqual(R.aiDrivers(day + 1).map((a) => a.us), ai.map((a) => a.us));
});

test("opponents: always 5, nearest by MMR, fastest first, AI filling in", () => {
  const ai = R.aiDrivers(1);
  const h = (name: string, mmr: number, us: number) => ({ name, mmr, us, ai: false, tier: "SILVER", division: "II" });
  // no humans: the five AI nearest 1200
  const alone = R.pickOpponents(1200, ai);
  assert.equal(alone.length, 5);
  assert.ok(alone.every((o) => o.ai));
  assert.deepEqual(alone.map((o) => o.mmr).sort(), [1100, 1300, 1500, 1700, 900]);
  for (let i = 1; i < 5; i++) assert.ok(alone[i - 1].us <= alone[i].us);
  // humans near you come in, the AI fill the rest
  const some = R.pickOpponents(1200, [h("A", 1210, 69e6), h("B", 1150, 70e6), h("Far", 2400, 60e6), ...ai]);
  assert.equal(some.length, 5);
  assert.deepEqual(some.filter((o) => !o.ai).map((o) => o.name).sort(), ["A", "B"]);
  // a human ties an AI on distance: the human goes first
  assert.ok(R.pickOpponents(1300, [h("Tie", 1300, 75e6), ...ai]).some((o) => o.name === "Tie"));
  // plenty of humans: still 5, all the nearest
  const crowd = Array.from({ length: 30 }, (_, i) => h(`H${i}`, 1000 + i * 15, 68e6 + i * 1000));
  const many = R.pickOpponents(1200, [...crowd, ...ai]);
  assert.equal(many.length, 5);
  assert.deepEqual(many.map((o) => o.name).sort(), ["H11", "H12", "H13", "H14", "H15"]); // 1165..1225
});

test("a ranked attempt starts a race: 5 opponents with humans who drove ranked in the last 7 days", async () => {
  nextWeek();
  const old = newPlayer();
  await race(old, [lap(69_000_000)], "Old Lap");
  now += 8 * DAY; // that lap leaves the window
  const recent = newPlayer();
  await race(recent, [lap(69_500_000)], "Recent Lap");
  now += 3 * DAY;
  const me = newPlayer();
  const start = await Q.startAttempt(me, "Me", "ranked", {});
  const opponents = (start as { rankedMatch: { opponents: Record<string, unknown>[] } }).rankedMatch.opponents;
  assert.equal(opponents.length, 5);
  for (const o of opponents) assert.deepEqual(Object.keys(o).sort(), ["ai", "division", "name", "tier", "us"]);
  for (let i = 1; i < 5; i++) assert.ok((opponents[i - 1].us as number) <= (opponents[i].us as number));
  const human = opponents.find((o) => !o.ai);
  assert.deepEqual(human, { name: "Recent Lap", tier: "UNRANKED", division: "", us: 69_500_000, ai: false });
  assert.ok(!opponents.some((o) => o.name === "Old Lap"));
  // non-ranked attempts carry no race
  assert.equal("rankedMatch" in (await Q.startAttempt(me, "Me", "practice", {})), false);
});

// ---------------------------------------------------------------- races

test("placements: 5 races without a rank (K = 64), then placed by MMR", async () => {
  nextWeek();
  const p = newPlayer();
  let mmr = R.START_MMR;
  for (let i = 1; i <= 5; i++) {
    const { ranked } = await race(p, [lap(60_000_000)]);
    const opponents = R.ladderStore()[p].recent[0];
    assert.equal(opponents.wins, 5);
    assert.equal(ranked.rpChange, 0);
    assert.equal(ranked.wins, 5);
    assert.equal(ranked.of, 5);
    assert.ok(R.ladderStore()[p].mmr > mmr, "beating everyone raises the MMR");
    mmr = R.ladderStore()[p].mmr;
    if (i < 5) {
      assert.equal(ranked.placed, false);
      assert.deepEqual(ranked.rank, { tier: "UNRANKED", division: "", rp: 0, ladder: 0, placementsLeft: 5 - i });
    } else {
      assert.equal(ranked.placed, true);
      const ladder = R.placementLadder(mmr);
      assert.deepEqual(ranked.rank, R.rankFromLadder(ladder));
      assert.equal(ranked.rank.placementsLeft, 0);
      assert.notEqual(ranked.rank.tier, "UNRANKED");
    }
  }
  // the next race moves RP
  const { ranked } = await race(p, [lap(80_000_000)]);
  assert.equal(ranked.placed, false);
  assert.ok(ranked.rpChange < 0);
  const info = R.rankedInfo(p);
  assert.equal(info.you!.races, 6);
  assert.equal(info.you!.wins, 5);
  assert.equal(info.you!.losses, 1);
  assert.equal(info.you!.recent.length, 5);
  assert.equal(info.you!.recent[0].rpChange, ranked.rpChange);
});

test("the race is the FIRST completed lap: a deleted first lap is a forfeit even with a fast second lap", async () => {
  nextWeek();
  const p = newPlayer();
  const { ranked, run } = await race(p, [lap(60_000_000, false, 1), lap(60_000_000, true, 2)]);
  assert.equal(ranked.forfeit, true);
  assert.equal(ranked.us, null);
  assert.equal(ranked.wins, 0);
  assert.ok(ranked.opponents.every((o) => !o.beat));
  assert.equal(ranked.medal, null);
  assert.deepEqual(ranked.packsEarned, []);
  assert.equal(run.best!.us, 60_000_000); // the usual fields are unchanged
  // no lap at all is a forfeit too
  assert.equal((await race(p, [])).ranked.forfeit, true);
  // a valid first lap counts, not the faster second one
  const counted = (await race(p, [lap(69_000_000, true, 1), lap(60_000_000, true, 2)])).ranked;
  assert.equal(counted.forfeit, false);
  assert.equal(counted.us, 69_000_000);
  assert.equal(counted.counted, true);
});

test("an abandoned race is a forfeit at the next start, or after 30 minutes; each resolves once", async () => {
  nextWeek();
  const p = newPlayer();
  const a = await Q.startAttempt(p, "Quitter", "ranked", {});
  const b = await Q.startAttempt(p, "Quitter", "ranked", {});
  let info = R.rankedInfo(p);
  assert.equal(info.you!.races, 1);
  assert.equal(info.you!.recent[0].forfeit, true);
  assert.equal(info.you!.recent[0].wins, 0);
  // the abandoned attempt's run comes too late: the stored forfeit stands
  nextLaps = [lap(60_000_000)];
  const late = await Q.submitRun(a.attempt, "AAAA");
  assert.equal(late.ranked!.forfeit, true);
  assert.equal(R.rankedInfo(p).you!.races, 1);
  // b is open; a run being re-driven as the attempt expires gets a minute's grace, then it is a forfeit
  now += 30 * MIN + 30_000;
  assert.equal(R.rankedInfo(p).you!.races, 1);
  now += 2 * MIN;
  info = R.rankedInfo(p);
  assert.equal(info.you!.races, 2);
  assert.equal(info.you!.recent[0].forfeit, true);
  assert.equal(R.ladderStore()[p].pending, null);
  const lateB = await Q.submitRun(b.attempt, "AAAA");
  assert.equal(lateB.ranked!.forfeit, true);
  assert.equal(R.rankedInfo(p).you!.races, 2);
});

test("a race is resolved once: the run asked again returns the stored result without a re-drive", async () => {
  nextWeek();
  const p = newPlayer();
  const start = await Q.startAttempt(p, "Once", "ranked", {});
  nextLaps = [lap(66_000_000)];
  const before = redrives;
  const first = await Q.submitRun(start.attempt, "AAAA");
  nextLaps = [lap(60_000_000)];
  const again = await Q.submitRun(start.attempt, "AAAAAAAA");
  assert.equal(redrives, before + 1);
  assert.deepEqual(again, first);
  assert.equal(again.ranked!.us, 66_000_000);
  assert.equal(R.rankedInfo(p).you!.races, 1);
  assert.equal(R.resolveRankedRace(p, start.attempt, { us: 1, valid: true })!.us, 66_000_000);
  // the result's opponents are the race's
  const match = (start as { rankedMatch: { opponents: { name: string; us: number }[] } }).rankedMatch.opponents;
  assert.deepEqual(first.ranked!.opponents.map((o) => [o.name, o.us]), match.map((o) => [o.name, o.us]));
  assert.deepEqual(Object.keys(first.ranked!).sort(), ["counted", "daily", "demoted", "forfeit", "medal", "of", "opponents", "packsEarned", "placed", "promoted", "rank", "rpChange", "us", "wins"]);
  assert.deepEqual(Object.keys(first.ranked!.rank).sort(), ["division", "ladder", "placementsLeft", "rp", "tier"]);
});

test("a race result reports promotion and demotion, and the Iron IV floor holds", async () => {
  nextWeek();
  const p = newPlayer();
  await race(p, [lap(80_000_000)]); // creates the ladder record
  const store = R.ladderStore();
  Object.assign(store[p], { mmr: 1200, ladder: 1195, placementsLeft: 0 }); // SILVER I 95
  const up = (await race(p, [lap(60_000_000)])).ranked;
  assert.equal(up.promoted, true);
  assert.equal(up.demoted, false);
  assert.deepEqual([up.rank.tier, up.rank.division, up.rank.rp], ["GOLD", "IV", 1195 + up.rpChange - 1200]);
  Object.assign(store[p], { mmr: 1200, ladder: 1205 });
  const down = (await race(p, [])).ranked;
  assert.equal(down.demoted, true);
  assert.deepEqual([down.rank.tier, down.rank.division, down.rank.rp, down.rank.ladder], ["SILVER", "I", 75, 1175]);
  Object.assign(store[p], { mmr: 700, ladder: 5 });
  const floor = (await race(p, [])).ranked;
  assert.equal(floor.demoted, false);
  assert.deepEqual([floor.rank.tier, floor.rank.division, floor.rank.rp], ["IRON", "IV", 0]);
});

// ---------------------------------------------------------------- medals and packs

test("medal packs: each tier once per UTC day; gold earns all three", async () => {
  nextWeek();
  const p = newPlayer();
  const medalsOf = (packs: unknown[]) => (packs as { medal: string; reason: string }[]).map((x) => `${x.reason}:${x.medal}`);
  const gold = (await race(p, [lap(64_900_000)])).ranked;
  assert.equal(gold.medal, "gold");
  assert.deepEqual(medalsOf(gold.packsEarned), ["ranked_bronze:bronze", "ranked_silver:silver", "ranked_gold:gold"]);
  assert.equal((gold.packsEarned[2] as { reasonName: string }).reasonName, "Gold medal pack");
  assert.deepEqual(gold.daily, { rank: 1, of: 1 });
  // the same day: nothing more, and the day's best medal stays gold after a slow lap
  const slow = (await race(p, [lap(70_000_000)])).ranked;
  assert.deepEqual(slow.packsEarned, []);
  assert.equal(slow.medal, "gold");
  // the next day: bronze first, silver later in the day adds only silver
  now += DAY;
  const bronze = (await race(p, [lap(68_000_000)])).ranked;
  assert.deepEqual(medalsOf(bronze.packsEarned), ["ranked_bronze:bronze"]);
  const silver = (await race(p, [lap(66_000_000)])).ranked;
  assert.deepEqual(medalsOf(silver.packsEarned), ["ranked_silver:silver"]);
  assert.equal(silver.medal, "silver");
  // no medal, no pack; a forfeit earns nothing
  const q = newPlayer();
  const none = (await race(q, [lap(69_000_000)])).ranked;
  assert.equal(none.medal, null);
  assert.deepEqual(none.packsEarned, []);
  // the garage lists them with their medal; other packs have none
  const pending = P.garage(p).packs.pending as { medal?: string; reason: string }[];
  assert.equal(pending.filter((x) => x.medal === "gold").length, 1);
  assert.equal(pending.filter((x) => x.medal === "bronze").length, 2);
  assert.ok(pending.every((x) => x.medal === x.reason.replace("ranked_", "")));
  const first = P.awardPack(q, "first_quali", "1");
  assert.equal("medal" in first.pack!, false);
});

test("pack odds come from the earn reason; packs without odds roll exactly as before", () => {
  assert.deepEqual(P.packOdds("ranked_gold"), [["common", 35], ["rare", 37], ["epic", 21], ["legendary", 7]]);
  assert.deepEqual(P.packOdds("ranked_silver"), [["common", 52], ["rare", 32], ["epic", 13], ["legendary", 3]]);
  assert.deepEqual(P.packOdds("ranked_bronze"), [["common", 70], ["rare", 22], ["epic", 7], ["legendary", 1]]);
  assert.deepEqual(P.packOdds("first_quali"), P.packOdds());
  for (let i = 0; i < 50; i++) {
    const id = `odds-${i}`;
    assert.deepEqual(P.rollPack(id, "s"), P.rollPack(id, "s", P.packOdds("first_quali")));
    assert.deepEqual(P.rollPack(id, "s", P.packOdds("ranked_gold")), P.rollPack(id, "s", P.packOdds("ranked_gold")));
  }
  const share = (reason: string) => {
    const n: Record<string, number> = {};
    for (let i = 0; i < 500; i++) for (const part of P.rollPack(`share-${i}`, "s", P.packOdds(reason))) n[part.rarity] = (n[part.rarity] ?? 0) + 1;
    return (r: string) => (n[r] ?? 0) / 1500;
  };
  const gold = share("ranked_gold");
  assert.ok(gold("common") > 0.31 && gold("common") < 0.39, `common ${gold("common")}`);
  assert.ok(gold("legendary") > 0.05 && gold("legendary") < 0.09, `legendary ${gold("legendary")}`);
  const silver = share("ranked_silver");
  assert.ok(silver("common") > 0.48 && silver("common") < 0.56, `common ${silver("common")}`);
  // opening a gold medal pack uses the gold odds
  const p = newPlayer();
  const award = P.awardPack(p, "ranked_gold", "odds-day");
  const opened = P.openPack(p, award.pack!.id);
  assert.deepEqual(
    (opened.parts as { concept: string }[]).map((x) => x.concept),
    P.rollPack(award.pack!.id, config.seedSecret, P.packOdds("ranked_gold")).map((r) => r.concept),
  );
  assert.equal(opened.pack.medal, "gold");
});

// ---------------------------------------------------------------- the ladder and the API

test("MASTER+: the top 3 by ladder are CHALLENGER, the next 7 GRANDMASTER; the ladder lists ranked players only", () => {
  const store = R.ladderStore();
  for (const id of Object.keys(store)) store[id].placementsLeft = Math.max(store[id].placementsLeft, 1); // earlier tests' players out of the way
  const ids: string[] = [];
  for (let i = 0; i < 12; i++) {
    const id = newPlayer();
    ids.push(id);
    store[id] = { name: `M${i}`, mmr: 2400, ladder: 2800 + i * 10, placementsLeft: 0, wins: 0, losses: 0, races: 5, recent: [], pending: null, createdAt: now, updatedAt: now };
  }
  const diamond = newPlayer();
  store[diamond] = { name: "D", mmr: 2300, ladder: 2799, placementsLeft: 0, wins: 0, losses: 0, races: 5, recent: [], pending: null, createdAt: now, updatedAt: now };
  const info = R.rankedInfo(ids[11]);
  assert.deepEqual(info.ladder.slice(0, 13).map((r) => r.tier), [...Array(3).fill("CHALLENGER"), ...Array(7).fill("GRANDMASTER"), "MASTER", "MASTER", "DIAMOND"]);
  assert.deepEqual(info.ladder[0], { rank: 1, name: "M11", tier: "CHALLENGER", division: "", rp: 110, you: true });
  assert.deepEqual(info.ladder[12], { rank: 13, name: "D", tier: "DIAMOND", division: "I", rp: 99, you: false });
  assert.equal(info.ladder.length, 13);
  assert.equal(info.you!.tier, "CHALLENGER");
  assert.equal(R.rankedInfo(ids[0]).you!.tier, "MASTER");
});

test("GET /api/ranked: the contract's shape, for guests too", async () => {
  nextWeek();
  const p = newPlayer();
  await race(p, [lap(64_500_000)], "Shape");
  const get = async (q: string) => (await fetch(`${base}/api/ranked${q}`)).json();
  const body = await get(`?player=${p}`);
  assert.deepEqual(Object.keys(body).sort(), ["daily", "ladder", "season", "tiers", "you"]);
  assert.deepEqual(body.season, { id: 1, name: "SEASON 1", endsAt: R.SEASON.endsAt });
  assert.equal(typeof body.season.endsAt, "number");
  assert.deepEqual(body.tiers, ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]);
  assert.deepEqual(Object.keys(body.you).sort(), ["division", "ladder", "losses", "placementsLeft", "races", "recent", "rp", "tier", "wins"]);
  assert.equal(body.you.tier, "UNRANKED");
  assert.equal(body.you.placementsLeft, 4);
  assert.deepEqual(Object.keys(body.you.recent[0]).sort(), ["at", "forfeit", "of", "rpChange", "us", "wins"]);
  assert.deepEqual({ ...body.you.recent[0], at: 0 }, { at: 0, rpChange: 0, wins: 5, of: 5, us: 64_500_000, forfeit: false });
  for (const row of body.ladder) assert.deepEqual(Object.keys(row).sort(), ["division", "name", "rank", "rp", "tier", "you"]);
  assert.ok(body.ladder.length <= 20);
  for (const k of ["closesAt", "medals", "leaderboard", "you"]) assert.ok(k in body.daily, k);
  assert.deepEqual(body.daily.medals, { gold: 65_000_000, silver: 66_500_000, bronze: 68_500_000 });
  assert.equal(body.daily.closesAt, (Math.floor(now / DAY) + 1) * DAY);
  assert.deepEqual(body.daily.leaderboard, [{ rank: 1, name: "Shape", us: 64_500_000, medal: "gold", you: true }]);
  assert.deepEqual({ rank: body.daily.you.rank, us: body.daily.you.us, medal: body.daily.you.medal }, { rank: 1, us: 64_500_000, medal: "gold" });
  // a guest with no id: no `you`
  const guest = await get("");
  assert.equal(guest.you, null);
  assert.equal(guest.daily.you, null);
  assert.equal(guest.daily.leaderboard[0].you, false);
  // a player who never raced: unranked, 5 placements to go
  const fresh = await get(`?player=${newPlayer()}`);
  assert.deepEqual(fresh.you, { tier: "UNRANKED", division: "", rp: 0, ladder: 0, placementsLeft: 5, wins: 0, losses: 0, races: 0, recent: [] });
});

test("POST /api/attempts {session: ranked} returns rankedMatch; the run returns ranked", async () => {
  nextWeek();
  const p = newPlayer();
  const res = await fetch(`${base}/api/attempts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ player: p, name: "Http", session: "ranked", setup: {} }) });
  assert.equal(res.status, 201);
  const start = await res.json();
  assert.equal(start.rankedMatch.opponents.length, 5);
  for (const k of ["attempt", "seed", "setup", "stats", "car", "eventId"]) assert.ok(k in start, k);
  nextLaps = [lap(67_000_000)];
  const run = await (await fetch(`${base}/api/attempts/${start.attempt}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ inputs: "AAAA" }) })).json();
  assert.equal(run.verified, true);
  assert.equal(run.ranked.us, 67_000_000);
  assert.equal(run.ranked.medal, "bronze");
  assert.equal(run.ranked.packsEarned.length, 1);
  assert.equal(run.ranked.packsEarned[0].medal, "bronze");
  // other sessions are untouched: no ranked part
  const q = await (await fetch(`${base}/api/attempts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ player: p, name: "Http", session: "practice", setup: {} }) })).json();
  assert.equal("rankedMatch" in q, false);
  nextLaps = [lap(66_000_000)];
  const qrun = await (await fetch(`${base}/api/attempts/${q.attempt}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ inputs: "AAAA" }) })).json();
  assert.equal(qrun.ranked, null);
});
