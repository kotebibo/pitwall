// Pit Wall race server: a small JSON API for the Godot client, plus the web build.
//
// Players are guests (a random id the client keeps) or accounts (accounts.ts),
// which own a player id. Every route that acts on a player id checks that an
// owned id comes with that account's Bearer token; guest ids need none. No
// response carries another player's id: for a guest it is all it takes to act
// as them.

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import * as accounts from "./accounts.ts";
import { AccountError } from "./accounts.ts";
import * as chain from "./chain.ts";
import { config, DEV_SEED_SECRET } from "./config.ts";
import { PLAYER_DRIVER, TRACKS, TRACK_NAMES } from "./content.ts";
import { drivenInputs, finishDrivenRace, getDrivenRace, startDrivenRace } from "./driven.ts";
import { awardPack, catalog, equip, garage, openPack, scrapPart, setLivery } from "./parts.ts";
import { attemptPlayer, eventInfo, ghost, startAttempt, submitRun } from "./quali.ts";
import { clientIp, limits, takeChainRace } from "./ratelimit.ts";
import { bootstrap, getRace, startRace, validateSetup, verifyRace } from "./races.ts";
import * as stats from "./stats.ts";
import * as passes from "./passes.ts";
import { rankedInfo } from "./ranked.ts";

const WEB_DIR = process.env.WEB_DIR ?? new URL("../../build/web/", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".wasm": "application/wasm",
  ".pck": "application/octet-stream",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json",
};

function json(res: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "Access-Control-Allow-Origin": config.corsOrigin,
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    ...headers,
  });
  res.end(JSON.stringify(body));
}

/**
 * The request's JSON object body; 413 past config.maxBodyBytes. An oversized body
 * is read to the end (and dropped) before the answer, or the client would see a
 * reset instead of the 413; past four times the limit the connection is closed.
 */
function body(req: IncomingMessage): Promise<Record<string, unknown>> {
  const max = config.maxBodyBytes;
  const tooLarge = (close: boolean) => Object.assign(new AccountError(413, `request body is larger than ${Math.floor(max / 1024 / 1024)} MB`), { close });
  if (Number(req.headers["content-length"] ?? 0) > 4 * max) return Promise.reject(tooLarge(true));
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    let done = false;
    req.on("data", (c: Buffer) => {
      if (done) return;
      size += c.length;
      if (size > 4 * max) {
        done = true;
        reject(tooLarge(true));
      } else if (size <= max) chunks.push(c);
    });
    req.on("end", () => {
      if (done) return;
      done = true;
      if (size > max) return reject(tooLarge(false));
      const text = Buffer.concat(chunks).toString("utf8");
      try {
        const parsed: unknown = text ? JSON.parse(text) : {};
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new AccountError(400, "the body must be a JSON object");
        resolve(parsed as Record<string, unknown>);
      } catch (err) {
        reject(err instanceof AccountError ? err : new AccountError(400, "the body is not valid JSON"));
      }
    });
    req.on("error", (err) => {
      if (!done) reject(err);
      done = true;
    });
  });
}

const BRAND_DIR = process.env.BRAND_DIR ?? new URL("../../brand/", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

/** Static files: the web build, plus /brand/* (logos, link-preview images).
 * Serves a pre-compressed `.gz` next to a file when the browser accepts gzip
 * (the 40 MB .wasm is 10 MB gzipped), and lets browsers cache the big files. */
function serveStatic(path: string, res: ServerResponse, acceptEncoding = "", head = false): boolean {
  const brand = path.startsWith("/brand/");
  const root = brand ? BRAND_DIR : WEB_DIR;
  const rel = brand ? path.slice("/brand/".length) : path === "/" ? "index.html" : path;
  const file = normalize(join(root, rel));
  if (!file.startsWith(normalize(root)) || !existsSync(file) || statSync(file).isDirectory()) return false;
  const headers: Record<string, string> = { "Content-Type": MIME[extname(file)] ?? "application/octet-stream" };
  const ext = extname(file);
  headers["Cache-Control"] = ext === ".html" ? "no-cache" : brand ? "public, max-age=86400" : "public, max-age=3600";
  let body = file;
  if (acceptEncoding.includes("gzip") && existsSync(file + ".gz")) {
    body = file + ".gz";
    headers["Content-Encoding"] = "gzip";
    headers["Vary"] = "Accept-Encoding";
  }
  headers["Content-Length"] = String(statSync(body).size);
  res.writeHead(200, headers);
  // link-preview bots (WhatsApp, iMessage, Slack...) check files with HEAD first
  res.end(head ? undefined : readFileSync(body));
  return true;
}

/** Race state for anyone to read: without the player id. */
function publicRace<T extends { player?: string }>(state: T): Omit<T, "player"> {
  const { player: _, ...rest } = state;
  return rest;
}

export async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", "http://localhost");
  const parts = url.pathname.split("/").filter(Boolean);
  try {
    if (req.method === "OPTIONS") return json(res, 204, null);
    if (parts[0] === "admin" && req.method === "GET") {
      // private play-test stats: HTTP Basic auth with ADMIN_PASSWORD; nothing links here
      if (!stats.isAdmin(req)) {
        res.writeHead(401, { "WWW-Authenticate": 'Basic realm="Pit Wall admin", charset="UTF-8"', "Content-Type": "text/plain" });
        return void res.end("Sign in required.");
      }
      const info = await eventInfo("");
      const timesheet = (info.leaderboard as { ai?: boolean; name: string; us: number }[]).filter((r) => !r.ai).map((r) => ({ name: r.name, us: r.us }));
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" });
      return void res.end(stats.adminPage({ timesheet }));
    }
    if (parts[0] !== "api") {
      if ((req.method === "GET" || req.method === "HEAD") && serveStatic(url.pathname, res, String(req.headers["accept-encoding"] ?? ""), req.method === "HEAD")) return;
      return json(res, 404, { error: "not found" });
    }
    const ip = clientIp(req);
    (req.method === "POST" ? limits.post : limits.get).take(ip);
    const [, resource, id, action] = parts;
    /** An owned player id needs its account's token (401 otherwise); a guest id needs none. */
    const authorize = (player: string) => accounts.requireOwner(req, player);

    if (req.method === "GET" && resource === "ranked" && !id) {
      // the ranked ladder and the daily medal board, standard car (guests too)
      const player = String(url.searchParams.get("player") ?? "");
      if (player) authorize(player);
      return json(res, 200, rankedInfo(player));
    }
    if (resource === "passes") {
      // race passes: staked daily/weekly time trials on equal cars, paid out on-chain
      const accountOf = (player: string) => {
        try {
          return accounts.me(player);
        } catch {
          return null;
        }
      };
      if (req.method === "GET" && !id) {
        const player = String(url.searchParams.get("player") ?? "");
        if (player) authorize(player);
        return json(res, 200, passes.passesInfo(player, player ? (accountOf(player)?.wallet ?? null) : null));
      }
      if (req.method === "POST" && id === "sprint") {
        if (!stats.isAdmin(req)) return json(res, 401, { error: "admin only" });
        const b = await body(req);
        return json(res, 201, passes.createSprint(Math.min(240, Math.max(2, Number(b.minutes ?? 15))), Math.min(1, Math.max(0.001, Number(b.stakeSol ?? 0.01)))));
      }
      if (req.method === "POST" && id && (action === "enter" || action === "confirm")) {
        const b = await body(req);
        const player = String(b.player ?? "");
        authorize(player);
        const acct = accountOf(player);
        if (!acct) return json(res, 400, { error: "Create an account and link a Solana wallet to buy race passes." });
        if (!acct.wallet) return json(res, 400, { error: "Link a Solana wallet to your account first (ACCOUNT > LINK SOLANA WALLET)." });
        try {
          if (action === "enter") return json(res, 200, await passes.enterTx(player, acct.wallet, Number(id)));
          const r = await passes.confirmEntry(player, acct.wallet, acct.name, Number(id), String(b.tx ?? ""));
          stats.record("pass_bought", player, String(id));
          return json(res, 200, r);
        } catch (err) {
          const e = err as Error & { status?: number };
          if (e.status) return json(res, e.status, { error: e.message });
          throw err;
        }
      }
    }
    if (req.method === "POST" && resource === "track" && !id) {
      const b = await body(req);
      const event = String(b.event ?? "");
      if (stats.CLIENT_EVENTS.has(event)) stats.record(event, typeof b.player === "string" ? b.player : undefined, b.data ? String(b.data) : undefined, String(req.headers["user-agent"] ?? ""));
      return json(res, 204, null);
    }
    if (resource === "accounts") {
      if (req.method === "POST" && id === "register" && !action) {
        limits.auth.take(ip);
        const created = await accounts.register(await body(req));
        stats.record("account_created", created.player);
        // every new account gets one free development pack (a claimed guest id too: once per account)
        let signupPack = null;
        try {
          const award = awardPack(created.player, "signup", "account");
          signupPack = award.awarded ? award.pack : null;
        } catch (err) {
          console.error("signup pack:", err);
        }
        return json(res, 201, { ...created, signupPack });
      }
      if (req.method === "POST" && id === "login" && !action) {
        limits.auth.take(ip);
        return json(res, 200, await accounts.login(await body(req)));
      }
      if (req.method === "GET" && id === "me" && !action) return json(res, 200, accounts.me(accounts.requireAuth(req)));
      if (req.method === "POST" && id === "wallet") {
        if (action === "challenge") return json(res, 200, accounts.walletChallenge(accounts.requireAuth(req)));
        if (action === "link") {
          const player = accounts.requireAuth(req);
          const linked = accounts.linkWallet(player, await body(req));
          stats.record("wallet_linked", player);
          return json(res, 200, linked);
        }
        if (action === "login-challenge") {
          limits.auth.take(ip);
          return json(res, 200, accounts.walletLoginChallenge(await body(req)));
        }
        if (action === "login") {
          limits.auth.take(ip);
          return json(res, 200, accounts.walletLogin(await body(req)));
        }
      }
      return json(res, 404, { error: "not found" });
    }

    if (req.method === "GET" && resource === "health") {
      return json(res, 200, { ok: true, programId: chain.programId.toBase58(), authority: chain.authority.publicKey.toBase58(), rpc: config.rpcUrl });
    }
    if (req.method === "GET" && resource === "circuits") {
      return json(res, 200, TRACKS.map((t) => ({ ...t, name: TRACK_NAMES[t.id] })));
    }
    if (req.method === "GET" && resource === "driver") {
      const d = await chain.fetchDriver(PLAYER_DRIVER.driverId);
      if (!d) return json(res, 404, { error: "driver not created yet" });
      return json(res, 200, {
        address: chain.pda.driver(PLAYER_DRIVER.driverId).toBase58(),
        name: chain.bytesToName(d.name),
        pace: d.pace,
        racecraft: d.racecraft,
        tyreManagement: d.tyreManagement,
        potential: d.potential,
        xp: d.xp,
        level: d.level,
        races: d.races,
        wins: d.wins,
        retired: d.retired,
      });
    }
    if (req.method === "GET" && resource === "event") {
      const player = String(url.searchParams.get("player") ?? "");
      authorize(player);
      return json(res, 200, await eventInfo(player));
    }
    if (req.method === "POST" && resource === "attempts" && !id) {
      const b = await body(req);
      const player = String(b.player ?? "");
      authorize(player);
      try {
        return json(res, 201, await startAttempt(player, String(b.name ?? ""), String(b.session ?? ""), b.setup as never));
      } catch (err) {
        const e = err as Error & { status?: number; setup?: unknown };
        if (e.status === 409) return json(res, 409, { error: e.message, setup: e.setup });
        throw err;
      }
    }
    if (req.method === "POST" && resource === "attempts" && id && action === "run") {
      const owner = attemptPlayer(id);
      if (owner) authorize(owner);
      const b = await body(req);
      const run = await submitRun(id, String(b.inputs ?? ""));
      if (run.best && owner) stats.record("lap_verified", owner, `${(run.best.us / 1e6).toFixed(3)} s, P${run.position}`);
      return json(res, 200, run);
    }
    if (req.method === "GET" && resource === "attempts" && id && action === "ghost") {
      return json(res, 200, ghost(id));
    }
    if (req.method === "GET" && resource === "garage" && !id) {
      const player = String(url.searchParams.get("player") ?? "");
      authorize(player);
      return json(res, 200, garage(player));
    }
    if (req.method === "POST" && resource === "garage" && id === "equip") {
      const b = await body(req);
      authorize(String(b.player ?? ""));
      return json(res, 200, equip(String(b.player ?? ""), String(b.partId ?? "")));
    }
    if (req.method === "POST" && resource === "garage" && id === "scrap") {
      const b = await body(req);
      authorize(String(b.player ?? ""));
      const scrapped = scrapPart(String(b.player ?? ""), String(b.partId ?? ""));
      stats.record("part_scrapped", String(b.player ?? ""), `+${scrapped.scrapped.credits} credits`);
      return json(res, 200, scrapped);
    }
    if (req.method === "POST" && resource === "garage" && id === "livery") {
      const b = await body(req);
      authorize(String(b.player ?? ""));
      return json(res, 200, setLivery(String(b.player ?? ""), b.primary, b.secondary));
    }
    if (req.method === "POST" && resource === "packs" && id === "open") {
      const b = await body(req);
      authorize(String(b.player ?? ""));
      const opened = openPack(String(b.player ?? ""), b.packId ? String(b.packId) : undefined);
      stats.record("pack_opened", String(b.player ?? ""));
      return json(res, 200, opened);
    }
    if (req.method === "GET" && resource === "parts" && id === "catalog") {
      return json(res, 200, catalog);
    }
    if (req.method === "POST" && resource === "drivenraces" && !id) {
      const b = await body(req);
      const player = String(b.player ?? "");
      authorize(player);
      takeChainRace(ip);
      return json(res, 201, await startDrivenRace(player, { compound: b.compound, name: b.name }));
    }
    if (req.method === "POST" && resource === "drivenraces" && id && action === "finish") {
      const race = getDrivenRace(Number(id));
      if (race) authorize(race.player);
      const b = await body(req);
      const result = await finishDrivenRace(Number(id), b.inputs);
      if (race && (result as { verified?: boolean }).verified) {
        const order = ((result as { order?: number[] }).order ?? []) as number[];
        stats.record("race_finished", race.player, `P${order.indexOf(0) + 1}`);
      }
      return json(res, 200, result);
    }
    if (req.method === "GET" && resource === "drivenraces" && id) {
      if (action === "inputs") {
        const inputs = drivenInputs(Number(id));
        return inputs ? json(res, 200, { raceId: Number(id), inputs }) : json(res, 404, { error: "no verified inputs for that race" });
      }
      const state = getDrivenRace(Number(id));
      return state ? json(res, 200, publicRace(state)) : json(res, 404, { error: "unknown race" });
    }
    if (req.method === "POST" && resource === "races" && !id) {
      const b = await body(req);
      const player = typeof b.player === "string" ? b.player : undefined;
      if (player) authorize(player);
      const setup = validateSetup(b as never);
      // the strategy race is created on Solana too: same budget as driven races
      takeChainRace(ip);
      const state = await startRace(String(b.trackId ?? TRACKS[0].id), setup, player);
      return json(res, 201, publicRace(state));
    }
    if (req.method === "GET" && resource === "races" && id) {
      const raceId = Number(id);
      if (action === "verify") return json(res, 200, await verifyRace(raceId));
      const state = getRace(raceId);
      return state ? json(res, 200, publicRace(state)) : json(res, 404, { error: "unknown race" });
    }
    return json(res, 404, { error: "not found" });
  } catch (err) {
    // Errors with a status (PartsError, DrivenError, AccountError, RateLimitError) are expected refusals: send their status and details
    const e = err as Error & { status?: number; details?: Record<string, unknown>; close?: boolean };
    if (typeof e.status === "number") {
      const headers: Record<string, string> = {};
      if (e.status === 429 && e.details?.retryAfter) headers["Retry-After"] = String(e.details.retryAfter);
      // the rest of a huge body is not read: close the connection after answering
      if (e.close) headers.Connection = "close";
      return json(res, e.status, { error: e.message, ...e.details }, headers);
    }
    console.error(err);
    return json(res, 400, { error: String((err as Error).message ?? err) });
  }
}

export const server = createServer((req, res) => void handle(req, res));

if (import.meta.main) {
  if (process.env.FLY_APP_NAME && config.seedSecret === DEV_SEED_SECRET) {
    console.error("SEED_SECRET is not set: with the development default anyone could forge sign-in tokens and predict races. Set it with `fly secrets set SEED_SECRET=...`.");
    process.exit(1);
  }
  await bootstrap();
  server.listen(config.port, () => {
    console.log(`Pit Wall server on http://localhost:${config.port}  rpc=${config.rpcUrl}  program=${chain.programId.toBase58()}`);
  });
}
