// Accounts and the public-server hardening: register/login/me, a guest id carried
// over, tokens, wallet linking and "Sign in with Solana" with a real ed25519
// key, ownership of player ids on the API routes, the timesheet's `you` flag,
// rate limits and the body size limit. Runs the real HTTP handler on a random
// port with a throwaway authority key, a fake Solana RPC that knows no accounts
// and fake driven-race dependencies: never touches Solana or Godot.

import { after, test } from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, randomBytes, sign as edSign } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Keypair, PublicKey } from "@solana/web3.js";

const DAY = 86_400_000;
const dataDir = mkdtempSync(join(tmpdir(), "pitwall-accounts-"));
process.env.DATA_DIR = dataDir;
process.env.CHAIN_RACES_PER_DAY = "10";
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

// today's qualifying: three human laps, written before the server first loads the event
const GUEST_FAST = "1a".repeat(16);
const CLAIMED = "2b".repeat(16); // registers below, taking over this guest id
const IMPOSTOR = "3c".repeat(16); // a guest using that account's name
const eventId = Math.floor(Date.now() / DAY);
const lap = (us: number, attempt: string) => ({ us, sectors: [us / 4, us / 2, us / 4], attempt, lap: 1, inputHash: "00".repeat(32), at: Date.now() });
mkdirSync(join(dataDir, "quali", "inputs"), { recursive: true });
writeFileSync(
  join(dataDir, "quali", `${eventId}.json`),
  JSON.stringify({
    eventId,
    players: {
      [GUEST_FAST]: { name: "Fast Guest", best: lap(55_000_000, "a1a1a1a1a1a1a1a1"), laps: 1 },
      [CLAIMED]: { name: "Old Team Name", best: lap(56_000_000, "a2a2a2a2a2a2a2a2"), laps: 1 },
      [IMPOSTOR]: { name: "speedy  ONE", best: lap(57_000_000, "a3a3a3a3a3a3a3a3"), laps: 1 },
    },
    attempts: {},
  }),
);

const { server } = await import("../src/index.ts");
const A = await import("../src/accounts.ts");
const D = await import("../src/driven.ts");
const P = await import("../src/parts.ts");
const R = await import("../src/ratelimit.ts");

let fakeNow = Date.now();
D.setDeps({
  createRace: async () => "create-sig",
  enterAll: async () => "enter-sig",
  revealSeed: async () => "reveal-sig",
  postResult: async () => "result-sig",
  settleAll: async () => "settle-sig",
  driverAccount: (id) => new PublicKey(createHash("sha256").update(`driver:${id}`).digest()),
  fetchDriver: async () => null,
  playerStats: async () => ({ braking: 64, cornering: 64, traction: 68, energy: 72 }),
  qualiSetup: () => undefined,
  gridOrder: () => [],
  carSpec: P.carSpec,
  redrive: async () => {
    throw new D.DrivenError(400, "no re-drive in these tests");
  },
  awardRaceFinish: P.awardRaceFinish,
  now: () => (fakeNow += 1000),
  sleep: async () => {},
});

await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
after(() => {
  server.closeAllConnections();
  server.close();
  rpc.closeAllConnections();
  rpc.close();
  rmSync(dataDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------- helpers

type Reply = { status: number; body: any; headers: Headers };
let ipN = 0;
/** A client with its own address (fly-client-ip), so its rate-limit buckets are its own. */
function client() {
  const ip = `203.0.113.${++ipN}`;
  const send = async (method: string, path: string, payload?: unknown, token?: string): Promise<Reply> => {
    const headers: Record<string, string> = { "fly-client-ip": ip };
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(base + path, { method, headers, body: payload === undefined ? undefined : JSON.stringify(payload) });
    return { status: res.status, body: await res.json(), headers: res.headers };
  };
  return {
    get: (path: string, token?: string) => send("GET", path, undefined, token),
    post: (path: string, payload: unknown = {}, token?: string) => send("POST", path, payload, token),
  };
}
const PASSWORD = "correct horse";
const register = (name: string, extra: Record<string, unknown> = {}) => client().post("/api/accounts/register", { name, password: PASSWORD, ...extra });
const hexId = () => randomBytes(16).toString("hex");

/** An ed25519 key pair as a Solana wallet: its base58 address and signMessage. */
function wallet() {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const raw = Buffer.from(publicKey.export({ format: "jwk" }).x!, "base64url");
  return { address: new PublicKey(raw).toBase58(), sign: (message: string) => edSign(null, Buffer.from(message, "utf8"), privateKey) };
}

// ---------------------------------------------------------------- register, login, me

test("register, log in and read the account back", async () => {
  const c = client();
  const reg = await c.post("/api/accounts/register", { name: "  Nino   Racer ", password: "hunter22" });
  assert.equal(reg.status, 201);
  assert.deepEqual(Object.keys(reg.body).sort(), ["name", "player", "signupPack", "token", "wallet"]);
  assert.match(reg.body.player, /^[0-9a-f]{32}$/);
  assert.equal(reg.body.name, "Nino Racer"); // trimmed, spaces collapsed
  assert.equal(reg.body.wallet, null);
  assert.equal(A.verifyToken(reg.body.token), reg.body.player);

  const me = await c.get("/api/accounts/me", reg.body.token);
  assert.equal(me.status, 200);
  assert.deepEqual(Object.keys(me.body).sort(), ["createdAt", "name", "player", "wallet"]);
  assert.equal(me.body.player, reg.body.player);
  assert.equal(me.body.name, "Nino Racer");
  assert.ok(Math.abs(me.body.createdAt - Date.now()) < 60_000);

  // names log in ignoring case and extra spaces
  const login = await c.post("/api/accounts/login", { name: "nino  RACER", password: "hunter22" });
  assert.equal(login.status, 200);
  assert.deepEqual({ ...login.body, token: undefined }, { token: undefined, player: reg.body.player, name: "Nino Racer", wallet: null });
  assert.equal((await c.get("/api/accounts/me", login.body.token)).body.player, reg.body.player);

  assert.equal((await c.get("/api/accounts/me")).status, 401);
  assert.equal((await c.get("/api/accounts/me", "not-a-token")).status, 401);

  // stored hashed: no password in the file
  const stored = readFileSync(join(dataDir, "accounts.json"), "utf8");
  assert.ok(!stored.includes("hunter22"));
  const acct = JSON.parse(stored).accounts.find((a: { player: string }) => a.player === reg.body.player);
  assert.deepEqual({ N: acct.password.N, r: acct.password.r, p: acct.password.p }, { N: 16384, r: 8, p: 1 });
  assert.match(acct.password.salt, /^[0-9a-f]{32}$/);
  assert.match(acct.password.key, /^[0-9a-f]{128}$/);
});

test("names are unique ignoring case; bad names and passwords are refused", async () => {
  assert.equal((await register("Under_score-1")).status, 201);
  for (const name of ["UNDER_SCORE-1", " under_score-1 ", "Giorgi Kapanadze", "kutaisi gp", "your team"]) {
    const r = await register(name);
    assert.equal(r.status, 409, name);
    assert.deepEqual(r.body, { error: "that name is taken" });
  }
  for (const name of ["ab", "bad!name", "x".repeat(21), "naïve", 12345, ""]) assert.equal((await register(name as string)).status, 400, String(name));
  for (const password of ["12345", "x".repeat(129), 123456]) {
    assert.equal((await client().post("/api/accounts/register", { name: "Good Name", password })).status, 400, String(password));
  }
});

test("a wrong password and an unknown name get the same 401", async () => {
  assert.equal((await register("Careful Carla")).status, 201);
  const c = client();
  const wrong = await c.post("/api/accounts/login", { name: "Careful Carla", password: "not the password" });
  const unknown = await c.post("/api/accounts/login", { name: "Nobody Atall", password: PASSWORD });
  const empty = await c.post("/api/accounts/login", {});
  for (const r of [wrong, unknown, empty]) {
    assert.equal(r.status, 401);
    assert.deepEqual(r.body, { error: "wrong name or password" });
  }
});

test("registering with the guest id keeps the guest's garage; an owned id is not taken twice", async () => {
  const guest = hexId();
  P.awardPack(guest, "first_quali", "claim-test");
  const c = client();
  assert.equal((await c.get(`/api/garage?player=${guest}`)).body.packs.unopened, 1);

  const reg = await register("Claimer", { guestId: guest.toUpperCase() });
  assert.equal(reg.status, 201);
  assert.equal(reg.body.player, guest);
  // the id is the account's now: its garage needs the token
  const locked = await c.get(`/api/garage?player=${guest}`);
  assert.equal(locked.status, 401);
  assert.deepEqual(locked.body, { error: "sign in to use this account" });
  const mine = await c.get(`/api/garage?player=${guest}`, reg.body.token);
  assert.equal(mine.status, 200);
  assert.equal(mine.body.packs.unopened, 2); // the guest's pack plus the free signup pack

  // claiming an owned id again gives a new id instead
  const again = await register("Second Claimer", { guestId: guest });
  assert.equal(again.status, 201);
  assert.notEqual(again.body.player, guest);
  assert.match(again.body.player, /^[0-9a-f]{32}$/);
  for (const guestId of ["not hex at all", "abcd", "a".repeat(65), 42]) assert.equal((await register(`Bad Guest ${String(guestId).length}`, { guestId })).status, 400);
});

test("a new account gets one free development pack, in the register response and its garage; a claimed guest id too, once", async () => {
  const c = client();
  const reg = await register("Free Pack One");
  assert.equal(reg.status, 201);
  assert.equal(reg.body.signupPack.reason, "signup");
  assert.equal(reg.body.signupPack.openedAt, null);
  const g = (await c.get(`/api/garage?player=${reg.body.player}`, reg.body.token)).body;
  assert.equal(g.packs.unopened, 1);
  assert.equal(g.packs.pending[0].id, reg.body.signupPack.id);
  assert.equal(g.packs.earnedThisWeek, 0); // outside the weekly limit, which is for packs earned by driving

  // a guest who has used up the week's driving packs still gets it when claiming its progress
  const guest = hexId();
  let earned = 0;
  while (P.awardPack(guest, "first_quali", `full-${earned}`).awarded) earned++;
  assert.ok(earned > 0);
  const claimed = await register("Free Pack Two", { guestId: guest });
  assert.equal(claimed.body.player, guest);
  assert.equal(claimed.body.signupPack.reason, "signup");
  assert.equal((await c.get(`/api/garage?player=${guest}`, claimed.body.token)).body.packs.unopened, earned + 1);
  // once per account
  assert.equal(P.awardPack(guest, "signup", "account").awarded, false);
  assert.equal((await c.get(`/api/garage?player=${guest}`, claimed.body.token)).body.packs.unopened, earned + 1);
});

test("livery: POST /api/garage/livery saves palette colours for the owner; GET /api/garage returns them", async () => {
  const c = client();
  const { body: owner } = await register("Livery Owner");
  const { body: other } = await register("Livery Other");
  const p = owner.player;
  const garage = async () => (await c.get(`/api/garage?player=${p}`, owner.token)).body.livery;
  assert.deepEqual(await garage(), { primary: "#e8352b", secondary: "#f1efea" });

  const want = { player: p, primary: "#2546C9", secondary: "f2c230" };
  assert.equal((await c.post("/api/garage/livery", want)).status, 401);
  assert.equal((await c.post("/api/garage/livery", want, other.token)).status, 401);
  const saved = await c.post("/api/garage/livery", want, owner.token);
  assert.equal(saved.status, 200);
  assert.deepEqual(saved.body, { livery: { primary: "#2546c9", secondary: "#f2c230" } });
  assert.deepEqual(await garage(), saved.body.livery);

  // colours off the palette (or off that slot's palette) are refused and change nothing
  for (const bad of [{ primary: "#123456", secondary: "#f2c230" }, { primary: "#2546c9", secondary: "#8e1b2e" }, { primary: "red", secondary: "#f2c230" }, { primary: 0xe8352b }, {}]) {
    const r = await c.post("/api/garage/livery", { player: p, ...bad }, owner.token);
    assert.equal(r.status, 400, JSON.stringify(bad));
    assert.match(r.body.error, /palette/);
  }
  assert.deepEqual(await garage(), saved.body.livery);

  // a guest needs no token; the livery is kept with the garage on disk
  const guest = hexId();
  assert.equal((await c.post("/api/garage/livery", { player: guest, primary: "#3ecf6a", secondary: "#1d1f23" })).status, 200);
  const stored = JSON.parse(readFileSync(join(dataDir, "parts", "players", `${guest}.json`), "utf8"));
  assert.deepEqual(stored.livery, { primary: "#3ecf6a", secondary: "#1d1f23" });
  assert.equal((await c.post("/api/garage/livery", { player: "nope", primary: "#3ecf6a", secondary: "#1d1f23" })).status, 400);
});

test("tokens: tampered, foreign, expired and unknown-account tokens are refused", async () => {
  const reg = await register("Token Tester");
  const other = await register("Token Other");
  const token: string = reg.body.token;
  const [player, expires, sig] = token.split(".");
  assert.equal(player, reg.body.player);
  assert.ok(Number(expires) * 1000 - Date.now() > 29 * DAY && Number(expires) * 1000 - Date.now() <= 30 * DAY);
  assert.equal(A.verifyToken(token), player);

  const flip = (s: string) => (s[0] === "A" ? "B" : "A") + s.slice(1);
  assert.equal(A.verifyToken(`${player}.${expires}.${flip(sig)}`), null);
  assert.equal(A.verifyToken(`${player}.${Number(expires) + 86_400}.${sig}`), null);
  assert.equal(A.verifyToken(`${other.body.player}.${expires}.${sig}`), null);
  assert.equal(A.verifyToken(`${player}.${expires}`), null);
  assert.equal(A.verifyToken(""), null);
  // properly signed, but no account owns the id
  assert.equal(A.verifyToken(A.issueToken(hexId())), null);
  // 30 days
  assert.equal(A.verifyToken(A.issueToken(player, Date.now() - 29 * DAY)), player);
  assert.equal(A.verifyToken(A.issueToken(player, Date.now() - 30 * DAY - 1000)), null);
  const realNow = A.clock.now;
  A.clock.now = () => Date.now() + 30 * DAY + 1000;
  try {
    assert.equal(A.verifyToken(token), null);
  } finally {
    A.clock.now = realNow;
  }

  const c = client();
  assert.equal((await c.get("/api/accounts/me", `${player}.${expires}.${flip(sig)}`)).status, 401);
  assert.equal((await c.get(`/api/garage?player=${player}`, other.body.token)).status, 401);
  assert.equal((await c.get(`/api/garage?player=${player}`, token)).status, 200);
});

// ---------------------------------------------------------------- wallets

async function linkWallet(token: string, w: ReturnType<typeof wallet>) {
  const c = client();
  const ch = await c.post("/api/accounts/wallet/challenge", {}, token);
  assert.equal(ch.status, 200);
  return c.post("/api/accounts/wallet/link", { wallet: w.address, signature: w.sign(ch.body.message).toString("base64") }, token);
}

test("wallet: sign the challenge with the key to link it; a wallet links to one account", async () => {
  const c = client();
  const { body: acct } = await register("Wallet Owner");
  const w = wallet();
  assert.equal((await c.post("/api/accounts/wallet/challenge")).status, 401);

  const ch = await c.post("/api/accounts/wallet/challenge", {}, acct.token);
  assert.equal(ch.status, 200);
  const message: string = ch.body.message;
  assert.match(message, /^Pit Wall: link this wallet to the account Wallet Owner\.\nNonce: [0-9a-f]{32}\nIssued: \d{4}-\d\d-\d\dT[\d:.]+Z$/);

  const link = (signature: string, wal = w.address, token = acct.token) => c.post("/api/accounts/wallet/link", { wallet: wal, signature }, token);
  // a signature of another message, by another key, or garbage: refused
  assert.equal((await link(w.sign("something else").toString("base64"))).status, 400);
  assert.equal((await link(wallet().sign(message).toString("base64"))).status, 400);
  assert.equal((await link("not a signature")).status, 400);
  assert.equal((await link(w.sign(message).toString("base64"), "not-a-wallet")).status, 400);
  assert.equal((await link(w.sign(message).toString("base64"), w.address, "")).status, 401);

  const ok = await link(w.sign(message).toString("base64"));
  assert.equal(ok.status, 200);
  assert.deepEqual(ok.body, { wallet: w.address });
  assert.equal((await c.get("/api/accounts/me", acct.token)).body.wallet, w.address);
  assert.equal((await client().post("/api/accounts/login", { name: "Wallet Owner", password: PASSWORD })).body.wallet, w.address);
  // the challenge was used up
  assert.equal((await link(w.sign(message).toString("base64"))).status, 400);

  // another account proving the same key still cannot take the wallet
  const { body: thief } = await register("Wallet Thief");
  const taken = await linkWallet(thief.token, w);
  assert.equal(taken.status, 409);
  assert.match(taken.body.error, /linked to another account/);
  // a challenge expires after 10 minutes
  const late = await c.post("/api/accounts/wallet/challenge", {}, thief.token);
  const realNow = A.clock.now;
  A.clock.now = () => Date.now() + 10 * 60_000 + 1000;
  try {
    const w2 = wallet();
    assert.equal((await c.post("/api/accounts/wallet/link", { wallet: w2.address, signature: w2.sign(late.body.message).toString("base64") }, thief.token)).status, 400);
  } finally {
    A.clock.now = realNow;
  }
});

test("sign in with Solana: a signed login challenge signs in to the linked account", async () => {
  const { body: acct } = await register("Solana Signer");
  const w = wallet();
  assert.equal((await linkWallet(acct.token, w)).status, 200);

  const c = client();
  const ch = await c.post("/api/accounts/wallet/login-challenge", { wallet: w.address });
  assert.equal(ch.status, 200);
  assert.ok(ch.body.message.includes(w.address));
  // wallets give the signature as bytes: base58 here (base64 works too)
  const signature = A.base58Encode(w.sign(ch.body.message));
  const login = await c.post("/api/accounts/wallet/login", { wallet: w.address, signature });
  assert.equal(login.status, 200);
  assert.deepEqual({ ...login.body, token: undefined }, { token: undefined, player: acct.player, name: "Solana Signer", wallet: w.address });
  assert.equal((await c.get("/api/accounts/me", login.body.token)).body.player, acct.player);
  // single use
  assert.equal((await c.post("/api/accounts/wallet/login", { wallet: w.address, signature })).status, 401);

  // the wrong key, and a key that is linked to nobody
  const ch2 = await c.post("/api/accounts/wallet/login-challenge", { wallet: w.address });
  assert.equal((await c.post("/api/accounts/wallet/login", { wallet: w.address, signature: A.base58Encode(wallet().sign(ch2.body.message)) })).status, 401);
  const stranger = wallet();
  const ch3 = await c.post("/api/accounts/wallet/login-challenge", { wallet: stranger.address });
  assert.equal(ch3.status, 200);
  const nobody = await c.post("/api/accounts/wallet/login", { wallet: stranger.address, signature: stranger.sign(ch3.body.message).toString("base64") });
  assert.equal(nobody.status, 401);
  assert.match(nobody.body.error, /no account is linked/);
  assert.equal((await c.post("/api/accounts/wallet/login-challenge", { wallet: "1111" })).status, 400);
});

test("base58 matches Solana's for keys and round-trips signatures", () => {
  for (let i = 0; i < 50; i++) {
    const key = Keypair.generate().publicKey;
    assert.equal(A.base58Encode(key.toBytes()), key.toBase58());
    const sig = randomBytes(64);
    if (i % 5 === 0) sig.fill(0, 0, i % 3); // leading zero bytes
    assert.deepEqual(A.base58Decode(A.base58Encode(sig)), sig);
  }
  assert.equal(A.base58Decode("0OIl"), null);
});

// ---------------------------------------------------------------- ownership

test("routes acting on an owned player id need its token; guest ids need none", async () => {
  const c = client();
  const { body: owner } = await register("Owner One");
  const { body: other } = await register("Owner Two");
  const p = owner.player;

  assert.equal((await c.get(`/api/garage?player=${p}`)).status, 401);
  assert.equal((await c.get(`/api/garage?player=${p}`, other.token)).status, 401);
  assert.equal((await c.get(`/api/garage?player=${p}`, owner.token)).status, 200);
  assert.equal((await c.get(`/api/event?player=${p}`)).status, 401);
  assert.equal((await c.get(`/api/event?player=${p}`, owner.token)).status, 200);

  assert.equal((await c.post("/api/packs/open", { player: p })).status, 401);
  assert.equal((await c.post("/api/packs/open", { player: p }, owner.token)).status, 200); // the free signup pack
  assert.deepEqual((await c.post("/api/packs/open", { player: p }, owner.token)).body, { error: "no unopened packs" });
  assert.equal((await c.post("/api/garage/equip", { player: p, partId: "nope" }, other.token)).status, 401);
  assert.equal((await c.post("/api/garage/equip", { player: p, partId: "nope" }, owner.token)).status, 404);

  // qualifying: the attempt runs under the account name, whatever name the client sends
  const attempt = { player: p, name: "Somebody Else", session: "practice", setup: {} };
  assert.equal((await c.post("/api/attempts", attempt)).status, 401);
  const started = await c.post("/api/attempts", attempt, owner.token);
  assert.equal(started.status, 201);
  const run = await c.post(`/api/attempts/${started.body.attempt}/run`, { inputs: "x" });
  assert.equal(run.status, 401); // refused before any re-drive
  assert.equal((await c.post(`/api/attempts/${started.body.attempt}/run`, { inputs: "x" }, other.token)).status, 401);

  // driven races
  assert.equal((await c.post("/api/drivenraces", { player: p })).status, 401);
  const race = await c.post("/api/drivenraces", { player: p }, owner.token);
  assert.equal(race.status, 201);
  const state = await c.get(`/api/drivenraces/${race.body.raceId}`);
  assert.equal(state.status, 200);
  assert.ok(!("player" in state.body));
  assert.ok(!JSON.stringify(state.body).includes(p));
  assert.equal((await c.post(`/api/drivenraces/${race.body.raceId}/finish`, { inputs: "x" })).status, 401);
  assert.equal((await c.post(`/api/drivenraces/${race.body.raceId}/finish`, { inputs: "x" }, other.token)).status, 401);
  const finish = await c.post(`/api/drivenraces/${race.body.raceId}/finish`, { inputs: "x" }, owner.token);
  assert.equal(finish.status, 400); // past the check: the (fake) re-drive ran
  assert.match(finish.body.error, /no re-drive/);

  // a guest id works without a token, and any token is ignored for it
  const guest = hexId();
  assert.equal((await c.get(`/api/garage?player=${guest}`)).status, 200);
  assert.equal((await c.get(`/api/garage?player=${guest}`, "junk")).status, 200);
  assert.deepEqual((await c.post("/api/packs/open", { player: guest })).body, { error: "no unopened packs" });
  const guestRace = await c.post("/api/drivenraces", { player: guest });
  assert.equal(guestRace.status, 201);
});

// ---------------------------------------------------------------- timesheet

test("timesheet: rows carry `you` instead of player ids, accounts show their account name", async () => {
  const c = client();
  const claimed = await register("Speedy One", { guestId: CLAIMED });
  assert.equal(claimed.body.player, CLAIMED);

  const asGuest = await c.get(`/api/event?player=${GUEST_FAST}`);
  assert.equal(asGuest.status, 200);
  const text = JSON.stringify(asGuest.body);
  for (const id of [GUEST_FAST, CLAIMED, IMPOSTOR]) assert.ok(!text.includes(id), `${id} leaked`);
  const board = asGuest.body.leaderboard as any[];
  for (const r of board) {
    assert.equal(typeof r.you, "boolean");
    if (r.ai) assert.match(r.player, /^ai:/);
    else assert.ok(!("player" in r));
  }
  assert.deepEqual(
    board.slice(0, 3).map((r) => [r.position, r.name, r.team, r.you, r.ai]),
    [
      [1, "Fast Guest", "Fast Guest", true, false],
      [2, "Speedy One", "Speedy One", false, false], // the account name, not the old guest name
      [3, "speedy  ONE (guest)", "speedy  ONE (guest)", false, false], // a guest cannot pass as the account
    ],
  );
  assert.equal(board[0].attempt, "a1a1a1a1a1a1a1a1"); // ghosts still work by attempt id
  assert.equal(board.filter((r) => r.ai).length, 5);
  assert.equal(asGuest.body.you.position, 1);

  // the account's own view needs its token and marks its row
  assert.equal((await c.get(`/api/event?player=${CLAIMED}`)).status, 401);
  const mine = await c.get(`/api/event?player=${CLAIMED}`, claimed.body.token);
  assert.deepEqual(
    mine.body.leaderboard.filter((r: any) => r.you).map((r: any) => r.name),
    ["Speedy One"],
  );
  assert.equal(mine.body.you.bestUs, 56_000_000);
  // nobody's row is `you` for an anonymous viewer
  assert.ok((await c.get("/api/event")).body.leaderboard.every((r: any) => r.you === false));
});

// ---------------------------------------------------------------- limits

test("token buckets refill over time, and the daily cap resets at midnight UTC", () => {
  const realNow = R.clock.now;
  let t = Date.UTC(2031, 0, 1, 23, 0, 0);
  R.clock.now = () => t;
  try {
    const l = new R.Limiter(3, 60_000, "Slow down.");
    for (let i = 0; i < 3; i++) l.take("a");
    assert.throws(() => l.take("a"), (e: any) => e.status === 429 && e.details.retryAfter === 20 && e.message === "Slow down. Try again in 20 s.");
    l.take("b"); // per key
    t += 20_000;
    l.take("a");
    assert.throws(() => l.take("a"));
    const off = new R.Limiter(0, 1000, "");
    for (let i = 0; i < 100; i++) off.take("x");

    const cap = new R.DailyCap(2, "Budget used.");
    cap.take();
    cap.take();
    assert.throws(() => cap.take(), (e: any) => e.status === 429 && e.details.retryAfter === 3600 - 20 && /resets at 00:00 UTC, in 60 min/.test(e.message));
    t += 3600_000;
    cap.take();
    assert.equal(cap.used, 1);
  } finally {
    R.clock.now = realNow;
  }
});

test("rate limits over HTTP: sign-ins per minute, races per hour per address and per day for the server", async () => {
  const c = client();
  const attempt = () => c.post("/api/accounts/login", { name: "Nobody Here", password: "whatever" });
  for (let i = 0; i < 10; i++) assert.equal((await attempt()).status, 401);
  const limited = await attempt();
  assert.equal(limited.status, 429);
  assert.match(limited.body.error, /^Too many sign-in attempts\. Try again in \d+ s\.$/);
  assert.ok(limited.body.retryAfter > 0 && limited.body.retryAfter <= 60);
  assert.equal(limited.headers.get("retry-after"), String(limited.body.retryAfter));
  assert.equal((await client().post("/api/accounts/login", { name: "Nobody Here", password: "whatever" })).status, 401);

  // races spend SOL: 6 an hour from one address
  const racer = client();
  const guest = hexId();
  for (let i = 0; i < 6; i++) assert.equal((await racer.post("/api/drivenraces", { player: guest })).status, 201);
  const seventh = await racer.post("/api/drivenraces", { player: guest });
  assert.equal(seventh.status, 429);
  assert.match(seventh.body.error, /6 races an hour/);
  assert.ok(seventh.body.retryAfter > 0 && seventh.body.retryAfter <= 3600);

  // and the server's daily budget (10 in this test) holds across addresses
  let refused: Reply | undefined;
  for (let i = 0; i < 12 && !refused; i++) {
    const r = await client().post("/api/drivenraces", { player: guest });
    if (r.status !== 201) refused = r;
  }
  assert.equal(refused?.status, 429);
  assert.match(refused!.body.error, /race budget for today is used up \(10 races\)/);
  assert.ok(refused!.body.retryAfter > 0 && refused!.body.retryAfter <= 86_400);
  assert.equal(R.limits.chainRaceDay.used, 10);
});

test("a body over 3 MB gets 413; broken JSON gets 400", async () => {
  const post = (body: string) => fetch(`${base}/api/attempts/0123456789abcdef/run`, { method: "POST", headers: { "Content-Type": "application/json", "fly-client-ip": "198.51.100.1" }, body });
  const big = await post(JSON.stringify({ inputs: "x".repeat(3 * 1024 * 1024) }));
  assert.equal(big.status, 413);
  assert.match((await big.json()).error, /larger than 3 MB/);
  // 2 MB passes the size check (and fails as an unknown attempt)
  const ok = await post(JSON.stringify({ inputs: "x".repeat(2_000_000) }));
  assert.equal(ok.status, 400);
  assert.deepEqual(await ok.json(), { error: "unknown attempt" });
  const broken = await post("{not json");
  assert.equal(broken.status, 400);
  assert.deepEqual(await broken.json(), { error: "the body is not valid JSON" });
  const array = await post("[1,2]");
  assert.equal(array.status, 400);
});
