class_name HubScreen
extends Control
## The race weekend menu, over a live view of the circuit: practice and
## qualifying (you drive, laps verified on Solana), the race you call from the
## pit wall, the garage, the timesheet and your driver.

signal practice
signal qualifying
signal race
signal garage
signal passes
signal tutorial

var _board: VBoxContainer
var _driver_box: VBoxContainer
var _status: Label
var _closes: Label
var _items := {}
var _showcase: CarShowcase
var _account_chip: Button


func _refresh_account() -> void:
	if Profile.is_signed_in():
		_account_chip.text = Profile.team_name.to_upper() + ("  ·  WALLET LINKED" if Profile.wallet != "" else "  ·  ACCOUNT")
		_account_chip.tooltip_text = "Your account: link a Solana wallet or sign out."
	else:
		_account_chip.text = "GUEST  ·  SIGN IN / CREATE ACCOUNT"
		_account_chip.tooltip_text = "Save your progress and show your team name on the timesheet."


func _open_account() -> void:
	var panel := AccountPanel.new()
	add_child(panel)
	await panel.closed
	panel.queue_free()
	Profile.account_prompted = true
	Profile.save()
	_refresh_account()
	_load()


func _full_look() -> Dictionary:
	var look := Catalog.car_look()
	for area: String in ["suspension", "power_unit"]:
		look[area] = String(Catalog.equipped_part(area).get("concept", ""))
	return look


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(MenuBackdrop.new())
	Sfx.music("music_menu")
	_shade()
	_build()
	_load()


func _shade() -> void:
	var g := Gradient.new()
	g.set_color(0, Color(Ui.BG, 0.96))
	g.set_color(1, Color(Ui.BG, 0.0))
	g.add_point(0.45, Color(Ui.BG, 0.82))
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill_from = Vector2(0, 0)
	tex.fill_to = Vector2(1, 0)
	tex.width = 256
	tex.height = 4
	var left := TextureRect.new()
	left.texture = tex
	left.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	left.anchor_right = 0.62
	left.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	left.stretch_mode = TextureRect.STRETCH_SCALE
	left.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(left)
	var right := TextureRect.new()
	right.texture = tex
	right.flip_h = true
	right.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	right.anchor_left = 0.55
	right.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	right.stretch_mode = TextureRect.STRETCH_SCALE
	right.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(right)
	var vignette := PartCard.texture("res://assets/sprites/ui/vignette.png")
	if vignette:
		var v := TextureRect.new()
		v.texture = vignette
		v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		v.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		v.stretch_mode = TextureRect.STRETCH_SCALE
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(v)


func _build() -> void:
	# Left: brand and the menu
	var left := Ui.vbox(6)
	left.position = Vector2(22, 18)
	left.custom_minimum_size = Vector2(250, 0)
	add_child(left)
	var logo_tex := PartCard.texture("res://assets/sprites/ui/logo.png")
	if logo_tex:
		var logo := TextureRect.new()
		logo.texture = logo_tex
		logo.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		logo.custom_minimum_size = logo_tex.get_size()
		logo.stretch_mode = TextureRect.STRETCH_KEEP
		left.add_child(logo)
	else:
		left.add_child(Ui.label("PIT WALL", 40, Ui.INK, true))
	var sub := Ui.label("RACE WEEKEND  ·  MTKVARI CIRCUIT  ·  3.2 KM", Ui.SIZE_SMALL, Ui.INK_2, true)
	left.add_child(sub)
	_closes = Ui.label("", Ui.SIZE_SMALL, Ui.YELLOW)
	left.add_child(_closes)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 6)
	left.add_child(gap)
	_items["tutorial"] = _menu_item("ROOKIE TEST", "Two minutes: learn to drive the car." if not Profile.tutorial_done else "Replay the driving tutorial.", "icon_play", tutorial, not Profile.tutorial_done)
	_items["practice"] = _menu_item("PRACTICE", "Learn the track. Racing line on, setup free.", "icon_stopwatch", practice)
	_items["qualifying"] = _menu_item("QUALIFYING", "Set your fastest lap. Verified on Solana.", "icon_flag", qualifying, Profile.tutorial_done)
	_items["race"] = _menu_item("RACE", "Five laps from your grid slot. One pit stop.", "icon_trophy", race)
	_items["garage"] = _menu_item("GARAGE", "Fit parts, tune the car, open packs.", "icon_wrench", garage)
	_items["passes"] = _menu_item("RACE PASSES", "Stake a pass, race equal cars, win the pot.", "icon_coin", passes)
	for k: String in ["tutorial", "practice", "qualifying", "race", "passes", "garage"]:
		left.add_child(_items[k])
	if Profile.tutorial_done:
		(_items["tutorial"] as Control).custom_minimum_size.y = 30
	else:
		_tag("tutorial", "START HERE")

	# Account chip, top right
	_account_chip = Ui.button("")
	_account_chip.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	_account_chip.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_account_chip.position = Vector2(-262, 8)
	_account_chip.custom_minimum_size = Vector2(242, 0)
	_account_chip.pressed.connect(_open_account)
	add_child(_account_chip)
	_refresh_account()

	# Footer
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.INK_3)
	_status.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_status.position = Vector2(24, -18)
	_status.size = Vector2(400, 12)
	add_child(_status)

	# Right: timesheet and driver
	var right := Ui.vbox(6)
	right.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	right.position = Vector2(-262, 34)
	right.custom_minimum_size = Vector2(242, 0)
	add_child(right)
	var sheet := _glass_panel()
	right.add_child(sheet)
	var sv := Ui.vbox(2)
	sheet.add_child(sv)
	var head := Ui.hbox(6)
	head.add_child(Ui.label("QUALIFYING", Ui.SIZE_SMALL, Ui.RED, true))
	var live := Ui.label("TIMESHEET", Ui.SIZE_SMALL, Ui.INK_2, true)
	head.add_child(live)
	sv.add_child(head)
	_board = Ui.vbox(1)
	sv.add_child(_board)
	var driver := _glass_panel()
	right.add_child(driver)
	_driver_box = Ui.vbox(3)
	driver.add_child(_driver_box)

	# Your car, in 3D, on a turntable: click to open the garage
	var car := CarShowcase.new()
	car.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	car.position = Vector2(-262, -128)
	car.size = Vector2(242, 112)
	car.custom_minimum_size = Vector2(242, 112)
	add_child(car)
	car.set_parts(_full_look())
	car.set_colors(Ui.RED, Ui.INK)
	_showcase = car
	var go := Ui.button("YOUR CAR  ·  GARAGE  >")
	go.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	go.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	go.position = Vector2(-262, -22)
	go.pressed.connect(func() -> void: garage.emit())
	add_child(go)


func _glass_panel() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.085, 0.1, 0.86)
	sb.border_color = Color(1, 1, 1, 0.08)
	sb.set_border_width_all(1)
	sb.border_width_top = 2
	sb.set_content_margin_all(8)
	p.add_theme_stylebox_override("panel", sb)
	return p


## A big menu entry: icon, title, hint; slides and lights up on hover.
func _menu_item(title: String, hint: String, icon: String, sig: Signal, primary: bool = false) -> Control:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_ALL
	b.custom_minimum_size = Vector2(250, 44)
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.1, 0.105, 0.12, 0.78) if not primary else Color(Ui.RED_DARK, 0.92)
	normal.border_color = Ui.RED if primary else Color(1, 1, 1, 0.07)
	normal.border_width_left = 3
	normal.set_border_width_all(1)
	normal.border_width_left = 3
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.16, 0.165, 0.19, 0.92) if not primary else Color(0.42, 0.13, 0.12, 0.95)
	hover.border_color = Ui.RED
	hover.border_width_left = 6
	for st: String in ["normal", "focus", "disabled"]:
		b.add_theme_stylebox_override(st, normal)
	for st: String in ["hover", "pressed", "hover_pressed"]:
		b.add_theme_stylebox_override(st, hover)
	b.add_theme_stylebox_override("focus", hover)
	b.pressed.connect(func() -> void: sig.emit())
	b.tooltip_text = hint
	var tex := PartCard.texture("res://assets/sprites/ui/%s.png" % icon)
	var x := 12.0
	if tex:
		var ic := TextureRect.new()
		ic.texture = tex
		ic.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		ic.position = Vector2(12, 14)
		ic.size = Vector2(16, 16)
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		ic.modulate = Ui.INK if not primary else Color.WHITE
		b.add_child(ic)
		x = 36.0
	var t := Ui.label(title, Ui.SIZE_HEADING, Ui.INK, true)
	t.position = Vector2(x, 5)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(t)
	var h := Ui.label(hint, Ui.SIZE_SMALL, Ui.INK_2 if not primary else Ui.INK)
	h.position = Vector2(x, 25)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(h)
	var tag := Ui.label("", Ui.SIZE_SMALL, Ui.YELLOW, true)
	tag.name = "Tag"
	tag.position = Vector2(150, 7)
	tag.size = Vector2(92, 12)
	tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(tag)
	b.mouse_entered.connect(func() -> void:
		create_tween().tween_property(t, "position:x", x + 5, 0.08)
		create_tween().tween_property(h, "position:x", x + 5, 0.08))
	b.mouse_exited.connect(func() -> void:
		create_tween().tween_property(t, "position:x", x, 0.12)
		create_tween().tween_property(h, "position:x", x, 0.12))
	return b


func _tag(item: String, text: String, color: Color = Ui.YELLOW) -> void:
	var l := (_items[item] as Control).get_node("Tag") as Label
	l.text = text
	l.add_theme_color_override("font_color", color)


func _load() -> void:
	if not Profile.is_signed_in() and not Profile.account_prompted and Profile.tutorial_done:
		Profile.account_prompted = true
		Profile.save()
		_open_account.call_deferred()
		return
	_show_driver({})
	var info: Variant = await Api.get_json("/api/event?player=" + Profile.id)
	if not info is Dictionary:
		_status.text = "OFFLINE · can't reach the server at %s · practice still works" % Api.base_url
		return
	Profile.event = info
	var you: Dictionary = (info as Dictionary).get("you", {})
	if you.get("setup") is Dictionary:
		for k: String in (you["setup"] as Dictionary):
			Profile.setup[k] = int(you["setup"][k])
	_show_driver((info as Dictionary).get("driver", {}))
	_show_board((info as Dictionary).get("leaderboard", []))
	var closes := int(float(info.get("closesAt", 0)) / 1000.0 - Time.get_unix_time_from_system())
	_closes.text = "QUALIFYING CLOSES IN %dH %02dM" % [closes / 3600, (closes % 3600) / 60] + ("  ·  PARC FERME" if Profile.setup_locked() else "")
	if you.get("bestUs") != null:
		_tag("qualifying", "P%d  %s" % [int(you.get("position", 0)), Ui.format_time(int(you["bestUs"]) / 1000)], Ui.INK)
		_tag("race", "GRID P%d" % int(you.get("position", 0)), Ui.INK)
	_status.text = "DEVNET  ·  EVERY QUALIFYING LAP RE-DRIVEN BY THE SERVER AND RECORDED ON SOLANA"
	if await Catalog.load_garage():
		if _showcase:
			_showcase.set_parts(_full_look())
		var packs := Catalog.unopened_packs()
		if packs > 0:
			_tag("garage", "%d PACK%s TO OPEN" % [packs, "" if packs == 1 else "S"])


func _show_driver(d: Dictionary) -> void:
	for c in _driver_box.get_children():
		c.queue_free()
	var head := Ui.hbox(6)
	head.add_child(Ui.label("YOUR DRIVER", Ui.SIZE_SMALL, Ui.INK_2, true))
	var lvl := Ui.label("LV %d" % int(d.get("level", 1)), Ui.SIZE_SMALL, Ui.YELLOW, true)
	lvl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lvl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(lvl)
	_driver_box.add_child(head)
	_driver_box.add_child(Ui.label(String(d.get("name", "Nino Beridze")).to_upper(), Ui.SIZE_HEADING, Ui.INK, true))
	var stats := Profile.stats()
	for key: String in ["braking", "cornering", "traction", "energy"]:
		var row := Ui.hbox(6)
		var l := Ui.label(key.to_upper(), Ui.SIZE_SMALL, Ui.INK_2)
		l.custom_minimum_size = Vector2(64, 0)
		row.add_child(l)
		row.add_child(Ui.stat_bar(int(stats[key])))
		var v := Ui.label(str(stats[key]), Ui.SIZE_SMALL, Ui.INK, true)
		v.custom_minimum_size = Vector2(16, 0)
		row.add_child(v)
		_driver_box.add_child(row)


func _show_board(rows: Array) -> void:
	for c in _board.get_children():
		c.queue_free()
	var leader := 0
	var shown := 0
	for r: Dictionary in rows:
		if shown >= 9:
			break
		shown += 1
		var us := int(r.get("us", 0))
		if leader == 0:
			leader = us
		var you := bool(r.get("you", false)) or String(r.get("player", "")) == Profile.id
		var row := Ui.hbox(4)
		if you:
			var mark := ColorRect.new()
			mark.color = Ui.RED
			mark.custom_minimum_size = Vector2(2, 10)
			row.add_child(mark)
		row.add_child(_cell(str(int(r.get("position", 0))), 14, Ui.RED if you else Ui.INK_2, true))
		row.add_child(_cell(String(r.get("name", "")).to_upper(), 104, Ui.INK if you else (Ui.INK_2 if bool(r.get("ai", false)) else Ui.INK), you))
		row.add_child(_cell(Ui.format_time(us / 1000) if us == leader else "+%.3f" % ((us - leader) / 1000000.0), 50, Ui.INK if us == leader else Ui.INK_2, us == leader))
		if r.get("tx") is String:
			var b := Button.new()
			b.text = "SOL >"
			b.flat = true
			b.focus_mode = Control.FOCUS_NONE
			b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
			b.add_theme_color_override("font_color", Color("a855f7"))
			var tx: String = r["tx"]
			b.pressed.connect(func() -> void: Api.open_tx(tx))
			row.add_child(b)
		else:
			row.add_child(_cell("AI" if bool(r.get("ai", false)) else "OK", 30, Ui.INK_3, false))
		_board.add_child(row)
	if rows.is_empty():
		_board.add_child(Ui.label("No laps yet. Be the first.", Ui.SIZE_SMALL, Ui.INK_2))


func _cell(text: String, width: float, color: Color, bold: bool) -> Label:
	var l := Ui.label(text, Ui.SIZE_SMALL, color, bold)
	l.custom_minimum_size = Vector2(width, 0)
	l.clip_text = true
	return l
