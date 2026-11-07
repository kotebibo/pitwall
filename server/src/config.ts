// Runtime settings. Everything comes from the environment so the same code runs
// locally (test validator) and on Fly.io (devnet) without edits.

import { homedir } from "node:os";
import { join } from "node:path";

/** The development default; index.ts refuses to start on Fly.io with it (tokens and seeds would be forgeable). */
export const DEV_SEED_SECRET = "local-dev-secret-change-me";

export const config = {
  port: Number(process.env.PORT ?? 8787),
  rpcUrl: process.env.RPC_URL ?? "http://127.0.0.1:8899",
  /** Keypair that signs as the race authority (set in the program's Config account). */
  authorityKeypairPath: process.env.AUTHORITY_KEYPAIR ?? join(homedir(), ".config", "solana", "id.json"),
  /** Secret the race seeds are derived from. Anyone holding it could predict races: keep it out of git. */
  seedSecret: process.env.SEED_SECRET ?? DEV_SEED_SECRET,
  /** Seconds between creating a race and locking setups. */
  lockSeconds: Number(process.env.LOCK_SECONDS ?? 20),
  /** Where replays are written so they survive restarts. */
  dataDir: process.env.DATA_DIR ?? new URL("../.data/", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"),
  /** Browser origins allowed to call the API (Godot web build). */
  corsOrigin: process.env.CORS_ORIGIN ?? "*",
  /** Reject runs with more ticks than real time allows. Only switch off for automated tests. */
  realtimeCheck: process.env.REALTIME_CHECK !== "0",
  /** Godot binary and project used to re-drive laps (the same physics the player drove). */
  godotBin: process.env.GODOT_BIN ?? "D:/dev/tools/godot/Godot_v4.7.2-stable_win64_console.exe",
  gameDir: process.env.GAME_DIR ?? new URL("../../game/", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"),
  /** Parts catalogue shared with the Godot client. Defaults to <gameDir>/data/parts.json. */
  partsCatalog: process.env.PARTS_CATALOG ?? "",
  /** Hard cap on parts entering the economy per week (all players together). */
  partsWeeklyCap: Number(process.env.PARTS_WEEKLY_CAP ?? 3000),
  /** Weekly supply = this many parts per player active last week, between the floor and the hard cap. 0 = always the hard cap. */
  partsPerActivePlayer: Number(process.env.PARTS_PER_ACTIVE_PLAYER ?? 3),
  partsWeeklyFloor: Number(process.env.PARTS_WEEKLY_FLOOR ?? 300),
  /** Packs one player can earn per week, and how many unopened packs they can hold. */
  packsPerPlayerWeek: Number(process.env.PACKS_PER_PLAYER_WEEK ?? 5),
  maxUnopenedPacks: Number(process.env.MAX_UNOPENED_PACKS ?? 10),
  /** Largest JSON request body accepted (driving input logs are big). */
  maxBodyBytes: Number(process.env.MAX_BODY_BYTES ?? 3 * 1024 * 1024),
  /** Per-IP request limits; 0 switches one off. */
  postsPerMinute: Number(process.env.POSTS_PER_MINUTE ?? 60),
  getsPerMinute: Number(process.env.GETS_PER_MINUTE ?? 600),
  /** Register, password login and wallet sign-in together. */
  authPerMinute: Number(process.env.AUTH_PER_MINUTE ?? 10),
  /** Races created on Solana cost the authority SOL (~0.01 each): per IP, and for the whole server per UTC day. */
  chainRacesPerIpHour: Number(process.env.CHAIN_RACES_PER_IP_HOUR ?? 6),
  chainRacesPerDay: Number(process.env.CHAIN_RACES_PER_DAY ?? 120),
};
