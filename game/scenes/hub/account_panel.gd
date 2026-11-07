class_name AccountPanel
extends Control
## Sign in, create an account, or play as a guest. Signed in, link a Solana
## wallet (or sign in with one next time). A guest's progress moves into the
## new account when they create one.

signal closed

var _mode := "signin"  # signin | create | account
var _box: VBoxContainer
var _name: LineEdit
var _pass: LineEdit
var _status: Label
var _busy := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	theme = Ui.theme
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.025, 0.03, 0.78)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.98)
	sb.border_color = Ui.RED
	sb.border_width_top = 3
	sb.set_content_margin_all(14)
	panel.add_theme_stylebox_override("panel", sb)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(280, 0)
	panel.position = Vector2(-140, -120)
	add_child(panel)
	_box = Ui.vbox(6)
	panel.add_child(_box)
	_mode = "account" if Profile.is_signed_in() else "signin"
	_render()


func _clear() -> void:
	for c in _box.get_children():
		c.queue_free()


func _field(placeholder: String, secret: bool) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.secret = secret
	e.custom_minimum_size = Vector2(0, 22)
	e.add_theme_font_size_override("font_size", Ui.SIZE_BODY)
	e.text_submitted.connect(func(_t: String) -> void: _submit())
	return e


func _render() -> void:
	_clear()
	match _mode:
		"account":
			_box.add_child(Ui.label("YOUR ACCOUNT", Ui.SIZE_SMALL, Ui.INK_2, true))
			_box.add_child(Ui.label(Profile.team_name.to_upper(), Ui.SIZE_TITLE, Ui.INK, true))
			var w := Profile.wallet
			_box.add_child(Ui.label(("WALLET  " + Ui.short_hash(w)) if w != "" else "NO WALLET LINKED", Ui.SIZE_SMALL, Color("a855f7") if w != "" else Ui.INK_3, true))
			if w == "":
				var link := Ui.button("LINK SOLANA WALLET", true)
				link.tooltip_text = "Prove you own a wallet by signing a message (no transaction, no fee). Parts you trade later go to this wallet."
				link.pressed.connect(_link_wallet)
				_box.add_child(link)
			var out := Ui.button("SIGN OUT")
			out.pressed.connect(func() -> void:
				Profile.sign_out()
				_mode = "signin"
				_render())
			_box.add_child(out)
		_:
			var creating := _mode == "create"
			_box.add_child(Ui.label("CREATE ACCOUNT" if creating else "SIGN IN", Ui.SIZE_TITLE, Ui.INK, true))
			var hint := "Your team name is shown on the timesheet. Progress as a guest comes with you." if creating else "Save your times, parts and packs across devices."
			var h := Ui.label(hint, Ui.SIZE_SMALL, Ui.INK_2)
			h.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			_box.add_child(h)
			_name = _field("TEAM NAME", false)
			_name.max_length = 20
			_box.add_child(_name)
			_pass = _field("PASSWORD (6+ CHARACTERS)" if creating else "PASSWORD", true)
			_box.add_child(_pass)
			var go := Ui.button("CREATE ACCOUNT" if creating else "SIGN IN", true)
			go.custom_minimum_size = Vector2(0, 24)
			go.pressed.connect(_submit)
			_box.add_child(go)
			var swap := Ui.button("NEW HERE? CREATE AN ACCOUNT" if not creating else "HAVE AN ACCOUNT? SIGN IN")
			swap.pressed.connect(func() -> void:
				_mode = "signin" if creating else "create"
				_render())
			_box.add_child(swap)
			if SolanaWallet.available() and not creating:
				var wallet := Ui.button("SIGN IN WITH SOLANA WALLET")
				wallet.add_theme_color_override("font_color", Color("a855f7"))
				wallet.tooltip_text = "For accounts with a linked wallet: sign a message in Phantom, Backpack or Solflare."
				wallet.pressed.connect(_wallet_login)
				_box.add_child(wallet)
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.YELLOW)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_box.add_child(_status)
	var close := Ui.button("PLAY AS GUEST" if _mode != "account" else "CLOSE")
	close.pressed.connect(func() -> void: closed.emit())
	_box.add_child(close)


func _submit() -> void:
	if _busy or _mode == "account":
		return
	var team := _name.text.strip_edges()
	var password := _pass.text
	if team.length() < 3 or password.length() < (6 if _mode == "create" else 1):
		_status.text = "Team name 3+ characters, password 6+." if _mode == "create" else "Enter your team name and password."
		return
	_busy = true
	_status.text = "…"
	var res: Variant
	if _mode == "create":
		res = await Api.post_json("/api/accounts/register", {"name": team, "password": password, "guestId": Profile.id})
	else:
		res = await Api.post_json("/api/accounts/login", {"name": team, "password": password})
	_busy = false
	if res is Dictionary and (res as Dictionary).has("token"):
		Profile.sign_in(res)
		Sfx.play("ui_confirm")
		_mode = "account"
		_render()
		_status.text = "Signed in. Welcome, %s." % Profile.team_name
		_status.add_theme_color_override("font_color", Color("3ecf6a"))
	else:
		Sfx.play("ui_error")
		_status.text = Api.last_error if Api.last_error != "" else "Can't reach the server."


func _link_wallet() -> void:
	if _busy:
		return
	_busy = true
	_status.text = "Connecting to your wallet…"
	var pubkey := await SolanaWallet.connect_wallet(get_tree())
	if pubkey == "":
		_busy = false
		_status.text = SolanaWallet.last_error
		return
	var ch: Variant = await Api.post_json("/api/accounts/wallet/challenge", {})
	if not ch is Dictionary:
		_busy = false
		_status.text = Api.last_error if Api.last_error != "" else "Can't reach the server."
		return
	_status.text = "Sign the message in your wallet (it costs nothing)."
	var sig := await SolanaWallet.sign(get_tree(), String(ch.get("message", "")))
	if sig == "":
		_busy = false
		_status.text = SolanaWallet.last_error
		return
	var res: Variant = await Api.post_json("/api/accounts/wallet/link", {"wallet": pubkey, "signature": sig})
	_busy = false
	if res is Dictionary and (res as Dictionary).has("wallet"):
		Profile.wallet = String(res["wallet"])
		Profile.save()
		Sfx.play("verified")
		_render()
		_status.text = "Wallet linked."
	else:
		_status.text = Api.last_error if Api.last_error != "" else "Linking failed."


func _wallet_login() -> void:
	if _busy:
		return
	_busy = true
	_status.text = "Connecting to your wallet…"
	var pubkey := await SolanaWallet.connect_wallet(get_tree())
	if pubkey == "":
		_busy = false
		_status.text = SolanaWallet.last_error
		return
	var ch: Variant = await Api.post_json("/api/accounts/wallet/login-challenge", {"wallet": pubkey})
	if not ch is Dictionary:
		_busy = false
		_status.text = Api.last_error if Api.last_error != "" else "Can't reach the server."
		return
	_status.text = "Sign the message in your wallet (it costs nothing)."
	var sig := await SolanaWallet.sign(get_tree(), String(ch.get("message", "")))
	if sig == "":
		_busy = false
		_status.text = SolanaWallet.last_error
		return
	var res: Variant = await Api.post_json("/api/accounts/wallet/login", {"wallet": pubkey, "signature": sig})
	_busy = false
	if res is Dictionary and (res as Dictionary).has("token"):
		Profile.sign_in(res)
		Sfx.play("ui_confirm")
		_mode = "account"
		_render()
	else:
		_status.text = Api.last_error if Api.last_error != "" else "No account has this wallet linked yet. Sign in with your password and link it first."
