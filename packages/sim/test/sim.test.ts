import { test } from "node:test";
import assert from "node:assert/strict";
import { simulate, commitmentFor, type RaceInput } from "../src/sim.ts";

const SEED = "9f4c2a7e1b83d6050c1d7a4e2f9b8c3d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b";

const race: RaceInput = {
  seedHex: SEED,
  track: { id: "tbilisi-street", type: "street", laps: 24, baseLapMs: 92_000 },
  entries: [
    { team: "Tbilisi Racing", driver: { pace: 62, racecraft: 80, tyreManagement: 70 }, setup: { design: 0, tyre: 0, stops: 1, risk: 55 } },
    { team: "Kutaisi GP", driver: { pace: 78, racecraft: 60, tyreManagement: 50 }, setup: { design: 2, tyre: 1, stops: 1, risk: 40 } },
    { team: "Batumi Motorsport", driver: { pace: 70, racecraft: 70, tyreManagement: 60 }, setup: { design: 1, tyre: 2, stops: 1, risk: 30 } },
    { team: "Rustavi Works", driver: { pace: 66, racecraft: 55, tyreManagement: 75 }, setup: { design: 0, tyre: 1, stops: 2, risk: 65 } },
    { team: "Gori Autosport", driver: { pace: 74, racecraft: 65, tyreManagement: 55 }, setup: { design: 1, tyre: 0, stops: 2, risk: 50 } },
    { team: "Mtskheta Racing", driver: { pace: 58, racecraft: 75, tyreManagement: 80 }, setup: { design: 2, tyre: 2, stops: 1, risk: 20 } },
  ],
};

test("same input, same result", () => {
  assert.equal(simulate(race).resultHash, simulate(race).resultHash);
});

test("a different seed changes the race", () => {
  const other = simulate({ ...race, seedHex: "0".repeat(63) + "1" });
  assert.notEqual(other.resultHash, simulate(race).resultHash);
});

test("golden result: changing this hash means the sim changed, so bump SIM_VERSION", () => {
  assert.equal(simulate(race).resultHash, GOLDEN_HASH);
});

test("commitment is sha256 of the raw seed bytes", () => {
  assert.equal(commitmentFor("00".repeat(32)), "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925");
});

test("every team has one entry per lap and pits on its planned laps", () => {
  const r = simulate(race);
  for (const teamLaps of r.laps) assert.equal(teamLaps.length, race.track.laps);
  for (const e of r.events.filter((e) => e.type === "pit")) assert.ok(r.pitLaps[e.team].includes(e.lap));
  assert.deepEqual([...r.order].sort(), [0, 1, 2, 3, 4, 5]);
});

test("the right design for the track matters", () => {
  const base = { ...race, entries: race.entries.map((e) => ({ ...e, setup: { ...e.setup, risk: 0 } })) };
  const streetWithDownforce = simulate(base).laps[0].at(-1)!;
  const streetWithLowDrag = simulate({ ...base, entries: base.entries.map((e, i) => (i === 0 ? { ...e, setup: { ...e.setup, design: 2 } } : e)) }).laps[0].at(-1)!;
  assert.ok(streetWithDownforce < streetWithLowDrag);
});

test("invalid setups are rejected", () => {
  assert.throws(() => simulate({ ...race, entries: [{ ...race.entries[0], setup: { design: 0, tyre: 0, stops: 3, risk: 0 } }, race.entries[1]] }));
});

const GOLDEN_HASH = "6722f2e0a8d55bccfb98beebfbd0df04b188b1cd860d6613be5b18a8277a211f";
