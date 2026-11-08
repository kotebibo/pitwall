# Pit Wall economy

**Free to play must cost the team almost nothing, and the game must pay for itself.** Three rules make that work. Parts stay in the game database until a player trades or withdraws one, and the player pays that mint. The chain gets one transaction per day and one per week, never one per player. The money comes from things that never change lap time: cosmetics, trackside sponsors and a small fee on trades.

**Assumptions** used for every figure below:

- **SOL price:** $100 (spot was about $90 on 7 November 2026). Every SOL figure scales linearly with the price.
- **Player activity:** a weekly player drives 24 verified runs a week (6 runs on 4 days).
- **Server load:** re-driving a run costs about 1 s of CPU in headless Godot. Measured: 0.45 s of physics for an 85 s lap, plus process start-up.
- **Peak load:** traffic at peak is 4 times the weekly average.

These figures are planning estimates, not quotes.

## 1. What it costs

### Solana mainnet prices

| Item | Cost | Who pays |
|---|---|---|
| Transaction fee | 5,000 lamports = 0.000005 SOL ($0.0005) | sender |
| Account rent (refunded when the account is closed) | 0.00089 SOL + 0.00000696 SOL per byte | creator |
| Qualifying best-lap account (`LapRecord`, 98 bytes) | 0.00157 SOL ($0.16) per player per daily event | server, today |
| Driver account (88 bytes) | 0.0015 SOL ($0.15) | server, today |
| Program deploy (259 KB `.so`) | 1.80 SOL ($180) once; 3.6 SOL if deployed with 2x room for upgrades; refunded if the program is closed | team |
| Compressed NFT tree, 16,384 parts (depth 14, buffer 64, canopy 8) | 0.34 SOL ($34) once, not refundable | team |
| Compressed NFT tree, 131,072 parts (depth 17, canopy 10) | 0.72 SOL ($72) once | team |
| Compressed NFT mint (Bubblegum v2) | about 0.000095 SOL ($0.01): fee + 0.00009 SOL Metaplex protocol fee | player |
| Metaplex Core NFT (no tree needed) | about 0.0029 SOL ($0.29), including the 0.0015 SOL protocol fee | player |
| Classic Token Metadata NFT | about 0.022 SOL ($2.20): mint, token account, metadata, edition and a 0.01 SOL protocol fee | not used |

**The current devnet design would not survive mainnet.** It opens a `LapRecord` account per player per day and sends a transaction for every personal best. At 10,000 weekly players (4 event days each) that locks 63 SOL ($6,300) of rent a week and costs $60 a week in fees. It has to be batched (section 2).

### Hosting

| Weekly players | 1,000 | 10,000 | 100,000 |
|---|---|---|---|
| Re-drive CPU | 7 CPU-hours/week (0.04 cores average, 0.2 at peak) | 67 (0.4 average, 1.6 at peak) | 667 (4 average, 16 at peak) |
| API traffic (input logs, ghosts) | 5 GB/month | 52 GB/month | 520 GB/month |
| Oracle Cloud Always Free (Arm, 2 OCPU, 12 GB, 10 TB egress) | $0 | $0 (peaks queue a few seconds) | too small |
| Fly.io | shared-cpu-1x 1 GB with auto-stop, volume, egress: about $4/month | performance-1x ($33) + a peak machine + egress: about $46/month | 2 always-on performance-2x ($66 each) + autoscaled peak machines + egress + paid RPC tier: about $350/month |

**Notes on hosting:**

- **Oracle:** halved its free Arm allowance in June 2026 and may reclaim an idle free VM (below 20% CPU, network and memory for 7 days). Upgrading the account to pay-as-you-go keeps the free allowance and reportedly avoids reclamation; it needs a card but charges nothing.
- **Godot on Arm:** Godot has official Linux arm64 builds. The physics is whole-number maths, so Arm and x86 re-drive identically.
- **Web build:** the game is 10 MB gzipped. Serve it from a free static host (itch.io, GitHub Pages or Cloudflare R2, which charges nothing for egress), never from the API machine. Cloudflare Pages will not work: it caps files at 25 MB and the `.wasm` is 39.5 MB.
- **Cheaper re-drives:** a persistent Godot worker would avoid the process start on every run. Not re-driving practice runs would also roughly halve the CPU.

### Cost per weekly player per week

| Weekly players | 1,000 | 10,000 | 100,000 |
|---|---|---|---|
| Hosting | $0 (Oracle) to $0.0009 (Fly) | $0 to $0.0011 | $0.0008 |
| Chain, batched (8 transactions a week, $0.04 total) | $0.00004 | $0.000004 | $0.0000004 |

**One-time mainnet launch:** the program deploy plus the first compressed NFT tree come to 2.14 SOL, about $214. That can wait: the game runs on devnet for free until the first sponsor deal or a small ecosystem grant pays for it.

## 2. Parts and results cost nothing on-chain

**Parts live in the database.** Each part, as stored, has:

- an id, its rolled stats and traits, and a serial within its week (for example `#0412`);
- `minted: "db"` until it goes on-chain;
- a sha256 of its fields (built).

**Weekly supply proof.** Every Monday the server posts one root on-chain: the Merkle root of every part created that week, plus the count (about $0.0005). Anyone can check that a part belongs to week N, and that week N stayed under its cap, without a single per-part account. The root is computed today (`supply.root` in the API). Posting it needs one new program instruction, or the SPL Memo program until then.

**Rolls are auditable.** A pack's id is the hash of (player, rule, event), so the server cannot re-roll a pack by picking a new id. Its contents come from `HMAC(season secret, pack id)`. The secret's hash goes on-chain at season start and the secret is revealed at season end, so anyone can recompute every pack. This is the same commit-reveal the races already use.

**Lazy minting.** A part touches the chain only when a player withdraws it to a wallet or sells it.

- **Withdraw.** The player pays the mint: about $0.01 as a compressed NFT, or $0.29 as a Core asset.
- **Sell a database part (mint on purchase).** The buyer's single transaction pays 95% to the seller and 5% to the treasury in USDC, and mints the part to the buyer. The server co-signs only transactions that include the fee, so the fee is enforced without holding anyone's money.
- **Resell a part already minted.** The program's escrow takes the same 5%. A 5% royalty is set on the collection, but external marketplaces honour it only sometimes.
- **What to launch with.** Core assets need no upfront tree and keep the team at $0. Switch to compressed NFTs once withdrawals pass a few hundred a month, paying for the tree from fees.

**Qualifying results.**

- **Mainnet plan:** keep personal bests off-chain during the event. At the close, post one Merkle root of every verified best lap (leaf = event, player key, lap time, input hash, physics version).
- **Top 10:** keep `LapRecord` accounts for the top 10 only, and close them after 7 days to recover the rent. That needs a `close_lap` instruction; the float is 0.11 SOL, recycled weekly.
- **Drivers:** the same lazy rule applies. Starter drivers stay in the database and become accounts only when traded.

## 3. Revenue

Ranked by fit with "skill beats spend". Monthly figures, conservative conversion:

| # | Stream | Why it fits | Assumption | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|---|---|
| 1 | Cosmetics: liveries, helmets, car numbers, engine sounds | No stats, ever. Sold directly, never random | 1% of players buy $4 a month | $40 | $400 | $4,000 |
| 2 | Sponsor boards on circuits, sold weekly to web3 projects | Real F1 does it; zero gameplay effect. The track already places a billboard every 90 m of straight | 40 boards seen per player-week, $1.50 CPM, 25% sold | $65 | $650 | $6,500 |
| 3 | Cosmetic season pass (8 weeks) | Paid track is cosmetic only: no packs, no parts | 1.5% buy $5 a season | $41 | $406 | $4,060 |
| 4 | 5% marketplace fee on part and driver trades | Parts trade, but ranked ignores them and classes cap them | 4% of players trade $5 a month | $10 | $100 | $1,000 |
| 5 | Paid-entry skill tournaments, equal cars (later) | Pure skill, but legally complex (section 5) | not counted | | | |
| | Card payment fees (8% of streams 1 and 3) | | | -$6 | -$65 | -$646 |
| | **Net revenue** | | | **$149** | **$1,491** | **$14,910** |
| | Running cost (Fly) | | | $4 | $46 | $350 |

**Break-even.**

- **Base case:** the Fly server breaks even at about 27 weekly players. On Oracle's free tier it is never in the red.
- **Pessimistic case** (a tenth of the conversion and no sponsors): revenue is $8, $84 and $841 a month, and break-even on Fly moves to about 480 weekly players.
- **Launch:** the one-time $214 is recovered in about 6 weeks at 1,000 weekly players.
- **Being honest:** paying one person $4,000 a month needs about 27,000 weekly players in the base case, and far more if conversion is low. At 1,000 players, "sponsors" really means one partner deal a month, not an ad market.

These rates are guesses until the closed beta measures them. The point of this design is that a bad guess cannot cost the team money.

**Never sold:** packs, parts, anything that gives packs, R&D credits or repairs, and any token.

## 4. Supply and demand

**Earning (built):**

- **Qualifying:** 1 pack for the first qualifying run of the day that completes a lap, and 1 pack for a top-3 qualifying time (once a day).
- **Racing:** 1 pack per race finish (a function for the race flow).
- **Limits:** 5 packs per player per week, 10 unopened at most.
- **Contents:** 3 parts per pack, never 3 from one area.
- **Rarity weights:** 70 / 22 / 7 / 1 for common, rare, epic and legendary.

**Weekly supply cap (built).** The number of parts that may enter the economy each week is:

```
supply = clamp(3 parts × players active last week, floor 300, hard cap 3,000)
```

It is frozen when the week starts and shown to players with its reset time. The hard cap is the monetary policy. Raise it only in announced steps. At steady state it should allow about one new part per weekly player per week, which fits the current 3,000 up to roughly 3,000 weekly players. When the cap is reached, packs keep until Monday.

**Sinks:**

- **Wear (built).** Each part has a mileage life: wings 1,500 km, floor 1,800, sidepods and suspension 2,000, power unit 2,500. That is about 8 to 13 weeks of an active player's driving. Starter parts never wear out.
  - **What counts:** the distance of every verified qualifying run (the re-drive reports it) and every finished race goes on the fitted parts. Practice is not verified, so it does not count.
  - **Fade:** over the last 30% of its life a part's stats fade linearly to 60% of full strength (rounded toward the faster side, so it is never worse than the standard part). The car spec the physics drives with includes it; the garage shows "WORN: n% effect".
  - **Retirement:** at its life a part is retired: unfitted (the starter part goes back on) and kept in the garage, greyed. It can only be scrapped.
- **Scrapping (built).** Scrapping a part that is not fitted gives R&D credits: 10, 25, 60 or 150 by rarity, kept on the player (`credits`).
- **Repairs.** Credits buy repairs that restore up to 30% of a part's life, at most twice.

Credits are earned only by racing and scrapping, never bought. The model below assumes 8% of circulating parts leave each week.

**Why the cap keeps value up.**

- **Fixed supply:** supply is fixed and public, while demand grows with players.
- **Equilibrium:** circulation settles at supply ÷ sink rate (3,000 ÷ 0.08 = 37,500 parts).
- **Scarcity:** every extra player makes each serial scarcer.
- **Different, not better:** no rarity is strictly better, so value comes from track fit, synergies and collecting, not from power.

**Eight weeks after launch** (300 closed-beta players before week 1, an average of 2.5 packs earned per player per week):

| Week | Weekly players | Packs earned | Supply (parts) | Packs opened | Earned per opened | Parts retired | In circulation | Per player |
|---|---|---|---|---|---|---|---|---|
| 1 | 500 | 1,250 | 900 | 300 | 4.2 | 0 | 900 | 1.8 |
| 2 | 900 | 2,250 | 1,500 | 500 | 4.5 | 72 | 2,328 | 2.6 |
| 3 | 1,400 | 3,500 | 2,700 | 900 | 3.9 | 186 | 4,842 | 3.5 |
| 4 | 2,000 | 5,000 | 3,000 | 1,000 | 5.0 | 387 | 7,455 | 3.7 |
| 5 | 2,600 | 6,500 | 3,000 | 1,000 | 6.5 | 596 | 9,859 | 3.8 |
| 6 | 3,200 | 8,000 | 3,000 | 1,000 | 8.0 | 789 | 12,070 | 3.8 |
| 7 | 3,700 | 9,250 | 3,000 | 1,000 | 9.3 | 966 | 14,104 | 3.8 |
| 8 | 4,200 | 10,500 | 3,000 | 1,000 | 10.5 | 1,128 | 15,976 | 3.8 |

**The table shows the open problem.** At scale, players earn 4 to 10 times more packs than the supply allows. Opening first-come-first-served (the hackathon rule) turns Monday into a race and fills every garage with unopened packs.

**The fix after the hackathon is pack points.** Each earn rule gives 10 points. A pack costs 10 points while supply is plentiful, and its price is set each Monday so that expected packs match the supply. In week 8 that is about 105 points: a pack every week or two for a player who drives every day. There is no backlog and no rush, and the cap holds exactly. It is a small change in `parts.ts`.

**Different, not better (enforced by tests).**

- **The budget:** every part spends the same lap-time budget: 50 points, where 1 point is 0.001% of lap time, plus at most 5% for rarity.
- **Measured weights:** the weights come from a lap model of `car_sim.gd` on Mtkvari. 1% grip is worth 0.46% of lap time, 1% downforce 0.15%, 1% traction 0.10%, 1% drag 0.05%, 1 kW 0.018% and 1% recovery 0.008%. 1 kg of weight costs 0.034%: 1 kg is 0.125% of the car's mass, about 0.9 kW on the straights plus 1.25 per mille of downforce in corners and under braking.
- **The 2% bound:** tests check that the best and worst possible cars differ by at most 2% on every track type (1.87% on speed tracks, 1.51% on street circuits, 0.86% on Mtkvari). They also check that no car can reach the physics clamps.

## 5. Risks

**Bots farming packs.**

- **Driving is required:** every lap is re-driven on the server, no run can be faster than the clock, and each attempt has its own seed.
- **Account limits:** 5 packs a week per account, and starter items are not tradeable.
- **The global cap:** it bounds the damage. Taking the whole 3,000-part supply needs about 200 accounts, each driving verified laps on 5 days a week.
- **Detection alone will not stop them.** The repository already contains an autopilot that drives clean laps. The real defence is economic. Recommended before mainnet:
  - parts tradeable only after an account is 14 days old with 50 verified laps;
  - a per-account weekly listing limit;
  - statistical flags on input logs (identical lines, inhuman smoothness);
  - a proof-of-personhood check, or a small refundable deposit, to withdraw or trade.

**Regulation.**

- **No paid randomness.** Packs are never sold, the season pass gives no packs, and tournaments will not award packs. Paid loot boxes are what Belgium bans and what other regulators target. Free earned packs with tradeable contents are lower risk, not zero risk.
- **No custody.** Trades settle peer to peer on-chain, so the team never holds player funds. Screen wallets at linking.
- **No token, staking or yield.**
- **Tournaments:** paid-entry skill tournaments are restricted in several US states and treated as gambling in some countries. They need geofencing, KYC on payouts and a lawyer first.
- **Sponsors:** vet every sponsor, label ads, and refuse gambling or token-sale promotions.

**Pay-to-win perception.**

- **Ranked:** ranked mode uses equal cars.
- **Classes:** car-rating classes in the Weekly Grand Prix stop bought parts from dominating a class.
- **Same budget:** every part has the same budget, the starter car stays competitive, and the 2% bound is tested and published.
- **The lesson:** earlier web3 racers failed when owned stats decided races. Publish the calibration so players can check it.

## Next steps

1. **Stay on devnet** until revenue or a grant covers the $214 launch.
2. **Program upgrade:** `post_root` (daily results, weekly supply), `close_lap`, lazy driver creation.
3. **Pack points** to replace first-come-first-served opening.
4. **Trade gates** (account age, verified laps, listing limits) before any marketplace.
5. **Cosmetics shop and the first sponsor board:** the two streams with no gameplay risk.
