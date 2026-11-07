class_name ResultsScreen
extends Control
## Finishing order, why you finished there, and one-click verification on Solana.

signal next_race

const XP := [50, 35, 25, 18, 12, 8]
const DESIGN_NAMES := ["High downforce", "Balanced", "Low drag"]
const BEST_DESIGN := {"street": 0, "speed": 2, "mixed": 1}

var race: Dictionary
var _verify_box: VBoxContainer
var _verify_button: Button


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(MenuBackdrop.new())
	var shade := ColorRect.new()
	shade.color = Color(Ui.BG, 0.8)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(shade)
	var replay: Dictionary = race["replay"]
	var order: Array[int] = []
	for o: Variant in replay["order"]:
		order.append(int(o))  # JSON numbers arrive as floats
	var teams: Array = replay["teams"]
	var laps: Array = replay["laps"]
	var slot := int(race.get("playerSlot", 0))
	var position := order.find(slot) + 1
	var retired := (laps[slot] as Array).has(null)

	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	add_child(margin)
	var cols := Ui.hbox(14)
	margin.add_child(cols)

	# Left: your result + why
	var left := Ui.vbox(4)
	left.custom_minimum_size = Vector2(250, 0)
	cols.add_child(left)
	left.add_child(Ui.label(String(race.get("trackName", "")).to_upper(), Ui.SIZE_SMALL, Ui.INK_2))
	left.add_child(Ui.label("DNF" if retired else "P%d" % position, 64, Ui.RED if position == 1 and not retired else Ui.INK, true))
	var verdict := "YOU WON" if position == 1 and not retired else ("RETIRED" if retired else "FINISHED P%d" % position)
	left.add_child(Ui.label("%s · +%d XP" % [verdict, XP[position - 1] if position <= XP.size() else 5], Ui.SIZE_HEADING, Ui.INK, true))
	left.add_child(Ui.label("WHY", Ui.SIZE_SMALL, Ui.INK_2))
	for line: String in _why(replay, slot, retired):
		var l := Ui.label(line, Ui.SIZE_BODY, Ui.INK)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		left.add_child(l)
	var push := Control.new()
	push.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left.add_child(push)
	var again := Ui.button("BACK TO WEEKEND", true)
	again.custom_minimum_size = Vector2(0, 26)
	again.pressed.connect(func() -> void: next_race.emit())
	left.add_child(again)

	# Right: classification + verification
	var right := Ui.vbox(3)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(right)
	right.add_child(Ui.label("CLASSIFICATION", Ui.SIZE_SMALL, Ui.INK_2))
	var winner_time: Variant = (laps[order[0]] as Array)[-1]
	for i in order.size():
		var c: int = order[i]
		var row := Ui.hbox(6)
		var name := Ui.label("P%d  %s" % [i + 1, String(teams[c]).to_upper()], Ui.SIZE_BODY, Ui.RED if c == slot else Ui.INK)
		name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(name)
		var t: Variant = (laps[c] as Array)[-1]
		var time_text := "DNF" if t == null else (Ui.format_time(int(t)) if i == 0 else "+%.1fs" % ((float(t) - float(winner_time)) / 1000.0))
		row.add_child(Ui.label(time_text, Ui.SIZE_BODY, Ui.INK_2))
		right.add_child(row)

	var verify_panel := Ui.panel()
	verify_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(verify_panel)
	_verify_box = Ui.vbox(3)
	verify_panel.add_child(_verify_box)
	_verify_box.add_child(Ui.label("PROVABLY FAIR", Ui.SIZE_SMALL, Ui.INK_2))
	_verify_box.add_child(Ui.label("Re-run this race from Solana data alone.", Ui.SIZE_BODY))
	_verify_button = Ui.button("VERIFY ON SOLANA")
	_verify_button.pressed.connect(_verify)
	_verify_box.add_child(_verify_button)


func _why(replay: Dictionary, slot: int, retired: bool) -> Array[String]:
	var setups: Array = race.get("setups", [])
	if setups.is_empty():
		return []
	var s: Dictionary = setups[slot]
	var track_type := String((replay["track"] as Dictionary)["type"])
	var design := int(s["design"])
	var best := int(BEST_DESIGN.get(track_type, 1))
	var lines: Array[String] = []
	if design == best:
		lines.append("+ %s suits a %s circuit." % [DESIGN_NAMES[design], track_type])
	else:
		lines.append("- %s cost time here. %s suits %s circuits." % [DESIGN_NAMES[design], DESIGN_NAMES[best], track_type])
	match int(s["tyre"]):
		0:
			lines.append("+ Softs were quick but wore fast." if int(s["stops"]) == 2 else "- Softs on one stop faded late in each stint.")
		1:
			lines.append("+ Mediums balanced pace and wear.")
		2:
			lines.append("- Hards lasted but gave away pace.")
	var risk := int(s["risk"])
	if retired:
		lines.append("- Risk %d ended your race." % risk)
	elif risk > 65:
		lines.append("+ Pushing at risk %d gained time, but could have cost the race." % risk)
	elif risk < 30:
		lines.append("- Playing safe at risk %d cost time every lap." % risk)
	return lines


func _verify() -> void:
	_verify_button.disabled = true
	_verify_button.text = "RE-RUNNING FROM CHAIN DATA…"
	var v: Variant = await Api.get_json("/api/races/%d/verify" % int(race["raceId"]))
	_verify_button.queue_free()
	if not v is Dictionary:
		_verify_box.add_child(Ui.label("Couldn't reach the verifier.", Ui.SIZE_BODY, Ui.RED))
		return
	var r: Dictionary = v
	var ok := bool(r["verified"])
	_verify_box.add_child(Ui.label("VERIFIED" if ok else "MISMATCH", Ui.SIZE_HEADING, Ui.RED if ok else Ui.YELLOW, true))
	_verify_box.add_child(Ui.label("Seed matches commitment: %s" % ("yes" if r["seedMatchesCommitment"] else "NO"), Ui.SIZE_SMALL))
	_verify_box.add_child(Ui.label("On-chain result  %s" % Ui.short_hash(String(r["onChainResultHash"])), Ui.SIZE_SMALL, Ui.INK_2))
	_verify_box.add_child(Ui.label("Re-run result    %s" % Ui.short_hash(String(r["recomputedResultHash"])), Ui.SIZE_SMALL, Ui.INK_2))
	var links := Ui.hbox(3)
	var txs: Dictionary = race.get("txs", {})
	for key: String in ["create", "reveal", "result"]:
		if txs.has(key):
			var b := Ui.button("%s  >" % key.to_upper())
			b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
			b.pressed.connect(Api.open_tx.bind(String(txs[key])))
			links.add_child(b)
	_verify_box.add_child(links)
