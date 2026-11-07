extends Node
## Sound effects and music for every screen (autoload "Sfx").
##
##   Sfx.play("ui_confirm")              # one-shot on the SFX bus at its default level
##   Sfx.play("coins", -6.0, 1.1)        # 6 dB quieter, a little higher
##   Sfx.play_varied("card_flip")        # small random pitch so repeats don't sound identical
##   Sfx.music("music_menu")             # 1 s crossfade to a music loop
##   Sfx.stop_music()
##   Sfx.set_volume("Music", 0.5)        # "Master", "SFX" or "Music", 0..1, saved to user://audio.cfg
##   Sfx.toggle_mute()
##
## Every BaseButton gets a hover tick (mouse or keyboard/gamepad focus) and a
## click (ui_toggle for toggle buttons); sliders and spin boxes tick as the
## user changes them. Opt a node, or a whole container, out with
## node.set_meta("no_sfx", true).
##
## All files in res://assets/audio are peak-normalised; GAIN_DB holds each
## sound's default mix level so callers can simply use 0 dB.

const DIR := "res://assets/audio/"
const SFX_BUS := "SFX"
const MUSIC_BUS := "Music"
const CFG_PATH := "user://audio.cfg"
const POOL_SIZE := 12
const MUSIC_FADE := 1.0
const HOVER_GAP_MS := 40
const SLIDER_GAP_MS := 45
const NO_SFX := &"no_sfx"
const HOOKED := &"_sfx_hooked"

## One-shots loaded at start-up (music and car loops load on first use).
const SOUNDS: PackedStringArray = [
	"ui_hover", "ui_click", "ui_confirm", "ui_back", "ui_error", "ui_toggle", "ui_slider", "ui_dial",
	"equip", "unequip",
	"lap_pb", "lap_purple", "sector_green", "lap_deleted", "verified",
	"pack_shake", "pack_open", "card_flip", "reveal_common", "reveal_rare", "reveal_epic", "reveal_legendary", "coins",
	"lights_beep", "lights_go", "boost_on", "straight_mode", "battery_empty",
	"impact_1", "impact_2", "impact_3", "shift_up", "shift_down",
	"start_light", "start_go", "crowd_cheer",
	"pit_limiter_on", "wheel_gun", "jack_up", "jack_down", "tyre_drop", "pit_release", "pit_radio",
	"overtake", "position_lost", "last_lap", "chequered", "car_contact",
]

## Default level of each one-shot (dB), from its measured loudness. Lap feedback,
## lights and coins are set to cut through a car at full throttle (about -12 dBFS
## RMS); the files peak at -3 dBFS, so +2 dB keeps them under the -1 dB limiter.
const GAIN_DB := {
	"ui_hover": -10.0, "ui_slider": -6.5, "ui_dial": -5.0, "ui_click": -2.0, "ui_toggle": -5.0,
	"ui_confirm": -9.5, "ui_back": -9.5, "ui_error": -9.5, "equip": -1.0, "unequip": -2.0,
	"sector_green": -5.0, "lap_pb": 2.0, "lap_deleted": -2.0, "verified": 2.0, "lap_purple": 2.0,
	"pack_shake": -1.0, "pack_open": 0.0, "card_flip": -2.5, "reveal_common": -2.0, "reveal_rare": -5.0,
	"reveal_epic": -1.0, "reveal_legendary": 0.0, "coins": 0.0,
	"lights_beep": 0.0, "lights_go": 0.0, "boost_on": -3.0, "straight_mode": 0.0, "battery_empty": -3.0,
	"impact_1": 0.0, "impact_2": 0.0, "impact_3": 0.0, "shift_up": -2.0, "shift_down": -4.0,
	# race mode
	"start_light": 2.0, "start_go": 0.0, "crowd_cheer": -2.0,
	"pit_limiter_on": -6.0, "wheel_gun": 0.0, "jack_up": 0.0, "jack_down": -1.0, "tyre_drop": -2.0,
	"pit_release": -2.0, "pit_radio": 1.0,
	"overtake": -3.5, "position_lost": -5.5, "last_lap": -1.5, "chequered": 2.0, "car_contact": 2.0,
	"podium_music": -7.0,  # not a loop, so play it with play(); loads on first use
	# Loops: the level for your own looping AudioStreamPlayer. Never play() a loop (it never stops).
	"grid_ambience": -12.0, "crowd_loop": -15.0,
}

## Default level of each music loop (dB). The drive loop sits under the engine.
const MUSIC_DB := {"music_menu": -5.0, "music_drive": -9.0}

const DEFAULT_VOLUME := {"Master": 1.0, "SFX": 1.0, "Music": 0.8}
## Make-up gain per bus: the mix measured about -28 dBFS RMS in a browser, too quiet
## next to other tabs; the Master limiter (-1 dBFS) catches the peaks this creates.
const MAKEUP_DB := {"Master": 0.0, "SFX": 8.0, "Music": 7.0}

var _streams: Dictionary = {}  # name -> AudioStream (null when missing)
var _pool: Array[AudioStreamPlayer] = []
var _next := 0
var _music: Array[AudioStreamPlayer] = []
var _music_gain: Array[float] = [0.0, 0.0]  # linear fade level of each music player
var _music_db: Array[float] = [0.0, 0.0]  # base level of the loop each one plays
var _music_on := 0
var _music_name := ""
var _music_tween: Tween
var _volume: Dictionary = DEFAULT_VOLUME.duplicate()
var _muted := false
var _save_queued := false
var _last_hover := -1000
var _last_slider := -1000


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS  # UI sounds and fades keep working while paused
	_ensure_bus(SFX_BUS)
	_ensure_bus(MUSIC_BUS)
	_ensure_limiter()
	for s in SOUNDS:
		stream(s)
	for i in POOL_SIZE:
		var p := AudioStreamPlayer.new()
		p.bus = SFX_BUS
		add_child(p)
		_pool.append(p)
	for i in 2:
		var m := AudioStreamPlayer.new()
		m.bus = MUSIC_BUS
		m.volume_db = -80.0
		add_child(m)
		_music.append(m)
	_load_settings()
	get_tree().node_added.connect(_on_node_added)
	_hook_tree.call_deferred(get_tree().root)


# ---------------------------------------------------------------------------
# One-shots
# ---------------------------------------------------------------------------

## Play a one-shot. volume_db is added to the sound's default level.
func play(sound: String, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var s := stream(sound)
	if s == null or _pool.is_empty():
		return
	var p := _free_player()
	p.stream = s
	p.volume_db = volume_db + float(GAIN_DB.get(sound, 0.0))
	p.pitch_scale = clampf(pitch, 0.05, 4.0)
	p.play()


## play() with a small random pitch offset (spread 0.05 = +-5 %).
func play_varied(sound: String, volume_db: float = 0.0, spread: float = 0.05) -> void:
	play(sound, volume_db, 1.0 + randf_range(-spread, spread))


## The loaded stream for a sound name, or null if the file is missing.
func stream(sound: String) -> AudioStream:
	if _streams.has(sound):
		return _streams[sound] as AudioStream
	var path := DIR + sound + ".wav"
	var s: AudioStream = null
	if ResourceLoader.exists(path):
		s = load(path) as AudioStream
	else:
		push_warning("Sfx: no sound at " + path)
	_streams[sound] = s
	return s


## Make an imported WAV loop over its whole length (the import settings may not).
static func make_looping(s: AudioStream) -> AudioStream:
	var wav := s as AudioStreamWAV
	if wav != null:
		var frames := int(round(wav.get_length() * wav.mix_rate))
		if wav.loop_mode == AudioStreamWAV.LOOP_DISABLED or wav.loop_end <= 0 or wav.loop_end > frames:
			wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
			wav.loop_begin = 0
			wav.loop_end = frames
	return s


func _free_player() -> AudioStreamPlayer:
	for i in POOL_SIZE:
		var k := (_next + i) % POOL_SIZE
		if not _pool[k].playing:
			_next = (k + 1) % POOL_SIZE
			return _pool[k]
	var p := _pool[_next]  # all busy: take the oldest
	_next = (_next + 1) % POOL_SIZE
	return p


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

## Crossfade to a music loop ("music_menu", "music_drive"). Same track again: no-op.
func music(track: String) -> void:
	if _music.is_empty() or (track == _music_name and _music[_music_on].playing):
		return
	if OS.is_debug_build() and "--no-music" in Api.args:
		return  # recording footage: the video gets its own continuous music bed
	var s := stream(track)
	if s == null:
		return
	make_looping(s)
	var old := _music_on
	var cur := 1 - _music_on
	_music_on = cur
	_music_name = track
	_music_db[cur] = float(MUSIC_DB.get(track, 0.0))
	_music[cur].stream = s
	_music_gain[cur] = 0.0
	_apply_music(cur)
	_music[cur].play()
	_fade_music(cur, old)


## Fade the current music out.
func stop_music() -> void:
	_music_name = ""
	if _music.is_empty() or not _music[_music_on].playing:
		return
	_fade_music(-1, _music_on)


func current_music() -> String:
	return _music_name


func _fade_music(fade_in: int, fade_out: int) -> void:
	if _music_tween != null and _music_tween.is_valid():
		_music_tween.kill()
	_music_tween = null
	var fading_out := fade_out >= 0 and fade_out != fade_in and _music[fade_out].playing
	if fade_in < 0 and not fading_out:
		return  # nothing to fade (a Tween without tweeners is an error)
	_music_tween = create_tween().set_parallel(true)
	if fade_in >= 0:
		_music_tween.tween_method(_set_music_gain.bind(fade_in), _music_gain[fade_in], 1.0, MUSIC_FADE)
	if fading_out:
		_music_tween.tween_method(_set_music_gain.bind(fade_out), _music_gain[fade_out], 0.0, MUSIC_FADE)
		_music_tween.chain().tween_callback(_stop_if_silent.bind(fade_out))


func _set_music_gain(v: float, i: int) -> void:
	_music_gain[i] = v
	_apply_music(i)


func _apply_music(i: int) -> void:
	_music[i].volume_db = linear_to_db(maxf(_music_gain[i], 0.0001)) + _music_db[i]


func _stop_if_silent(i: int) -> void:
	if _music_gain[i] <= 0.001:
		_music[i].stop()


# ---------------------------------------------------------------------------
# Volume settings
# ---------------------------------------------------------------------------

## Bus volume, 0..1 linear amplitude ("Master", "SFX" or "Music"). Saved to user://audio.cfg.
func set_volume(bus: String, linear: float) -> void:
	_volume[bus] = clampf(linear, 0.0, 1.0)
	_apply_bus(bus)
	_queue_save()


func get_volume(bus: String) -> float:
	return float(_volume.get(bus, 1.0))


## Mute or unmute everything. Returns the new state.
func toggle_mute() -> bool:
	set_muted(not _muted)
	return _muted


func set_muted(on: bool) -> void:
	_muted = on
	_apply_bus("Master")
	_queue_save()


func is_muted() -> bool:
	return _muted


func _apply_bus(bus: String) -> void:
	var idx := AudioServer.get_bus_index(bus)
	if idx < 0:
		return
	var v := get_volume(bus)
	AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.0001)) + float(MAKEUP_DB.get(bus, 0.0)))
	AudioServer.set_bus_mute(idx, v <= 0.001 or (bus == "Master" and _muted))


func _ensure_bus(bus: String) -> void:
	if AudioServer.get_bus_index(bus) != -1:
		return
	AudioServer.add_bus()
	var idx := AudioServer.bus_count - 1
	AudioServer.set_bus_name(idx, bus)
	AudioServer.set_bus_send(idx, "Master")


## A hard limiter on Master (ceiling -1 dBFS) so stacked sounds never clip.
func _ensure_limiter() -> void:
	for i in AudioServer.get_bus_effect_count(0):
		if AudioServer.get_bus_effect(0, i) is AudioEffectHardLimiter:
			return
	var lim := AudioEffectHardLimiter.new()
	lim.ceiling_db = -1.0
	AudioServer.add_bus_effect(0, lim)


func _load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(CFG_PATH) == OK:
		for bus: String in DEFAULT_VOLUME:
			_volume[bus] = clampf(float(cfg.get_value("volume", bus, DEFAULT_VOLUME[bus])), 0.0, 1.0)
		_muted = bool(cfg.get_value("volume", "muted", false))
	for bus: String in _volume:
		_apply_bus(bus)


## Slider drags change the volume many times a second; write the file once they settle.
func _queue_save() -> void:
	if _save_queued or not is_inside_tree():
		return
	_save_queued = true
	get_tree().create_timer(0.5, true).timeout.connect(_save_settings)


func _save_settings() -> void:
	_save_queued = false
	var cfg := ConfigFile.new()
	for bus: String in _volume:
		cfg.set_value("volume", bus, _volume[bus])
	cfg.set_value("volume", "muted", _muted)
	cfg.save(CFG_PATH)


# ---------------------------------------------------------------------------
# Automatic UI sounds
# ---------------------------------------------------------------------------

func _hook_tree(node: Node) -> void:
	_on_node_added(node)
	for c in node.get_children(true):
		_hook_tree(c)


func _on_node_added(node: Node) -> void:
	if node.has_meta(HOOKED):
		return
	if node is BaseButton:
		var b := node as BaseButton
		node.set_meta(HOOKED, true)
		b.mouse_entered.connect(_on_button_hover.bind(b))
		b.focus_entered.connect(_on_button_focus.bind(b))
		b.pressed.connect(_on_button_pressed.bind(b))
	elif node is Slider or node is SpinBox:
		var r := node as Range
		node.set_meta(HOOKED, true)
		r.value_changed.connect(_on_range_changed.bind(r))
	elif node is PopupMenu:  # OptionButton / MenuButton lists
		var m := node as PopupMenu
		node.set_meta(HOOKED, true)
		m.id_focused.connect(_on_menu_focus.bind(m))
		m.id_pressed.connect(_on_menu_pressed.bind(m))


## A node is silent when it, or any of its parents, has the "no_sfx" meta set.
func _opted_out(node: Node) -> bool:
	var n := node
	while n != null:
		if n.has_meta(NO_SFX) and bool(n.get_meta(NO_SFX)):
			return true
		n = n.get_parent()
	return false


func _hover_tick(node: Node) -> void:
	if _opted_out(node):
		return
	var now := Time.get_ticks_msec()
	if now - _last_hover < HOVER_GAP_MS:
		return
	_last_hover = now
	play_varied("ui_hover", 0.0, 0.04)


func _on_button_hover(b: BaseButton) -> void:
	if not b.disabled:
		_hover_tick(b)


## Keyboard / gamepad navigation; mouse clicks also grab focus, so skip those.
func _on_button_focus(b: BaseButton) -> void:
	if b.disabled or b.get_global_rect().has_point(b.get_global_mouse_position()):
		return
	_hover_tick(b)


func _on_button_pressed(b: BaseButton) -> void:
	if _opted_out(b):
		return
	if b.toggle_mode:
		play("ui_toggle", 0.0, 1.06 if b.button_pressed else 0.94)
	else:
		play_varied("ui_click", 0.0, 0.03)


func _on_menu_focus(_id: int, m: PopupMenu) -> void:
	_hover_tick(m)


func _on_menu_pressed(_id: int, m: PopupMenu) -> void:
	if not _opted_out(m):
		play_varied("ui_click", 0.0, 0.03)


## Only user changes tick (focused or under the mouse), not values set from code.
func _on_range_changed(_value: float, r: Range) -> void:
	if not r.is_visible_in_tree() or _opted_out(r):
		return
	if not (r.has_focus() or r.get_global_rect().has_point(r.get_global_mouse_position())):
		return
	var now := Time.get_ticks_msec()
	if now - _last_slider < SLIDER_GAP_MS:
		return
	_last_slider = now
	var t := 0.5
	if r.max_value > r.min_value:
		t = clampf((r.value - r.min_value) / (r.max_value - r.min_value), 0.0, 1.0)
	play("ui_slider", 0.0, 0.85 + 0.35 * t)  # pitch rises with the value
