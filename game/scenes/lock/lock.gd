class_name LockScreen
extends Control
## Countdown to the lock while the seed's commitment sits on-chain, then the
## server reveals the seed, simulates and posts the result.

signal finished(race: Dictionary)
signal back

const STEPS := [
	["create", "Race created, seed commitment posted"],
	["enter", "6 setups locked on-chain"],
	["reveal", "Seed revealed, checked by the program"],
	["result", "Race simulated, result hash posted"],
	["settle", "Positions and XP settled on drivers"],
]

var race: Dictionary
var _countdown: Label
var _phase: Label
var _steps_box: VBoxContainer
var _poll_timer := 0.0
var _polling := false
var _done := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(MenuBackdrop.new())
	var shade := ColorRect.new()
	shade.color = Color(Ui.BG, 0.8)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(shade)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	add_child(margin)
	var col := Ui.vbox(6)
	margin.add_child(col)

	col.add_child(Ui.label(String(race.get("trackName", "")).to_upper(), Ui.SIZE_SMALL, Ui.INK_2))
	_phase = Ui.label("SETUPS LOCK IN", Ui.SIZE_HEADING, Ui.INK, true)
	col.add_child(_phase)
	_countdown = Ui.label("", 48, Ui.RED, true)
	col.add_child(_countdown)

	var commit := Ui.panel()
	col.add_child(commit)
	var commit_box := Ui.vbox(2)
	commit.add_child(commit_box)
	commit_box.add_child(Ui.label("SEED COMMITMENT ON SOLANA (SHA-256)", Ui.SIZE_SMALL, Ui.INK_2))
	commit_box.add_child(Ui.label(String(race.get("commitment", "")), Ui.SIZE_SMALL, Ui.INK))
	commit_box.add_child(Ui.label("Nobody, not even us, can change the race after this.", Ui.SIZE_SMALL, Ui.INK_2))

	_steps_box = Ui.vbox(3)
	col.add_child(_steps_box)
	_render_steps()


func _process(delta: float) -> void:
	var left := int(race.get("lockTs", 0)) - int(Time.get_unix_time_from_system())
	if left > 0:
		_countdown.text = "0:%02d" % left
	else:
		_phase.text = "LOCKED · REVEALING AND RACING"
		_countdown.text = "0:00"
	_poll_timer -= delta
	if _poll_timer <= 0.0 and not _polling and not _done:
		_poll_timer = 1.5
		_poll()


func _poll() -> void:
	_polling = true
	var fresh: Variant = await Api.get_json("/api/races/%d" % int(race["raceId"]))
	_polling = false
	if not fresh is Dictionary:
		return
	race = fresh
	_render_steps()
	match String(race.get("status", "")):
		"finished":
			_done = true
			await get_tree().create_timer(1.0).timeout
			finished.emit(race)
		"failed":
			_done = true
			_phase.text = "SOMETHING WENT WRONG"
			_steps_box.add_child(Ui.label(String(race.get("error", "unknown error")), Ui.SIZE_SMALL, Ui.RED))
			var b := Ui.button("BACK TO RACE DAY")
			b.pressed.connect(func() -> void: back.emit())
			_steps_box.add_child(b)


func _render_steps() -> void:
	for c in _steps_box.get_children():
		c.queue_free()
	var txs: Dictionary = race.get("txs", {})
	for step: Array in STEPS:
		var key: String = step[0]
		var done := txs.has(key)
		var row := Ui.hbox(6)
		row.add_child(Ui.label("•" if done else "-", Ui.SIZE_BODY, Ui.RED if done else Ui.INK_3))
		var text := Ui.label(step[1], Ui.SIZE_BODY, Ui.INK if done else Ui.INK_3)
		text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(text)
		if done:
			var link := Ui.button("TX  >")
			link.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
			link.pressed.connect(Api.open_tx.bind(String(txs[key])))
			row.add_child(link)
		_steps_box.add_child(row)
