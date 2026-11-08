extends Node
## The player on this device: an anonymous id, a team name and the car setup.
## No wallet or login; the server keys qualifying results by this id.

const PATH := "user://profile.cfg"
const DEFAULT_SETUP := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}

var id := ""
var team_name := "Your Team"
var tutorial_done := false
## Account (empty token = playing as a guest)
var token := ""
var wallet := ""
var account_prompted := false
var garage_tour_done := false
var setup := DEFAULT_SETUP.duplicate()
## Car colours ("#rrggbb"; "" = default): the account's livery, cached so it shows offline.
## Cosmetic only: never sent to the sim. Read it through Catalog.livery_color().
var livery := {"primary": "", "secondary": ""}
## Last event info from the server (driver stats, leaderboard, setup lock).
var event: Dictionary = {}


func _ready() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(PATH) == OK:
		id = cfg.get_value("player", "id", "")
		team_name = cfg.get_value("player", "team", team_name)
		tutorial_done = cfg.get_value("player", "tutorial_done", false)
		token = cfg.get_value("account", "token", "")
		wallet = cfg.get_value("account", "wallet", "")
		account_prompted = cfg.get_value("account", "prompted", false)
		garage_tour_done = cfg.get_value("player", "garage_tour_done", false)
		var saved: Variant = cfg.get_value("car", "setup", {})
		if saved is Dictionary:
			for k: String in DEFAULT_SETUP:
				setup[k] = int((saved as Dictionary).get(k, DEFAULT_SETUP[k]))
		var saved_livery: Variant = cfg.get_value("car", "livery", {})
		if saved_livery is Dictionary:
			for k: String in livery:
				livery[k] = String((saved_livery as Dictionary).get(k, ""))
	if id.is_empty():
		id = Crypto.new().generate_random_bytes(16).hex_encode()
		save()
	var args := Api.args
	if "--player" in args:
		id = args[args.find("--player") + 1]  # testing: act as another player


func save() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("player", "id", id)
	cfg.set_value("player", "team", team_name)
	cfg.set_value("player", "tutorial_done", tutorial_done)
	cfg.set_value("account", "token", token)
	cfg.set_value("account", "wallet", wallet)
	cfg.set_value("account", "prompted", account_prompted)
	cfg.set_value("player", "garage_tour_done", garage_tour_done)
	cfg.set_value("car", "setup", setup)
	cfg.set_value("car", "livery", livery)
	cfg.save(PATH)


func is_signed_in() -> bool:
	return token != ""


## Server response from register / login: {token, player, name, wallet}.
func sign_in(res: Dictionary) -> void:
	token = String(res.get("token", ""))
	if String(res.get("player", id)) != id:
		livery = {"primary": "", "secondary": ""}  # another player's car: its garage brings its livery
	id = String(res.get("player", id))
	team_name = String(res.get("name", team_name))
	wallet = String(res.get("wallet", "")) if res.get("wallet") is String else ""
	account_prompted = true
	save()


## Back to a fresh guest: the account's progress stays with the account.
func sign_out() -> void:
	token = ""
	wallet = ""
	team_name = "Your Team"
	livery = {"primary": "", "secondary": ""}
	id = Crypto.new().generate_random_bytes(16).hex_encode()
	event = {}
	save()


## Driver stats for driving, from the server's event info (starter values offline).
func stats() -> Dictionary:
	var driver: Dictionary = event.get("driver", {})
	var s: Dictionary = driver.get("stats", {})
	if s.is_empty():
		return {"braking": 64, "cornering": 64, "traction": 68, "energy": 72}
	var out := {}
	for k: String in s:
		out[k] = int(s[k])
	return out


func setup_locked() -> bool:
	var you: Dictionary = event.get("you", {})
	return bool(you.get("setupLocked", false))
