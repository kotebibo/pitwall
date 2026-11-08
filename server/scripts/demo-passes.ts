// End-to-end race-pass run against a server on devnet: four test teams link wallets, buy passes
// in a short sprint pool, three drive verified laps (the autopilot), and the server pays out.
//
//   ADMIN_PASSWORD=... node scripts/demo-passes.ts http://localhost:8787 [minutes]
//
// The server must run with REALTIME_CHECK=0 (the autopilot laps are not driven in real time)
// and the same ADMIN_PASSWORD. Test wallets are funded from the devnet authority keypair.

import { execFileSync } from "node:child_process";
import { createPrivateKey, randomBytes, sign } from "node:crypto";
import { mkdtempSync, readFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { Connection, Keypair, LAMPORTS_PER_SOL, SystemProgram, Transaction, sendAndConfirmTransaction } from "@solana/web3.js";

const BASE = process.argv[2] ?? "http://localhost:8787";
const MINUTES = Number(process.argv[3] ?? 3);
const ADMIN = process.env.ADMIN_PASSWORD ?? "";
const GODOT = process.env.GODOT_BIN ?? "D:/dev/tools/godot/Godot_v4.7.2-stable_win64_console.exe";
const GAME = new URL("../../game", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const SETUP = { front_wing: 6, rear_wing: 6, brake_bias: 57, differential: 6 };
const rpc = new Connection(process.env.RPC_URL ?? "https://api.devnet.solana.com", "confirmed");
const authority = Keypair.fromSecretKey(Uint8Array.from(JSON.parse(readFileSync(join(homedir(), ".config", "solana", "id.json"), "utf8"))));

async function call(method: string, path: string, body?: unknown, token?: string, basic?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (basic) headers.Authorization = `Basic ${Buffer.from(`admin:${basic}`).toString("base64")}`;
  const r = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status} ${JSON.stringify(j)}`);
  return j as any;
}

function signMessage(kp: Keypair, message: string) {
  const der = Buffer.concat([Buffer.from("302e020100300506032b657004220420", "hex"), Buffer.from(kp.secretKey.slice(0, 32))]);
  return sign(null, Buffer.from(message, "utf8"), createPrivateKey({ key: der, format: "der", type: "pkcs8" })).toString("base64");
}

async function team(name: string) {
  const acct = await call("POST", "/api/accounts/register", { name, password: randomBytes(9).toString("base64url") });
  const kp = Keypair.generate();
  const { message } = await call("POST", "/api/accounts/wallet/challenge", {}, acct.token);
  await call("POST", "/api/accounts/wallet/link", { wallet: kp.publicKey.toBase58(), signature: signMessage(kp, message) }, acct.token);
  await sendAndConfirmTransaction(rpc, new Transaction().add(SystemProgram.transfer({ fromPubkey: authority.publicKey, toPubkey: kp.publicKey, lamports: 0.03 * LAMPORTS_PER_SOL })), [authority]);
  return { name, player: acct.player as string, token: acct.token as string, kp };
}

async function driveLap(t: Awaited<ReturnType<typeof team>>) {
  const a = await call("POST", "/api/attempts", { player: t.player, name: t.name, session: "pass", setup: SETUP }, t.token);
  const st = a.stats;
  const out = join(mkdtempSync(join(tmpdir(), "pw-lap-")), "inputs.txt");
  execFileSync(GODOT, ["--headless", "--path", GAME, "-s", "res://sim/test_drive.gd", "--", "--seed", a.seed, "--laps", "1",
    "--stats", `${st.braking},${st.cornering},${st.traction},${st.energy}`, "--out", out], { stdio: "ignore" });
  const run = await call("POST", `/api/attempts/${a.attempt}/run`, { inputs: readFileSync(out, "utf8") }, t.token);
  console.log(`${t.name}: lap ${(run.best?.us / 1e6).toFixed(3)} s verified, pass standings ${JSON.stringify(run.pass)}`);
}

const suffix = randomBytes(2).toString("hex").toUpperCase();
const pool = await call("POST", "/api/passes/sprint", { minutes: MINUTES, stakeSol: 0.01 }, undefined, ADMIN);
console.log(`sprint pool ${pool.id}: ${pool.stakeSol} SOL stake, closes ${new Date(pool.closesAt).toISOString()}`);
const teams = [];
for (const n of ["Kutaisi Speed", "Batumi Blue", "Gori Garage", "Telavi Tech"]) teams.push(await team(`${n} ${suffix}`));
for (const t of teams) {
  const e = await call("POST", `/api/passes/${pool.id}/enter`, { player: t.player }, t.token);
  const tx = Transaction.from(Buffer.from(e.tx, "base64"));
  tx.partialSign(t.kp);
  const c = await call("POST", `/api/passes/${pool.id}/confirm`, { player: t.player, tx: tx.serialize().toString("base64") }, t.token);
  console.log(`${t.name} bought a pass: ${c.tx}`);
}
for (const t of teams.slice(0, 3)) await driveLap(t);
console.log("waiting for the pool to close and settle on-chain...");
for (;;) {
  await new Promise((r) => setTimeout(r, 20_000));
  const info = await call("GET", `/api/passes?player=${teams[0].player}`, undefined, teams[0].token);
  const p = info.pools.find((x: any) => x.id === pool.id);
  if (p?.settled) {
    console.log("settled:", JSON.stringify(p.settled, null, 1));
    console.log("standings:", JSON.stringify(p.standings));
    for (const t of teams) console.log(`${t.name}: ${(await rpc.getBalance(t.kp.publicKey)) / LAMPORTS_PER_SOL} SOL`);
    break;
  }
  console.log(`  ${Math.max(0, Math.round((pool.closesAt - Date.now()) / 1000))} s to close`);
}
