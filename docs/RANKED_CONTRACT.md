# Ranked: the API both halves build to (server: feat/ranked-server, game: feat/compete-ui)

## Rules
- **The car:** everyone drives the standard car (`zeroSpec()`), with their own tuning (setup).
- **The ladder:**
  - Tiers in order: IRON, BRONZE, SILVER, GOLD, PLATINUM, EMERALD, DIAMOND. Each has divisions IV, III, II and I, and each division is 100 RP.
  - Ladder points (internal): `ladder = tierIndex * 400 + (3 - divisionIndex) * 100 + rp`, where divisionIndex 0 = IV and 3 = I.
  - MASTER from ladder 2800 (rp keeps counting).
  - Among MASTER+ players by ladder: the top 3 are CHALLENGER and the next 7 GRANDMASTER.
- **Hidden rating (MMR):** Elo-style, starting at 1200.
- **Placements:** the first 5 ranked races (no visible rank: tier "UNRANKED", `placementsLeft` > 0, K = 64). After the 5th, ladder = clamp((mmr - 800) * 1.75, 0, 3200).
- **A ranked race:**
  - It starts when the player starts a ranked attempt (`POST /api/attempts {session: "ranked"}`). The server then picks 5 opponents with the MMR nearest the player's.
  - Opponents are human players with a ranked lap in the last 7 days (their best lap and their MMR), plus AI benchmark drivers filling in. There are 10 AI drivers, one per MMR step from 700 to 2500, each with a lap time: `us(mmr) = 72_000_000 - (mmr - 700) * 4278`, i.e. 1:12.0 at 700 and about 1:04.3 at 2500, with ±150 ms deterministic daily jitter.
- **The result:**
  - It is the FIRST completed lap of the attempt.
  - A deleted (invalid) lap, or no lap at all, is a forfeit: it loses to every opponent.
  - An unresolved race is resolved as a forfeit when the player starts the next ranked attempt, or after 30 minutes.
- **Scoring:**
  - The score against each opponent is 1 if your lap is faster, otherwise 0.
  - `expected_i = 1 / (1 + 10^((opp.mmr - mmr) / 400))`.
  - `mmr += K * sum(score_i - expected_i) / 5`, with K = 32 after placements.
  - `rpChange = round(40 * sum(score_i - expected_i) / 5 + clamp((mmr - ladderMmr) / 40, -8, 8))`, where `ladderMmr = 800 + ladder / 1.75`. Typical changes are ±10 to 30.
  - rp ≥ 100 promotes (the rest carries over), rp < 0 demotes (to 75 of the division below). Iron IV never drops below 0.
- **Daily medal layer:**
  - The day's best ranked lap: GOLD ≤ 1:05.000, SILVER ≤ 1:06.500, BRONZE ≤ 1:08.500 (`MEDALS` in ranked.ts).
  - Each medal tier earns its own pack once per UTC day, through `awardPack(player, "ranked_bronze" | "ranked_silver" | "ranked_gold", dayKey)`. Reaching gold also awards silver and bronze if they are not yet earned that day.
  - Pack odds per earn reason live in `game/data/parts.json` `packs.earn[reason].odds` as `{common, rare, epic, legendary}`:
    - bronze uses the default odds (70/22/7/1);
    - silver is 52/32/13/3;
    - gold is 35/37/21/7.
  - The weekly pack cap and the unopened cap still apply. A pack view gets `"medal": "bronze" | "silver" | "gold"`.
- **Season:** `season: {id: 1, name: "SEASON 1", endsAt}`. No reset logic yet.

## API
`POST /api/attempts {player, name, session: "ranked", setup}` returns the usual attempt fields plus:
```
rankedMatch: { opponents: [{ name, tier, division, us, ai }] }   // 5 entries, sorted fastest first
```

`POST /api/attempts/:id/run` for a ranked attempt returns the usual fields plus:
```
ranked: {
  counted: true, forfeit: false, us: 64830000,            // the first completed lap (null on forfeit)
  opponents: [{ name, us, beat: true, ai }],
  wins: 3, of: 5, rpChange: 18,
  rank: { tier: "GOLD", division: "II", rp: 42, ladder: 1342, placementsLeft: 0 },
  promoted: false, demoted: false, placed: false,           // placed = this race ended placements
  medal: "silver",                                          // the day's best medal (null if none)
  packsEarned: [ packView... ],
  daily: { rank: 3, of: 41 }
}
```
Calling run again for the same attempt returns the stored result; it is resolved only once.

`GET /api/ranked?player=` (guests too):
```
{
  season: { id, name, endsAt },
  you: { tier, division, rp, ladder, placementsLeft, wins, losses, races,
         recent: [{ at, rpChange, wins, of, us, forfeit }] } | null,   // last 5
  ladder: [{ rank, name, tier, division, rp, you }],                     // top 20, ranked players only
  daily: { closesAt, medals: { gold, silver, bronze },
           leaderboard: [{ rank, name, us, medal, you }], you: { rank, us, medal } | null },
  tiers: ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]
}
```
Tier colours (game): IRON #6e6f78, BRONZE #c98a5a, SILVER #c6c8d0, GOLD #f2c230, PLATINUM #5ec8b0, EMERALD #3ecf6a, DIAMOND #5ec8e5, MASTER #a855f7, GRANDMASTER #e8352b, CHALLENGER #f1efea.
