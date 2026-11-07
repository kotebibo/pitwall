// Driven races: the field and grid the client gets, the result hash, and the
// finish flow (real-time check, idempotency, chain retries) with the chain and
// the Godot re-drive replaced by fakes. Never touches Solana or Godot.

import { after, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PublicKey } from "@solana/web3.js";

process.env.DATA_DIR = mkdtempSync(join(tmpdir(), "pitwall-driven-"));
delete process.env.REALTIME_CHECK; // the real-time check stays on here
after(() => rmSync(process.env.DATA_DIR!, { recursive: true, force: true }));
const D = await import("../src/driven.ts");
const { RIVALS, PLAYER_DRIVER } = await import("../src/content.ts");
const P = await import("../src/parts.ts");
type DrivenDeps = import("../src/driven.ts").DrivenDeps;
type RedriveResult = import("../src/driven.ts").RedriveResult;

const SETUP = { front_wing: 8, rear_wing: 5, brake_bias: 55, differential: 4 };
const STATS = { braking: 64, cornering: 64, traction: 68, energy: 72 };
const sha = (s: string | Buffer) => createHash("sha256").update(s).digest("hex");
let playerN = 0;
const newPlayer = () => (0xd000000000000000n + BigInt(++playerN)).toString(16);
/** The one player with a qualifying setup today. */
const QUALIFIED = "aa".repeat(8);

// ---------------------------------------------------------------- pure part

const rivals = RIVALS.map((r) => ({ team: r.team, driver: r.driver }));
const entriesFor = (seed: Buffer, compound = 0) => D.buildEntries({ seed, setup: SETUP, stats: STATS, car: { downforce: 12, drag: -4 }, compound, rivals });

test("entries: the player first, then the rivals with their pace, crew, tyres and pit plan", () => {
  const seed = D.raceSeed(1_800_000_000_000);
  const entries = entriesFor(seed, 2);
  assert.equal(entries.length, 6);
  assert.deepEqual(entries[0], { setup: SETUP, stats: STATS, car: { downforce: 12, drag: -4 }, crew: 70, compound: 2 });
  for (let k = 0; k < RIVALS.length; k++) {
    const e = entries[k + 1];
    const d = RIVALS[k].driver;
    assert.deepEqual(e.setup, D.DEFAULT_SETUP);
    assert.deepEqual(e.stats, { braking: d.pace, cornering: d.pace, traction: d.tyreManagement, energy: d.racecraft });
    assert.deepEqual(e.car, {});
    assert.equal(e.pace, Math.min(975, Math.max(900, 925 + (d.pace - 60) * 3)));
    assert.ok(e.crew >= 45 && e.crew <= 85, `crew ${e.crew}`);
    assert.equal(e.compound, k % 2);
    assert.equal(e.pit_compound, e.compound === 0 ? 1 : 0);
    assert.ok(e.pit_lap === 2 || e.pit_lap === 3);
    for (const v of [e.pace, e.crew, e.compound, e.pit_lap, e.pit_compound]) assert.ok(Number.isInteger(v));
  }
  // crews differ between teams
  assert.ok(new Set(entries.slice(1).map((e) => e.crew)).size > 2);
});

test("entries are a pure function of the seed and the inputs", () => {
  const a = entriesFor(D.raceSeed(1_800_000_000_001));
  assert.deepEqual(entriesFor(D.raceSeed(1_800_000_000_001)), a);
  assert.deepEqual(JSON.parse(JSON.stringify(a)), a);
  // pit laps follow the seed: across many races both laps 2 and 3 appear for every team
  const laps = RIVALS.map(() => new Set<number>());
  for (let i = 0; i < 40; i++) entriesFor(D.raceSeed(1_800_000_000_000 + i)).slice(1).forEach((e, k) => laps[k].add(e.pit_lap!));
  for (const s of laps) assert.deepEqual([...s].sort(), [2, 3]);
});

test("AI pace is clamped to 900..975 per mille", () => {
  assert.equal(D.aiPace(60), 925);
  assert.equal(D.aiPace(76), 973);
  assert.equal(D.aiPace(90), 975);
  assert.equal(D.aiPace(40), 900);
});

test("grid: qualifying order mapped to entry indices, else the entry order", () => {
  const teams = RIVALS.map((r) => r.team);
  assert.deepEqual(D.gridFromQuali([teams[2], "you", teams[0], teams[4], teams[1], teams[3]]), [3, 0, 1, 5, 2, 4]);
  // no qualifying time for the player: the grid does not cover the field
  assert.deepEqual(D.gridFromQuali(teams), [0, 1, 2, 3, 4, 5]);
  assert.deepEqual(D.gridFromQuali(["you", "Somebody Else", ...teams.slice(1)]), [0, 1, 2, 3, 4, 5]);
  assert.deepEqual(D.gridFromQuali(["you", teams[0], teams[0], teams[2], teams[3], teams[4]]), [0, 1, 2, 3, 4, 5]);
});

const RESULT: RedriveResult = {
  physicsVersion: 3,
  ticks: 41_854,
  finished: true,
  order: [1, 0, 2, 4, 5, 3],
  cars: [
    { raceUs: 333_607_000, penaltyS: 0, pitStops: 1, laps: 5 },
    { raceUs: 333_068_000, penaltyS: 0, pitStops: 1, laps: 5 },
    { raceUs: 335_763_000, penaltyS: 0, pitStops: 1, laps: 5 },
    { raceUs: -1, penaltyS: 0, pitStops: 1, laps: 4 },
    { raceUs: 340_681_000, penaltyS: 0, pitStops: 1, laps: 5 },
    { raceUs: 362_397_000, penaltyS: 20, pitStops: 0, laps: 5 },
  ],
  inputHash: "ab".repeat(32),
};

test("result hash: sha256 of the physics version, order, race times and input hash", () => {
  const expected = sha(JSON.stringify({ physicsVersion: 3, order: RESULT.order, raceUs: RESULT.cars.map((c) => c.raceUs), inputHash: RESULT.inputHash }));
  assert.equal(D.resultHash(RESULT), expected);
  assert.equal(D.resultHash({ ...RESULT, ticks: 1, finished: false }), expected); // only what is listed counts
  assert.notEqual(D.resultHash({ ...RESULT, order: [0, 1, 2, 4, 5, 3] }), expected);
  assert.notEqual(D.resultHash({ ...RESULT, inputHash: "cd".repeat(32) }), expected);
  assert.notEqual(D.resultHash({ ...RESULT, cars: RESULT.cars.map((c, i) => (i === 2 ? { ...c, raceUs: c.raceUs + 1 } : c)) }), expected);
});

// ---------------------------------------------------------------- flow with fakes

const account = (id: number) => new PublicKey(createHash("sha256").update(`driver:${id}`).digest());
let clock = 1_800_000_000_000;
let calls: { name: string; args: unknown[] }[] = [];
let redriveResult: RedriveResult = RESULT;
let failNext: Record<string, string> = {};
const called = (name: string) => calls.filter((c) => c.name === name);

function chainFake(name: string) {
  return async (...args: unknown[]) => {
    calls.push({ name, args });
    clock += 1500; // a confirmation takes a moment
    if (failNext[name]) {
      const msg = failNext[name];
      delete failNext[name];
      throw new Error(msg);
    }
    return `${name}-sig-${calls.length}`;
  };
}

const fakes: DrivenDeps = {
  createRace: chainFake("createRace"),
  enterAll: chainFake("enterAll"),
  revealSeed: chainFake("revealSeed"),
  postResult: chainFake("postResult"),
  settleAll: chainFake("settleAll"),
  driverAccount: account,
  fetchDriver: async (id) => (id === RIVALS[0].driver.driverId ? { pace: 80, racecraft: 61, tyreManagement: 53 } : null),
  playerStats: async () => STATS,
  qualiSetup: (player) => (player === QUALIFIED ? SETUP : undefined),
  gridOrder: () => [RIVALS[1].team, RIVALS[0].team, "you", RIVALS[2].team, RIVALS[3].team, RIVALS[4].team],
  carSpec: P.carSpec,
  redrive: async (job) => {
    calls.push({ name: "redrive", args: [job] });
    return structuredClone(redriveResult);
  },
  awardRaceFinish: (player, raceId, result) => {
    calls.push({ name: "award", args: [player, raceId, result] });
    return P.awardRaceFinish(player, raceId, result);
  },
  now: () => clock,
  sleep: async (ms) => {
    calls.push({ name: "sleep", args: [ms] });
    clock += ms;
  },
};
D.setDeps(fakes);
beforeEach(() => {
  calls = [];
  redriveResult = RESULT;
  failNext = {};
  clock += 3_600_000;
});

test("start: commits the seed and enters all six cars, and gives the client the whole race", async () => {
  const player = newPlayer();
  const raceId = clock;
  const r = await D.startDrivenRace(player, { compound: 1, name: "  Tamuna  " });
  assert.equal(r.raceId, raceId);
  const seed = D.raceSeed(raceId);
  assert.equal(r.seed, seed.toString("hex"));
  assert.equal(r.commitment, sha(seed));
  assert.equal(r.laps, 5);
  assert.equal(r.track, "mtkvari");
  assert.deepEqual(r.grid, [2, 1, 0, 3, 4, 5]);
  assert.deepEqual(r.names, ["Tamuna", ...RIVALS.map((x) => x.team)]);
  assert.deepEqual(r.drivers, [PLAYER_DRIVER.name, ...RIVALS.map((x) => x.driver.name)]);
  assert.equal(r.colors[0], "#e8352b");
  assert.equal(new Set(r.colors).size, 6);
  assert.deepEqual(r.txs, { create: "createRace-sig-1", enter: "enterAll-sig-2" });
  // the player's qualifying setup (this player has none: Profile defaults), parts spec, stats, chosen tyre
  assert.deepEqual(r.entries[0], { setup: D.DEFAULT_SETUP, stats: STATS, car: P.carSpec(player), crew: 70, compound: 1 });
  // a rival's on-chain stats win over the starter values
  assert.equal(r.entries[1].pace, D.aiPace(80));
  assert.equal(r.entries[1].stats.braking, 80);
  assert.equal(r.entries[2].pace, D.aiPace(RIVALS[1].driver.pace));

  const [create] = called("createRace");
  const params = create.args[1] as { trackType: number; laps: number; baseLapMs: number; commitment: Buffer; lockTs: number };
  assert.equal(create.args[0], raceId);
  assert.equal(params.trackType, 2); // "mixed"
  assert.equal(params.laps, 5);
  assert.equal(params.baseLapMs, 65_000);
  assert.equal(params.commitment.toString("hex"), sha(seed));
  assert.ok(params.lockTs > raceId / 1000 && params.lockTs <= raceId / 1000 + 15);
  const [enter] = called("enterAll");
  const setups = enter.args[1] as { driver: PublicKey; team: string; design: number; tyre: number; stops: number; risk: number }[];
  assert.deepEqual(
    setups.map((s) => [s.driver.toBase58(), s.team, s.design, s.tyre, s.stops, s.risk]),
    [PLAYER_DRIVER.driverId, ...RIVALS.map((x) => x.driver.driverId)].map((id, i) => [account(id).toBase58(), i === 0 ? "Your Team" : RIVALS[i - 1].team, 1, r.entries[i].compound, 1, 0]),
  );
  // everything the re-drive needs is stored
  const s = D.getDrivenRace(raceId)!;
  assert.equal(s.status, "racing");
  assert.deepEqual([s.seed, s.entries, s.grid, s.laps], [r.seed, r.entries, r.grid, 5]);
  assert.equal(s.startedAt, clock);
});

test("start: the player's qualifying setup, default soft tyre and name", async () => {
  const r = await D.startDrivenRace(newPlayer());
  const q = await D.startDrivenRace(QUALIFIED);
  assert.deepEqual(q.entries[0].setup, SETUP);
  assert.equal(q.entries[0].compound, 0);
  assert.equal(q.names[0], "You");
  assert.notEqual(q.raceId, r.raceId);
});

test("start: refuses bad players and tyres before touching the chain", async () => {
  await assert.rejects(D.startDrivenRace("not-a-player"), /bad player id/);
  await assert.rejects(D.startDrivenRace(newPlayer(), { compound: 3 }), /compound/);
  await assert.rejects(D.startDrivenRace(newPlayer(), { compound: "x" }), /compound/);
  assert.equal(calls.length, 0);
});

async function startRace() {
  const player = newPlayer();
  const r = await D.startDrivenRace(player);
  calls = [];
  return { player, raceId: r.raceId };
}

test("finish: re-drives the stored race, settles it on-chain and awards a pack; a second call returns the same", async () => {
  const { player, raceId } = await startRace();
  clock += 400_000; // more than the 349 s the race took
  const out = await D.finishDrivenRace(raceId, "AAAA");
  const [job] = called("redrive").map((c) => c.args[0] as Record<string, unknown>);
  const s = D.getDrivenRace(raceId)!;
  assert.deepEqual(job, { track: "mtkvari", kind: "race", seed: s.seed, inputs: "AAAA", entries: s.entries, grid: s.grid, laps: 5 });
  assert.equal(out.verified, true);
  assert.deepEqual(out.order, RESULT.order);
  assert.equal(out.resultHash, D.resultHash(RESULT));
  assert.equal(out.cars[1].position, 1);
  assert.equal(out.cars[1].name, RIVALS[0].team);
  assert.equal(out.cars[0].position, 2);
  assert.equal(out.cars[3].raceUs, -1);
  // on-chain: reveal the committed seed, post the hash, settle positions in finishing order
  assert.deepEqual(calls.filter((c) => c.name !== "redrive" && c.name !== "award").map((c) => c.name), ["revealSeed", "postResult", "settleAll"]);
  assert.equal((called("revealSeed")[0].args[1] as Buffer).toString("hex"), s.seed);
  assert.equal(sha(called("revealSeed")[0].args[1] as Buffer), s.commitment);
  assert.equal((called("postResult")[0].args[1] as Buffer).toString("hex"), out.resultHash);
  const positions = called("settleAll")[0].args[1] as { driver: PublicKey; position: number }[];
  assert.deepEqual(
    positions.map((p) => [p.driver.toBase58(), p.position]),
    RESULT.order.map((entry, i) => [account(s.driverIds[entry]).toBase58(), i + 1]),
  );
  assert.equal(positions[1].driver.toBase58(), account(PLAYER_DRIVER.driverId).toBase58());
  assert.deepEqual(out.txs, { create: s.txs.create, enter: s.txs.enter, reveal: "revealSeed-sig-2", result: "postResult-sig-3", settle: "settleAll-sig-4" });
  assert.deepEqual(called("award")[0].args, [player, raceId, { km: 16, won: false }]);
  assert.equal(out.packsEarned.length, 1);
  assert.equal(s.status, "finished");
  assert.equal(D.drivenInputs(raceId), "AAAA");

  // idempotent: nothing is re-driven or sent again, other inputs are ignored
  const n = calls.length;
  assert.deepEqual(await D.finishDrivenRace(raceId, "BBBB"), out);
  assert.equal(calls.length, n);
  assert.equal(D.drivenInputs(raceId), "AAAA");
});

test("finish: concurrent calls share one re-drive and one settlement", async () => {
  const { raceId } = await startRace();
  clock += 400_000;
  const [a, b] = await Promise.all([D.finishDrivenRace(raceId, "AAAA"), D.finishDrivenRace(raceId, "AAAA")]);
  assert.deepEqual(a, b);
  assert.equal(called("redrive").length, 1);
  assert.equal(called("settleAll").length, 1);
});

test("finish: a log longer than the time since the start is refused, and the race can still be finished", async () => {
  const { raceId } = await startRace();
  clock += 200_000; // 200 s, the log says 349 s
  await assert.rejects(D.finishDrivenRace(raceId, "AAAA"), /longer than the time since it started/);
  assert.equal(D.getDrivenRace(raceId)!.result, undefined);
  assert.equal(called("revealSeed").length, 0);
  // 5 s of slack: 344 s + 5 s covers 41854 ticks (348.8 s)
  clock += 144_000;
  const out = await D.finishDrivenRace(raceId, "AAAA");
  assert.deepEqual(out.order, RESULT.order);
});

test("finish: an unfinished race is refused without touching the chain", async () => {
  const { raceId } = await startRace();
  clock += 400_000;
  redriveResult = { ...RESULT, finished: false };
  await assert.rejects(D.finishDrivenRace(raceId, "AAAA"), (err: Error & { status?: number }) => err.status === 400 && /not finished in the input log/.test(err.message));
  assert.equal(called("revealSeed").length + called("award").length, 0);
  assert.equal(D.getDrivenRace(raceId)!.status, "racing");
  assert.equal(D.drivenInputs(raceId), undefined);
});

test("finish: bad input, unknown and expired races", async () => {
  const { raceId } = await startRace();
  await assert.rejects(D.finishDrivenRace(raceId, ""), /bad inputs/);
  await assert.rejects(D.finishDrivenRace(raceId, 42), /bad inputs/);
  await assert.rejects(D.finishDrivenRace(123, "AAAA"), (err: Error & { status?: number }) => err.status === 404);
  clock += 2 * 3_600_000;
  await assert.rejects(D.finishDrivenRace(raceId, "AAAA"), /expired/);
  assert.equal(called("redrive").length, 0);
});

test("finish: a failed chain step is retried by finishing again, from where it stopped", async () => {
  const { raceId } = await startRace();
  clock += 400_000;
  failNext.postResult = "blockhash not found";
  await assert.rejects(D.finishDrivenRace(raceId, "AAAA"), (err: Error & { status?: number; details?: Record<string, unknown> }) => err.status === 502 && err.details?.verified === true);
  const s = D.getDrivenRace(raceId)!;
  assert.equal(s.status, "verified");
  assert.ok(s.txs.reveal && !s.txs.result);
  assert.equal(called("award").length, 0);

  const out = await D.finishDrivenRace(raceId, "something else entirely");
  assert.equal(called("redrive").length, 1);
  assert.equal(called("revealSeed").length, 1);
  assert.equal(called("postResult").length, 2);
  assert.equal(called("settleAll").length, 1);
  assert.equal(out.resultHash, D.resultHash(RESULT));
  assert.equal(D.drivenInputs(raceId), "AAAA");
  assert.equal(D.getDrivenRace(raceId)!.error, undefined);
});

test("finish: waits for the lock before revealing, and retries while the chain clock trails", async () => {
  const { raceId } = await startRace();
  const s = D.getDrivenRace(raceId)!;
  redriveResult = { ...RESULT, ticks: 100 };
  failNext.revealSeed = "Error Code: RaceNotLocked";
  const out = await D.finishDrivenRace(raceId, "AAAA");
  const sleeps = called("sleep").map((c) => c.args[0] as number);
  assert.ok(sleeps[0] > 0, "waited for the lock");
  assert.equal(sleeps[1], 2000);
  assert.equal(called("revealSeed").length, 2);
  assert.ok(clock >= (s.lockTs + 1) * 1000);
  assert.match(out.txs.reveal!, /^revealSeed-sig-/);
});

test("a race whose entries failed cannot be finished", async () => {
  failNext.enterAll = "RaceLocked";
  const raceId = clock;
  await assert.rejects(D.startDrivenRace(newPlayer()), /RaceLocked/);
  assert.equal(D.getDrivenRace(raceId)!.status, "failed");
  await assert.rejects(D.finishDrivenRace(raceId, "AAAA"), (err: Error & { status?: number }) => err.status === 409);
});
