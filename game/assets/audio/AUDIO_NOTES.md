# Pit Wall audio

All sounds are synthesised by `tools/audio/` (see the bottom of this file to rebuild).

## Engine and power unit (used by CarAudio)

| File | Length | Loop | For |
|---|---|---|---|
| `engine_low.wav` | 1.50 s | yes | On-throttle engine layer at 4000.00 rpm (firing 200.0 Hz). Pitch = rpm / 4000.00. |
| `engine_mid.wav` | 1.50 s | yes | On-throttle engine layer at 7495.75 rpm (firing 374.8 Hz). Pitch = rpm / 7495.75. |
| `engine_high.wav` | 1.51 s | yes | On-throttle engine layer at 11002.08 rpm (firing 550.1 Hz). Pitch = rpm / 11002.08. |
| `engine_off.wav` | 2.00 s | yes | Overrun / lift-off burble with crackles and pops at 7993.96 rpm. Pitch = rpm / 7993.96. |
| `engine_idle.wav` | 3.00 s | yes | Idling V6 at 4000.00 rpm: lumpy, slightly hunting idle with valvetrain ticks. Pitch = rpm / 4000.00. |
| `pit_limiter.wav` | 2.00 s | yes | Pit limiter: engine at 9000 rpm bouncing off the speed limiter, ignition cut 4 times a second with pops. Pitch 1 at pit speed (or rpm / 9000). |
| `turbo_whine.wav` | 1.00 s | yes | Turbo whistle (3150 Hz) with wobble; pitch follows turbo speed. |
| `electric_whine.wav` | 1.00 s | yes | MGU-K / Boost electric whine (520 Hz fundamental); pitch follows speed. |
| `shift_up.wav` | 0.09 s | no | Upshift: ignition-cut bap + dog-ring click (85 ms). |
| `shift_down.wav` | 0.30 s | no | Downshift: throttle blip (rev match) and exhaust pops (300 ms). |

## Tyres, surfaces, air, contact (used by CarAudio)

| File | Length | Loop | For |
|---|---|---|---|
| `tyre_squeal.wav` | 2.00 s | yes | Tyres at the limit: wavering tonal screech (1.2/1.8/2.6 kHz) over hiss. |
| `lockup.wav` | 1.50 s | yes | Locked front tyre: harsh low scrub and juddering howl. |
| `kerb.wav` | 1.00 s | yes | Kerb rumble: 30 strip hits per second with chassis rattle (pitch with speed). |
| `gravel.wav` | 1.50 s | yes | Gravel trap: dense crunchy stone grains, floor hits and rumble. |
| `grass.wav` | 2.00 s | yes | Grass: soft rumble, bumps and swish. |
| `wind.wav` | 3.00 s | yes | Air rushing past the cockpit with buffeting (volume rises with speed^2). |
| `scrape.wav` | 1.50 s | yes | Bodywork grinding along a wall: metallic/carbon scrape with chips. |
| `impact_1.wav` | 0.45 s | no | Wall impact, light tap: thud + carbon crunch + debris. |
| `impact_2.wav` | 0.88 s | no | Wall impact, solid hit: thud + carbon crunch + debris. |
| `impact_3.wav` | 1.70 s | no | Wall impact, heavy crash: thud + carbon crunch + debris. |

## Car systems and start

| File | Length | Loop | For |
|---|---|---|---|
| `boost_on.wav` | 0.75 s | no | Boost engaged: whoosh + rising electric surge (0.75 s). |
| `straight_mode.wav` | 0.49 s | no | Straight Mode wings open: actuator clack-clack + drag falling away. |
| `battery_empty.wav` | 0.38 s | no | Battery depleted: descending electric blip. |
| `lights_beep.wav` | 0.16 s | no | Start light on / countdown tick (C6 beep). |
| `lights_go.wav` | 0.60 s | no | Lights out, GO: bright two-tone chord. |

## UI (Sfx plays hover/click/toggle/slider automatically)

| File | Length | Loop | For |
|---|---|---|---|
| `ui_hover.wav` | 0.03 s | no | Button hover: tiny soft tick. |
| `ui_click.wav` | 0.06 s | no | Button press: snappy click. |
| `ui_confirm.wav` | 0.32 s | no | Confirm / accept: rising two-note blip. |
| `ui_back.wav` | 0.26 s | no | Back / cancel: falling two-note blip. |
| `ui_error.wav` | 0.25 s | no | Error / not allowed: low buzzy double blip. |
| `ui_toggle.wav` | 0.07 s | no | Toggle switch: two-stage click. |
| `ui_slider.wav` | 0.01 s | no | Slider detent tick (very short). |
| `ui_dial.wav` | 0.03 s | no | Rotary dial click. |
| `equip.wav` | 0.55 s | no | Part fitted to the car: clunk + ratchet + lock. |
| `unequip.wav` | 0.45 s | no | Part removed: ratchet release + lighter clank. |

## Lap feedback

| File | Length | Loop | For |
|---|---|---|---|
| `sector_green.wav` | 0.50 s | no | Sector improved: tiny ding. |
| `lap_pb.wav` | 1.40 s | no | Personal best lap: bright rising three-note chime. |
| `lap_purple.wav` | 2.40 s | no | Fastest overall (purple): fanfare arpeggio into a shimmering major chord. |
| `lap_deleted.wav` | 0.57 s | no | Lap deleted / track limits: low negative buzz. |
| `verified.wav` | 1.30 s | no | Lap verified on Solana: crisp stamp + digital sparkle. |

## Pack opening

| File | Length | Loop | For |
|---|---|---|---|
| `pack_shake.wav` | 0.77 s | no | Pack shake: foil rustle and cards rattling. |
| `pack_open.wav` | 1.40 s | no | Pack open: foil tear, burst and sparkle. |
| `card_flip.wav` | 0.13 s | no | Card flip: swish + snap. |
| `reveal_common.wav` | 0.90 s | no | Card reveal, common: soft pluck chord. |
| `reveal_rare.wav` | 1.40 s | no | Card reveal, rare: brighter pluck + two chime notes. |
| `reveal_epic.wav` | 2.20 s | no | Card reveal, epic: riser into a wide chord hit. |
| `reveal_legendary.wav` | 4.20 s | no | Card reveal, legendary: riser, boom, synth chord + choir swell + shimmering bells. |
| `coins.wav` | 1.00 s | no | Coins: cascading metallic clinks. |

## Race start and crowd

| File | Length | Loop | For |
|---|---|---|---|
| `start_light.wav` | 0.50 s | no | One red start light on: low electric clunk + mains buzz + A5 beep. |
| `start_go.wav` | 2.70 s | no | Lights out: contactor release, whoosh, sub drop and airy stinger as the crowd lifts. |
| `grid_ambience.wav` | 10.00 s | yes | Grid ambience loop: cars idling around you, grandstand murmur, distant PA, generators. |
| `crowd_cheer.wav` | 3.00 s | no | Big crowd cheer (3 s): shouting voices, roar, applause and whistles. |
| `crowd_loop.wav` | 8.00 s | yes | Grandstand crowd loop: distant chatter, the odd shout, clap and whistle (quiet bed). |

## Pit stop

| File | Length | Loop | For |
|---|---|---|---|
| `pit_limiter_on.wav` | 0.15 s | no | Pit limiter engaged: short two-step dash beep. |
| `wheel_gun.wav` | 0.36 s | no | Wheel gun: air motor whine, clutch rattle, then hammering blows as the nut torques up (0.36 s). |
| `jack_up.wav` | 0.48 s | no | Jack up: nose clunk, pneumatic hiss as the car lifts, latch click. |
| `jack_down.wav` | 0.51 s | no | Jack down: release click, air dump and the car dropping onto its tyres. |
| `tyre_drop.wav` | 0.50 s | no | Tyre and rim dropped on the pit lane: rubbery thud with two small bounces. |
| `pit_release.wav` | 1.26 s | no | Pit release: go beep, then the engine revs out of the box and bounces off the pit limiter. |
| `pit_radio.wav` | 0.29 s | no | Team radio opens: press-to-talk click and a burst of digital static (put before engineer lines). |

## Race feedback

| File | Length | Loop | For |
|---|---|---|---|
| `overtake.wav` | 0.75 s | no | Position gained: soft rising D6-A6 chime. |
| `position_lost.wav` | 0.60 s | no | Position lost: subtle low tone sagging a semitone (E4). |
| `last_lap.wav` | 2.20 s | no | Last lap: hand bell struck twice (G5). |
| `chequered.wav` | 3.86 s | no | Chequered flag: two quick pickups into a big A major brass hit with crash and bells. |
| `car_contact.wav` | 0.25 s | no | Car-to-car touch: plasticky panel knock, tyre thump and a short rubber scuff. |

## Music

| File | Length | Loop | For |
|---|---|---|---|
| `music_menu.wav` | 36.57 s | yes | Menu music: moody synthwave/garage, A minor, 105 BPM, 16 bars (Am F C G / Am F Dm E). |
| `music_drive.wav` | 30.48 s | yes | Drive music: minimal percussive loop, E minor, 126 BPM, 16 bars. Sits under the engine. |
| `podium_music.wav` | 12.80 s | no | Podium fanfare (not a loop): synthwave in A major, 105 BPM, swell + 4 bars (A / E / F#m D / F G) into a held A major chord. |

68 files, 14.8 MB of WAV (about 1/5 of that after Godot's QOA import).

## Format

* 44.1 kHz, mono, 16-bit PCM WAV, peak-normalised to about -3 dBFS (music: -16 / -18 LUFS;
  `podium_music` -16 LUFS).
  The mix level of each sound lives in code (`Sfx.GAIN_DB`, `CarAudio.LEVEL_DB`), so files can be
  regenerated without touching the game.
* Loops are rendered circularly (notes, noise, filters, echoes and reverb tails wrap from the end
  back to the start), so they are seamless with no crossfade. Engine loops are a whole number of
  engine cycles long (the pit limiter also a whole number of 4 Hz cuts, and every idling car in
  `grid_ambience` a whole number of its own cycles); music loops are a whole number of bars.
  `podium_music` and `chequered` are one-shots, not loops.
* Every loop carries a RIFF `smpl` chunk, which Godot's importer reads ("Loop Mode: Detect From
  WAV", the default), and the scripts also force `LOOP_FORWARD` over the whole file at load time,
  so loops work whatever the import settings say. Default import compresses to QOA, which is fine.
* Everything is synthesised by `tools/audio/*.py` (numpy + scipy). No samples, no licences.
  Rebuild with `python tools/audio/build_all.py` (about 50 s); output is deterministic.

## Sfx (autoload, `res://autoload/sfx.gd`)

Register as autoload `Sfx`. On start it creates the buses `SFX` and `Music` (sending to `Master`)
if they are missing, puts an `AudioEffectHardLimiter` (ceiling -1 dBFS) on `Master`, preloads all one-shots and keeps a
pool of 12 `AudioStreamPlayer`s (round-robin; the oldest is stolen when all are busy). It runs with
`PROCESS_MODE_ALWAYS`, so UI sounds and music fades work while the tree is paused.

| Call | What it does |
|---|---|
| `play(name: String, volume_db := 0.0, pitch := 1.0) -> void` | One-shot on the SFX bus. `volume_db` is added to the sound's default level in `GAIN_DB`. |
| `play_varied(name: String, volume_db := 0.0, spread := 0.05) -> void` | Same with a random pitch of 1 +- spread (repeats sound less mechanical). |
| `stream(name: String) -> AudioStream` | The loaded stream (null if missing). |
| `make_looping(stream: AudioStream) -> AudioStream` (static) | Forces forward looping over the whole WAV. |
| `music(name: String) -> void` | 1 s crossfade to a music loop; calling it with the current track does nothing. |
| `stop_music() -> void` | 1 s fade out. |
| `current_music() -> String` | Name of the playing track or "". |
| `set_volume(bus: String, linear: float) -> void` | `"Master"`, `"SFX"` or `"Music"`, 0..1 linear amplitude. Saved to `user://audio.cfg` (debounced 0.5 s). |
| `get_volume(bus: String) -> float` | |
| `toggle_mute() -> bool` / `set_muted(on: bool)` / `is_muted() -> bool` | Mutes Master; saved too. |

Automatic UI sounds (via `get_tree().node_added`, plus one pass over the tree at start-up):

* every `BaseButton`: `mouse_entered` and keyboard/gamepad `focus_entered` play `ui_hover`
  (at most one per 40 ms, skipped while disabled); `pressed` plays `ui_click`, or `ui_toggle` for
  `toggle_mode` buttons (higher pitch when switched on);
* `Slider` and `SpinBox`: `value_changed` plays `ui_slider` (at most one per 45 ms, pitch rises with
  the value) but only when the user is changing it (focused or under the mouse), not when code
  sets the value. `ScrollBar` and `ProgressBar` are left alone;
* `PopupMenu` (OptionButton / MenuButton lists): hover and click.
* Opt out with `node.set_meta("no_sfx", true)`. It applies to the node and everything under it, so
  a whole panel can be silenced. Use it on buttons that play their own sound (for example a BUY
  button that plays `coins`) to avoid a click on top.

Things the game triggers itself: `Sfx.play("lights_beep")` per start light, `"lights_go"` at lights
out, `"sector_green"`, `"lap_pb"`, `"lap_purple"`, `"lap_deleted"` (lap or track limits),
`"verified"` when the server confirms the lap, `"battery_empty"` when the battery hits zero
(CarAudio cannot see the battery), `"equip"`/`"unequip"` in the garage, the pack sequence
(`pack_shake` -> `pack_open` -> `card_flip` per card -> `reveal_<rarity>`), `"coins"`, and
`"ui_confirm"`/`"ui_back"`/`"ui_error"` where a screen wants something more than the default click.

## CarAudio (`res://scenes/drive/car_audio.gd`, `class_name CarAudio extends Node`)

One per car; it builds its own players (13 loops + 2 one-shot players, non-positional, on `SFX`)
and stops any loop whose volume is ~0, so a car usually has 6-8 voices running.

| Member | |
|---|---|
| `update(speed_ms: float, throttle: float, brake: float, slip: float, locked: bool, surface: int, boosting: bool, straight_mode: bool, delta: float) -> void` | Call every frame. throttle/brake 0..1; slip 0..1 = how far past the grip limit; surface 0 asphalt, 1 kerb, 2 grass/gravel. |
| `impact(strength: float) -> void` | Wall hit, 0..1 (impact speed / 25 m/s works well): <0.34 `impact_1`, <0.67 `impact_2`, else `impact_3`; volume -8..+2 dB, small random pitch. Grazes under 0.06 are ignored (the scrape loop covers them) and a repeat within 0.15 s only plays if it is 1.5x harder, so riding a wall does not machine-gun. |
| `scrape(on: bool) -> void` | Start/stop the wall-scrape loop (volume follows speed). |
| `set_ghost(on: bool) -> void` | -18 dB for a ghost car. |
| `set_paused(paused: bool) -> void` | Pauses/resumes all of this car's players (the drive screen pauses by state, not by tree). |
| `stop_all() -> void` | Silences everything and resets gear/rpm (restart). |
| `gear: int` | Simulated gear 1-8, for the HUD. |
| `rpm: float` | Simulated engine rpm (4000-11800), for the HUD. |

What it does with the inputs:

* Gearbox (sound only): 8 speeds, 1st tops out at 95 km/h and 8th at 350 km/h at 11,500 rpm
  (`GEAR_TOP_KMH`). Upshift at 11,300 rpm with a 70 ms ignition cut (engine dips, `shift_up`),
  downshift below 7,000 rpm with a 160 ms throttle blip (+1,300 rpm, `shift_down`), at least
  0.12 s between shifts. Pulling away, the clutch holds the engine near launch revs (9,500 rpm at
  full throttle) until the wheels catch up; wheelspin (slip x throttle) adds up to 700 rpm.
* Engine: `engine_low/mid/high` play at pitch rpm / layer rpm (4000 / 7495.75 / 11002.08) with
  linear (sum-to-1) crossfades at 4,800-6,200 and 8,600-10,000 rpm; on-throttle layers are scaled by
  smoothed throttle, `engine_off` (overrun with pops, pitch rpm / 7993.96) by lift-off. Turbo
  whistle follows a spool value that rises with rpm x throttle (slowly up, faster down). MGU-K
  whine is full while `boosting` and quieter while braking (harvest); its pitch follows speed.
  `boost_on` plays when Boost starts after at least 0.4 s off; `straight_mode` plays when the wings
  open (and lower when they close) once the state has settled (0.08 s open / 0.3 s closed, at most
  one clack per 0.6 s), because the sim flickers Straight Mode whenever the throttle dips.
* Tyres: squeal from slip (only above 5 m/s; reduced while locked), `lockup` while locked.
  Surfaces: `kerb` (pitch follows speed, so the strip rate does too), `grass` + `gravel` on
  surface 2. `wind` rises with speed squared (Straight Mode takes a little off).
* Every volume is smoothed per frame (exponential, 4-25 /s) and every pitch follows the smoothed
  rpm/speed, so there is no zipper noise. Levels are in `LEVEL_DB`, smoothing rates in `RATE`.
* Levels: the rpm crossfade weights sum to 1 and on-throttle + overrun <= 1, so the engine layers
  never add up past 0 dB. Measured from Movie Maker captures: steady full throttle at 330 km/h is
  about -12.3 dBFS RMS with peaks around -2.4 dBFS; the autopilot lap (throttle flicking between
  55 % and 100 %) is about -15 dBFS RMS with peaks under -2 dBFS and no limiter action. Godot's
  Movie Maker writes 32-bit integer PCM WAV, so read it as int32 (/ 2^31), not int16.

### Example (drive screen)

```gdscript
var _car_audio := CarAudio.new()

func _build() -> void:
	...
	add_child(_car_audio)
	Sfx.music("music_drive")

func _process(delta: float) -> void:
	...
	var car := _session.car
	var v := car.speed / 65536.0
	if _state == "driving":
		_car_audio.update(v, _input.throttle, _input.brake, slip_0_to_1, car.front_locked,
				int(car.surface), car.boosting, car.straight_mode, delta)
	_hud.gear = _car_audio.gear  # optional

func _toggle_pause() -> void:
	...
	_car_audio.set_paused(_state.begins_with("paused_"))

# in _after_tick, on a "wall" event:
	_car_audio.impact(hit / 65536.0 / 25.0)

# lap feedback
	Sfx.play("lap_pb")        # personal best
	Sfx.play("lap_deleted")   # track limits / invalid lap
	Sfx.play("verified")      # server re-drive confirmed
```

A good `slip` is the larger of the two axles' |slip angle| over their peak, minus about 0.7,
scaled to 0..1 (or `1.0 if car.rear_sliding else 0.0` as a first pass).

## Race mode (suggested wiring)

### Loops and one-shots

`grid_ambience`, `crowd_loop`, `engine_idle` and `pit_limiter` are loops: their WAVs carry a `smpl`
chunk, so the imported stream loops for ever. Never `Sfx.play()` one (the pool player would never
stop). Give each its own player and fade it with a tween on `volume_db`:

```gdscript
var _ambience := AudioStreamPlayer.new()

func _start_grid_audio() -> void:
	_ambience.stream = Sfx.make_looping(Sfx.stream("grid_ambience"))
	_ambience.bus = "SFX"
	_ambience.volume_db = Sfx.GAIN_DB["grid_ambience"]
	add_child(_ambience)
	_ambience.play()

func _fade_out(p: AudioStreamPlayer, seconds: float) -> void:
	var tw := create_tween()
	tw.tween_property(p, "volume_db", -60.0, seconds)
	tw.tween_callback(p.stop)
```

`GAIN_DB` has the default level of the two ambience loops for exactly this. `engine_idle` and
`pit_limiter` belong in CarAudio (below).

`podium_music` is a 12.8 s cue, not a loop: `Sfx.stop_music()` then `Sfx.play("podium_music")` (SFX
bus). `Sfx.music()` would loop it. To have the Music slider apply, play it on your own player on the
`"Music"` bus at about -4 dB (the same loudness at default volumes). It loads on first use, so call
`Sfx.stream("podium_music")` during the race-end transition to avoid a hitch.

### CarAudio: idle and pit limiter (to add to car_audio.gd)

* Add `"engine_idle": -10.0, "pit_limiter": -5.0` to `LEVEL_DB` and `"engine_idle": 8.0,
  "pit_limiter": 12.0` to `RATE`; `_build()` then makes their players like the other loops. That puts
  the idle about 13 dB and the pit limiter about 7 dB under a car at full throttle.
* Idle: `engine_idle` is rendered at 4000 rpm (= `IDLE_RPM`), so its pitch is `rpm / IDLE_RPM`. Fade
  it in as the car settles at idle and take the same share off the other layers, so the sum stays
  at 1:

```gdscript
	var idle := (1.0 - _thr) * (1.0 - smoothstep(4300.0, 5600.0, rpm))
	# multiply the engine_low/mid/high and engine_off targets by (1.0 - idle)
	_drive_loop("engine_idle", idle, rpm / IDLE_RPM, delta)
```

* Pit limiter: while the limiter is on and the car is at the limit, `pit_limiter` replaces the whole
  engine (on-throttle layers, overrun, idle and turbo). It is the engine at 9000 rpm with the
  ignition cut 4 times a second plus pops; play it at pitch 1.0 (or `rpm / 9000.0` to follow the
  gearbox: in 1st at 80 km/h CarAudio sits near 9,700 rpm, pitch 1.08). Crossfade on speed so pulling
  away from the box still uses the normal layers until the limiter bites:

```gdscript
	var pit := smoothstep(0.85, 0.98, v / PIT_SPEED_MS) if pit_limiter_on else 0.0
	# multiply every engine layer, engine_off, engine_idle and turbo_whine target by (1.0 - pit)
	_drive_loop("pit_limiter", pit * clampf(0.3 + _thr, 0.0, 1.0), 1.0, delta)
```

  Play `Sfx.play("pit_limiter_on")` when the driver switches the limiter on (at the pit entry line)
  and `Sfx.play("pit_limiter_on", -2.0, 0.8)` when it goes off at the exit.

### Sequences

* Grid and start: `Sfx.stop_music()`, start `grid_ambience` (the player's car idles through
  CarAudio's `engine_idle`). Five lights one second apart, `Sfx.play("start_light")` for each (A5
  beep; `lights_beep` stays for the time-trial countdown). Hold for a random 0.2-3 s, then at lights
  out `Sfx.play("start_go")` and fade `grid_ambience` out over about 2 s while the engines take over.
* Pit stop (in the box the car is stationary, so CarAudio is on `engine_idle`):
  `jack_up` (front), again about 0.12 s later at -3 dB (rear); wheels off: `wheel_gun` four times,
  30-80 ms apart, with `Sfx.play_varied("wheel_gun", -3.0, 0.06)` for the second to fourth (four at
  0 dB stack to +6 dB); `tyre_drop` (play_varied, -3..0 dB) as each old tyre hits the ground; wheels
  on: `wheel_gun` x4 again; `jack_down` (front, rear 0.1 s later); `pit_release`. `pit_release` has its
  own rev from idle to the limiter (1.3 s): in a pit-stop cutscene let it stand in for CarAudio
  (`set_paused(true)` for that time, or duck it), then hand back to CarAudio's `pit_limiter`; driven
  from the cockpit, play it at about -8 dB just for the beep.
* `pit_radio` immediately before an engineer message (text or voice); start the message about
  0.25 s later.
* Positions: `overtake` / `position_lost` when the player's position changes. Gather the changes
  for about a second and play only the net result, so a swap back and forth does not chirp twice.
* `last_lap` as the player starts the final lap. At the finish: `chequered`, then `crowd_cheer`
  about 0.4 s later (-4 dB if not on the podium).
* `car_contact`: car-to-car touches, strength 0..1 (closing speed / 15 m/s works well):
  `Sfx.play("car_contact", lerpf(-10.0, 0.0, s), randf_range(0.92, 1.08))`. Ignore touches under
  0.05, and re-trigger within 0.15 s only if 1.5x harder, as `CarAudio.impact()` does. A hard hit
  (> 0.7) can add `CarAudio.impact()` for the carbon crunch.
* `crowd_loop` near grandstands: its own looping player, `GAIN_DB["crowd_loop"]` at the stand,
  fading to silence about 150 m away (it is 19 dB under a full-throttle car, a bed, not a feature).
* Podium: `Sfx.stop_music()`, `Sfx.play("podium_music")`, `crowd_loop` about 8 dB above its default
  (the stands are right there), and `crowd_cheer` as the trophy is lifted.

### Levels

`GAIN_DB` for the race sounds comes from each file's maximum momentary loudness (400 ms, K-weighted)
compared with the existing cues: `start_go`, `last_lap` and `chequered` sit with `lights_go`, `lap_pb`
and `lap_purple` (they cut through a car at full throttle); `overtake`, `position_lost` and
`pit_limiter_on` at or under `sector_green` (subtle); the pit-stop foley near `impact_1`/`impact_2`;
`grid_ambience` about 3 dB under the suggested idle level and 16 dB under full throttle.

## Rebuilding

```
python tools/audio/build_all.py      # all generators + checks + this file
python tools/audio/gen_engine.py     # engine layers, overrun, idle, pit limiter, turbo, MGU-K, shifts
python tools/audio/gen_sfx.py        # car sounds, UI, lap feedback, packs
python tools/audio/gen_race.py       # race start, crowds, pit stop, race feedback, car contact
python tools/audio/gen_music.py      # music_menu, music_drive, chequered, podium_music
python tools/audio/check_audio.py --png <dir>   # clipping/DC/seam checks + spectrograms
```

If an engine layer is re-rendered at a different rpm, update `LOW_RPM`/`MID_RPM`/`HIGH_RPM`/`OFF_RPM`
in `car_audio.gd` (gen_engine prints the exact values). If a one-shot's loudness changes a lot,
adjust its entry in `Sfx.GAIN_DB`.
