// Re-driving a lap with a weighted parts spec: an autopilot lap driven with the
// spec (game/sim/test_drive.gd) must verify exactly on the server's re-drive,
// and the weight must change the lap. Needs headless Godot; skipped without it.

import { after, test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

process.env.DATA_DIR = mkdtempSync(join(tmpdir(), "pitwall-redrive-"));
after(() => rmSync(process.env.DATA_DIR!, { recursive: true, force: true }));
const { config } = await import("../src/config.ts");
const { redrive } = await import("../src/redrive.ts");
const { zeroSpec } = await import("../src/parts.ts");

type Lap = { lap: number; us: number; valid: boolean };
type Result = { physicsVersion: number; ticks: number; laps: Lap[]; inputHash: string; metres: number };

const SETUP = { front_wing: 6, rear_wing: 6, brake_bias: 57, differential: 6 };
const STATS = { braking: 50, cornering: 50, traction: 50, energy: 50 };
const CAR = { ...zeroSpec(), weight: 24, downforce: 10 };

test("a lap driven with a weighted spec re-drives identically, and the weight changes the lap", { skip: !existsSync(config.godotBin) && "Godot not found" }, async () => {
  const out = join(process.env.DATA_DIR!, "inputs.txt");
  const { stdout } = await promisify(execFile)(
    config.godotBin,
    ["--headless", "--path", config.gameDir, "-s", "res://sim/test_drive.gd", "--", "--laps", "1", "--car", JSON.stringify(CAR), "--out", out],
    { timeout: 120_000 },
  );
  assert.match(stdout, /re-drive identical: true/);
  const lapUs = Number(/lap 1: (\d+):(\d+\.\d+)/.exec(stdout)!.slice(1).reduce((m, s) => m * 60 + Number(s), 0) * 1e6);
  const inputs = readFileSync(out, "utf8");
  const job = { track: "mtkvari", setup: SETUP, stats: STATS, seed: "80000000", inputs, kind: "qualifying" };

  const weighted = await redrive<Result>({ ...job, car: CAR });
  assert.equal(weighted.physicsVersion, 5);
  assert.ok(weighted.laps.length >= 1);
  // the server's re-drive gives the lap the client drove (test_drive prints it to the millisecond)
  assert.ok(Math.abs(weighted.laps[0].us - lapUs) <= 501, `${weighted.laps[0].us} vs ${lapUs}`);
  // about a lap and a bit of Mtkvari (3.245 km), for part wear
  assert.ok(weighted.metres > 3000 && weighted.metres < 8000, String(weighted.metres));

  const standard = await redrive<Result>({ ...job, car: zeroSpec() });
  assert.notEqual(standard.laps[0]?.us, weighted.laps[0].us);
  assert.equal(standard.inputHash, weighted.inputHash);
});
