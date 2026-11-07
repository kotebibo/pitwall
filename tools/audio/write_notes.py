"""Writes game/assets/audio/AUDIO_NOTES.md from the WAV files themselves.

    python tools/audio/write_notes.py

Each WAV carries its description in a LIST/INFO comment (see dsp.write_wav),
so this table is always in step with what is on disk.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

from dsp import OUT_DIR, SR, read_meta, read_wav

GROUPS = [
    ("Engine and power unit (used by CarAudio)", ["engine_low", "engine_mid", "engine_high", "engine_off",
                                                  "engine_idle", "pit_limiter", "turbo_whine", "electric_whine",
                                                  "shift_up", "shift_down"]),
    ("Tyres, surfaces, air, contact (used by CarAudio)", ["tyre_squeal", "lockup", "kerb", "gravel", "grass", "wind",
                                                         "scrape", "impact_1", "impact_2", "impact_3"]),
    ("Car systems and start", ["boost_on", "straight_mode", "battery_empty", "lights_beep", "lights_go"]),
    ("UI (Sfx plays hover/click/toggle/slider automatically)", ["ui_hover", "ui_click", "ui_confirm", "ui_back",
                                                                "ui_error", "ui_toggle", "ui_slider", "ui_dial",
                                                                "equip", "unequip"]),
    ("Lap feedback", ["sector_green", "lap_pb", "lap_purple", "lap_deleted", "verified"]),
    ("Pack opening", ["pack_shake", "pack_open", "card_flip", "reveal_common", "reveal_rare", "reveal_epic",
                      "reveal_legendary", "coins"]),
    ("Race start and crowd", ["start_light", "start_go", "grid_ambience", "crowd_cheer", "crowd_loop"]),
    ("Pit stop", ["pit_limiter_on", "wheel_gun", "jack_up", "jack_down", "tyre_drop", "pit_release", "pit_radio"]),
    ("Race feedback", ["overtake", "position_lost", "last_lap", "chequered", "car_contact"]),
    ("Music", ["music_menu", "music_drive", "podium_music"]),
]

API = '''
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
'''


def main() -> None:
    lines = ["# Pit Wall audio", "",
             "All sounds are synthesised by `tools/audio/` (see the bottom of this file to rebuild).", ""]
    seen = set()
    for title, names in GROUPS:
        lines += [f"## {title}", "", "| File | Length | Loop | For |", "|---|---|---|---|"]
        for n in names:
            p = OUT_DIR / f"{n}.wav"
            if not p.exists():
                continue
            seen.add(n)
            x, sr, loop = read_wav(p)
            meta = read_meta(p)
            lines.append(f"| `{n}.wav` | {len(x) / sr:.2f} s | {'yes' if loop else 'no'} | {meta.get('desc', '')} |")
        lines.append("")
    rest = sorted(p.stem for p in OUT_DIR.glob("*.wav") if p.stem not in seen)
    if rest:
        lines += ["## Other", "", "| File | Length | Loop | For |", "|---|---|---|---|"]
        for n in rest:
            p = OUT_DIR / f"{n}.wav"
            x, sr, loop = read_wav(p)
            lines.append(f"| `{n}.wav` | {len(x) / sr:.2f} s | {'yes' if loop else 'no'} | {read_meta(p).get('desc', '')} |")
        lines.append("")
    total = sum(p.stat().st_size for p in OUT_DIR.glob("*.wav"))
    lines.append(f"{len(list(OUT_DIR.glob('*.wav')))} files, {total / 1e6:.1f} MB of WAV (about 1/5 of that after Godot's QOA import).")
    lines.append(API)
    lines += ["## Rebuilding", "",
              "```",
              "python tools/audio/build_all.py      # all generators + checks + this file",
              "python tools/audio/gen_engine.py     # engine layers, overrun, idle, pit limiter, turbo, MGU-K, shifts",
              "python tools/audio/gen_sfx.py        # car sounds, UI, lap feedback, packs",
              "python tools/audio/gen_race.py       # race start, crowds, pit stop, race feedback, car contact",
              "python tools/audio/gen_music.py      # music_menu, music_drive, chequered, podium_music",
              "python tools/audio/check_audio.py --png <dir>   # clipping/DC/seam checks + spectrograms",
              "```", "",
              "If an engine layer is re-rendered at a different rpm, update `LOW_RPM`/`MID_RPM`/`HIGH_RPM`/`OFF_RPM`",
              "in `car_audio.gd` (gen_engine prints the exact values). If a one-shot's loudness changes a lot,",
              "adjust its entry in `Sfx.GAIN_DB`.", ""]
    (OUT_DIR / "AUDIO_NOTES.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT_DIR / "AUDIO_NOTES.md")


if __name__ == "__main__":
    main()
