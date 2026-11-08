extends Node
## Pit Wall look: palette, pixel font and widget helpers shared by every screen.
## Screens build their layout with these helpers so a reskin is a change here.

const BG := Color("141518")
const PANEL := Color("1d1f23")
const LINE := Color("34363c")
const LINE_STRONG := Color("4a4c54")
const INK := Color("f1efea")
const INK_2 := Color("a3a3ad")
const INK_3 := Color("6e6f78")
const RED := Color("e8352b")
const RED_DARK := Color("3a1c1d")
const YELLOW := Color("f2c230")
const TEAM_COLORS: Array[Color] = [
	Color("e8352b"), Color("f1efea"), Color("f2c230"), Color("9aa0aa"), Color("c8a27a"), Color("6f8fa8"),
]

const SIZE_SMALL := 8
const SIZE_BODY := 11
const SIZE_HEADING := 16
const SIZE_TITLE := 32

var theme: Theme
var font: FontFile
var font_bold: FontFile
var _toasts: VBoxContainer


func _ready() -> void:
	# Pixelify Sans with a clearer B and 5 (players read them as G and S);
	# made by tools/fonts/patch_pixelify.py.
	font = load("res://assets/fonts/PitWallPixel-Regular.ttf") as FontFile
	font_bold = load("res://assets/fonts/PitWallPixel-Bold.ttf") as FontFile
	# Text renders at full screen resolution (canvas_items stretch), so normal
	# antialiasing keeps it crisp; sprites still use nearest filtering.
	for f: FontFile in [font, font_bold]:
		f.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
	theme = _build_theme()


func _box(bg: Color, border: Color, width: int = 1, pad: int = 4) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(width)
	s.set_content_margin_all(pad)
	s.anti_aliasing = false
	return s


## A 9-slice style from a pixel-art sprite in assets/sprites/ui, or `fallback` if it isn't there.
func _art(name: String, margin: int, pad: int, fallback: StyleBox) -> StyleBox:
	var path := "res://assets/sprites/ui/%s.png" % name
	if not ResourceLoader.exists(path):
		return fallback
	var s := StyleBoxTexture.new()
	s.texture = load(path)
	s.set_texture_margin_all(margin)
	s.set_content_margin_all(pad)
	s.content_margin_left = pad + 2
	s.content_margin_right = pad + 2
	return s


func _build_theme() -> Theme:
	var t := Theme.new()
	t.default_font = font
	t.default_font_size = SIZE_BODY
	t.set_color("font_color", "Label", INK)

	t.set_stylebox("normal", "Button", _art("button", 6, 4, _box(PANEL, LINE)))
	t.set_stylebox("hover", "Button", _art("button_hover", 6, 4, _box(PANEL, LINE_STRONG)))
	t.set_stylebox("pressed", "Button", _art("button_pressed", 6, 4, _box(RED_DARK, RED)))
	t.set_stylebox("hover_pressed", "Button", _art("button_pressed", 6, 4, _box(RED_DARK, RED)))
	t.set_stylebox("disabled", "Button", _box(BG, LINE))
	t.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	for state: String in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		t.set_color(state, "Button", INK)
	t.set_color("font_disabled_color", "Button", INK_3)

	t.set_type_variation("PrimaryButton", "Button")
	t.set_stylebox("normal", "PrimaryButton", _art("button_primary", 6, 6, _box(RED, RED, 1, 6)))
	t.set_stylebox("hover", "PrimaryButton", _art("button_primary_hover", 6, 6, _box(Color("ff4a3f"), Color("ff4a3f"), 1, 6)))
	t.set_stylebox("pressed", "PrimaryButton", _box(Color("b8261d"), Color("b8261d"), 1, 6))
	t.set_stylebox("disabled", "PrimaryButton", _box(RED_DARK, RED_DARK, 1, 6))
	t.set_font("font", "PrimaryButton", font_bold)

	t.set_stylebox("panel", "PanelContainer", _art("panel", 8, 8, _box(PANEL, LINE, 1, 8)))
	t.set_type_variation("AccentPanel", "PanelContainer")
	t.set_stylebox("panel", "AccentPanel", _art("panel_accent", 8, 8, _box(RED_DARK, RED, 1, 8)))

	var slider_bg := _box(LINE, LINE, 0, 0)
	slider_bg.content_margin_top = 2
	slider_bg.content_margin_bottom = 2
	t.set_stylebox("slider", "HSlider", slider_bg)
	var fill := _box(RED, RED, 0, 0)
	fill.content_margin_top = 2
	fill.content_margin_bottom = 2
	t.set_stylebox("grabber_area", "HSlider", fill)
	t.set_stylebox("grabber_area_highlight", "HSlider", fill)
	t.set_icon("grabber", "HSlider", _square_icon(8, INK))
	t.set_icon("grabber_highlight", "HSlider", _square_icon(8, INK))

	var field := _box(Color(0.05, 0.055, 0.065), LINE_STRONG, 1, 6)
	var field_focus := _box(Color(0.05, 0.055, 0.065), RED, 1, 6)
	t.set_stylebox("normal", "LineEdit", field)
	t.set_stylebox("focus", "LineEdit", field_focus)
	t.set_stylebox("read_only", "LineEdit", field)
	t.set_color("font_color", "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", INK_3)
	t.set_color("caret_color", "LineEdit", RED)
	t.set_color("selection_color", "LineEdit", RED_DARK)

	var tip := _box(Color(0.07, 0.075, 0.09, 0.97), YELLOW, 1, 6)
	tip.border_width_left = 3
	t.set_stylebox("panel", "TooltipPanel", tip)
	t.set_color("font_color", "TooltipLabel", INK)
	t.set_font_size("font_size", "TooltipLabel", SIZE_SMALL)
	t.set_font("font", "TooltipLabel", font)

	t.set_stylebox("background", "ProgressBar", _box(LINE, LINE, 0, 0))
	t.set_stylebox("fill", "ProgressBar", _box(RED, RED, 0, 0))
	return t


func _square_icon(size: int, color: Color) -> ImageTexture:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	img.fill(color)
	return ImageTexture.create_from_image(img)


# ---- widget helpers ----

func label(text: String, size: int = SIZE_BODY, color: Color = INK, bold: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if bold:
		l.add_theme_font_override("font", font_bold)
	return l


func button(text: String, primary: bool = false) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	if primary:
		b.theme_type_variation = "PrimaryButton"
	return b


## A row of toggle buttons where exactly one is pressed. Emits on_change(index).
func choice_row(options: Array[String], selected: int, on_change: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	var group := ButtonGroup.new()
	for i in options.size():
		var b := button(options[i])
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = i == selected
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(on_change.bind(i))
		row.add_child(b)
	return row


func panel(accent: bool = false) -> PanelContainer:
	var p := PanelContainer.new()
	if accent:
		p.theme_type_variation = "AccentPanel"
	return p


func vbox(separation: int = 4) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", separation)
	return v


func hbox(separation: int = 4) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", separation)
	return h


func stat_bar(value: int, max_value: int = 100) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.max_value = max_value
	bar.value = value
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 3)
	bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return bar


func format_time(ms: int) -> String:
	var minutes := ms / 60000
	var seconds := (ms % 60000) / 1000
	var millis := ms % 1000
	return "%d:%02d.%03d" % [minutes, seconds, millis]


func short_hash(h: String) -> String:
	return h.substr(0, 8) + "…" + h.substr(h.length() - 8) if h.length() > 20 else h


## A short notice at the top of the screen, over every screen (it survives
## screen changes), e.g. a reward. Fades out after `seconds`.
func toast(text: String, color: Color = YELLOW, seconds: float = 4.5) -> void:
	if _toasts == null:
		var layer := CanvasLayer.new()
		layer.layer = 90
		add_child(layer)
		_toasts = VBoxContainer.new()
		_toasts.theme = theme
		_toasts.add_theme_constant_override("separation", 4)
		_toasts.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_toasts.anchor_left = 0.5
		_toasts.anchor_right = 0.5
		_toasts.offset_top = 10
		_toasts.grow_horizontal = Control.GROW_DIRECTION_BOTH
		layer.add_child(_toasts)
	var p := PanelContainer.new()
	var sb := _box(Color(0.07, 0.075, 0.09, 0.97), color, 1, 6)
	sb.border_width_left = 3
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	p.add_theme_stylebox_override("panel", sb)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	p.add_child(label(text, SIZE_BODY, color, true))
	p.modulate.a = 0.0
	_toasts.add_child(p)
	var t := p.create_tween()
	t.tween_property(p, "modulate:a", 1.0, 0.2)
	t.tween_interval(seconds)
	t.tween_property(p, "modulate:a", 0.0, 0.5)
	t.tween_callback(p.queue_free)
