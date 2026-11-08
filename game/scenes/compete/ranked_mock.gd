class_name RankedMock
## DEBUG ONLY: built-in fixtures for the COMPETE screen and the ranked race, to the shapes in
## docs/RANKED_CONTRACT.md, while the server side is not there yet.
##   -- --mock-ranked            GOLD II, 42 RP; a race result that promotes to GOLD I
##   -- --mock-ranked placing    in placements (1 left); the race result ends them (PLACED)
## Release builds never use them: enabled() is false unless OS.is_debug_build().

const DAY_MS := 86_400_000


static func enabled() -> bool:
	return OS.is_debug_build() and "--mock-ranked" in Api.args


static func placing() -> bool:
	var i := Api.args.find("--mock-ranked")
	return i >= 0 and i + 1 < Api.args.size() and Api.args[i + 1] == "placing"


static func _now_ms() -> int:
	return int(Time.get_unix_time_from_system() * 1000.0)


static func _you() -> Dictionary:
	var recent := [
		{"at": _now_ms() - 600_000, "rpChange": 18, "wins": 4, "of": 5, "us": 65_412_000, "forfeit": false},
		{"at": _now_ms() - 3_600_000, "rpChange": -12, "wins": 1, "of": 5, "us": 66_930_000, "forfeit": false},
		{"at": _now_ms() - 7_200_000, "rpChange": 21, "wins": 4, "of": 5, "us": 65_208_000, "forfeit": false},
		{"at": _now_ms() - 86_000_000, "rpChange": -19, "wins": 0, "of": 5, "us": null, "forfeit": true},
		{"at": _now_ms() - 90_000_000, "rpChange": 14, "wins": 3, "of": 5, "us": 65_877_000, "forfeit": false},
	]
	if placing():
		for r: Dictionary in recent:
			r["rpChange"] = 0  # no RP during placements
		return {"tier": "UNRANKED", "division": "", "rp": 0, "ladder": 0, "placementsLeft": 1,
			"wins": 3, "losses": 1, "races": 4, "recent": recent.slice(0, 4)}
	return {"tier": "GOLD", "division": "II", "rp": 42, "ladder": 1442, "placementsLeft": 0,
		"wins": 23, "losses": 17, "races": 40, "recent": recent}


## GET /api/ranked?player=
static func info() -> Dictionary:
	var ladder := []
	var names := ["Mtkvari Mafia", "Nika K", "Apex Predators", "Kaito Mori", "Tbilisi GP", "Lena Brandt", "Rustavi Racing", "Sami Haddad", "Late Brakers", "Your Team"]
	var tiers := [["CHALLENGER", "", 212], ["CHALLENGER", "", 160], ["CHALLENGER", "", 97], ["GRANDMASTER", "", 71],
		["GRANDMASTER", "", 40], ["MASTER", "", 22], ["DIAMOND", "I", 64], ["DIAMOND", "III", 12], ["EMERALD", "I", 88], ["PLATINUM", "IV", 5]]
	for i in names.size():
		ladder.append({"rank": i + 1, "name": names[i], "tier": tiers[i][0], "division": tiers[i][1], "rp": tiers[i][2], "you": false})
	for i in 10:
		ladder.append({"rank": 11 + i, "name": "Driver %d" % (11 + i), "tier": "PLATINUM", "division": "IV", "rp": 3 - i / 4, "you": false})
	var board := []
	var times := [64_712_000, 64_955_000, 65_208_000, 65_544_000, 65_901_000, 66_120_000, 66_480_000, 66_902_000, 67_640_000, 68_310_000, 68_904_000, 69_420_000]
	var bnames := ["Mtkvari Mafia", "Kaito Mori", "Your Team", "Nika K", "Apex Predators", "Lena Brandt", "Tbilisi GP", "Sami Haddad", "Late Brakers", "Rustavi Racing", "Pit Lane Pals", "Grid Walkers"]
	for i in times.size():
		var us: int = times[i]
		board.append({"rank": i + 1, "name": bnames[i], "us": us, "medal": _medal(us), "you": bnames[i] == "Your Team"})
	var day := _now_ms() / DAY_MS
	return {
		"season": {"id": 1, "name": "SEASON 1", "endsAt": _now_ms() + 23 * DAY_MS},
		"you": _you(),
		"ladder": ladder,
		"daily": {"day": day, "drivers": 41, "closesAt": (day + 1) * DAY_MS, "medals": {"gold": 65_000_000, "silver": 66_500_000, "bronze": 68_500_000},
			"leaderboard": board, "you": {"rank": 3, "us": 65_208_000, "medal": "silver", "laps": 4},
			"ghost": {"attempt": "mock-ghost", "name": "Mtkvari Mafia", "us": 64_712_000}},
		"tiers": RankEmblem.TIERS.duplicate(),
	}


static func _medal(us: int) -> Variant:
	if us <= 65_000_000:
		return "gold"
	if us <= 66_500_000:
		return "silver"
	if us <= 68_500_000:
		return "bronze"
	return null


## POST /api/attempts {session: "ranked"}: the usual attempt fields plus rankedMatch.
static func attempt() -> Dictionary:
	var seed := Crypto.new().generate_random_bytes(32).hex_encode()
	return {
		"attempt": "mock-ranked-" + seed.substr(0, 8), "seed": seed, "car": {}, "stats": Profile.stats(), "setup": Profile.setup.duplicate(),
		"rankedMatch": {"opponents": _opponents(66_000_000)},
	}


## Five opponents around a lap time, fastest first: two faster, three slower.
static func _opponents(us: int) -> Array:
	var o := [
		{"name": "Kaito Mori", "tier": "GOLD", "division": "I", "us": us - 850_000, "ai": false},
		{"name": "AI Benchmark 1640", "tier": "GOLD", "division": "II", "us": us - 310_000, "ai": true},
		{"name": "Nika K", "tier": "GOLD", "division": "II", "us": us + 240_000, "ai": false},
		{"name": "Late Brakers", "tier": "GOLD", "division": "III", "us": us + 620_000, "ai": false},
		{"name": "AI Benchmark 1440", "tier": "SILVER", "division": "I", "us": us + 1_310_000, "ai": true},
	]
	return o


## POST /api/attempts/:id/run for a ranked attempt. `us` is the first completed lap (0: none or deleted).
static func run(us: int, valid: bool) -> Dictionary:
	var forfeit := us <= 0 or not valid
	var opps := []
	var wins := 0
	for o: Dictionary in _opponents(us if not forfeit else 66_000_000):
		var beat := not forfeit and us < int(o["us"])
		wins += 1 if beat else 0
		opps.append({"name": o["name"], "tier": o["tier"], "division": o["division"], "us": o["us"], "beat": beat, "ai": o["ai"]})
	var medal: Variant = "silver" if not forfeit else null
	var packs := []
	if not forfeit:
		packs = [{"id": "mock-pack-b", "reason": "ranked_bronze", "reasonName": "Ranked bronze medal", "earnedAt": _now_ms(), "openedAt": null, "medal": "bronze"},
			{"id": "mock-pack-s", "reason": "ranked_silver", "reasonName": "Ranked silver medal", "earnedAt": _now_ms(), "openedAt": null, "medal": "silver"}]
	var ranked := {
		"counted": true, "forfeit": forfeit, "us": us if not forfeit else null,
		"opponents": opps, "wins": wins, "of": 5, "rpChange": 18 if not forfeit else -21,
		"rank": {"tier": "GOLD", "division": "I", "rp": 6, "ladder": 1506, "placementsLeft": 0},
		"promoted": not forfeit, "demoted": false, "placed": false,
		"medal": medal, "packsEarned": packs, "daily": {"rank": 3, "of": 41},
	}
	if forfeit:
		ranked["rank"] = {"tier": "GOLD", "division": "II", "rp": 21, "ladder": 1421, "placementsLeft": 0}
	if placing():
		ranked["rank"] = {"tier": "GOLD", "division": "IV", "rp": 30, "ladder": 1230, "placementsLeft": 0}
		ranked["rpChange"] = 0  # no RP during placements
		ranked["promoted"] = false
		ranked["placed"] = true
	return {"verified": true, "best": {"us": us} if not forfeit else null, "position": 0, "packsEarned": packs, "pass": [], "ranked": ranked, "kmDriven": 0}


## GET /api/passes: 12 pools, 6 per class (daily and weekly; BRONZE, SILVER, GOLD).
static func passes() -> Dictionary:
	var pools := []
	var id := 100
	var day := _now_ms() / DAY_MS
	for cls: String in ["spec", "open"]:
		for kind: String in ["daily", "weekly"]:
			for t in 3:
				id += 1
				var stake: float = float([0.01, 0.05, 0.25][t]) * (1.0 if kind == "daily" else 4.0)
				var n: int = int([17, 9, 4][t]) + (3 if cls == "open" else 0)
				var standings := []
				for k in mini(n, 7):
					standings.append({"rank": k + 1, "name": ["Mtkvari Mafia", "Kaito Mori", "Your Team", "Nika K", "Apex Predators", "Lena Brandt", "Tbilisi GP"][k], "us": 64_900_000 + k * 410_000, "you": k == 2, "winSol": 0})
				pools.append({"id": id, "kind": kind, "cls": cls, "name": "%s %s" % [kind.to_upper(), ["BRONZE", "SILVER", "GOLD"][t]],
					"stakeSol": stake, "potSol": stake * n * 0.9, "entrants": n, "opensAt": day * DAY_MS,
					"closesAt": (day + (1 if kind == "daily" else 5)) * DAY_MS, "settled": null,
					"exampleSol": [stake * 7.2, stake * 4.1, stake * 2.6], "standings": standings,
					"you": {"entered": t == 0, "rank": 3 if t == 0 else 0}})
	return {"pools": pools, "wallet": null, "rules": {"paidPct": 20, "minPayoutX": 1.5, "rakePct": 10, "minEntrants": 4}}


## The garage offline in mock mode: three unopened packs, a gold medal pack first.
static func patch_garage(g: Dictionary) -> void:
	var packs: Dictionary = g.get("packs", {}) if g.get("packs") is Dictionary else {}
	var pending: Array = packs.get("pending", []) if packs.get("pending") is Array else []
	pending.push_front({"id": "mock-pack-g", "reason": "ranked_gold", "reasonName": "Ranked gold medal", "earnedAt": _now_ms(), "openedAt": null, "medal": "gold"})
	pending.append({"id": "mock-pack-s", "reason": "ranked_silver", "reasonName": "Ranked silver medal", "earnedAt": _now_ms(), "openedAt": null, "medal": "silver"})
	packs["pending"] = pending
	packs["unopened"] = pending.size()
	g["packs"] = packs
