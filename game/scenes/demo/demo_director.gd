extends CanvasLayer
## Plays a scripted walkthrough for recording the demo video with Godot's movie
## maker (`-- --demo garage`). It draws a cursor and sends real mouse events, so
## every hover, tooltip and click is the game's own UI reacting. Debug builds only.
##
##   godot --path game --write-movie out.avi --fixed-fps 30 -- --demo garage

const ARROW := [
	"X..........",
	"XX.........",
	"XOX........",
	"XOOX.......",
	"XOOOX......",
	"XOOOOX.....",
	"XOOOOOX....",
	"XOOOOOOX...",
	"XOOOOOOOX..",
	"XOOOOOOOOX.",
	"XOOOOOXXXXX",
	"XOOXOOX....",
	"XOX.XOOX...",
	"XX..XOOX...",
	"X....XOOX..",
	".....XXX...",
]

## Events this script sends carry this device id; real mouse and keyboard input is
## dropped while recording, so touching the PC cannot disturb a take.
const DEVICE := 7

var shot := ""
var _cursor: Control
var _pos := Vector2(560, 300)  # canvas coordinates
var _down := false


func _ready() -> void:
	layer = 200
	var args := Api.args
	if args.find("--demo") + 1 < args.size():
		shot = args[args.find("--demo") + 1]
	_cursor = Control.new()
	_cursor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_cursor.draw.connect(_draw_cursor)
	add_child(_cursor)
	_cursor.visible = shot in ["hub", "garage", "garage3", "livery", "tuning", "passes"]
	_set_pos(_pos)
	match shot:
		"hub": _hub()
		"garage": _garage()
		"tuning": _tuning()
		"passes": _passes()
		"garage3": _garage3()
		"livery": _livery()


# ---- cursor and events ----

func _input(event: InputEvent) -> void:
	if (event is InputEventMouse or event is InputEventKey) and event.device != DEVICE:
		get_viewport().set_input_as_handled()


func _draw_cursor() -> void:
	for y in ARROW.size():
		var row: String = ARROW[y]
		for x in row.length():
			var ch := row[x]
			if ch == "X":
				_cursor.draw_rect(Rect2(x, y, 1, 1), Color("0b0c0e"))
			elif ch == "O":
				_cursor.draw_rect(Rect2(x, y, 1, 1), Color("f1efea") if not _down else Color("f2c230"))


func _to_window(p: Vector2) -> Vector2:
	return get_viewport().get_final_transform() * p


func _set_pos(p: Vector2) -> void:
	var rel := p - _pos
	_pos = p
	_cursor.position = p
	var e := InputEventMouseMotion.new()
	e.device = DEVICE
	e.position = _to_window(p)
	e.global_position = e.position
	e.relative = rel * 3.0
	e.button_mask = MOUSE_BUTTON_MASK_LEFT if _down else 0
	Input.parse_input_event(e)


func _button(pressed: bool) -> void:
	_down = pressed
	_cursor.queue_redraw()
	var e := InputEventMouseButton.new()
	e.device = DEVICE
	e.button_index = MOUSE_BUTTON_LEFT
	e.pressed = pressed
	e.position = _to_window(_pos)
	e.global_position = e.position
	e.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	Input.parse_input_event(e)


func wait(s: float) -> void:
	await get_tree().create_timer(s).timeout


## Moves the cursor in an eased arc to a canvas point (or a Control's centre).
func move(target: Variant, t: float = 0.55, off := Vector2.ZERO) -> void:
	var to: Vector2 = _target(target) + off
	var from := _pos
	var bend := (to - from).orthogonal().normalized() * minf(18.0, from.distance_to(to) * 0.12)
	var n := maxi(2, roundi(t * 30.0))
	for i in range(1, n + 1):
		var k := float(i) / n
		var e := k * k * (3.0 - 2.0 * k)
		_set_pos(from.lerp(to, e) + bend * sin(PI * e))
		await get_tree().process_frame


func click(hold: float = 0.08) -> void:
	_button(true)
	await wait(hold)
	_button(false)
	await wait(0.05)


func drag(by: Vector2, t: float) -> void:
	_button(true)
	var from := _pos
	var n := maxi(2, roundi(t * 30.0))
	for i in range(1, n + 1):
		var k := float(i) / n
		_set_pos(from + by * (k * k * (3.0 - 2.0 * k)))
		await get_tree().process_frame
	_button(false)


func _target(target: Variant) -> Vector2:
	if target is Vector2:
		return target
	if target is Control:
		return (target as Control).get_global_rect().get_center()
	if target is String:
		var c := find_text(target)
		if c:
			return c.get_global_rect().get_center()
		push_warning("demo: no control with text %s" % target)
	return _pos


## The first visible Button/Label whose text contains `text` (case-insensitive).
## A label inside a button resolves to the button.
func find_text(text: String, root: Node = null) -> Control:
	var hit := _find(root if root else get_tree().root, text.to_upper())
	if hit is Label:
		var p := hit.get_parent()
		while p and not p is BaseButton and p is Control:
			p = p.get_parent()
		if p is BaseButton:
			return p
	return hit


func _find(n: Node, text: String) -> Control:
	for c in n.get_children():
		if c == self:
			continue
		if c is CanvasItem and not (c as CanvasItem).is_visible_in_tree():
			continue
		if (c is Button or c is Label) and String(c.get("text")).to_upper().contains(text):
			return c
		var deep := _find(c, text)
		if deep:
			return deep
	return null


func find_class(cls: String, root: Node = null) -> Node:
	var start := root if root else get_tree().root
	for c in start.get_children():
		if c.get_script() and (c.get_script() as Script).get_global_name() == cls:
			return c
		var deep := find_class(cls, c)
		if deep:
			return deep
	return null


# ---- shots ----

## The lobby: the cursor looks over the menu, spins the car, opens the garage.
func _hub() -> void:
	await wait(1.6)
	await move("PRACTICE", 0.7)
	await wait(0.5)
	await move("QUALIFYING", 0.35)
	await wait(0.5)
	await move("RACE", 0.35)
	await wait(0.9)
	var show := find_class("CarShowcase")
	if show:
		await move(show, 0.7, Vector2(-10, -6))
		await wait(0.2)
		await drag(Vector2(90, 4), 0.9)
		await wait(1.2)
	await move("YOUR CAR", 0.6)
	await wait(0.4)
	await click()
	await wait(2.0)


## Garage: open a pack, fit a new part, tune the car.
func _garage() -> void:
	await wait(1.0)
	await move("GARAGE", 0.6)
	await click()
	await wait(1.4)
	# packs first, so the new parts are in the garage
	await move("PACKS", 0.6)
	await click()
	await wait(1.2)
	var open := find_text("OPEN PACK")
	if open:
		await move(open, 0.6)
		await wait(0.2)
		await click()
		await wait(3.6)
		var pack := find_class("PackOpening")
		if pack:
			for card: Variant in pack.get("_cards"):
				await move(card, 0.45)
				await click()
				await wait(0.9)
			await wait(0.8)
			await move("ADD TO GARAGE", 0.5)
			await wait(0.3)
			await click()
			await wait(1.4)
	# parts: pick an area with a new part, try parts on, fit one
	var area := _area_with_new_part()
	var garage := find_class("GarageScreen")
	if garage and area != "":
		var slots: Dictionary = garage.get("_slots")
		await move(slots[area], 0.6)
		await wait(0.3)
		await click()
		await wait(1.0)
		var rows: Array = (garage.get("_list") as Node).get_children()
		for row: Variant in rows:
			if row is Control:
				await move(row, 0.4)
				await wait(0.9)
		var newest: Variant = rows[rows.size() - 1] if rows.size() > 0 else null
		if newest is Control:
			await move(newest, 0.3)
			await click()
			await wait(0.6)
			await move("FIT PART", 0.5)
			await wait(0.2)
			await click()
			await wait(2.2)
	await _tune()


## Garage, second take: open a pack, read what a part does, test-drive it, fit it.
func _garage3() -> void:
	await wait(1.0)
	await move("GARAGE", 0.6)
	await click()
	await wait(1.4)
	await move("PACKS", 0.6)
	await click()
	await wait(1.0)
	var open := find_text("OPEN PACK")
	if open:
		await move(open, 0.6)
		await wait(0.2)
		await click()
		await wait(3.6)
		var pack := find_class("PackOpening")
		if pack:
			for card: Variant in pack.get("_cards"):
				await move(card, 0.45)
				await click()
				await wait(1.0)
			await wait(1.0)
			await move("ADD TO GARAGE", 0.5)
			await wait(0.3)
			await click()
			await wait(1.4)
	var garage := find_class("GarageScreen")
	if garage == null:
		return
	# the area with the most parts to compare
	var best := "rear_wing"
	var most := 0
	for area: String in ["front_wing", "rear_wing", "sidepods", "floor"]:
		var n := Catalog.inventory().filter(func(x: Dictionary) -> bool: return String(x.get("area", "")) == area).size()
		if n > most:
			most = n
			best = area
	var slots: Dictionary = garage.get("_slots")
	await move(slots[best], 0.6)
	await wait(0.2)
	await click()
	await wait(1.0)
	var rows: Array = (garage.get("_list") as Node).get_children()
	for row: Variant in rows:
		if row is Control:
			await move(row, 0.4)
			await wait(1.2)
	var pick: Variant = rows[rows.size() - 1] if rows.size() > 0 else null
	if pick is Control:
		await move(pick, 0.3)
		await click()
		await wait(1.0)
	await move("TEST DRIVE", 0.5)
	await wait(0.2)
	await click()
	for i in 40:  # wait for the test-drive result
		await wait(0.25)
		if find_text("A LAP") != null:
			break
	await wait(3.2)
	await move("CLOSE", 0.5)
	await click()
	await wait(0.6)
	await move("FIT PART", 0.5)
	await wait(0.2)
	await click()
	await wait(2.0)


## Livery: repaint the car and save it.
func _livery() -> void:
	await wait(0.8)
	await move("GARAGE", 0.6)
	await click()
	await wait(1.2)
	await move("LIVERY", 0.6)
	await click()
	await wait(1.0)
	var panel := find_class("LiveryPanel")
	if panel == null:
		return
	var swatches: Array[Button] = []
	_collect_swatches(panel, swatches)
	var picks := [2, 5, 8, 14]  # a few primaries, then a secondary
	for i in picks:
		if i < swatches.size():
			await move(swatches[i], 0.4)
			await click()
			await wait(0.8)
	var save := find_text("SAVE LIVERY")
	if save:
		await move(save, 0.5)
		await click()
		await wait(1.6)


func _collect_swatches(n: Node, out: Array[Button]) -> void:
	for c in n.get_children():
		if c is Button and (c as Button).text == "" and (c as Button).is_visible_in_tree():
			out.append(c)
		_collect_swatches(c, out)


## Race passes: the pools, your pool's standings, a pool that has paid out.
func _passes() -> void:
	await wait(1.4)
	var screen := find_class("RacePassScreen")
	if screen == null:
		return
	var grid: Node = screen.get("_grid")
	var cards: Array = grid.get_children() if grid else []
	for i in [0, 2, 3, 5]:
		if i < cards.size():
			await move(cards[i], 0.4)
			await wait(0.35)
	if cards.size() > 1:
		await move(cards[1], 0.4)
		await click()
		await wait(3.0)
	cards = grid.get_children()  # the screen rebuilds its cards after a click
	if cards.size() > 6:
		await move(cards[6], 0.5)
		await click()
		await wait(1.2)
		await move("VIEW PAYOUT", 0.6)
		await wait(2.0)


## Tuning on its own (needs a team that has not qualified yet: parc ferme).
func _tuning() -> void:
	await wait(0.8)
	await move("GARAGE", 0.6)
	await click()
	await wait(1.2)
	await _tune()


func _tune() -> void:
	await move("TUNING", 0.6)
	await click()
	await wait(1.0)
	var tp := find_class("TuningPanel")
	if tp:
		var plus: Array[Button] = []
		for c in tp.get_children():
			if c is Button and (c as Button).text == "+":
				plus.append(c)
		for b in plus:
			await move(b, 0.5)
			for k in 2:
				await click()
				await wait(0.25)
			await wait(0.4)
		var dials: Array = (tp.get("_dials") as Array).duplicate()  # rebuilt on every redraw
		for d: Variant in dials:
			var centre: Vector2 = (tp as Control).get_global_transform() * (d["centre"] as Vector2)
			await move(centre + Vector2(6, 0), 0.6)
			await wait(1.3)  # tooltip
			await click()
			await wait(0.4)
	await wait(1.5)


func _area_with_new_part() -> String:
	var best := ""
	for p: Dictionary in Catalog.inventory():
		var area := String(p.get("area", ""))
		if String(p.get("rarity", "starter")) != "starter" and area in ["front_wing", "rear_wing", "sidepods", "floor"]:
			if best == "" or String(p.get("rarity", "")) in ["legendary", "epic"]:
				best = area
	return best
