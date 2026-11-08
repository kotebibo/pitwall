extends Control
## Switches between the game's screens. The weekend hub leads to practice and
## qualifying (you drive) and the race (race day → lock → replay → results).

var _screen: Control


func _ready() -> void:
	theme = Ui.theme
	Api.track("visit", "web" if OS.has_feature("web") else OS.get_name())
	var args := Api.args
	if "--demo" in args and OS.is_debug_build():
		# scripted walkthrough for recording the demo video (movie maker)
		add_child(load("res://scenes/demo/demo_director.gd").new())
	if "--drive" in args:
		var info: Variant = await Api.get_json("/api/event?player=" + Profile.id)
		if info is Dictionary:
			Profile.event = info
		_show_drive(SessionSim.Kind.PRACTICE if "--practice" in args else SessionSim.Kind.QUALIFYING)
		return
	if "--race" in args:
		var info: Variant = await Api.get_json("/api/event?player=" + Profile.id)
		if info is Dictionary:
			Profile.event = info
		_show_race()
		return
	if "--tutorial" in args:
		_show_drive(SessionSim.Kind.PRACTICE, true)
		return
	if "--packtest" in args:
		_show_garage()
		var o := PackOpening.new()
		if OS.is_debug_build() and args.find("--packtest") + 1 < args.size():
			o.medal = args[args.find("--packtest") + 1]  # testing: a medal pack (bronze, silver, gold)
		o.parts = [
			{"area": "rear_wing", "concept": "spoon", "rarity": "rare", "serial": "#0412", "stats": {"drag": -21, "downforce": -8}, "display": {"name": "Spoon rear wing"}},
			{"area": "floor", "concept": "venturi", "rarity": "legendary", "serial": "#0003", "stats": {"downforce": 14, "drag": -7, "grip": -5}, "display": {"name": "Venturi floor"}},
			{"area": "power_unit", "concept": "efficiency", "rarity": "common", "serial": "#1187", "stats": {"harvest": 41, "power": -6}, "display": {"name": "Efficiency power unit"}},
		]
		add_child(o)
		await get_tree().create_timer(3.2).timeout
		for c in o.get_children():
			if c is PartCard:
				c.picked.emit(c.part)
				await get_tree().create_timer(0.7).timeout
		return
	if "--raceday" in args:
		_show_race_day()
		return
	if "--garage" in args:
		_show_garage()
		if OS.is_debug_build() and args.find("--tab") + 1 < args.size():
			(_screen as GarageScreen).call("_show_tab", int(args[args.find("--tab") + 1]))  # testing: open a garage tab
		return
	if "--passes" in args:
		var t := "ranked"
		if OS.is_debug_build() and args.find("--tab") >= 0 and args.find("--tab") + 1 < args.size():
			t = args[args.find("--tab") + 1]  # testing: open a COMPETE tab (ranked, spec, open)
		_show_passes(t)
		return
	if "--settings" in args and OS.is_debug_build():
		# testing: the settings screen over the hub (--tab 1: sound, 2: game)
		_show_hub()
		var tab := int(args[args.find("--tab") + 1]) if args.find("--tab") >= 0 and args.find("--tab") + 1 < args.size() else 0
		(_screen as HubScreen).open_settings.call_deferred(tab)
		return
	if "--passdrive" in args:
		_show_comp_drive("spec")
		return
	if "--rankeddrive" in args:
		_show_comp_drive("ranked")
		return
	if "--results" in args:
		var rr: Variant = await Api.get_json("/api/races/" + args[args.find("--results") + 1])
		if rr is Dictionary:
			_show_results(rr)
			return
	if "--replay" in args:
		var r: Variant = await Api.get_json("/api/races/" + args[args.find("--replay") + 1])
		if r is Dictionary:
			_show_replay(r)
			return
	_show_hub()


func _swap(next: Control) -> void:
	if _screen:
		_screen.queue_free()
	_screen = next
	next.modulate.a = 0.0
	add_child(next)
	create_tween().tween_property(next, "modulate:a", 1.0, 0.22)


func _show_hub() -> void:
	var s := HubScreen.new()
	s.practice.connect(_show_drive.bind(SessionSim.Kind.PRACTICE))
	s.qualifying.connect(_show_drive.bind(SessionSim.Kind.QUALIFYING))
	s.race.connect(_show_race)
	s.garage.connect(_show_garage)
	s.passes.connect(_show_passes.bind("ranked"))
	s.tutorial.connect(_show_drive.bind(SessionSim.Kind.PRACTICE, true))
	_swap(s)


func _show_garage() -> void:
	Api.track("garage_open")
	var s := GarageScreen.new()
	s.done.connect(_show_hub)
	_swap(s)


## COMPETE: ranked, and the SPEC and OPEN race passes. `tab`: "ranked", "spec" or "open".
func _show_passes(tab: String = "ranked") -> void:
	Api.track("passes_open", tab)
	var s := RacePassScreen.new()
	s.tab = tab
	s.exited.connect(_show_hub)
	s.drive.connect(func(mode: String, _pool: int) -> void: _show_comp_drive(mode))
	_swap(s)


const COMP_SESSIONS := {"ranked": "ranked", "spec": "pass", "open": "pass_open"}


## A competition lap, qualifying rules. mode "ranked": a ranked race (standard car, your own
## setup, the first lap is the result); "spec": a SPEC race-pass lap (standard car);
## "open": an OPEN race-pass lap (your own car: parts, look and livery).
func _show_comp_drive(mode: String) -> void:
	if not COMP_SESSIONS.has(mode):
		mode = "spec"
	var s := DriveScreen.new()
	s.kind = SessionSim.Kind.QUALIFYING
	s.title = {"ranked": "RANKED RACE", "spec": "SPEC RACE PASS", "open": "OPEN RACE PASS"}[mode]
	s.setup = Profile.setup.duplicate()
	s.stats = Profile.stats()
	if mode == "open":
		s.car_spec = Catalog.car_spec()
		s.car_parts = Catalog.car_look()
		s.team_color = Catalog.livery_color("primary")
		s.team_secondary = Catalog.livery_color("secondary")
	else:
		s.car_spec = {}
		s.car_parts = {"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash", "floor": "low_rake"}
	s.ranked = mode == "ranked"
	if s.ranked and not RankedMock.enabled():
		# chase the day's fastest ranked lap (GET /api/ranked daily.ghost)
		var daily: Variant = RankedView.last_info.get("daily")
		var ghost: Variant = (daily as Dictionary).get("ghost") if daily is Dictionary else null
		if ghost is Dictionary and (ghost as Dictionary).get("attempt") is String:
			s.rival_attempt = ghost["attempt"]
	s.exit_text = "EXIT TO COMPETE"
	s.on_attempt = _new_attempt.bind(SessionSim.Kind.QUALIFYING, COMP_SESSIONS[mode])
	s.verify_laps = true
	s.exited.connect(_show_passes.bind(mode))
	s.ranked_again.connect(_show_comp_drive.bind("ranked"))
	Api.track("comp_start", mode)
	_swap(s)


func _show_drive(kind: SessionSim.Kind, tutorial: bool = false) -> void:
	var s := DriveScreen.new()
	s.kind = kind
	s.tutorial = tutorial
	s.title = "ROOKIE TEST" if tutorial else ("PRACTICE" if kind == SessionSim.Kind.PRACTICE else "QUALIFYING")
	Api.track("rookie_start" if tutorial else ("practice_start" if kind == SessionSim.Kind.PRACTICE else "quali_start"))
	s.setup = Profile.setup.duplicate()
	s.stats = Profile.stats()
	s.car_spec = Catalog.car_spec()
	s.car_parts = Catalog.car_look()
	s.team_color = Catalog.livery_color("primary")
	s.team_secondary = Catalog.livery_color("secondary")
	s.on_attempt = _new_attempt.bind(kind)
	s.verify_laps = kind == SessionSim.Kind.QUALIFYING
	if kind == SessionSim.Kind.QUALIFYING:
		# race the ghost of the fastest other player (their lap, re-driven from its inputs)
		for r: Variant in Profile.event.get("leaderboard", []):
			if r is Dictionary and not bool(r.get("ai", false)) and not bool(r.get("you", false)) and String(r.get("player", "")) != Profile.id and r.get("attempt") is String:
				s.rival_attempt = r["attempt"]
				break
	s.exited.connect(_show_hub)
	_swap(s)


## Asks the server for an attempt seed. In qualifying the first run locks the setup.
func _new_attempt(kind: SessionSim.Kind, session: String = "") -> Variant:
	var res: Variant
	if session == "ranked" and RankedMock.enabled():
		await get_tree().create_timer(0.3).timeout
		res = RankedMock.attempt()  # debug only: --mock-ranked
	else:
		res = await Api.post_json("/api/attempts", {
			"player": Profile.id,
			"name": Profile.team_name,
			"session": session if session != "" else ("practice" if kind == SessionSim.Kind.PRACTICE else "qualifying"),
			"setup": Profile.setup,
		})
	if not res is Dictionary:
		return null
	var r: Dictionary = res
	var seed_hex := String(r.get("seed", ""))
	var seed := PackedByteArray()
	for i in range(0, seed_hex.length() - 1, 2):
		seed.append(seed_hex.substr(i, 2).hex_to_int())
	if kind == SessionSim.Kind.QUALIFYING and session == "":
		var you: Dictionary = Profile.event.get("you", {})
		you["setupLocked"] = true
		Profile.event["you"] = you
	return {"attempt": r.get("attempt", ""), "seed": seed, "car": r.get("car", {}), "stats": r.get("stats", {}), "setup": r.get("setup", {}),
		"rankedMatch": r.get("rankedMatch")}


func _show_race() -> void:
	var s := RaceScreen.new()
	s.setup = Profile.setup.duplicate()
	s.stats = Profile.stats()
	s.car_spec = Catalog.car_spec()
	s.car_parts = Catalog.car_look()
	s.team_color = Catalog.livery_color("primary")
	s.team_secondary = Catalog.livery_color("secondary")
	s.exited.connect(_show_hub)
	_swap(s)


func _show_race_day() -> void:
	var s := RaceDayScreen.new()
	s.locked.connect(_show_lock)
	s.back.connect(_show_hub)
	_swap(s)


func _show_lock(race: Dictionary) -> void:
	var s := LockScreen.new()
	s.race = race
	s.finished.connect(_show_replay)
	s.back.connect(_show_hub)
	_swap(s)


func _show_replay(race: Dictionary) -> void:
	var s := ReplayScreen.new()
	s.race = race
	s.done.connect(_show_results)
	_swap(s)


func _show_results(race: Dictionary) -> void:
	var s := ResultsScreen.new()
	s.race = race
	s.next_race.connect(_show_hub)
	_swap(s)
