// Accounts: a name and password (and optionally a linked Solana wallet) that own
// a player id. Players start as guests: the client makes up a random id and
// sends it with every request. Registering can claim that guest id, so the
// guest's qualifying times, parts and packs carry over; quali.ts, parts.ts and
// driven.ts keep keying everything by player id. index.ts only checks that a
// request for an owned id carries that account's token (requireOwner).
//
// Store: config.dataDir/accounts.json, rewritten atomically (tmp file + rename).
// Passwords: scrypt (N=16384, r=8, p=1, 64-byte key) with a random 16-byte salt.
// Tokens are stateless: `${player}.${expiresAtSec}.${HMAC-SHA256 base64url}`,
// valid 30 days. Wallets are linked and signed in with by signing a one-time
// message (ed25519, as every Solana wallet's signMessage does).

import { createHmac, createPublicKey, randomBytes, scrypt, timingSafeEqual, verify } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import type { IncomingMessage } from "node:http";
import { join } from "node:path";
import { PublicKey } from "@solana/web3.js";
import { config } from "./config.ts";
import { PLAYER_DRIVER, PLAYER_TEAM, RIVALS } from "./content.ts";

const TOKEN_TTL_S = 30 * 86_400;
const CHALLENGE_TTL_MS = 10 * 60_000;
/** Outstanding challenges kept per account or wallet, so asking again does not void one being signed. */
const CHALLENGES_KEPT = 4;
const SCRYPT = { N: 16_384, r: 8, p: 1 };
const KEY_LEN = 64;

/** Overridable in tests. */
export const clock = { now: () => Date.now() };

export class AccountError extends Error {
  status: number;
  details: Record<string, unknown>;
  constructor(status: number, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

interface Account {
  player: string;
  name: string;
  password: { salt: string; key: string; N: number; r: number; p: number };
  /** Base58 Solana address, or null. */
  wallet: string | null;
  createdAt: number;
}

// ---------------------------------------------------------------- store

const file = join(config.dataDir, "accounts.json");
const byPlayer = new Map<string, Account>();
const byName = new Map<string, Account>();
const byWallet = new Map<string, Account>();

function index(a: Account) {
  byPlayer.set(a.player, a);
  byName.set(a.name.toLowerCase(), a);
  if (a.wallet) byWallet.set(a.wallet, a);
}

mkdirSync(config.dataDir, { recursive: true });
// A broken file stops the server rather than being replaced by an empty one
if (existsSync(file)) for (const a of (JSON.parse(readFileSync(file, "utf8")) as { accounts: Account[] }).accounts) index(a);

function save() {
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify({ version: 1, accounts: [...byPlayer.values()] }));
  renameSync(tmp, file);
}

// ---------------------------------------------------------------- names and passwords

/** Names the AI field and the game itself use: nobody can register them. */
const RESERVED = new Set(
  [PLAYER_DRIVER.name, PLAYER_TEAM, "You", "Guest", ...RIVALS.flatMap((r) => [r.team, r.driver.name])].map((n) => n.toLowerCase()),
);

const tidyName = (s: string) => s.trim().replace(/\s+/g, " ");

/** Trims, collapses spaces, and checks 3..20 of letters, digits, space, _ and -. */
export function normalizeName(raw: unknown): string {
  const name = typeof raw === "string" ? tidyName(raw) : "";
  if (!/^[A-Za-z0-9 _-]{3,20}$/.test(name)) throw new AccountError(400, "name must be 3 to 20 letters, digits, spaces, _ or -");
  return name;
}

const nameTaken = (name: string) => byName.has(name.toLowerCase()) || RESERVED.has(name.toLowerCase());

function checkPassword(raw: unknown): string {
  if (typeof raw !== "string" || raw.length < 6 || raw.length > 128) throw new AccountError(400, "password must be 6 to 128 characters");
  return raw;
}

const derive = (password: string, salt: Buffer, p = SCRYPT) =>
  new Promise<Buffer>((resolve, reject) =>
    scrypt(password, salt, KEY_LEN, { N: p.N, r: p.r, p: p.p, maxmem: 64 * 1024 * 1024 }, (err, key) => (err ? reject(err) : resolve(key))),
  );

/** Compared against when the name is unknown, so a login takes as long either way. */
const DUMMY_SALT = randomBytes(16);

// ---------------------------------------------------------------- tokens

const tokenKey = createHmac("sha256", config.seedSecret).update("pitwall:account-token:v1").digest();
const sign = (payload: string) => createHmac("sha256", tokenKey).update(payload).digest("base64url");

export function issueToken(player: string, now = clock.now()): string {
  const expires = Math.floor(now / 1000) + TOKEN_TTL_S;
  return `${player}.${expires}.${sign(`${player}.${expires}`)}`;
}

/** The player a token signs in as, or null when it is malformed, tampered with, expired or for no account. */
export function verifyToken(token: string, now = clock.now()): string | null {
  const m = /^([0-9a-f]{16,64})\.(\d{1,12})\.([A-Za-z0-9_-]{43})$/.exec(token);
  if (!m) return null;
  const [, player, expires, sig] = m;
  const want = Buffer.from(sign(`${player}.${expires}`));
  if (!timingSafeEqual(want, Buffer.from(sig))) return null;
  if (Number(expires) * 1000 <= now) return null;
  return byPlayer.has(player) ? player : null;
}

/** The player of the request's `Authorization: Bearer <token>`, or null. */
export function playerFromAuth(req: IncomingMessage): string | null {
  const h = req.headers.authorization;
  const m = typeof h === "string" ? /^Bearer\s+(\S+)\s*$/i.exec(h) : null;
  return m ? verifyToken(m[1]) : null;
}

/** The signed-in player, or 401. */
export function requireAuth(req: IncomingMessage): string {
  const player = playerFromAuth(req);
  if (!player) throw new AccountError(401, "not signed in");
  return player;
}

/** Requests acting on an owned player id need that account's token; guest ids work without one. */
export function requireOwner(req: IncomingMessage, player: string) {
  if (byPlayer.has(player) && playerFromAuth(req) !== player) throw new AccountError(401, "sign in to use this account");
}

export const isOwned = (player: string) => byPlayer.has(player);
export const accountName = (player: string): string | undefined => byPlayer.get(player)?.name;
/** True when a (guest's) display name is an account's name, ignoring case and extra spaces. */
export const isAccountName = (name: string) => byName.has(tidyName(name).toLowerCase());

const session = (a: Account) => ({ token: issueToken(a.player), player: a.player, name: a.name, wallet: a.wallet });

// ---------------------------------------------------------------- register, login, me

export async function register(input: { name?: unknown; password?: unknown; guestId?: unknown }) {
  const name = normalizeName(input.name);
  const password = checkPassword(input.password);
  let guestId: string | undefined;
  if (input.guestId !== undefined && input.guestId !== null && input.guestId !== "") {
    if (typeof input.guestId !== "string" || !/^[0-9a-f]{32,64}$/i.test(input.guestId)) throw new AccountError(400, "guestId must be 32 to 64 hex characters");
    guestId = input.guestId.toLowerCase();
  }
  if (nameTaken(name)) throw new AccountError(409, "that name is taken");
  const salt = randomBytes(16);
  const key = await derive(password, salt);
  // again: another registration may have taken the name (or the guest id) while the key was derived
  if (nameTaken(name)) throw new AccountError(409, "that name is taken");
  let player = guestId && !byPlayer.has(guestId) ? guestId : "";
  while (!player || byPlayer.has(player)) player = randomBytes(16).toString("hex");
  const a: Account = { player, name, password: { salt: salt.toString("hex"), key: key.toString("hex"), ...SCRYPT }, wallet: null, createdAt: clock.now() };
  index(a);
  save();
  return session(a);
}

export async function login(input: { name?: unknown; password?: unknown }) {
  const name = typeof input.name === "string" ? tidyName(input.name) : "";
  const password = typeof input.password === "string" && input.password.length <= 128 ? input.password : "";
  const a = byName.get(name.toLowerCase());
  const key = await derive(password, a ? Buffer.from(a.password.salt, "hex") : DUMMY_SALT, a?.password);
  if (!a || !password || !timingSafeEqual(key, Buffer.from(a.password.key, "hex"))) throw new AccountError(401, "wrong name or password");
  return session(a);
}

export function me(player: string) {
  const a = byPlayer.get(player);
  if (!a) throw new AccountError(401, "not signed in");
  return { player: a.player, name: a.name, wallet: a.wallet, createdAt: a.createdAt };
}

// ---------------------------------------------------------------- wallets

interface Challenge {
  message: string;
  expiresAt: number;
}
/** Link challenges by player id; sign-in challenges by wallet. Memory only: a restart voids them. */
const linkChallenges = new Map<string, Challenge[]>();
const loginChallenges = new Map<string, Challenge[]>();

function issueChallenge(store: Map<string, Challenge[]>, key: string, text: (nonce: string, issued: string) => string) {
  const now = clock.now();
  if (store.size > 10_000) {
    for (const [k, list] of store) if (list.every((c) => c.expiresAt <= now)) store.delete(k);
    // still full: drop the oldest keys
    for (const k of store.keys()) {
      if (store.size <= 10_000) break;
      store.delete(k);
    }
  }
  const message = text(randomBytes(16).toString("hex"), new Date(now).toISOString());
  const list = (store.get(key) ?? []).filter((c) => c.expiresAt > now).slice(-(CHALLENGES_KEPT - 1));
  list.push({ message, expiresAt: now + CHALLENGE_TTL_MS });
  store.set(key, list);
  return { message };
}

/** Finds an unexpired challenge the signature signs, and uses it up. */
function takeSigned(store: Map<string, Challenge[]>, key: string, wallet: Buffer, signature: unknown): boolean {
  const now = clock.now();
  const list = (store.get(key) ?? []).filter((c) => c.expiresAt > now);
  const sigs = signatureBytes(signature);
  const hit = list.find((c) => sigs.some((s) => verifyEd25519(wallet, c.message, s)));
  if (!hit) return false;
  const rest = list.filter((c) => c !== hit);
  if (rest.length) store.set(key, rest);
  else store.delete(key);
  return true;
}

function parseWallet(raw: unknown): { address: string; bytes: Buffer } {
  if (typeof raw === "string" && raw.length >= 32 && raw.length <= 44) {
    try {
      const key = new PublicKey(raw);
      if (key.toBase58() === raw) return { address: raw, bytes: key.toBuffer() };
    } catch {
      // not base58 or not 32 bytes
    }
  }
  throw new AccountError(400, "wallet must be a base58 Solana address");
}

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
export function base58Decode(s: string): Buffer | null {
  if (!/^[1-9A-HJ-NP-Za-km-z]+$/.test(s)) return null;
  let n = 0n;
  for (const c of s) n = n * 58n + BigInt(B58.indexOf(c));
  const bytes: number[] = [];
  for (; n > 0n; n >>= 8n) bytes.unshift(Number(n & 0xffn));
  const zeros = s.length - s.replace(/^1+/, "").length;
  return Buffer.from([...new Array<number>(zeros).fill(0), ...bytes]);
}
export function base58Encode(b: Uint8Array): string {
  let n = BigInt(`0x0${Buffer.from(b).toString("hex")}`);
  let out = "";
  for (; n > 0n; n /= 58n) out = B58[Number(n % 58n)] + out;
  for (let i = 0; i < b.length && b[i] === 0; i++) out = `1${out}`;
  return out;
}

/** A 64-byte signature sent as base64 (or base64url) or base58; a string valid as both is tried both ways. */
function signatureBytes(raw: unknown): Buffer[] {
  if (typeof raw !== "string" || raw.length > 200) return [];
  const s = raw.trim();
  const out: Buffer[] = [];
  if (/^[A-Za-z0-9+/_-]+={0,2}$/.test(s)) out.push(Buffer.from(s, "base64"));
  const b58 = base58Decode(s);
  if (b58) out.push(b58);
  return out.filter((b) => b.length === 64);
}

function verifyEd25519(publicKey: Buffer, message: string, signature: Buffer): boolean {
  try {
    const key = createPublicKey({ key: { kty: "OKP", crv: "Ed25519", x: publicKey.toString("base64url") }, format: "jwk" });
    return verify(null, Buffer.from(message, "utf8"), key, signature);
  } catch {
    return false;
  }
}

/** The message to sign with the wallet being linked to the signed-in account. */
export function walletChallenge(player: string) {
  const a = byPlayer.get(player);
  if (!a) throw new AccountError(401, "not signed in");
  return issueChallenge(linkChallenges, player, (nonce, issued) => `Pit Wall: link this wallet to the account ${a.name}.\nNonce: ${nonce}\nIssued: ${issued}`);
}

export function linkWallet(player: string, input: { wallet?: unknown; signature?: unknown }) {
  const a = byPlayer.get(player);
  if (!a) throw new AccountError(401, "not signed in");
  const wallet = parseWallet(input.wallet);
  if (!linkChallenges.get(player)?.some((c) => c.expiresAt > clock.now())) throw new AccountError(400, "no wallet challenge for this account (or it expired): ask for a new one");
  if (!takeSigned(linkChallenges, player, wallet.bytes, input.signature)) throw new AccountError(400, "the signature is not this wallet's signature of the challenge");
  // only after the signature: nobody learns which wallets are linked without holding the key
  const owner = byWallet.get(wallet.address);
  if (owner && owner !== a) throw new AccountError(409, "that wallet is linked to another account");
  if (a.wallet && a.wallet !== wallet.address) byWallet.delete(a.wallet);
  a.wallet = wallet.address;
  byWallet.set(wallet.address, a);
  save();
  return { wallet: a.wallet };
}

/** "Sign in with Solana", step 1: the message the wallet signs. Given for any address, linked or not. */
export function walletLoginChallenge(input: { wallet?: unknown }) {
  const wallet = parseWallet(input.wallet);
  return issueChallenge(loginChallenges, wallet.address, (nonce, issued) => `Pit Wall: sign in with this wallet.\nWallet: ${wallet.address}\nNonce: ${nonce}\nIssued: ${issued}`);
}

/** Step 2: the signed message signs in to the account the wallet is linked to. */
export function walletLogin(input: { wallet?: unknown; signature?: unknown }) {
  const wallet = parseWallet(input.wallet);
  if (!takeSigned(loginChallenges, wallet.address, wallet.bytes, input.signature)) throw new AccountError(401, "the signature does not match a sign-in challenge for this wallet: ask for a new one");
  const a = byWallet.get(wallet.address);
  if (!a) throw new AccountError(401, "no account is linked to this wallet");
  return session(a);
}
