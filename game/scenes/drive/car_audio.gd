class_name CarAudio
extends Node
## Engine, gearbox, tyres, surfaces and wind for one car.
##
## Add one per car and call update() every frame with the car state. The
## engine is three looping layers recorded at fixed rpm (low/mid/high) that
## are pitched by rpm / layer_rpm and crossfaded, plus an overrun layer for
## lift-off, a turbo whistle and the MGU-K whine. The 8-speed gearbox only
## exists for the sound (and the HUD): read `gear` and `rpm`.
##
##   var audio := CarAudio.new()
##   add_child(audio)
##   ...
##   audio.update(speed_ms, throttle, brake, slip, locked, surface, boosting, straight_mode, delta)
##   audio.impact(hit_speed_ms / 25.0)    # wall hit, 0..1
##   audio.scrape(touching_wall)
##
## Players are non-positional AudioStreamPlayers on the "SFX" bus; loops that
## are silent are stopped, so a car on track keeps about 6-8 voices running.

const DIR := "res://assets/audio/"
const BUS := "SFX"

## The rpm each engine loop was rendered at (tools/audio/gen_engine.py).
const LOW_RPM := 4000.0
const MID_RPM := 7495.751
const HIGH_RPM := 11002.079
const OFF_RPM := 7993.958

const IDLE_RPM := 4000.0
const LAUNCH_RPM := 9500.0
const MAX_RPM := 11500.0
const UPSHIFT_RPM := 11300.0
const DOWNSHIFT_RPM := 7000.0
const MIN_SHIFT_GAP := 0.12  # s between shifts
const CUT_TIME := 0.07  # ignition cut on an upshift
const BLIP_TIME := 0.16  # throttle blip on a downshift
## Road speed (km/h) at MAX_RPM in each gear, 1st to 8th.
const GEAR_TOP_KMH: Array[float] = [95.0, 118.0, 145.0, 175.0, 210.0, 250.0, 297.0, 350.0]

## Mix level (dB) of each loop at full intensity. The engine files sit at about
## -13 dBFS RMS, so a car at full throttle comes out near -12 dBFS RMS (peaks
## around -2 dBFS) with tyres, air and the turbo well below it.
const LEVEL_DB := {
	"engine_low": 1.0, "engine_mid": 1.0, "engine_high": 1.0, "engine_off": -3.0,
	"turbo_whine": -22.0, "electric_whine": -21.0,
	"tyre_squeal": -15.0, "lockup": -12.0,
	"kerb": -9.0, "grass": -8.0, "gravel": -12.0,
	"wind": -14.0, "scrape": -9.0,
}
## How fast each loop's volume follows its target (1/s).
const RATE := {
	"engine_low": 25.0, "engine_mid": 25.0, "engine_high": 25.0, "engine_off": 18.0,
	"turbo_whine": 10.0, "electric_whine": 8.0,
	"tyre_squeal": 14.0, "lockup": 20.0,
	"kerb": 20.0, "grass": 12.0, "gravel": 12.0,
	"wind": 4.0, "scrape": 18.0,
}
const SILENT := 0.003  # linear volume below which a loop is stopped

static var _cache: Dictionary = {}  # name -> AudioStream, shared by every car

## Current gear (1-8) and engine rpm, for the HUD.
var gear := 1
var rpm := IDLE_RPM

var _players: Dictionary = {}  # loop name -> AudioStreamPlayer
var _vol: Dictionary = {}  # loop name -> smoothed linear volume
var _shot_player: AudioStreamPlayer  # shifts, boost, straight mode
var _impact_player: AudioStreamPlayer
var _master_db := 0.0
var _speed := 0.0
var _thr := 0.0
var _spool := 0.0
var _since_shift := 1.0
var _cut := 0.0
var _blip := 0.0
var _scrape_on := false
var _was_boosting := false
var _boost_rest := 1.0  # s since Boost was last on
var _was_straight := false  # settled (audible) Straight Mode state
var _sm_hold := 0.0  # s the input has disagreed with it
var _sm_since := 1.0  # s since the last flap sound
var _last_impact := -1000.0  # _clock time of the last impact sound
var _last_strength := 0.0
var _clock := 0.0  # s of update() time, for cooldowns that follow game time


func _ready() -> void:
	_build()


## Feed the car state once per frame.
## speed_ms: m/s. throttle, brake: 0..1. slip: 0..1, how far past the grip limit the tyres are.
## locked: a wheel is locked. surface: 0 asphalt, 1 kerb, 2 grass/gravel.
func update(speed_ms: float, throttle: float, brake: float, slip: float, locked: bool, surface: int,
		boosting: bool, straight_mode: bool, delta: float) -> void:
	if delta <= 0.0:
		return
	_build()
	_clock += delta
	var v := absf(speed_ms)
	_speed = v
	var kmh := v * 3.6
	throttle = clampf(throttle, 0.0, 1.0)
	brake = clampf(brake, 0.0, 1.0)
	slip = clampf(slip, 0.0, 1.0)
	_thr = lerpf(_thr, throttle, 1.0 - exp(-delta * 14.0))

	_gearbox(kmh, throttle, slip, delta)

	# Engine: on-throttle layers crossfaded by rpm, overrun layer by lift-off. The
	# crossfade weights add up to 1 (and on + off <= 1), so layers never sum past 0 dB.
	var a := smoothstep(4800.0, 6200.0, rpm)
	var b := smoothstep(8600.0, 10000.0, rpm)
	var on := 0.1 + 0.9 * _thr
	if _cut > 0.0:
		on *= 0.22
	var rev_load := lerpf(0.6, 1.0, clampf((rpm - IDLE_RPM) / (MAX_RPM - IDLE_RPM), 0.0, 1.0))
	_drive_loop("engine_low", (1.0 - a) * on * rev_load, rpm / LOW_RPM, delta)
	_drive_loop("engine_mid", a * (1.0 - b) * on * rev_load, rpm / MID_RPM, delta)
	_drive_loop("engine_high", b * on * rev_load, rpm / HIGH_RPM, delta)
	var off := (1.0 - _thr) * 0.9 * rev_load  # on + off <= 1
	if _blip > 0.0:
		off *= 0.4
	_drive_loop("engine_off", off, rpm / OFF_RPM, delta)

	# Turbo spools up slowly with rpm and throttle, and drops faster
	var spool_target := clampf((rpm - 5000.0) / 6000.0, 0.0, 1.0) * _thr
	var spool_rate := 2.2 if spool_target > _spool else 4.0
	_spool = lerpf(_spool, spool_target, 1.0 - exp(-delta * spool_rate))
	_drive_loop("turbo_whine", pow(_spool, 1.5), 0.55 + 0.5 * _spool * rpm / HIGH_RPM, delta)

	# MGU-K: loud while deploying Boost, quieter while harvesting under braking
	var e := 1.0 if boosting else brake * 0.45 * clampf(kmh / 80.0, 0.0, 1.0)
	_drive_loop("electric_whine", e, 0.55 + kmh / 330.0, delta)
	# The whoosh marks a fresh deployment, not every flicker of the Boost button
	if boosting and not _was_boosting and _boost_rest > 0.4:
		_shot("boost_on", -5.0)
	_boost_rest = 0.0 if boosting else _boost_rest + delta
	_was_boosting = boosting
	# Straight Mode flickers when the throttle dips; only a settled change clacks the flaps
	_sm_hold = _sm_hold + delta if straight_mode != _was_straight else 0.0
	_sm_since += delta
	if _sm_hold > (0.08 if straight_mode else 0.3):
		_was_straight = straight_mode
		_sm_hold = 0.0
		if _sm_since > 0.6:
			_shot("straight_mode", -3.0, 1.0 if straight_mode else 0.85)
			_sm_since = 0.0
	straight_mode = _was_straight

	# Tyres
	var moving := clampf((v - 5.0) / 5.0, 0.0, 1.0)
	var squeal := smoothstep(0.2, 1.0, slip) * moving * (0.35 if locked else 1.0)
	_drive_loop("tyre_squeal", squeal, 0.92 + 0.12 * slip + v / 900.0, delta)
	var lock := clampf(v / 25.0, 0.35, 1.0) if locked and v > 3.0 else 0.0
	_drive_loop("lockup", lock, 0.8 + v / 150.0, delta)

	# Surfaces
	var rolling := clampf(v / 25.0, 0.0, 1.0)
	_drive_loop("kerb", rolling if surface == 1 and v > 2.0 else 0.0, clampf(0.5 + v / 60.0, 0.5, 2.0), delta)
	var off_road := surface == 2 and v > 1.0
	_drive_loop("grass", clampf(v / 20.0, 0.0, 1.0) if off_road else 0.0, 0.75 + v / 120.0, delta)
	_drive_loop("gravel", clampf(v / 30.0, 0.0, 1.0) * 0.8 if off_road else 0.0, 0.8 + v / 140.0, delta)

	# Air: rises with speed squared; the open wings of Straight Mode shed some of it
	var air := minf(pow(v / 90.0, 2.0), 1.2) * (0.8 if straight_mode else 1.0)
	_drive_loop("wind", air, 0.75 + v / 200.0 - (0.04 if straight_mode else 0.0), delta)

	_drive_loop("scrape", clampf(v / 15.0, 0.4, 1.0) if _scrape_on and v > 1.0 else 0.0, 0.8 + v / 100.0, delta)


## Wall hit. strength 0..1 (about impact speed / 25 m/s) picks a light, solid or heavy
## crash. Grazes under 0.06 are ignored, and repeats within 0.15 s only play if harder.
func impact(strength: float) -> void:
	_build()
	strength = clampf(strength, 0.0, 1.0)
	if strength < 0.06:
		return  # a graze (under ~1.5 m/s): the scrape loop covers it
	# Riding along a wall reports a hit every tick; only a clearly harder one re-triggers quickly
	if _clock - _last_impact < 0.15 and strength < _last_strength * 1.5:
		return
	_last_impact = _clock
	_last_strength = strength
	var sound := "impact_1" if strength < 0.34 else ("impact_2" if strength < 0.67 else "impact_3")
	var s := _stream(sound)
	if s == null:
		return
	_impact_player.stream = s
	_impact_player.volume_db = lerpf(-8.0, 2.0, strength) + _master_db
	_impact_player.pitch_scale = randf_range(0.93, 1.07)
	_impact_player.play()


## Bodywork sliding along a wall: true while touching, false when clear.
func scrape(on: bool) -> void:
	_scrape_on = on


## Ghost cars are 18 dB quieter.
func set_ghost(on: bool) -> void:
	_master_db = -18.0 if on else 0.0


## Pause or resume every sound of this car (e.g. while the session is paused).
func set_paused(paused: bool) -> void:
	for p: AudioStreamPlayer in _players.values():
		p.stream_paused = paused
	if _shot_player != null:
		_shot_player.stream_paused = paused
		_impact_player.stream_paused = paused


## Silence everything at once (session over, restart).
func stop_all() -> void:
	for k: String in _players:
		(_players[k] as AudioStreamPlayer).stop()
		_vol[k] = 0.0
	gear = 1
	rpm = IDLE_RPM
	_thr = 0.0
	_spool = 0.0
	_cut = 0.0
	_blip = 0.0
	_scrape_on = false
	_was_boosting = false
	_boost_rest = 1.0
	_was_straight = false
	_sm_hold = 0.0


# ---------------------------------------------------------------------------

func _gearbox(kmh: float, throttle: float, slip: float, delta: float) -> void:
	_since_shift += delta
	_cut = maxf(_cut - delta, 0.0)
	_blip = maxf(_blip - delta, 0.0)
	var wheel := kmh / GEAR_TOP_KMH[gear - 1] * MAX_RPM
	if _since_shift >= MIN_SHIFT_GAP:
		if wheel > UPSHIFT_RPM and gear < GEAR_TOP_KMH.size():
			gear += 1
			_since_shift = 0.0
			_cut = CUT_TIME
			_shot("shift_up", -4.0, randf_range(0.97, 1.03))
		elif wheel < DOWNSHIFT_RPM and gear > 1:
			gear -= 1
			_since_shift = 0.0
			_blip = BLIP_TIME
			_shot("shift_down", -4.0, randf_range(0.96, 1.04))
		wheel = kmh / GEAR_TOP_KMH[gear - 1] * MAX_RPM
	# Pulling away the clutch slips, so the engine sits at launch revs until the wheels catch up
	var clutch := IDLE_RPM + throttle * (LAUNCH_RPM - IDLE_RPM) * clampf(1.0 - kmh / 70.0, 0.0, 1.0)
	var target := maxf(wheel, clutch) + slip * throttle * 700.0
	if _blip > 0.0:
		target += 1300.0 * (_blip / BLIP_TIME)
	target = clampf(target, IDLE_RPM, MAX_RPM + 300.0)
	var rate := 30.0 if _cut > 0.0 or _blip > 0.0 else 16.0
	rpm = lerpf(rpm, target, 1.0 - exp(-delta * rate))


func _drive_loop(loop: String, target: float, pitch: float, delta: float) -> void:
	var p := _players.get(loop) as AudioStreamPlayer
	if p == null:
		return
	var cur := float(_vol.get(loop, 0.0))
	cur = lerpf(cur, maxf(target, 0.0), 1.0 - exp(-delta * float(RATE.get(loop, 12.0))))
	_vol[loop] = cur
	if cur < SILENT:
		if p.playing:
			p.stop()
		return
	p.volume_db = linear_to_db(cur) + float(LEVEL_DB.get(loop, 0.0)) + _master_db
	p.pitch_scale = clampf(pitch, 0.25, 4.0)
	if not p.playing:
		p.play(randf() * p.stream.get_length())


func _shot(sound: String, volume_db: float, pitch: float = 1.0) -> void:
	var s := _stream(sound)
	if s == null or _shot_player == null:
		return
	_shot_player.stream = s
	_shot_player.volume_db = volume_db + _master_db
	_shot_player.pitch_scale = pitch
	_shot_player.play()


func _build() -> void:
	if _shot_player != null:
		return
	var bus := BUS if AudioServer.get_bus_index(BUS) != -1 else "Master"
	for loop: String in LEVEL_DB:
		var s := _stream(loop)
		if s == null:
			continue
		_make_loop(s)
		var p := AudioStreamPlayer.new()
		p.stream = s
		p.bus = bus
		add_child(p)
		_players[loop] = p
		_vol[loop] = 0.0
	_shot_player = AudioStreamPlayer.new()
	_shot_player.bus = bus
	add_child(_shot_player)
	_impact_player = AudioStreamPlayer.new()
	_impact_player.bus = bus
	add_child(_impact_player)


static func _stream(sound: String) -> AudioStream:
	if _cache.has(sound):
		return _cache[sound] as AudioStream
	var path := DIR + sound + ".wav"
	var s: AudioStream = null
	if ResourceLoader.exists(path):
		s = load(path) as AudioStream
	_cache[sound] = s
	return s


static func _make_loop(s: AudioStream) -> void:
	var wav := s as AudioStreamWAV
	if wav == null:
		return
	var frames := int(round(wav.get_length() * wav.mix_rate))
	if wav.loop_mode == AudioStreamWAV.LOOP_DISABLED or wav.loop_end <= 0 or wav.loop_end > frames:
		wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wav.loop_begin = 0
		wav.loop_end = frames
