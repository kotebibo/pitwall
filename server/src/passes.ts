// Race passes: staked time-trial events on equal cars. Players stake from their own wallet into
// an on-chain pool; when the event closes, the program pays out by placing and keeps Pit Wall's
// share (it refuses to close the pool unless players got exactly the rest).
//
// Ranking: each entrant's best verified pass lap driven inside the pool's window, after they
// entered. Two classes: SPEC pools are driven in the standard car (only driving counts), OPEN
// pools in your own car, with your parts and setup.
// On devnet the stakes are devnet SOL, standing in for USDC.

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import anchor from "@anchor-lang/core";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { authority, connection, pda, program, programId } from "./chain.ts";
import { config } from "./config.ts";

const { BN } = anchor;
const DAY_MS = 86_400_000;
const weekOf = (ms: number) => Math.floor((Math.floor(ms / DAY_MS) + 3) / 7);
const weekStartMs = (week: number) => (week * 7 - 3) * DAY_MS;

export const RAKE_BPS = 1000; // Pit Wall's share: 10%
export const PAID_SHARE = 0.2; // the top 20% are paid
export const MIN_PAYOUT_X = 1.5; // every paid place gets at least 1.5x the stake
export const MIN_ENTRANTS = 4; // fewer entrants: everyone is refunded
const CURVE = 1.1;

type Kind = "daily" | "weekly" | "sprint";
export type PassClass = "spec" | "open";
export const CLASSES: PassClass[] = ["spec", "open"];
const TIERS: Record<"daily" | "weekly", { name: string; sol: number }[]> = {
  daily: [
    { name: "BRONZE", sol: 0.01 },
    { name: "SILVER", sol: 0.05 },
    { name: "GOLD", sol: 0.1 },
  ],
  weekly: [
    { name: "BRONZE", sol: 0.05 },
    { name: "SILVER", sol: 0.2 },
    { name: "GOLD", sol: 0.5 },
  ],
};
const GRANT_SOL = 0.3; // devnet test SOL for a wallet that cannot cover a stake (once per wallet)
const GRANT_BUDGET_SOL = Number(process.env.PASS_GRANT_BUDGET_SOL ?? 1.5);

interface Entrant {
  player: string;
  wallet: string;
  name: string;
  enteredAt: number;
  tx: string;
  best?: { us: number; attempt: string; inputHash: string; at: number };
}
interface Pool {
  id: number;
  kind: Kind;
  tier: number;
  /** spec: everyone in the standard car; open: your own parts and setup (missing = spec). */
  cls?: PassClass;
  name: string;
  stakeLamports: number;
  opensAt: number;
  closesAt: number;
  createTx?: string;
  entrants: Entrant[];
  settled?: { at: number; refund: boolean; resultsHash: string; txs: string[]; payouts: { player: string; wallet: string; lamports: number }[] };
  settleError?: string;
}
interface State {
  pools: Record<string, Pool>;
  grants: Record<string, number>; // wallet -> lamports granted
}

const dir = join(config.dataDir, "passes");
mkdirSync(dir, { recursive: true });
const file = join(dir, "state.json");
const state: State = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : { pools: {}, grants: {} };
function save() {
  writeFileSync(file + ".tmp", JSON.stringify(state));
  renameSync(file + ".tmp", file);
}

const enc = (s: string) => new TextEncoder().encode(s);
const u64le = (n: number) => {
  const b = Buffer.alloc(8);
  b.writeBigUInt64LE(BigInt(n));
  return b;
};
const poolPda = (id: number) => PublicKey.findProgramAddressSync([enc("pool"), u64le(id)], programId)[0];
const passPda = (pool: PublicKey, wallet: PublicKey) => PublicKey.findProgramAddressSync([enc("pass"), pool.toBuffer(), wallet.toBuffer()], programId)[0];
const sol = (lamports: number) => Math.round((lamports / LAMPORTS_PER_SOL) * 10000) / 10000;

// ---------------------------------------------------------------- payouts

/** Lamports per finishing place for a pool. Exactly stakes minus Pit Wall's share, or a full refund. */
export function payoutTable(entrants: number, ranked: number, stake: number): { refund: boolean; places: number[]; rake: number } {
  const total = entrants * stake;
  if (entrants < MIN_ENTRANTS || ranked === 0) return { refund: true, places: [], rake: 0 };
  const rake = Math.floor((total * RAKE_BPS) / 10_000);
  const prize = total - rake;
  const k = Math.min(ranked, Math.max(1, Math.round(entrants * PAID_SHARE)));
  const base = Math.floor(MIN_PAYOUT_X * stake);
  const rest = prize - base * k;
  const w = Array.from({ length: k }, (_, i) => 1 / Math.pow(i + 1, CURVE));
  const sum = w.reduce((a, b) => a + b, 0);
  const places = w.map((x) => base + Math.floor((rest * x) / sum));
  places[0] += prize - places.reduce((a, b) => a + b, 0); // rounding goes to the winner
  return { refund: false, places, rake };
}

function standings(p: Pool) {
  const ranked = p.entrants.filter((e) => e.best).sort((a, b) => a.best!.us - b.best!.us || a.best!.at - b.best!.at);
  const table = payoutTable(p.entrants.length, ranked.length, p.stakeLamports);
  return { ranked, table };
}

// ---------------------------------------------------------------- pools

// Each server (live, local dev, tests) gets its own range of on-chain pool ids, derived from its
// secret, so two servers sharing the devnet program never enter or settle each other's pools.
const NAMESPACE = createHash("sha256").update(`pools:${config.seedSecret}`).digest().readUInt32LE(0) % 100_000;

function poolId(kind: Kind, window: number, tier: number) {
  return NAMESPACE * 10_000_000_000 + (kind === "daily" ? 1 : kind === "weekly" ? 2 : 3) * 1_000_000_000 + window * 10 + tier;
}

/** Today's and this week's pools (created lazily; on-chain when someone first enters). */
function currentPools(now = Date.now()): Pool[] {
  const day = Math.floor(now / DAY_MS);
  const week = weekOf(now);
  const out: Pool[] = [];
  for (const cls of CLASSES) {
    for (const kind of ["daily", "weekly"] as const) {
      TIERS[kind].forEach((t, tier) => {
        const window = kind === "daily" ? day : week;
        const id = poolId(kind, window, tier + (cls === "open" ? 3 : 0));
        const opensAt = kind === "daily" ? day * DAY_MS : weekStartMs(week);
        const closesAt = kind === "daily" ? (day + 1) * DAY_MS : weekStartMs(week + 1);
        state.pools[id] ??= { id, kind, tier, cls, name: `${kind.toUpperCase()} ${t.name}`, stakeLamports: Math.round(t.sol * LAMPORTS_PER_SOL), opensAt, closesAt, entrants: [] };
        out.push(state.pools[id]);
      });
    }
  }
  // admin sprint pools that are still open or just settled
  for (const p of Object.values(state.pools)) if (p.kind === "sprint" && (p.closesAt > now || (p.settled && now - p.settled.at < 3 * 3600_000))) out.push(p);
  return out;
}

async function ensureOnChain(p: Pool) {
  if (p.createTx) return;
  if (await connection.getAccountInfo(poolPda(p.id))) {
    p.createTx = "existing";
    return;
  }
  p.createTx = await program.methods
    .createPool(new BN(p.id), { entryLamports: new BN(p.stakeLamports), closesTs: new BN(Math.floor(p.closesAt / 1000)), rakeBps: RAKE_BPS })
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), pool: poolPda(p.id), systemProgram: SystemProgram.programId })
    .rpc();
  save();
}

/** Admin: a short pool for demos and testing. */
export function createSprint(minutes: number, stakeSol: number) {
  const now = Date.now();
  const id = poolId("sprint", Math.floor(now / 60_000), 0);
  state.pools[id] = { id, kind: "sprint", tier: 0, name: `SPRINT ${minutes} MIN`, stakeLamports: Math.round(stakeSol * LAMPORTS_PER_SOL), opensAt: now, closesAt: now + minutes * 60_000, entrants: [] };
  save();
  return publicPool(state.pools[id], "");
}

function publicPool(p: Pool, player: string) {
  const { ranked, table } = standings(p);
  const paidFor = (i: number) => (table.refund ? p.stakeLamports : (table.places[i] ?? 0));
  const preview = payoutTable(Math.max(p.entrants.length, MIN_ENTRANTS), Math.max(p.entrants.length, MIN_ENTRANTS), p.stakeLamports);
  const me = p.entrants.find((e) => e.player === player);
  const myRank = me ? ranked.indexOf(me) + 1 : 0;
  return {
    id: p.id,
    kind: p.kind,
    cls: p.cls ?? "spec",
    name: p.name,
    stakeSol: sol(p.stakeLamports),
    opensAt: p.opensAt,
    closesAt: p.closesAt,
    entrants: p.entrants.length,
    potSol: sol(p.entrants.length * p.stakeLamports),
    prizeSol: sol(p.entrants.length * p.stakeLamports - payoutTable(p.entrants.length, p.entrants.length, p.stakeLamports).rake),
    paidPlaces: table.refund ? 0 : table.places.length,
    refund: table.refund,
    // what 1st-3rd would win if the pool closed with at least the minimum field
    previewSol: preview.places.slice(0, 3).map(sol),
    // a fuller field, to show what a pass can win
    exampleSol: payoutTable(20, 20, p.stakeLamports).places.slice(0, 3).map(sol),
    standings: ranked.slice(0, 10).map((e, i) => ({ rank: i + 1, name: e.name, us: e.best!.us, winSol: sol(table.refund ? p.stakeLamports : paidFor(i)), you: e.player === player })),
    you: me ? { entered: true, rank: myRank, us: me.best?.us ?? null, winSol: myRank ? sol(paidFor(myRank - 1)) : 0, tx: me.tx } : { entered: false },
    settled: p.settled ? { refund: p.settled.refund, txs: p.settled.txs, resultsHash: p.settled.resultsHash } : null,
  };
}

export function passesInfo(player: string, wallet: string | null) {
  const pools = currentPools().map((p) => publicPool(p, player));
  return {
    devnet: true,
    wallet,
    rules: {
      rakePct: RAKE_BPS / 100,
      paidPct: PAID_SHARE * 100,
      minPayoutX: MIN_PAYOUT_X,
      minEntrants: MIN_ENTRANTS,
    },
    pools,
  };
}

// ---------------------------------------------------------------- entering

function findPool(id: number): Pool {
  const p = state.pools[id];
  if (!p) throw Object.assign(new Error("no such pool"), { status: 404 });
  return p;
}

/** Builds the unsigned "enter_pool" transaction for the player's wallet to sign. */
export async function enterTx(player: string, wallet: string, id: number) {
  {
    const p = findPool(id);
    if (Date.now() >= p.closesAt) throw Object.assign(new Error("this pool is closed"), { status: 409 });
    if (p.entrants.some((e) => e.player === player)) throw Object.assign(new Error("you already have this race pass"), { status: 409 });
    await ensureOnChain(p);
    const w = new PublicKey(wallet);
    // devnet only: top up a test wallet that cannot cover the stake, once
    let grant: { sol: number; signature: string } | undefined;
    const balance = await connection.getBalance(w);
    const need = p.stakeLamports + 0.01 * LAMPORTS_PER_SOL;
    const spent = Object.values(state.grants).reduce((a, b) => a + b, 0);
    if (balance < need && !state.grants[wallet] && spent + GRANT_SOL * LAMPORTS_PER_SOL <= GRANT_BUDGET_SOL * LAMPORTS_PER_SOL) {
      const lamports = Math.max(Math.round(GRANT_SOL * LAMPORTS_PER_SOL), need - balance);
      const sig = await program.provider.sendAndConfirm!(new Transaction().add(SystemProgram.transfer({ fromPubkey: authority.publicKey, toPubkey: w, lamports })), []);
      state.grants[wallet] = lamports;
      save();
      grant = { sol: sol(lamports), signature: sig };
    }
    const ix = await program.methods
      .enterPool()
      .accountsPartial({ player: w, pool: poolPda(p.id), entry: passPda(poolPda(p.id), w), systemProgram: SystemProgram.programId })
      .instruction();
    const { blockhash } = await connection.getLatestBlockhash();
    const tx = new Transaction({ feePayer: w, recentBlockhash: blockhash }).add(ix);
    return { pool: p.id, stakeSol: sol(p.stakeLamports), tx: tx.serialize({ requireAllSignatures: false, verifySignatures: false }).toString("base64"), grant };
  }
}

/** Checks the wallet-signed transaction is exactly the pass purchase, broadcasts it and records the entry. */
export async function confirmEntry(player: string, wallet: string, name: string, id: number, signedB64: string) {
  const p = findPool(id);
  if (p.entrants.some((e) => e.player === player)) return { entered: true, tx: p.entrants.find((e) => e.player === player)!.tx };
  const tx = Transaction.from(Buffer.from(signedB64, "base64"));
  const w = new PublicKey(wallet);
  const pool = poolPda(p.id);
  const ix = tx.instructions.find((i) => i.programId.equals(programId));
  const expected = await program.methods.enterPool().accountsPartial({ player: w, pool, entry: passPda(pool, w), systemProgram: SystemProgram.programId }).instruction();
  const same = ix && Buffer.from(ix.data).equals(Buffer.from(expected.data)) && ix.keys.length === expected.keys.length && ix.keys.every((k, i) => k.pubkey.equals(expected.keys[i].pubkey));
  if (!same || !tx.feePayer?.equals(w) || !tx.verifySignatures()) throw Object.assign(new Error("that is not this race pass's transaction"), { status: 400 });
  const signature = await connection.sendRawTransaction(tx.serialize());
  await connection.confirmTransaction(signature, "confirmed");
  if (!(await connection.getAccountInfo(passPda(pool, w)))) throw Object.assign(new Error("the pass was not recorded on-chain"), { status: 502 });
  p.entrants.push({ player, wallet, name, enteredAt: Date.now(), tx: signature });
  save();
  return { entered: true, tx: signature };
}

// ---------------------------------------------------------------- laps

/** A verified pass lap counts in every pool the player had entered whose window contains it. */
export function recordPassLap(player: string, lap: { us: number; attempt: string; inputHash: string }, cls: PassClass = "spec") {
  const at = Date.now();
  const touched: { pool: string; rank: number; of: number }[] = [];
  for (const p of Object.values(state.pools)) {
    if (p.settled || at < p.opensAt || at >= p.closesAt || (p.cls ?? "spec") !== cls) continue;
    const e = p.entrants.find((x) => x.player === player && x.enteredAt <= at);
    if (!e) continue;
    if (!e.best || lap.us < e.best.us) e.best = { ...lap, at };
    const { ranked } = standings(p);
    touched.push({ pool: `${p.name} ${cls.toUpperCase()}`, rank: ranked.indexOf(e) + 1, of: p.entrants.length });
  }
  if (touched.length) save();
  return touched;
}

export const hasOpenPass = (player: string, cls: PassClass = "spec") =>
  Object.values(state.pools).some((p) => !p.settled && Date.now() < p.closesAt && (p.cls ?? "spec") === cls && p.entrants.some((e) => e.player === player));

// ---------------------------------------------------------------- settlement

async function settle(p: Pool) {
  const { ranked, table } = standings(p);
  const payouts = table.refund
    ? p.entrants.map((e) => ({ player: e.player, wallet: e.wallet, lamports: p.stakeLamports }))
    : table.places.map((lamports, i) => ({ player: ranked[i].player, wallet: ranked[i].wallet, lamports }));
  const results = { pool: p.id, refund: table.refund, ranked: ranked.map((e) => ({ wallet: e.wallet, us: e.best!.us, inputHash: e.best!.inputHash })), payouts };
  const resultsHash = createHash("sha256").update(JSON.stringify(results)).digest();
  const pool = poolPda(p.id);
  const txs: string[] = [];
  for (let i = 0; i < payouts.length; i += 6) {
    const ixs = [];
    for (const pay of payouts.slice(i, i + 6)) {
      const w = new PublicKey(pay.wallet);
      const entry = passPda(pool, w);
      const acc = await program.account.passEntry.fetch(entry);
      if ((acc as { paid: boolean }).paid) continue;
      ixs.push(await program.methods.payOut(new BN(pay.lamports)).accountsPartial({ authority: authority.publicKey, config: pda.config(), pool, entry, player: w }).instruction());
    }
    if (ixs.length) txs.push(await program.provider.sendAndConfirm!(new Transaction().add(...ixs), []));
  }
  txs.push(await program.methods.closePool([...resultsHash], table.refund).accountsPartial({ authority: authority.publicKey, config: pda.config(), pool }).rpc());
  p.settled = { at: Date.now(), refund: table.refund, resultsHash: resultsHash.toString("hex"), txs, payouts };
  p.settleError = undefined;
  save();
}

let busy = false;
/** Settles every pool whose entries have closed. Safe to call often. */
export async function settleDue() {
  if (busy) return;
  busy = true;
  try {
    for (const p of Object.values(state.pools)) {
      if (p.settled || Date.now() < p.closesAt + 2000) continue;
      if (p.entrants.length === 0) {
        p.settled = { at: Date.now(), refund: true, resultsHash: "", txs: [], payouts: [] };
        if (p.createTx && p.createTx !== "existing") {
          // an empty on-chain pool still gets closed so its state is final
          try {
            const tx = await program.methods.closePool(new Array(32).fill(0), true).accountsPartial({ authority: authority.publicKey, config: pda.config(), pool: poolPda(p.id) }).rpc();
            p.settled.txs.push(tx);
          } catch (err) {
            p.settleError = String((err as Error).message).slice(0, 200);
          }
        }
        save();
        continue;
      }
      try {
        await settle(p);
      } catch (err) {
        p.settleError = String((err as Error).message).slice(0, 200);
        save();
        console.error("pass settle failed", p.id, p.settleError);
      }
    }
  } finally {
    busy = false;
  }
}

if (process.env.PASSES_SETTLE !== "off") setInterval(() => void settleDue(), 60_000).unref();
