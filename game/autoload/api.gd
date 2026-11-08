extends Node
## The only place the game talks to the Pit Wall server.
##
## The client never decides race outcomes: it sends setups and receives results
## and replays produced by the server-side sim. In the web build the API is the
## server that served the page; in the editor it is a local server.

const LOCAL_BASE_URL := "http://localhost:8787"
const EXPLORER_TX := "https://explorer.solana.com/tx/%s?cluster=devnet"
const EXPLORER_ADDRESS := "https://explorer.solana.com/address/%s?cluster=devnet"

var base_url: String = LOCAL_BASE_URL
## The server's error message from the last failed request ("" if none).
var last_error := ""


## Debug and demo switches: command-line user args (`-- --autopilot`) or, on the
## web, URL parameters (`?autopilot&offline&race`), as "--name" strings.
var args: PackedStringArray = []


func _ready() -> void:
	args = OS.get_cmdline_user_args()
	if OS.is_debug_build() and args.has("--server") and args.find("--server") + 1 < args.size():
		base_url = args[args.find("--server") + 1]  # development: another local server
	# URL switches (?autopilot&offline...) only in debug builds: the public
	# release must not let an AI drive someone's qualifying laps.
	if OS.has_feature("web") and OS.is_debug_build():
		var query: Variant = JavaScriptBridge.eval("window.location.search", true)
		if query is String:
			for part: String in (query as String).trim_prefix("?").split("&", false):
				var kv := part.split("=")
				args.append("--" + kv[0])
				if kv.size() > 1:
					args.append(kv[1])
	if OS.has_feature("web"):
		var origin: Variant = JavaScriptBridge.eval("window.location.origin", true)
		if origin is String and not (origin as String).is_empty():
			base_url = origin


## GET a JSON value. Returns null on any failure; callers show their own error state.
func get_json(path: String) -> Variant:
	return await _request(path, HTTPClient.METHOD_GET, "")


## POST a JSON body. Returns the parsed response, or null on failure.
func post_json(path: String, payload: Dictionary) -> Variant:
	return await _request(path, HTTPClient.METHOD_POST, JSON.stringify(payload))


func _request(path: String, method: HTTPClient.Method, body: String) -> Variant:
	var request := HTTPRequest.new()
	request.timeout = 60.0
	add_child(request)
	var headers := PackedStringArray(["Content-Type: application/json"])
	if Profile.token != "":
		headers.append("Authorization: Bearer " + Profile.token)
	var err := request.request(base_url + path, headers, method, body)
	if err != OK:
		request.queue_free()
		return null
	var response: Array = await request.request_completed
	request.queue_free()
	var status: int = response[1]
	var raw: PackedByteArray = response[3]
	if status < 200 or status >= 300:
		push_warning("API %s %s -> %d %s" % [method, path, status, raw.get_string_from_utf8()])
		var body_json: Variant = JSON.parse_string(raw.get_string_from_utf8())
		last_error = String((body_json as Dictionary).get("error", "")) if body_json is Dictionary else ""
		return null
	last_error = ""
	if raw.is_empty():
		return {}  # 204 No Content (e.g. /api/track)
	return JSON.parse_string(raw.get_string_from_utf8())


## Anonymous play-test counters (what was opened or started); fire and forget.
func track(event: String, data: String = "") -> void:
	post_json("/api/track", {"player": Profile.id, "event": event, "data": data})


func open_tx(signature: String) -> void:
	OS.shell_open(EXPLORER_TX % signature)


func open_address(address: String) -> void:
	OS.shell_open(EXPLORER_ADDRESS % address)
