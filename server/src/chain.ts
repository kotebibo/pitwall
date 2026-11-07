// Everything the server does on Solana goes through this module.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import anchor from "@anchor-lang/core";
import { Connection, Keypair, PublicKey, Transaction, type TransactionInstruction } from "@solana/web3.js";
import { config } from "./config.ts";
import type { DriverSeed } from "./content.ts";

const { AnchorProvider, Program, Wallet, BN } = anchor;
const require = createRequire(import.meta.url);
const idl = require("../../target/idl/pitwall.json");

export const NAME_LEN = 24;
const enc = (s: string) => new TextEncoder().encode(s);

export function nameBytes(s: string): number[] {
  const out = new Array<number>(NAME_LEN).fill(0);
  enc(s).slice(0, NAME_LEN).forEach((b, i) => (out[i] = b));
  return out;
}
export function bytesToName(bytes: number[]): string {
  const end = bytes.indexOf(0);
  return new TextDecoder().decode(Uint8Array.from(end === -1 ? bytes : bytes.slice(0, end)));
}
const u64le = (n: number | bigint) => {
  const b = Buffer.alloc(8);
  b.writeBigUInt64LE(BigInt(n));
  return b;
};

export const authority = Keypair.fromSecretKey(Uint8Array.from(JSON.parse(readFileSync(config.authorityKeypairPath, "utf8"))));
export const connection = new Connection(config.rpcUrl, "confirmed");
const provider = new AnchorProvider(connection, new Wallet(authority), { commitment: "confirmed" });
export const program = new Program(idl, provider);
export const programId = program.programId;

export const pda = {
  config: () => PublicKey.findProgramAddressSync([enc("config")], programId)[0],
  race: (raceId: number | bigint) => PublicKey.findProgramAddressSync([enc("race"), u64le(raceId)], programId)[0],
  driver: (driverId: number | bigint) => PublicKey.findProgramAddressSync([enc("driver"), u64le(driverId)], programId)[0],
  entry: (race: PublicKey, driver: PublicKey) =>
    PublicKey.findProgramAddressSync([enc("entry"), race.toBuffer(), driver.toBuffer()], programId)[0],
};

async function send(ixs: TransactionInstruction[]): Promise<string> {
  return provider.sendAndConfirm(new Transaction().add(...ixs), []);
}

/** Creates the Config account on first run. */
export async function ensureConfig(): Promise<void> {
  if (await connection.getAccountInfo(pda.config())) return;
  await program.methods.initialize(authority.publicKey).accountsPartial({ payer: authority.publicKey, config: pda.config() }).rpc();
}

/** Creates a driver if it does not exist yet. */
export async function ensureDriver(d: DriverSeed, owner: PublicKey): Promise<PublicKey> {
  const driver = pda.driver(d.driverId);
  if (await connection.getAccountInfo(driver)) return driver;
  await program.methods
    .createDriver(new BN(d.driverId), {
      owner,
      name: nameBytes(d.name),
      rarity: d.rarity,
      pace: d.pace,
      racecraft: d.racecraft,
      tyreManagement: d.tyreManagement,
      potential: d.potential,
    })
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), driver })
    .rpc();
  return driver;
}

export interface ChainSetup {
  driver: PublicKey;
  team: string;
  design: number;
  tyre: number;
  stops: number;
  risk: number;
}

export async function createRace(
  raceId: number,
  p: { trackType: number; laps: number; baseLapMs: number; commitment: Buffer; lockTs: number },
): Promise<string> {
  return program.methods
    .createRace(new BN(raceId), {
      trackType: p.trackType,
      laps: p.laps,
      baseLapMs: p.baseLapMs,
      commitment: [...p.commitment],
      lockTs: new BN(p.lockTs),
    })
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), race: pda.race(raceId) })
    .rpc();
}

/** Enters every setup in one transaction (the authority signs for custodial players). */
export async function enterAll(raceId: number, setups: ChainSetup[]): Promise<string> {
  const race = pda.race(raceId);
  const ixs = await Promise.all(
    setups.map((s) =>
      program.methods
        .enterRace({ teamName: nameBytes(s.team), design: s.design, tyre: s.tyre, stops: s.stops, risk: s.risk })
        .accountsPartial({ signer: authority.publicKey, config: pda.config(), race, driver: s.driver, entry: pda.entry(race, s.driver) })
        .instruction(),
    ),
  );
  return send(ixs);
}

export async function revealSeed(raceId: number, seed: Buffer): Promise<string> {
  return program.methods
    .revealSeed([...seed])
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), race: pda.race(raceId) })
    .rpc();
}

export async function postResult(raceId: number, resultHash: Buffer): Promise<string> {
  return program.methods
    .postResult([...resultHash])
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), race: pda.race(raceId) })
    .rpc();
}

/** Settles every entry's finishing position in one transaction. */
export async function settleAll(raceId: number, positions: { driver: PublicKey; position: number }[]): Promise<string> {
  const race = pda.race(raceId);
  const ixs = await Promise.all(
    positions.map((p) =>
      program.methods
        .settleEntry(p.position)
        .accountsPartial({ authority: authority.publicKey, config: pda.config(), race, entry: pda.entry(race, p.driver), driver: p.driver })
        .instruction(),
    ),
  );
  return send(ixs);
}

/** A player's lap record for one qualifying event; `player` is the 32-byte sha256 of their id. */
export function lapPda(eventId: number, player: Buffer): PublicKey {
  return PublicKey.findProgramAddressSync([enc("lap"), u64le(eventId), player], programId)[0];
}

/** Records a lap the server has re-driven and verified; the program keeps the player's best. */
export async function submitLap(
  eventId: number,
  player: Buffer,
  p: { circuit: number; physicsVersion: number; lapUs: number; inputHash: Buffer },
): Promise<string> {
  return program.methods
    .submitLap(new BN(eventId), [...player], {
      circuit: p.circuit,
      physicsVersion: p.physicsVersion,
      lapUs: p.lapUs,
      inputHash: [...p.inputHash],
    })
    .accountsPartial({ authority: authority.publicKey, config: pda.config(), lapRecord: lapPda(eventId, player) })
    .rpc();
}

export async function fetchRace(raceId: number) {
  return program.account.race.fetchNullable(pda.race(raceId));
}

/** All entries of a race, in slot order (the order the sim takes teams). */
export async function fetchEntries(raceId: number) {
  const race = pda.race(raceId);
  const all = await program.account.entry.all([{ memcmp: { offset: 8, bytes: race.toBase58() } }]);
  return all.map((a) => ({ pubkey: a.publicKey, ...a.account })).sort((a, b) => a.slot - b.slot);
}

export async function fetchDriver(driverId: number) {
  return program.account.driver.fetchNullable(pda.driver(driverId));
}
