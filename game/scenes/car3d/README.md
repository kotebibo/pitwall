# 3D car showcase

A procedural, low-poly 2026-style F1 car for menus and the garage, drawn in the
same "high-res pixel art" style as the 2D game. It renders into a small
SubViewport and is scaled up with nearest filtering. Shading is toon with three
light bands, a hard glint and a rim light. A 1-pixel dark outline comes from the
depth buffer. Every part concept in `data/parts.json` has its own visible shape,
and fitting a part plays a pop-and-flash animation.

| File | What it is |
| --- | --- |
| `car_showcase.gd` | `CarShowcase` (Control): drop-in turntable view. Use this. |
| `car_model.gd` | `CarModel3D` (Node3D): the car itself, built in code. |
| `mesh_kit.gd` | Flat-shaded mesh builder used by the model (lofts, wings, boxes, wheels). |
| `toon.gdshader` | Car material: 3 light bands, hard specular, rim light. |
| `outline.gdshader` | Full-screen depth-edge outline (1 px). |
| `overlay.gdshader`, `halo.gdshader` | Hover tint and fit flash, plus the coloured rim around a part. |
| `floor.gdshader`, `blob_shadow.gdshader` | Turntable disc (grid, rings, fit pulse) and contact shadow. |
| `showcase_test.gd` | Demo and visual test (movie maker). |

No project settings are needed. It is built for the Compatibility renderer and
uses a custom `light()`, `hint_depth_texture` and `stencil_mode` (Godot 4.5+).

## Quick start: a menu or the lobby

```gdscript
var show := CarShowcase.new()
show.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
show.anchor_left = 0.45          # right part of the screen
add_child(show)
show.set_parts(Catalog.car_look())
show.set_colors(Ui.RED, Ui.INK)  # paint, accents and helmet
show.set_compound("medium")
```

The car spins slowly. Players can drag it to turn it (and tilt it a little).
Three seconds after a drag it drifts back to spinning. With the default
`transparent = true` the menu behind shows through. Set `transparent = false`
and `background` for a solid backdrop.

## Garage

`CarPreview` in `scenes/garage/car_preview.gd` can be replaced by
`CarShowcase`, or the showcase can sit next to it. The garage already has a
hook for each event:

```gdscript
# _parts_page(): create it where _preview was
_show = CarShowcase.new()
_show.anchor_right = 0.64
_show.anchor_bottom = 0.78
_show.offset_top = 46
_show.offset_bottom = -42
page.add_child(_show)
_show.set_parts(_full_look())

# _try_on(p): preview a part before fitting it (only that group is rebuilt)
_show.set_parts(look)

# after a part is fitted (where _preview.fitted() would be called)
_show.set_parts(_full_look())
_show.fit_part(area)               # pop + yellow flash + floor pulse
# _show.fit_part(area, Ui.RED)     # or flash in brand red

# slot hover / selection
_show.highlight(area)              # white rim and tint; "" clears it
_show.focus(area)                  # camera turns and zooms to the part; "" = overview

# leader lines from slots to the car (control-local coordinates)
var p := _show.area_screen_point(area)

func _full_look() -> Dictionary:
	# car_look() only covers the four areas the 2D sprites show; add the other two.
	var look := Catalog.car_look()
	for area: String in ["suspension", "power_unit"]:
		look[area] = String(Catalog.equipped_part(area).get("concept", ""))
	return look
```

Unknown concepts such as `"baseline"` or `""` fall back to the area's standard
look. Areas missing from the dictionary keep their current concept.

## CarShowcase API

| Member | |
| --- | --- |
| `car: CarModel3D` | The model, for anything not passed through. |
| `set_parts(look: Dictionary)` | `{"front_wing": "inwash", ...}`. Rebuilds only the changed groups. |
| `set_colors(primary: Color, secondary: Color)` | Paint, and accents/helmet/push-rods. Carbon parts stay carbon. |
| `set_compound(c: String)` | `soft` red, `medium` yellow, `hard` white (also `inter`, `wet`). |
| `set_wing_open(open: bool)` | Straight Mode / DRS: the rear-wing flap swings flat. |
| `fit_part(area, flash := YELLOW)` | Pop-in, flash and halo on the part, plus a pulse across the floor. |
| `highlight(area: String)` | Hover state: pulsing white rim and tint on the area; `""` clears it. |
| `focus(area: String)` | Eases the camera to the area (front wing from the front 3/4, rear wing from the rear 3/4, sidepods, floor from low down, suspension at the front wheel, power unit over the engine cover). `""` goes back to the spinning overview. |
| `focused() -> String` | The area in focus. |
| `set_yaw(radians)` | Sets the turntable angle directly (0 = side view, nose right). |
| `area_screen_point(area) -> Vector2` | Where the area appears, in this control's coordinates. |
| `pixel_size := 3` | Physical screen pixels per 3D pixel. 3 matches the 2D art at 1080p and is a little chunkier at 720p. It is always a whole number of screen pixels, so pixels stay even. |
| `spin`, `spin_speed`, `zoom`, `interactive`, `return_delay`, `idle_motion`, `show_floor`, `transparent`, `background` | Exported options. |

## CarModel3D API

The car can be used on its own in any 3D scene. It spans 5.6 m from +X (nose)
to -X, is 2.0 m wide and stands on Y = 0. The same methods are available:
`set_parts`, `set_colors`, `set_compound`, `set_wing_open`, `fit_part`,
`highlight`, and `area_point(area) -> Vector3` (local). Properties: `look`,
`steer` (front wheels, radians), `ride_offset` (chassis bob), `highlight_color`
and `triangles`. The toon shader needs directional lights. CarShowcase sets up
a key, a fill and a rim light.

## What each concept looks like

| Area | Concepts |
| --- | --- |
| Front wing | **outwash**: four elements sweeping up outboard, tall painted endplates curling out. **inwash**: three elements swept back into a chevron and dropping outboard, small carbon endplates. **highnose**: raised nose on two pylons over a flat wing. |
| Rear wing | **highdf**: deep mainplane, steep flap, tall endplates. **spoon**: elements dipping deep in the middle, lower rounded endplates. **beam**: smaller top wing with a big painted two-element beam wing below. |
| Sidepods | **downwash**: tall inlet, then a long steep ramp. **zeropod**: almost none; a slot inlet, with the floor exposed. **undercut**: wide letterbox inlet, deep undercut, louvres. |
| Floor | **low_rake**: flat, with a painted edge and a small diffuser. **high_rake**: the chassis pitched 2 degrees nose-down, front edge fins and a huge diffuser with painted strakes. **venturi**: sits lower, with tunnel fences at the inlets, a curled edge wing and a medium diffuser. |
| Suspension | **pushrod**: rod (accent colour) from the bottom of the upright to rockers on top of the nose. **pullrod**: from the top of the upright down to the bottom of the chassis. Fitting one bounces the car on its springs. |
| Power unit | **torque**: big exhaust with a gold collar, wastegates and gold heat shields on the engine cover. **topend**: two rows of louvres, "ear" inlets and a bigger airbox. **efficiency**: blue glowing battery vents that pulse. Fitting one flashes the whole engine cover and shakes it like a rev. |

## Performance

- About 3,500 triangles. Each part group is one mesh with one surface per
  material (about 8 materials, shared by all groups).
- One SubViewport at a third of the screen resolution: about 427x240 when full
  screen at 720p. MSAA, shadow maps and shadow atlas are off. The contact
  shadow is a blob.
- The viewport renders only while the control is visible
  (`UPDATE_WHEN_VISIBLE`, and processing stops when it is hidden).
- Measured on a laptop RTX 3050 Ti (desktop GL Compatibility), full screen:
  about 0.5 ms GPU per frame.
- A rebuild after `set_parts` builds one group (a few hundred triangles) and
  allocates a new ArrayMesh. That is fine on a click but not every frame. The
  suspension also rebuilds itself while the chassis moves (rake change, fit
  bounce).
- On the web the shaders compile the first time the showcase is drawn. To avoid
  a hitch when the garage opens, create the showcase hidden earlier or show it
  once behind a loading screen.

## Testing

```sh
# full demo (24 s): cycles parts, colours, fits, focus, Straight Mode, hover, drag
godot --path game --write-movie D:/dev/shots3d/s.png --fixed-fps 30 --quit-after 720 -s res://scenes/car3d/showcase_test.gd
# every concept of one area side by side, framed by focus()
godot --path game --write-movie D:/dev/shots3d/g.png --fixed-fps 30 --quit-after 75 -s res://scenes/car3d/showcase_test.gd -- grid=rear_wing
# one car from six angles, optional parts / hover / backdrop
godot --path game --write-movie D:/dev/shots3d/a.png --fixed-fps 30 --quit-after 20 -s res://scenes/car3d/showcase_test.gd -- angles look=floor:venturi,sidepods:undercut hl=sidepods bg=7a8fa8
```

`CarShowcase` and `CarModel3D` are global class names. A fresh checkout
registers them the first time the editor opens or after `godot --headless --import`.
