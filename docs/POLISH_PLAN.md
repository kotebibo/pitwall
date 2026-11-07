# Polish plan: from working to good

The core loop works end to end, but it plays bare. This plan explains why, fixes the game first and the presentation second, and fits the MLH deadline (**Sunday 22:00 Tbilisi**). Everything not listed for the weekend goes to [PARKING_LOT.md](PARKING_LOT.md).

## Why it feels bare today

1. **The puzzle is solved in two races.** Car design is worth up to 30 s a race and the right answer never changes per track type. Once you know "downforce on street", every race plays the same.
2. **You decide nothing after the lock.** The fantasy is *the pit wall*: making calls while the race happens. Right now you set four sliders and watch.
3. **You decide with no information.** No forecast, no rival intel, no track data beyond one hint line. Strategy needs something to read.
4. **Races have no drama.** Cars never block each other, nothing unexpected happens, and position comes purely from lap times, so pit timing has no tactical meaning.
5. **Nothing carries over.** No season, no standings, no history. XP goes up, but there is no goal.
6. **It looks and sounds like a prototype.** Dots for cars, no sound, no transitions, no feedback when something good happens, and the "why" text is a rule of thumb, not analysis.

## The three gameplay additions that fix it

Each one was chosen because it adds real decisions *and* uses Solana for something only a chain can do.

### 1. Live pit-wall calls (the headline feature)

The race pauses at **two decision points** (around one third and two thirds distance). You get 15 seconds to make a call:

- **Box now / stay out / extend the stint**
- **Push / balanced / conserve tyres** for the next stint

Rivals make calls too. Each call is **posted on-chain before its deadline**, and the program **rejects late calls**. The seed is still revealed only at the end, and the verifier re-runs the race with setups, calls and seed, all from chain data.

This turns watching into playing. It also uses Solana's speed for real: a call has to be confirmed within seconds, which only works on a fast, cheap chain.

### 2. Track position matters (overtaking model)

A car can only pass if it is faster by more than the track's **overtaking difficulty**. Otherwise it is stuck behind and loses time in dirty air.

- Street circuits are hard to pass on, speed tracks easy.
- Pit timing becomes tactical: pitting a lap early to jump a car stuck ahead of you (the undercut) now works.
- The replay gets real battles: cars queue, defend and break free.

### 3. Seeded race events and a forecast

Before the lock you see a **forecast** ("30% chance of rain", "safety car likely at street circuits"). What actually happens comes from the seed, so nobody knows in advance, and anyone can verify it afterwards.

- **Rain:** pace drops for everyone and the wrong tyres hurt. A call at a decision point can save you.
- **Safety car:** the field bunches up and a pit stop costs half as much. This is the classic "box now?" moment.

### Supporting changes

- **Track cards:** corners vs straights, tyre wear, overtaking difficulty, shown as small bars. You read the track instead of memorising one answer.
- **Scouting:** each rival's last three setups and tendencies, so you can predict and counter.
- **AI setups committed before the seed exists:** closes the gap where the operator knows the seed while choosing the rivals' setups. This takes 30 minutes and protects the fairness story with judges.
- **Real "why":** the sim is fast and deterministic, so after each race the server re-runs it with your one changed choice ("low drag would have finished 12 s faster", "boxing on lap 8 lost you P2"). That gives real analysis instead of a rule of thumb.

## Presentation polish

| Area | What changes |
|---|---|
| **Cars and track** | Top-down pixel cars in each team's colours (Aseprite), track drawn with kerbs, grass, pit boxes and a start gantry |
| **Race replay** | Start lights sequence, close-up label on battles, overtake flash, pit crew animation, safety car and rain effects, commentary ticker |
| **Sound** | Engine note that follows speed, start beeps, pit gun, crowd at the flag, UI clicks; mute toggle |
| **Motion** | Screen transitions, counters that count up, XP bar that fills, level-up banner showing the on-chain transaction |
| **Hub screen** | Title and garage: your driver, season standings, next race, race history with a verify link for every race |
| **Season** | 5-race championship with points and a final standings screen |
| **Results** | Lap-by-lap position chart, gaps chart, the "what if" analysis above, XP gained, links to every transaction |
| **Onboarding** | First-race tooltips explaining each choice in one line, with its effect shown on hover |
| **Loading** | Custom branded loading screen instead of Godot's default (the web build is 40 MB) |
| **Errors** | Clear messages when the server or devnet is slow, with retry instead of a dead screen |

## Weekend schedule

Only what fits by Sunday 21:00 (one hour of buffer before the 22:00 deadline). Each block names its fallback if it overruns.

| When | Build | If it slips past 2× |
|---|---|---|
| Sat 18:00–19:00 | AI setups committed before the seed; track cards; sim gets overtaking model and track data (sim 1.1, new golden hash) | ship without track cards |
| Sat 19:00–21:00 | Seeded rain and safety car, forecast shown on race day | keep safety car only |
| Sat 21:00–02:00 | **Live pit-wall calls**: program instruction with on-chain deadlines (program upgrade on devnet), server runs the race in stints, decision UI in Godot, AI calls | calls are set before the lock instead of live (no program change) |
| Sun 02:00–09:00 | Sleep | |
| Sun 09:00–12:00 | Pixel cars and track art, replay effects, sound | dots stay, effects only |
| Sun 12:00–14:00 | Hub screen with race history and a 5-race season | history list only |
| Sun 14:00–16:00 | "What if" analysis and charts on results; branded loading screen; onboarding tooltips | analysis text only |
| Sun 16:00–18:00 | Fly.io deploy, playtest on 3 browsers and a phone, bug fixes | |
| Sun 18:00–21:00 | Demo video, README, submission | |

**Cut order if the whole weekend slips:** onboarding tooltips, charts, season, sound, art. **Never cut:** live calls (or their pre-lock fallback), the fairness fix, the deploy, the video.

## After the weekend

Polish continues milestone by milestone (see [PLAN.md](PLAN.md)). The biggest remaining items:

- **Real ownership:** players sign with their own wallet (or an embedded wallet they control); the server stops holding driver keys.
- **Garage depth:** several drivers, car parts and R&D, choosing who races.
- **Daily rhythm:** one race a day on a real schedule, with a daily XP cap.
- **Marketplace:** list and buy drivers with USDC once the economy is balanced.
- **Art direction pass:** a consistent pixel art style across every screen, plus music.
- **Mobile layout** of the web build.
