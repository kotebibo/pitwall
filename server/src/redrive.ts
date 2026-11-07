// Re-driving runs with headless Godot: the same physics the player drove,
// fed with their recorded inputs (game/sim/redrive.gd). Used by qualifying
// (one lap session) and driven races (the whole race with the AI field).

import { randomBytes } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { promisify } from "node:util";
import { config } from "./config.ts";

const run = promisify(execFile);
const dir = join(config.dataDir, "redrive");
mkdirSync(dir, { recursive: true });

// One re-drive at a time keeps the server responsive on a small machine.
let queue: Promise<unknown> = Promise.resolve();

/** Runs res://sim/redrive.gd on a job (see that script for the job format) and returns what it printed. */
export function redrive<T>(job: object, timeoutMs = 60_000): Promise<T> {
  const task = queue.then(async () => {
    const base = join(dir, `run-${randomBytes(6).toString("hex")}`);
    writeFileSync(`${base}.in.json`, JSON.stringify(job));
    try {
      try {
        await run(config.godotBin, ["--headless", "--path", config.gameDir, "-s", "res://sim/redrive.gd", "--", "--in", `${base}.in.json`, "--out", `${base}.out.json`], {
          timeout: timeoutMs,
        });
      } catch (err) {
        // redrive.gd exits 1 with {"error"} in its output for a bad run: report that, not the command line
        const out = existsSync(`${base}.out.json`) ? (JSON.parse(readFileSync(`${base}.out.json`, "utf8")) as { error?: string }) : undefined;
        if (out?.error) throw new Error(out.error);
        throw err;
      }
      return JSON.parse(readFileSync(`${base}.out.json`, "utf8")) as T;
    } finally {
      rmSync(`${base}.in.json`, { force: true });
      rmSync(`${base}.out.json`, { force: true });
    }
  });
  queue = task.catch(() => undefined);
  return task;
}
