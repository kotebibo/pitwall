import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

process.env.DATA_DIR = mkdtempSync(join(tmpdir(), "pitwall-passes-"));
process.env.PASSES_SETTLE = "off";
const { payoutTable, MIN_ENTRANTS, MIN_PAYOUT_X, RAKE_BPS } = await import("../src/passes.ts");

const STAKE = 50_000_000;

test("payouts plus Pit Wall's share always equal the stakes exactly", () => {
  for (const n of [4, 5, 9, 10, 37, 100, 523]) {
    const t = payoutTable(n, n, STAKE);
    assert.equal(t.refund, false);
    const paid = t.places.reduce((a, b) => a + b, 0);
    assert.equal(paid + t.rake, n * STAKE, `field of ${n}`);
    assert.equal(t.rake, Math.floor((n * STAKE * RAKE_BPS) / 10_000));
  }
});

test("about the top 20% are paid, each at least 1.5x the stake, in finishing order", () => {
  const t = payoutTable(100, 100, STAKE);
  assert.equal(t.places.length, 20);
  for (const p of t.places) assert.ok(p >= MIN_PAYOUT_X * STAKE);
  for (let i = 1; i < t.places.length; i++) assert.ok(t.places[i - 1] >= t.places[i]);
  assert.ok(t.places[0] > 10 * STAKE, "the winner takes a real prize");
});

test("small fields and pools without a valid lap are refunded", () => {
  assert.equal(payoutTable(MIN_ENTRANTS - 1, 3, STAKE).refund, true);
  assert.equal(payoutTable(12, 0, STAKE).refund, true);
});

test("only drivers with a verified lap can be paid", () => {
  const t = payoutTable(50, 3, STAKE); // 50 passes sold, 3 set a lap
  assert.equal(t.places.length, 3);
  assert.equal(t.places.reduce((a, b) => a + b, 0) + t.rake, 50 * STAKE);
});
