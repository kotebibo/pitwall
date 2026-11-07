# Architecture

## Shape

```
 Godot client (web)          Pit Wall server (TypeScript)          Solana (M3+)
┌──────────────────┐  HTTPS  ┌───────────────────────────┐        ┌──────────────────┐
│ screens, replay  │ ──────► │ API → runs packages/sim   │ ─────► │ commit-reveal    │
│ viewer, UI       │ ◄────── │ stores races + replays    │ Ledger │ program, driver  │
│ (no game logic)  │  JSON   │ accounts, schedule        │ iface  │ NFTs             │
└──────────────────┘         └───────────────────────────┘        └──────────────────┘
                                         ▲
                       verifier (web + CLI) re-runs any race with packages/sim
```

## Repository layout

```
pitwall/
├── game/              Godot 4.7 project: typed GDScript, web-first
├── packages/sim/      deterministic race sim, the single source of truth for results
├── art/               Aseprite sources, exported into game/assets/
├── docs/              PLAN, ARCHITECTURE, PARKING_LOT
├── tools/             build and export scripts
├── server/            (M0) TypeScript API
├── packages/content/  (M1) tracks, parts and driver archetypes as JSON
└── programs/          (M3) Anchor program for seed commit-reveal
```

Folders are created when their milestone starts, not before.

## Foundational decisions

These are the choices made at the start so that the start does not limit the end. Change one only with a written reason added here.

| Decision | Why it keeps doors open |
|---|---|
| **The sim is a versioned pure function**: `simulate(simVersion, track, setups, seed) → result`. Integer and fixed-point maths only, seeded PRNG, no clocks. | Balance can change forever while every old race still verifies with the version it ran on. The same code runs on the server, in the verifier and, if ever needed, ported to Rust for on-chain use. |
| **The server is authoritative; Godot only presents.** The client sends setups and plays replays. It never computes outcomes. | No second implementation to keep bit-identical. Cheating is impossible client-side. A web dashboard or mobile client can be added against the same API. |
| **All client↔server traffic goes through the `Api` autoload.** | Switching between a local stub, staging and production touches one file. |
| **Replays are event logs produced by the sim** (lap times, pit in/out, overtakes, incidents), not video or positions. | The same file powers the replay viewer, the verifier, spectating, highlight clips and shareable race links later. |
| **Content is data**: tracks, car designs, parts and driver archetypes live in JSON read by both the sim and Godot. | New tracks or parts need no code. Balance changes are data diffs that are easy to review. |
| **Chain access sits behind a `Ledger` interface** with a database stub and a Solana implementation. | The game is fully playable before any chain work. Custody model, NFT standard or even chain can change in one place. |
| **Accounts are not wallets.** Email login first, embedded wallet created silently, external wallets linked later. | No wallet pop-up for new players; crypto-native features layer on top later. |
| **Web export without threads** (`variant/thread_support=false`). | The build runs on any static host (itch.io, Vercel, GitHub Pages) without special server headers. |
| **Compatibility renderer.** | Required for web; runs on low-end laptops and phones. |
| **640×360 base resolution, `canvas_items` stretch with integer scaling, nearest filtering for sprites.** | Crisp pixel art and crisp text at any window size (text renders at screen resolution); one UI scale to design for. Containers and one Theme resource make a later reskin or mobile layout a theming job, not a rewrite. |
| **Typed GDScript** (untyped declarations warn). | Type errors are caught in the editor, closest to what the team knows from TypeScript. |
| **Feature flags on the server.** | Ship features dark and enable them per beta group. |

## Replay format v1 (draft)

```json
{
  "replayVersion": 1,
  "simVersion": "0.1.0",
  "raceId": "r-2026-11-07-street-01",
  "track": { "id": "street-01", "type": "street", "laps": 24 },
  "seed": "9f4c2a7e1b83d605",
  "commitment": "33940731…fc25b1ba",
  "teams": [{ "id": "t-tbilisi", "name": "Tbilisi Racing", "setup": { "design": "high_downforce", "tyre": "soft", "stops": 1, "risk": 55 } }],
  "laps": [[89624, 179812]],
  "events": [{ "atMs": 1021540, "type": "pit_in", "team": "t-tbilisi" }],
  "result": { "order": ["t-tbilisi"], "hash": "63a08671…37b3c36b" }
}
```

`laps` holds each team's cumulative lap times in milliseconds, in the same order as `teams`. The replay viewer interpolates positions from these, exactly as the pitch video's race scene does.

## Decisions deliberately postponed

Decide these at the milestone that needs them, with what you know then.

| Decision | When | Current default |
|---|---|---|
| Embedded wallet provider | M3 | none chosen |
| Database | M2 | Postgres |
| Server hosting | M2 | any Node host |
| NFT standard | M3 | Metaplex Core |
| Mainnet, prizes, fees | after M4 | none |
