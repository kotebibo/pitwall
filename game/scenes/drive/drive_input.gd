class_name DriveInput
extends RefCounted
## Turns keyboard or gamepad into the four whole-number inputs the physics takes.
##
## Gamepad: analog steering, throttle and brake, passed straight through.
## Keyboard: keys are on or off, so steering and throttle ramp over a few ticks,
## and full brake follows the pressure curve a driver uses (hard at speed,
## bleeding off as downforce fades), set just under the locking point.
## The result is what gets recorded, so the server re-drives exactly this.

const STEER_IN := 14  # per tick toward full lock (about 75 ms)
const STEER_OUT := 22
const THROTTLE_IN := 15  # about 140 ms to full throttle
const THROTTLE_OUT := 64
const BRAKE_IN := 40
const DEADZONE := 0.08

var steer := 0
var throttle := 0
var brake := 0
var boost := false
var reverse := false
var using_gamepad := false


static func ensure_actions() -> void:
	var keys := {
		"drive_throttle": [KEY_UP, KEY_W],
		"drive_brake": [KEY_DOWN, KEY_S, KEY_SPACE],
		"drive_reverse": [KEY_X],
		"drive_left": [KEY_LEFT, KEY_A],
		"drive_right": [KEY_RIGHT, KEY_D],
		"drive_boost": [KEY_SHIFT, KEY_E],
		"drive_restart": [KEY_R],
		"drive_pause": [KEY_ESCAPE, KEY_P],
	}
	var pads := {
		"drive_boost": [JOY_BUTTON_A, JOY_BUTTON_RIGHT_SHOULDER],
		"drive_reverse": [JOY_BUTTON_B],
		"drive_restart": [JOY_BUTTON_Y],
		"drive_pause": [JOY_BUTTON_START],
	}
	for action: String in keys:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		for k: Key in keys[action]:
			var e := InputEventKey.new()
			e.physical_keycode = k
			InputMap.action_add_event(action, e)
		for b: JoyButton in pads.get(action, []):
			var j := InputEventJoypadButton.new()
			j.button_index = b
			InputMap.action_add_event(action, j)


## Reads the devices for one physics tick.
func poll(car: CarSim) -> void:
	var v := car.speed / 65536.0
	var pad_steer := 0.0
	var pad_throttle := 0.0
	var pad_brake := 0.0
	for device in Input.get_connected_joypads():
		var x := Input.get_joy_axis(device, JOY_AXIS_LEFT_X)
		if absf(x) > DEADZONE:
			pad_steer = signf(x) * pow((absf(x) - DEADZONE) / (1.0 - DEADZONE), 1.6)
		pad_throttle = maxf(pad_throttle, Input.get_joy_axis(device, JOY_AXIS_TRIGGER_RIGHT))
		pad_brake = maxf(pad_brake, Input.get_joy_axis(device, JOY_AXIS_TRIGGER_LEFT))
	var key_steer := int(Input.is_action_pressed("drive_right")) - int(Input.is_action_pressed("drive_left"))
	var key_throttle := Input.is_action_pressed("drive_throttle")
	var key_brake := Input.is_action_pressed("drive_brake")

	if absf(pad_steer) > 0.0 or pad_throttle > DEADZONE or pad_brake > DEADZONE:
		using_gamepad = true
	if key_steer != 0 or key_throttle or key_brake:
		using_gamepad = false

	# The faster the car, the less a full input steers (and the slower a key feeds it
	# in), so at speed you can't throw the car past the grip and into a slide.
	var fast := clampf((v - 15.0) / 55.0, 0.0, 1.0)
	if using_gamepad:
		steer = roundi(pad_steer * 127.0 * lerpf(1.0, 0.75, fast))
		throttle = roundi(clampf((pad_throttle - DEADZONE) / (1.0 - DEADZONE), 0.0, 1.0) * 255.0)
		brake = roundi(clampf((pad_brake - DEADZONE) / (1.0 - DEADZONE), 0.0, 1.0) * 255.0)
	else:
		# A key is all or nothing: about 55% of the lock at 300 km/h, fed in four times slower
		var lock := roundi(127.0 * lerpf(1.0, 0.55, fast))
		var rate := roundi(lerpf(14.0, 3.0, fast))
		var target := key_steer * lock
		if target == 0 or signi(target) != signi(steer):
			steer = move_toward(steer, 0, STEER_OUT) as int
		if target != 0:
			steer = move_toward(steer, target, rate) as int
		if absi(steer) > lock:
			steer = move_toward(steer, target, rate) as int
		if key_throttle:
			# out of a corner a key can't feather, so ease the cap while the wheel is turned
			var cap := roundi(_keyboard_throttle(car, v) * (1.0 - 0.35 * absi(steer) / 127.0))
			throttle = mini(move_toward(throttle, 255, THROTTLE_IN) as int, maxi(cap, 80))
		else:
			throttle = move_toward(throttle, 0, THROTTLE_OUT) as int
		if key_brake:
			brake = mini(brake + BRAKE_IN, _keyboard_brake(car, v))
		else:
			brake = 0
	boost = Input.is_action_pressed("drive_boost")
	reverse = Input.is_action_pressed("drive_reverse")


## Pedal a driver would hold at this speed: just under where the front locks.
func _keyboard_brake(car: CarSim, v: float) -> int:
	var k_down := car.k_down / 65536.0
	var share := car.front_share / 65536.0
	var mu := car.mu_base / 65536.0
	var front_load := 3706.0 + k_down * v * v * share + 2600.0  # static + downforce + transfer under braking
	var grip := mu * front_load * 0.97
	var pedal := grip / (54000.0 * car.brake_front / 65536.0)
	return clampi(roundi(pedal * 255.0), 60, 255)


## Throttle a driver would feed out of a slow corner: just under rear wheelspin in a straight line.
func _keyboard_throttle(car: CarSim, v: float) -> int:
	var k_down := car.k_down / 65536.0
	var share := car.front_share / 65536.0
	var mu := car.mu_base / 65536.0
	var rear_load := 4142.0 + k_down * v * v * (1.0 - share) + 500.0
	var grip := mu * rear_load * (car.traction_grip / 65536.0) * 0.96
	var power := (car.p_ice + (CarSim.P_BOOST if boost else 0)) / 1.0
	var drive := minf(power / maxf(v, 10.0), car.f_drive_max / 65536.0)
	return clampi(roundi(grip / drive * 255.0), 90, 255)


## Bit 0: Boost, bit 1: reverse gear.
func buttons() -> int:
	return (1 if boost else 0) | (2 if reverse else 0)
