extends Node
## The parts catalogue (game/data/parts.json, shared with the server) and the
## player's garage as last loaded from the server: inventory, fitted parts,
## the car spec the physics uses, packs and the weekly supply.

const AREAS: Array[String] = ["front_wing", "rear_wing", "sidepods", "floor", "suspension", "power_unit"]
const AREA_NAMES := {
	"front_wing": "FRONT WING", "rear_wing": "REAR WING", "sidepods": "SIDEPODS",
	"floor": "FLOOR", "suspension": "SUSPENSION", "power_unit": "POWER UNIT",
}
const STAT_ORDER: Array[String] = ["downforce", "drag", "power", "grip", "traction", "harvest", "balance"]
const STAT_NAMES := {
	"downforce": "DOWNFORCE", "drag": "DRAG", "balance": "BALANCE", "power": "POWER",
	"harvest": "ENERGY", "grip": "GRIP", "traction": "TRACTION",
}
const GREEN := Color("3ecf6a")
const AREA_HELP := {
	"front_wing": "FRONT WING\nFront downforce and turn-in. It shapes the air for the whole car behind it.",
	"rear_wing": "REAR WING\nRear grip in fast corners and stability. More wing means more drag on the straights.",
	"sidepods": "SIDEPODS\nCooling and the airflow feeding the floor. Slimmer pods, less drag.",
	"floor": "FLOOR\nMost of a 2026 car's downforce comes from under the floor (ground effect).",
	"suspension": "SUSPENSION\nMechanical grip in slow corners, kerb riding and a stable aero platform.",
	"power_unit": "POWER UNIT\n1.6 L V6 hybrid: power, torque out of corners and energy recovery for Boost.",
}
const STAT_HELP := {
	"downforce": "Downforce: grip that grows with speed. Faster in fast corners.",
	"drag": "Drag: air resistance. Lower drag, higher top speed (green when lower).",
	"power": "Power: engine output in kW. Acceleration and top speed.",
	"grip": "Mechanical grip: tyres and suspension. Helps most in slow corners.",
	"traction": "Traction: power down out of slow corners without wheelspin.",
	"harvest": "Energy: battery recovered under braking. More Boost each lap.",
	"balance": "Aero balance: share of downforce on the front. Front = sharper, rear = stabler.",
}

var data: Dictionary = {}
var garage: Dictionary = {}
## Livery colours players can pick (game/data/livery.json, shared with the server).
var livery_palette: Dictionary = {"default": {"primary": "#e8352b", "secondary": "#f1efea"}, "primary": [], "secondary": []}


func _ready() -> void:
	var path := "res://data/parts.json"
	if FileAccess.file_exists(path):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Dictionary:
			data = parsed
	if FileAccess.file_exists("res://data/livery.json"):
		var pal: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/livery.json"))
		if pal is Dictionary:
			livery_palette = pal


## Finds a concept's entry whatever the catalogue's exact nesting.
func concept(area: String, concept_id: String) -> Dictionary:
	for root: Variant in [data.get("areas", {}), data.get("concepts", {}), data]:
		if not root is Dictionary:
			continue
		var a: Variant = (root as Dictionary).get(area)
		if a is Dictionary:
			var c: Variant = (a as Dictionary).get(concept_id)
			if c is Dictionary:
				return c
			var nested: Variant = (a as Dictionary).get("concepts")
			if nested is Dictionary and (nested as Dictionary).get(concept_id) is Dictionary:
				return nested[concept_id]
			if nested is Array:
				for item: Variant in nested:
					if item is Dictionary and (item as Dictionary).get("id") == concept_id:
						return item
	return {}


func concept_name(area: String, concept_id: String) -> String:
	var c := concept(area, concept_id)
	if c.has("name"):
		return String(c["name"])
	if concept_id == "baseline" or concept_id == "":
		return "Baseline " + String(AREA_NAMES.get(area, area)).capitalize()
	return concept_id.replace("_", " ").capitalize()


func concept_description(area: String, concept_id: String) -> String:
	var c := concept(area, concept_id)
	return String(c.get("description", c.get("desc", "")))


## [label, value text, colour] for the biggest stat changes of a part, best first.
func stat_lines(part: Dictionary, count: int) -> Array:
	var stats: Dictionary = part.get("stats", {})
	var keys := STAT_ORDER.filter(func(k: String) -> bool: return int(stats.get(k, 0)) != 0)
	keys.sort_custom(func(a: String, b: String) -> bool: return absi(int(stats[a])) > absi(int(stats[b])))
	var out := []
	for k: String in keys.slice(0, count):
		var v := int(stats[k])
		out.append([STAT_NAMES[k], format_stat(k, v), stat_color(k, v)])
	if out.is_empty():
		out.append(["BASELINE", "-", Ui.INK_3])
	return out


func format_stat(key: String, v: int) -> String:
	if key == "power":
		return "%+d kW" % v
	return "%+.1f%%" % (v / 10.0)


## Green when the change helps lap time, red when it costs (drag is better lower).
func stat_color(key: String, v: int) -> Color:
	if key == "balance":
		return Ui.INK_2
	var good := v < 0 if key == "drag" else v > 0
	return GREEN if good else Ui.RED


# ---- garage ----

func load_garage() -> bool:
	var g: Variant = await Api.get_json("/api/garage?player=" + Profile.id)
	if g is Dictionary:
		garage = g
		if (g as Dictionary).get("livery") is Dictionary:
			cache_livery(g["livery"])
		return true
	return false


func inventory() -> Array:
	return garage.get("inventory", [])


func equipped_id(area: String) -> String:
	var e: Dictionary = garage.get("equipped", {})
	return String(e.get(area, ""))


func equipped_part(area: String) -> Dictionary:
	var id := equipped_id(area)
	for p: Dictionary in inventory():
		if String(p.get("id", "")) == id:
			return p
	return {"area": area, "concept": "baseline", "rarity": "starter", "stats": {}}


## The car spec the physics uses: from the server when known (it is the one re-driven).
func car_spec() -> Dictionary:
	var c: Variant = garage.get("car", {})
	return c if c is Dictionary else {}


## Visual concepts for the car sprite layers.
func car_look() -> Dictionary:
	var look := {"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash", "floor": "low_rake"}
	var server: Variant = garage.get("looks")
	if server is Dictionary:
		for area: String in look.keys():
			var c := String((server as Dictionary).get(area, ""))
			if c != "" and ResourceLoader.exists("res://assets/sprites/car/%s_%s%s.png" % [area, c, "" if area == "floor" else "_paint"]):
				look[area] = c
		return look
	for area: String in look.keys():
		var c := String(equipped_part(area).get("concept", ""))
		if c != "" and c != "baseline" and ResourceLoader.exists("res://assets/sprites/car/%s_%s%s.png" % [area, c, "" if area == "floor" else "_paint"]):
			look[area] = c
	return look


func unopened_packs() -> int:
	var p: Dictionary = garage.get("packs", {})
	return int(p.get("unopened", 0))


# ---- livery (cosmetic: colours are never passed to the sim) ----

## [{"hex": "#rrggbb", "name": ...}] for "primary" (body) or "secondary" (accents, helmet).
func livery_options(slot: String) -> Array:
	var list: Variant = livery_palette.get(slot, [])
	return list if list is Array else []


func _in_palette(slot: String, hex: String) -> bool:
	for o: Variant in livery_options(slot):
		if o is Dictionary and String((o as Dictionary).get("hex", "")) == hex:
			return true
	return false


## The player's colour for a slot: the cached livery if it is on the palette, else the default.
func livery_hex(slot: String) -> String:
	var hex := String(Profile.livery.get(slot, "")).to_lower()
	if hex != "" and _in_palette(slot, hex):
		return hex
	return String((livery_palette.get("default", {}) as Dictionary).get(slot, "#e8352b" if slot == "primary" else "#f1efea"))


func livery_color(slot: String) -> Color:
	return Color(livery_hex(slot))


## Keeps the server's livery on this device (Profile) so it also shows offline.
func cache_livery(l: Dictionary) -> void:
	var next := {"primary": String(l.get("primary", "")).to_lower(), "secondary": String(l.get("secondary", "")).to_lower()}
	garage["livery"] = next
	if next != Profile.livery:
		Profile.livery = next
		Profile.save()
