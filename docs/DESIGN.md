# Pit Wall game design

**You run an F1 team and you drive the car.** The car sets the ceiling, your driver widens the margins, your hands find the limit. Research behind this design (sources in the speaker notes): `pitwall-driving-design.html` presentation, 7 November 2026.

## Decisions made (7 Nov 2026)

| Topic | Decision |
|---|---|
| Driving | Players drive. The deterministic strategy sim stays as the AI that drives rival cars and your second driver. |
| Ranked | Yes: a ranked mode with equal cars, pure skill. |
| Trading | Drivers **and** parts are tradeable. |
| Parts | A large pool of unique parts. No standard parts, no two cars identical. |
| Weekly Grand Prix | Car-rating classes, so bought parts move you up a class instead of dominating one. |
| Controls | Keyboard and gamepad from the start. |
| Hackathon | Qualifying is built first on the full session engine, so nothing becomes dead code. |

## Calibration

Maximum lap-time swing of each factor, best case vs worst case:

| Factor | Swing | Why |
|---|---|---|
| Your skill | 5%+ | Decides who wins between players |
| Car parts | up to 2% | Close to real F1's car spread (1.1% in 2025) |
| Setup | up to 1% | Rewards reading the track and the car |
| Driver stats | up to 0.6% | Real teammate gaps are 0.05 to 0.4 s |

Among top players, who all drive near the limit, car, setup and driver decide, as in real F1 (86 to 88% car, 12 to 14% driver in published studies).

## Sessions

Practice, qualifying and race are one engine with different settings:

| Session | Cars on track | Laps | Rules |
|---|---|---|---|
| Practice | You | unlimited | Setup changes allowed, engineer feedback |
| Qualifying | You (+ ghosts) | 1 flying lap per attempt | Setup locks at the first attempt (parc fermé) |
| Race | You + AI field | 8 to 12 | Pit stops, tyres, energy, weather |

## Driving model

- Top-down 2D, own physics in **whole-number (fixed-point) maths** at 120 ticks per second, with a sine lookup table. Godot's built-in physics is not used for the car (not deterministic).
- Bicycle model: tyre grip rises with slide angle to a peak, then falls off. Downforce and drag grow with speed squared. Weight shifts under braking and acceleration.
- **2026 controls:**
  - Straight Mode opens the wings inside marked zones.
  - Boost spends battery energy (350 kW electric).
  - Harvesting refills it under braking and lift-off.
  - Overtake Mode gives +0.5 MJ when within 1 s of a car ahead.
- **Inputs:** steering, throttle, brake, boost, plus a gear-free automatic gearbox. Keyboard gives digital inputs smoothed over a few ticks; gamepad gives analog steering, throttle and brake.

## Driver attributes

Stats widen margins and change wear and energy. They never steer for you and add no random noise.

| Attribute | Effect when you drive | When the AI drives |
|---|---|---|
| Braking | Brake force before front lock-up (+0 to 6%) | Later braking points |
| Cornering | Grip kept past the tyre's peak | Corner speed |
| Traction | Throttle before rear wheelspin | Exit speed |
| Energy | Harvest efficiency per lap | Energy use |
| Starts | Width of the launch window | Start reaction |
| Tyre care | Wear and heat from sliding | Stint length |
| Consistency | Margins hold through a full race | Lap-time spread |
| Racecraft | Less grip lost in dirty air | Overtaking and defending |
| Wet skill | Grip in rain | Wet pace |
| Feedback | Precision of engineer advice in practice | n/a |

Drivers level up by racing, peak, decline and retire (on-chain, already built).

## Setup (free, per weekend)

| Lever | More gives | Costs |
|---|---|---|
| Front wing | Turn-in | Rear tyre wear |
| Rear wing | Corner grip | Top speed, battery |
| Ride height (lower) | Downforce | Bottoming on bumps |
| Stiffness | Response | Kerb grip, tyre wear |
| Brake bias (front) | Stability | Turn-in, front lock-ups |
| Differential (locked) | Traction | Rotation |

Practice laps produce engineer feedback ("understeer in slow corners"); the acceptable setup window narrows each run. The Feedback stat sharpens the advice.

## Parts: unique, tradeable, never strictly better

Seven areas: floor, front wing, rear wing, sidepods, suspension, chassis, power unit.

1. **Every part is one of a kind.** A part is created from a **concept** (a real engineering choice, e.g. downwash or zero-pod sidepods, pull-rod or push-rod suspension, high-rake floor, spoon rear wing). Its stats are rolled within the concept's ranges and it gets one or two **traits**. No two parts match, so no two cars match. Each part's history (races, wins) is on-chain.
2. **Trade-offs, not tiers.** Each part spends a fixed stat budget across opposing axes: downforce vs drag, grip vs tyre wear, power vs reliability, weight vs stiffness. A low-drag wing is fast on a speed track and slow on a street circuit.
3. **Synergy.** Parts built on matching aero concepts work better together; mismatched front and rear aero unbalances the car.
4. **Track fit.** Each circuit weights stats differently (slow corners, fast corners, straights, bumps, heat). The best car changes each week, so a varied garage beats one maxed set.
5. **Wear.** Parts have limited mileage and lose condition, like real F1 component limits. This is the economy's sink.
6. **Seasons.** Regulations shift which stats matter each season, keeping the market alive.
7. **Development** follows F1's sliding scale: championship leaders get 70% R&D speed, the last team 115%, under a weekly spending cap.

## Competition

| Mode | Cars | What counts |
|---|---|---|
| Ranked Time Trial (daily) | Equal for everyone | Skill only; verified laps, ghosts, medals |
| Weekly Grand Prix | Your team, in **car-rating classes** | Skill, setup, parts, driver |
| Second driver | AI with the driver's stats | Team points |

The Weekly Grand Prix gives everyone the same seed (weather, safety cars) and the same AI field built from other players' teams, so results compare fairly without live netcode.

## Verification and anti-cheat

- **Recording:** inputs are recorded per tick and streamed every second, so a lap must be driven in real time.
- **Re-driving:** the server re-drives every lap in headless Godot with the same game files, so there is a single physics implementation.
- **On-chain:** only the lap time, a hash of the input log and a server signature go on Solana. A personal-best account costs about 0.0012 SOL.
- **Per-attempt seed:** changes the lights-out delay and tiny grip details, so a pre-recorded lap fails.
- **Live bots:** handled by statistical flags, review of the top 10 and a hold on payouts.

## Economy safeguards

- Ranked mode ignores owned items entirely.
- Rating classes cap what money can buy in the Weekly Grand Prix.
- Driver stats are capped at 0.6% of lap time.
- Parts wear out and seasons rotate the meta.
- Earlier web3 racers failed when owned stats decided races. Here they never do.
