# Pit Wall development plan

**Pit Wall is an F1 team game where you also drive.** You own a racing team, build and set up the car for each track, drive it yourself, and win on skill and strategy, not spend. The full design is in [DESIGN.md](DESIGN.md). Solana makes every race verifiable and the drivers you develop yours.

This plan exists to stop scope creep. If something is not in the current milestone's **Must** list, it goes to [PARKING_LOT.md](PARKING_LOT.md).

## Pillars

Every feature must serve at least one of these. If it serves none, it does not get built.

1. **Skill and strategy beat spend.** Your driving decides most of the lap time; setup, parts, tyres and pit strategy decide the rest. Never paying.
2. **Every result is verifiable.** Deterministic fixed-point physics and sim, seed committed on-chain, every lap re-driven from its inputs, anyone can re-run it.
3. **Drivers have a life cycle.** They level up only by racing, peak, decline and retire. Developed drivers can be traded.

## Non-goals for v1

- 3D. The game is top-down 2D.
- Live wheel-to-wheel multiplayer netcode. Players race ghosts and AI built from other teams, asynchronously.
- Any token, staking or yield.
- Paid randomness. Random packs are earned by racing, never bought.
- Real F1 names, teams, logos or circuits. Everything is fictional (licensing).
- Native mobile apps. The web build runs in mobile browsers later.
- Chat, guilds, social feeds, livery editor.

## Milestones

A milestone ends when its **exit criteria pass**, not when the calendar says so. Do not start the next one before that. Estimates assume two people part-time and are there to spot overruns, not as deadlines.

### M0 · Foundation (about 1 week)

Goal: every part of the pipeline works end to end with nothing interesting in it yet.

- [x] Monorepo with `game/`, `packages/sim/`, `art/`, `docs/`
- [x] Godot 4.7 project boots, typed GDScript, Compatibility renderer, web export preset
- [x] Web export works (`tools\build-web.cmd`, verified running in a browser)
- [ ] Web build hosted at a fixed URL (itch.io or a static host), rebuilt every week
- [x] Sim rewritten in TypeScript, with golden-file determinism tests (7 tests)
- [x] `server/`: TypeScript API that runs races on-chain, simulates them and serves replays; also serves the web build
- [x] Art pipeline: an `.aseprite` file in `art/` exports to `game/assets/` with one script (`tools\export-art.cmd`)
- [ ] CI runs the sim tests on every push

**Exit:** opening the URL in a browser shows the game fetching a replay from the server and printing the finishing order.

### M1 · The fun core, offline (about 2 to 3 weeks)

Goal: find out whether the daily strategy loop is fun. Nothing else matters until this is answered.

- [ ] Race-day screen: car design (3 options), tyres (3), stops (1 or 2), risk slider, lock button
- [ ] 5 AI rival teams with their own setups
- [ ] Server runs the race with the sim; the client never computes results
- [ ] Replay viewer: top-down track, 6 cars, pit stops, overtakes, timing tower, skip to pit window and final lap
- [ ] Results screen that explains why you finished where you did (the 2 or 3 deciding factors)
- [ ] 3 track types: street, speed, mixed
- [ ] Debug "next day" button to play a week in 20 minutes

Not in M1: accounts, persistence beyond a local save, progression, anything on-chain.

**Exit:** 5 playtesters each play 7 in-game days. At least 3 want to keep playing, and every tester can explain why they won or lost. If this fails, iterate on M1. Do not move on.

### M2 · Progression and economy (about 2 to 3 weeks)

Goal: a reason to come back tomorrow and a driver economy that does not inflate.

- [ ] Accounts with email login (no wallet needed)
- [ ] Persistent team; free starter team that cannot be traded (stops bot farming)
- [ ] Driver levels from racing only, with a daily XP cap
- [ ] Rarity tiers that raise the ceiling, not the floor
- [ ] Ageing and retirement
- [ ] Real daily schedule: setups lock at a fixed time, race runs, results next morning
- [ ] Balance harness: run 1,000 headless seasons and print a report

**Exit:** the balance report shows no single strategy winning more than 40% of races across track types; a levelled common catches a fresh rare at roughly 40% of the rare's levels; driver supply stays flat over 20 simulated seasons.

### M3 · On-chain (about 2 to 3 weeks)

Goal: make fairness and ownership real without players noticing the chain.

- [ ] Anchor program on devnet: commit the seed hash before setups lock, reveal it after the race
- [ ] Drivers as NFTs held in embedded wallets created at sign-up (no wallet pop-ups)
- [ ] Public verifier, a web page and a CLI, that re-runs any race from on-chain data
- [ ] `Ledger` interface with two implementations: database stub and Solana

**Exit:** someone outside the team verifies a race with one command, and the game still runs with the Ledger switched to the stub.

### M4 · Closed beta (about 3 weeks)

Goal: real players, real retention numbers.

- [ ] 30 to 100 F1 management fans invited
- [ ] Analytics: day-1 and day-7 return rate, races entered, variety of setups chosen
- [ ] In-game bug report button
- [ ] Devnet marketplace (list and buy drivers with test USDC), only if M2's balance targets still hold

**Exit:** day-7 daily check-in rate of 30% or more.

### After M4

Decide with beta data, not before: mainnet, USDC prizes, marketplace fees, tournaments, engineers, R&D, mobile layouts.

### If you enter a hackathon

The demo slice is **M0 + M1 + the commit-reveal and verifier parts of M3**. That shows a fun loop and verifiable races, which is the whole pitch.

## Hackathon build status (MLH Solana Hackathon, Nov 6 to 8)

- [x] Anchor program on devnet (`FRMukL3ubSZcGHxAFjK1ywSqfY3bWod2ro1ySoULwH4r`): Race, Entry and Driver accounts; lock and reveal enforced on-chain; 4 LiteSVM tests
- [x] Server runs full races on devnet: commit, enter, reveal, simulate, post result, settle XP
- [x] Godot web client: race day, lock countdown, replay viewer, results with in-game verification
- [x] Verifier: in-game button and `node server/src/verify-cli.ts <raceId>`
- [x] Design pivot: players drive (see [DESIGN.md](DESIGN.md)); the strategy sim stays as the AI field

Driving slice, qualifying first on the full session engine:

- [ ] Fixed-point car physics at 120 ticks per second, one circuit with walls, keyboard and gamepad
- [ ] Session engine (practice, qualifying, race as settings); qualifying with setup lock
- [ ] Setup levers, 4 driver stats, battery energy and boost
- [ ] Input log recording; server re-drives the lap in headless Godot
- [ ] On-chain lap submission (program upgrade), leaderboard, ghost of the best lap
- [ ] Qualifying time sets the grid for the strategy race
- [ ] Deploy server + web build to Fly.io
- [ ] Demo video, README, submission (by Sun 21:00 Tbilisi)

## Scope rules

1. **New idea → parking lot.** Write one line in [PARKING_LOT.md](PARKING_LOT.md). It never enters the current milestone.
2. **The parking lot is reviewed only at a milestone boundary,** and only items that serve a pillar can move into the next milestone.
3. **Twice the estimate means cut.** If a task runs past 2× its estimate, simplify it or drop it.
4. **Vertical slices.** Each feature works end to end (sim or server → API → Godot screen) before the next one starts. No half-built systems lying around.
5. **Fun before chain.** No Solana code until M1's playtest passes.
6. **Placeholder art until M2's exit.** Polish only screens that survived playtests.
7. **A playable web build every week,** at the same URL.

## Weekly rhythm

- **Monday:** pick this week's items from the milestone's Must list. Nothing else.
- **Friday:** export the web build, play it for 10 minutes, tick the boxes above, write new ideas into the parking lot.
