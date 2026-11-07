// Request limits for the public server: in-memory token buckets per client IP
// (they start full again after a restart, which is fine for one small machine)
// and a daily budget for the races that spend the authority's SOL.

import type { IncomingMessage } from "node:http";
import { config } from "./config.ts";

const DAY_MS = 86_400_000;

/** Overridable in tests. */
export const clock = { now: () => Date.now() };

export class RateLimitError extends Error {
  status = 429;
  details: { retryAfter: number };
  constructor(message: string, retryAfterS: number) {
    super(message);
    this.details = { retryAfter: retryAfterS };
  }
}

/** Fly's proxy sets fly-client-ip; otherwise the first x-forwarded-for hop, then the socket's address. */
export function clientIp(req: IncomingMessage): string {
  const fly = req.headers["fly-client-ip"];
  if (typeof fly === "string" && fly.trim()) return fly.trim();
  const xff = req.headers["x-forwarded-for"];
  const first = (Array.isArray(xff) ? xff[0] : xff)?.split(",")[0]?.trim();
  return first || req.socket.remoteAddress || "unknown";
}

/** "40 s", "12 min", "3 h". */
export function waitText(seconds: number): string {
  if (seconds < 90) return `${seconds} s`;
  if (seconds < 90 * 60) return `${Math.ceil(seconds / 60)} min`;
  return `${Math.ceil(seconds / 3600)} h`;
}

/** `capacity` requests per `windowMs` for each key, refilled continuously; capacity 0 = no limit. */
export class Limiter {
  capacity: number;
  windowMs: number;
  message: string;
  #buckets = new Map<string, { tokens: number; at: number }>();
  constructor(capacity: number, windowMs: number, message: string) {
    this.capacity = capacity;
    this.windowMs = windowMs;
    this.message = message;
  }
  #level(b: { tokens: number; at: number }, now: number) {
    return Math.min(this.capacity, b.tokens + ((now - b.at) * this.capacity) / this.windowMs);
  }
  /** Seconds until `key` may make a request (0 = now). */
  wait(key: string): number {
    if (!(this.capacity > 0)) return 0;
    const b = this.#buckets.get(key);
    const level = b ? this.#level(b, clock.now()) : this.capacity;
    return level >= 1 ? 0 : Math.max(1, Math.ceil(((1 - level) * this.windowMs) / this.capacity / 1000));
  }
  /** Uses one request for `key`, or throws 429 with how long to wait. */
  take(key: string) {
    if (!(this.capacity > 0)) return;
    const now = clock.now();
    const wait = this.wait(key);
    if (wait > 0) throw new RateLimitError(`${this.message} Try again in ${waitText(wait)}.`, wait);
    const b = this.#buckets.get(key);
    this.#buckets.set(key, { tokens: (b ? this.#level(b, now) : this.capacity) - 1, at: now });
  }
  /** Forgets buckets that are full again, so memory follows recent clients only. */
  sweep() {
    const now = clock.now();
    for (const [k, b] of this.#buckets) if (this.#level(b, now) >= this.capacity) this.#buckets.delete(k);
  }
}

/** At most `limit` uses per UTC day for the whole server; 0 = no limit. */
export class DailyCap {
  limit: number;
  message: string;
  #day = -1;
  #used = 0;
  constructor(limit: number, message: string) {
    this.limit = limit;
    this.message = message;
  }
  #roll() {
    const day = Math.floor(clock.now() / DAY_MS);
    if (day !== this.#day) {
      this.#day = day;
      this.#used = 0;
    }
  }
  get used() {
    this.#roll();
    return this.#used;
  }
  /** Throws 429 (with the seconds until 00:00 UTC) when today's budget is used up. */
  check() {
    if (!(this.limit > 0)) return;
    this.#roll();
    if (this.#used < this.limit) return;
    const wait = Math.max(1, Math.ceil(((this.#day + 1) * DAY_MS - clock.now()) / 1000));
    throw new RateLimitError(`${this.message} It resets at 00:00 UTC, in ${waitText(wait)}.`, wait);
  }
  take() {
    this.check();
    this.#used++;
  }
}

export const limits = {
  post: new Limiter(config.postsPerMinute, 60_000, "Too many requests."),
  get: new Limiter(config.getsPerMinute, 60_000, "Too many requests."),
  auth: new Limiter(config.authPerMinute, 60_000, "Too many sign-in attempts."),
  chainRaceIp: new Limiter(config.chainRacesPerIpHour, 3_600_000, `Race limit reached: ${config.chainRacesPerIpHour} races an hour per connection.`),
  chainRaceDay: new DailyCap(config.chainRacesPerDay, `The server's race budget for today is used up (${config.chainRacesPerDay} races).`),
};

/** For a request that creates a race on Solana: the client's hourly races, then the server's daily budget. */
export function takeChainRace(ip: string) {
  limits.chainRaceDay.check();
  limits.chainRaceIp.take(ip);
  limits.chainRaceDay.take();
}

setInterval(() => {
  for (const l of [limits.post, limits.get, limits.auth, limits.chainRaceIp]) l.sweep();
}, 5 * 60_000).unref();
