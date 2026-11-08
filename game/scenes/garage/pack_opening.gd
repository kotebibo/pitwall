class_name PackOpening
extends Control
## Opening a development pack: the pack shakes, bursts, and three cards land
## face down; click each to flip it. Rarer parts glow and sound bigger.

signal closed

var parts: Array = []
var _pack: TextureRect
var _cards: Array[PartCard] = []
var _flipped := 0
var _done_button: Button
var _title: Label
var _flash: ColorRect
var _burst: TextureRect


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0.03, 0.03, 0.04, 0.88)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	_title = Ui.label("DEVELOPMENT PACK", Ui.SIZE_HEADING, Ui.INK, true)
	_title.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_title.position = Vector2(size.x / 2 - 150, 18)
	_title.size = Vector2(300, 20)
	add_child(_title)
	_burst = TextureRect.new()
	_burst.texture = PartCard.texture("res://assets/sprites/packs/burst.png")
	_burst.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_burst.size = Vector2(192, 192)
	_burst.pivot_offset = _burst.size / 2
	_burst.modulate.a = 0.0
	_burst.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_burst)
	_pack = TextureRect.new()
	_pack.texture = PartCard.texture("res://assets/sprites/packs/pack_closed.png")
	_pack.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_pack.size = Vector2(96, 112) * 1.6
	_pack.pivot_offset = _pack.size / 2
	_pack.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_pack)
	_flash = ColorRect.new()
	_flash.color = Color(1, 1, 1, 0)
	_flash.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_flash)
	_done_button = Ui.button("ADD TO GARAGE", true)
	_done_button.custom_minimum_size = Vector2(140, 24)
	_done_button.visible = false
	_done_button.pressed.connect(func() -> void: closed.emit())
	add_child(_done_button)
	await get_tree().process_frame
	_layout()
	_play()


func _layout() -> void:
	var c := size / 2
	_pack.position = c - _pack.size / 2
	_burst.position = c - _burst.size / 2
	_done_button.position = Vector2(c.x - 70, size.y - 40)
	_title.position = Vector2(c.x - 150, 18)


func _sfx(name: String) -> void:
	if has_node("/root/Sfx"):
		get_node("/root/Sfx").call("play", name)


func _play() -> void:
	# Anticipation: three shakes, each harder
	var shake1 := PartCard.texture("res://assets/sprites/packs/pack_shake_1.png")
	var shake2 := PartCard.texture("res://assets/sprites/packs/pack_shake_2.png")
	var closed_tex := _pack.texture
	for k in 3:
		_sfx("pack_shake")
		var tw := create_tween()
		var amp := 0.08 + k * 0.05
		tw.tween_property(_pack, "rotation", amp, 0.06)
		tw.tween_property(_pack, "rotation", -amp, 0.09)
		tw.tween_property(_pack, "rotation", 0.0, 0.06)
		if shake1 and shake2:
			_pack.texture = shake1 if k % 2 == 0 else shake2
		await tw.finished
		_pack.texture = closed_tex
		await get_tree().create_timer(0.18 - k * 0.04).timeout
	# Burst
	_sfx("pack_open")
	var open_tex := PartCard.texture("res://assets/sprites/packs/pack_open.png")
	if open_tex:
		_pack.texture = open_tex
	_flash.color.a = 0.85
	var tw := create_tween().set_parallel()
	tw.tween_property(_flash, "color:a", 0.0, 0.45)
	tw.tween_property(_burst, "modulate:a", 1.0, 0.08)
	tw.tween_property(_burst, "scale", Vector2(2.2, 2.2), 0.6).from(Vector2(0.4, 0.4))
	tw.tween_property(_burst, "rotation", 0.6, 0.6)
	tw.tween_property(_pack, "modulate:a", 0.0, 0.35).set_delay(0.15)
	tw.tween_property(_pack, "scale", Vector2(1.3, 1.3), 0.35)
	await tw.finished
	create_tween().tween_property(_burst, "modulate:a", 0.0, 0.4)
	# Cards fly out face down
	var c := size / 2
	var gap := PartCard.SIZE.x + 18
	for i in parts.size():
		var card := PartCard.new()
		card.part = parts[i]
		card.face_down = true
		card.pivot_offset = PartCard.SIZE / 2
		card.position = c - PartCard.SIZE / 2
		card.scale = Vector2(0.3, 0.3)
		card.picked.connect(_flip.bind(card))
		add_child(card)
		move_child(card, _flash.get_index())
		_cards.append(card)
		var target := Vector2(c.x + (i - (parts.size() - 1) / 2.0) * gap, c.y + 4) - PartCard.SIZE / 2
		var t2 := create_tween().set_parallel().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
		t2.tween_property(card, "position", target, 0.35)
		t2.tween_property(card, "scale", Vector2.ONE, 0.35)
		_sfx("card_flip")
		await get_tree().create_timer(0.12).timeout
	_title.text = "CLICK A CARD TO REVEAL"


func _flip(_p: Dictionary, card: PartCard) -> void:
	if not card.face_down:
		return
	var tw := create_tween()
	tw.tween_property(card, "scale:x", 0.0, 0.1)
	await tw.finished
	card.face_down = false
	card.queue_redraw()
	var rarity := String(card.part.get("rarity", "common"))
	_sfx("reveal_" + (rarity if rarity in ["rare", "epic", "legendary"] else "common"))
	if rarity in ["rare", "epic", "legendary"]:
		var glow := TextureRect.new()
		glow.texture = PartCard.texture("res://assets/sprites/cards/glow_%s.png" % rarity)
		if glow.texture == null:
			glow.queue_free()
		else:
			glow.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			glow.size = Vector2(136, 176)
			glow.position = card.position + (PartCard.SIZE - glow.size) / 2
			glow.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(glow)
			move_child(glow, card.get_index())
			var pulse := create_tween().set_loops()
			pulse.tween_property(glow, "modulate:a", 0.55, 0.6)
			pulse.tween_property(glow, "modulate:a", 1.0, 0.6)
		if rarity == "legendary":
			_flash.color = Color(PartCard.rarity_color(rarity), 0.5)
			create_tween().tween_property(_flash, "color:a", 0.0, 0.6)
	var t2 := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	t2.tween_property(card, "scale:x", 1.0, 0.16)
	t2.tween_property(card, "scale", Vector2(1.08, 1.08), 0.08)
	t2.tween_property(card, "scale", Vector2.ONE, 0.1)
	_say(card)
	_flipped += 1
	if _flipped == _cards.size():
		_title.text = "NEW PARTS"
		_done_button.visible = true


## Under the card, in plain words: what this part would do to your car.
func _say(card: PartCard) -> void:
	var text := PerfPanel.one_liner(card.part)
	if text == "":
		return
	var l := Ui.label(text, Ui.SIZE_SMALL, Ui.INK_2)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.add_theme_constant_override("line_spacing", -3)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	l.position = card.position + Vector2(-6, PartCard.SIZE.y + 6)
	l.size = Vector2(PartCard.SIZE.x + 12, 0)
	l.custom_minimum_size = Vector2(PartCard.SIZE.x + 12, 0)
	l.modulate.a = 0.0
	add_child(l)
	create_tween().tween_property(l, "modulate:a", 1.0, 0.3).set_delay(0.15)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_accept"):
		for card in _cards:
			if card.face_down:
				_flip({}, card)
				return
