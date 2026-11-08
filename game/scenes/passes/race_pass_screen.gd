class_name RacePassScreen
extends Control
## Race passes: buy an entry to a daily or weekly time trial with your wallet, drive the standard
## car (everyone drives the same car), and the fastest verified laps split the pot. The pool,
## the entries and the payouts are on Solana; on devnet the stakes are devnet SOL.

signal exited
signal drive(pool_id: int)

const TIER_COLORS := {"BRONZE": Color("c98a5a"), "SILVER": Color("c6c8d0"), "GOLD": Color("f2c230"), "SPRINT": Color("5ec8e5")}

var _info: Dictionary = {}
var _selected := 0
var _grid: GridContainer
var _detail: VBoxContainer
var _status: Label
var _wallet_chip: Button
var _busy := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	theme = Ui.theme
	add_child(MenuBackdrop.new())
	var shade := ColorRect.new()
	shade.color = Color(0.03, 0.035, 0.04, 0.72)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(shade)

	var top := Ui.hbox(8)
	top.position = Vector2(12, 10)
	add_child(top)
	var back := Ui.button("< WEEKEND")
	back.pressed.connect(func() -> void: exited.emit())
	top.add_child(back)
	top.add_child(Ui.label("RACE PASSES", Ui.SIZE_HEADING, Ui.INK, true))

	_wallet_chip = Ui.button("")
	_wallet_chip.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	_wallet_chip.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_wallet_chip.position = Vector2(-150, 10)
	_wallet_chip.custom_minimum_size = Vector2(138, 0)
	_wallet_chip.pressed.connect(_open_account)
	add_child(_wallet_chip)

	var intro := Ui.label("Buy a pass, then drive the standard car: everyone races the same car, so only driving counts. The fastest verified laps split the pot, paid out on Solana.", Ui.SIZE_SMALL, Ui.INK_2)
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.position = Vector2(14, 34)
	intro.custom_minimum_size = Vector2(600, 0)
	intro.size = Vector2(600, 0)
	add_child(intro)
	var devnet := Ui.label("DEVNET TEST · STAKES ARE DEVNET SOL WITH NO REAL VALUE · USDC ON MAINNET", Ui.SIZE_SMALL, Ui.YELLOW, true)
	devnet.position = Vector2(14, 56)
	add_child(devnet)

	_grid = GridContainer.new()
	_grid.columns = 3
	_grid.add_theme_constant_override("h_separation", 6)
	_grid.add_theme_constant_override("v_separation", 6)
	_grid.position = Vector2(14, 74)
	add_child(_grid)

	var panel := Ui.panel()
	panel.anchor_left = 0.53
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_left = 0
	panel.offset_right = -12
	panel.offset_top = 70
	panel.offset_bottom = -12
	add_child(panel)
	_detail = Ui.vbox(4)
	panel.add_child(_detail)

	_status = Ui.label("", Ui.SIZE_SMALL, Ui.YELLOW)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.anchor_top = 1.0
	_status.anchor_bottom = 1.0
	_status.offset_left = 14
	_status.offset_top = -30
	_status.custom_minimum_size = Vector2(320, 0)
	add_child(_status)
	_load()


func _load() -> void:
	var res: Variant = await Api.get_json("/api/passes?player=" + Profile.id)
	if not is_inside_tree():
		return
	if not res is Dictionary:
		_status.text = "Can't reach the server."
		return
	_info = res
	if _selected == 0:
		for p: Variant in _info.get("pools", []):
			if (p as Dictionary).get("you", {}).get("entered", false):
				_selected = int(p["id"])
				break
		if _selected == 0 and not (_info.get("pools", []) as Array).is_empty():
			_selected = int(_info["pools"][1 if (_info["pools"] as Array).size() > 1 else 0]["id"])
	_render()


func _pool(id: int) -> Dictionary:
	for p: Variant in _info.get("pools", []):
		if int((p as Dictionary).get("id", 0)) == id:
			return p
	return {}


func _tier(p: Dictionary) -> String:
	var n := String(p.get("name", ""))
	for t: String in TIER_COLORS.keys():
		if n.contains(t):
			return t
	return "SPRINT"


func _closes(p: Dictionary) -> String:
	var ms := int(p.get("closesAt", 0)) - int(Time.get_unix_time_from_system() * 1000.0)
	if p.get("settled") is Dictionary:
		return "PAID OUT"
	if ms <= 0:
		return "SETTLING"
	var m := ms / 60000
	if m >= 60 * 24:
		return "CLOSES IN %dD %dH" % [m / 1440, (m % 1440) / 60]
	if m >= 60:
		return "CLOSES IN %dH %02dM" % [m / 60, m % 60]
	return "CLOSES IN %dM %02dS" % [m, (ms / 1000) % 60]


func _sol(v: Variant) -> String:
	var f := float(v)
	return ("%.3f" % f).rstrip("0").rstrip(".") + " SOL"


func _render() -> void:
	var wallet: Variant = _info.get("wallet")
	_wallet_chip.text = ("WALLET  " + Ui.short_hash(String(wallet))) if wallet is String and wallet != "" else ("LINK A WALLET  >" if Profile.is_signed_in() else "SIGN IN  >")
	for c in _grid.get_children():
		c.queue_free()
	for p: Variant in _info.get("pools", []):
		_grid.add_child(_card(p))
	_detail_for(_pool(_selected))


func _card(p: Dictionary) -> Control:
	var tier := _tier(p)
	var col: Color = TIER_COLORS.get(tier, Ui.INK)
	var b := Button.new()
	b.custom_minimum_size = Vector2(104, 62)
	b.focus_mode = Control.FOCUS_NONE
	var sel := int(p.get("id", 0)) == _selected
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.095, 0.11, 0.92) if not sel else Color(0.15, 0.155, 0.18, 0.96)
	sb.border_color = col if sel else Color(1, 1, 1, 0.08)
	sb.set_border_width_all(1)
	sb.border_width_top = 3
	sb.border_color = col if sel else col.darkened(0.55)
	for st: String in ["normal", "hover", "pressed", "focus"]:
		b.add_theme_stylebox_override(st, sb)
	b.pressed.connect(func() -> void:
		_selected = int(p["id"])
		Sfx.play("ui_click")
		_render())
	var v := Ui.vbox(1)
	v.position = Vector2(6, 5)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(v)
	var kind := String(p.get("kind", "")).to_upper()
	v.add_child(_nomouse(Ui.label("%s  %s" % [kind, tier] if tier != "SPRINT" else String(p.get("name", "")), Ui.SIZE_SMALL, col, true)))
	v.add_child(_nomouse(Ui.label(_sol(p.get("stakeSol", 0)), Ui.SIZE_BODY, Ui.INK, true)))
	v.add_child(_nomouse(Ui.label("POT %s · %d IN" % [_sol(p.get("potSol", 0)), int(p.get("entrants", 0))], Ui.SIZE_SMALL, Ui.INK_2)))
	var you: Dictionary = p.get("you", {})
	var line := _closes(p)
	var line_col := Ui.INK_3
	if you.get("entered", false):
		line = ("P%d · " % int(you.get("rank", 0)) if int(you.get("rank", 0)) > 0 else "ENTERED · ") + line
		line_col = Color("3ecf6a")
	v.add_child(_nomouse(Ui.label(line, Ui.SIZE_SMALL, line_col)))
	return b


func _nomouse(c: Control) -> Control:
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


func _detail_for(p: Dictionary) -> void:
	for c in _detail.get_children():
		c.queue_free()
	if p.is_empty():
		return
	var tier := _tier(p)
	_detail.add_child(Ui.label(String(p.get("name", "")), Ui.SIZE_HEADING, TIER_COLORS.get(tier, Ui.INK), true))
	_detail.add_child(Ui.label("STAKE %s   ·   POT %s   ·   %d ENTERED" % [_sol(p.get("stakeSol", 0)), _sol(p.get("potSol", 0)), int(p.get("entrants", 0))], Ui.SIZE_SMALL, Ui.INK, true))
	_detail.add_child(Ui.label(_closes(p), Ui.SIZE_SMALL, Ui.INK_2))
	var ex: Array = p.get("exampleSol", [])
	if ex.size() >= 3:
		_detail.add_child(Ui.label("WITH 20 DRIVERS:  1ST %s  ·  2ND %s  ·  3RD %s" % [_sol(ex[0]), _sol(ex[1]), _sol(ex[2])], Ui.SIZE_SMALL, Ui.YELLOW))
	var rules: Dictionary = _info.get("rules", {})
	var r := Ui.label("Top %d%% are paid, each at least %.1fx the stake. %d%% of the pot goes to Pit Wall. Under %d drivers, everyone is refunded." % [int(rules.get("paidPct", 20)), float(rules.get("minPayoutX", 1.5)), int(rules.get("rakePct", 10)), int(rules.get("minEntrants", 4))], Ui.SIZE_SMALL, Ui.INK_3)
	r.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_detail.add_child(r)

	_detail.add_child(Ui.label("STANDINGS", Ui.SIZE_SMALL, Ui.INK_2, true))
	var standings: Array = p.get("standings", [])
	if standings.is_empty():
		_detail.add_child(Ui.label("No laps yet. Be the first.", Ui.SIZE_SMALL, Ui.INK_3))
	for s: Variant in standings.slice(0, 7):
		var row := Ui.hbox(6)
		var me: bool = (s as Dictionary).get("you", false)
		row.add_child(Ui.label("%d" % int(s["rank"]), Ui.SIZE_SMALL, Ui.INK_3, true))
		var name := Ui.label(String(s["name"]).to_upper(), Ui.SIZE_SMALL, Ui.RED if me else Ui.INK)
		name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name.clip_text = true
		row.add_child(name)
		row.add_child(Ui.label(Ui.format_time(int(s["us"]) / 1000), Ui.SIZE_SMALL, Ui.INK))
		var win := float(s.get("winSol", 0))
		row.add_child(Ui.label(("+" + _sol(win)) if win > 0 else "", Ui.SIZE_SMALL, Color("3ecf6a")))
		_detail.add_child(row)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_detail.add_child(spacer)
	var you: Dictionary = p.get("you", {})
	var settled: Variant = p.get("settled")
	if settled is Dictionary:
		var txs: Array = (settled as Dictionary).get("txs", [])
		_detail.add_child(Ui.label("PAID OUT ON SOLANA" if not (settled as Dictionary).get("refund", false) else "REFUNDED ON SOLANA", Ui.SIZE_SMALL, Color("3ecf6a"), true))
		if not txs.is_empty():
			var view := Ui.button("VIEW PAYOUT TRANSACTION  >")
			view.pressed.connect(func() -> void: Api.open_tx(String(txs[0])))
			_detail.add_child(view)
		return
	var open := int(p.get("closesAt", 0)) > int(Time.get_unix_time_from_system() * 1000.0)
	if you.get("entered", false):
		var go := Ui.button("DRIVE A PASS LAP  >", true)
		go.custom_minimum_size = Vector2(0, 24)
		go.disabled = not open
		go.tooltip_text = "Qualifying-style lap on the standard car. Your best verified lap counts in every pass you hold."
		go.pressed.connect(func() -> void: drive.emit(int(p["id"])))
		_detail.add_child(go)
		if String(you.get("tx", "")) != "":
			var view := Ui.button("YOUR PASS ON SOLANA  >")
			view.pressed.connect(func() -> void: Api.open_tx(String(you["tx"])))
			_detail.add_child(view)
	else:
		var buy := Ui.button("BUY PASS  ·  %s" % _sol(p.get("stakeSol", 0)), true)
		buy.custom_minimum_size = Vector2(0, 24)
		buy.disabled = not open
		buy.pressed.connect(_buy.bind(int(p["id"])))
		_detail.add_child(buy)


func _open_account() -> void:
	var a := AccountPanel.new()
	add_child(a)
	a.closed.connect(func() -> void:
		a.queue_free()
		_load())


func _buy(id: int) -> void:
	if _busy:
		return
	if not Profile.is_signed_in():
		_status.text = "Create an account first, then link a Solana wallet."
		_open_account()
		return
	if not (_info.get("wallet") is String) or String(_info.get("wallet")) == "":
		_status.text = "Link a Solana wallet to your account to buy passes."
		_open_account()
		return
	if not SolanaWallet.available():
		_status.text = "Buying passes works in the web version of the game."
		return
	_busy = true
	_status.add_theme_color_override("font_color", Ui.YELLOW)
	_status.text = "Preparing your pass on Solana…"
	var res: Variant = await Api.post_json("/api/passes/%d/enter" % id, {"player": Profile.id})
	if not res is Dictionary:
		_busy = false
		_status.text = Api.last_error if Api.last_error != "" else "Can't reach the server."
		return
	var grant: Variant = (res as Dictionary).get("grant")
	if grant is Dictionary:
		_status.text = "Sent %s devnet SOL to your wallet for testing. Now approve the pass in your wallet." % _sol((grant as Dictionary).get("sol", 0))
	else:
		_status.text = "Approve the pass in your wallet (%s)." % _sol((res as Dictionary).get("stakeSol", 0))
	await SolanaWallet.connect_wallet(get_tree())
	var signed := await SolanaWallet.sign_transaction(get_tree(), String((res as Dictionary).get("tx", "")))
	if signed == "":
		_busy = false
		_status.text = SolanaWallet.last_error if SolanaWallet.last_error != "" else "The wallet didn't sign."
		return
	_status.text = "Sending to Solana…"
	var done: Variant = await Api.post_json("/api/passes/%d/confirm" % id, {"player": Profile.id, "tx": signed})
	_busy = false
	if done is Dictionary and bool((done as Dictionary).get("entered", false)):
		Sfx.play("verified")
		_status.add_theme_color_override("font_color", Color("3ecf6a"))
		_status.text = "Race pass bought. Drive a lap: your best verified lap counts."
		_load()
	else:
		Sfx.play("ui_error")
		_status.text = Api.last_error if Api.last_error != "" else "The pass didn't go through."
