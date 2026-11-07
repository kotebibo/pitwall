class_name Fx
## Whole-number maths for the driving physics. Values are 16.16 fixed point
## (ONE = 1.0). No floats anywhere in sim/, so a lap driven in a browser
## re-drives to the exact same microsecond on the server.

const ONE := 65536
const HALF := 32768
const TWO_PI := 411775  # round(2 * pi * ONE); angles wrap at this value
const PI_FP := 205887
const TICKS := 120  # physics ticks per second


static func mul(a: int, b: int) -> int:
	return (a * b) >> 16


static func div(a: int, b: int) -> int:
	if b == 0:
		return 0
	return (a << 16) / b


static func wrap_angle(a: int) -> int:
	return posmod(a, TWO_PI)


## sin of an angle in fixed-point radians, from the stored table with linear interpolation.
static func sin_a(angle: int) -> int:
	var t := (wrap_angle(angle) << 28) / TWO_PI  # table index in 16.16
	var i := t >> 16
	var f := t & 0xFFFF
	var v := SineTable.VALUES
	return v[i] + (((v[i + 1] - v[i]) * f) >> 16)


static func cos_a(angle: int) -> int:
	return sin_a(angle + (PI_FP >> 1))


## Integer square root (floor). For a fixed-point x, isqrt(x << 16) is sqrt(x) in fixed point.
static func isqrt(n: int) -> int:
	if n <= 0:
		return 0
	var shift := 0
	var t := n
	while t > 0:
		t >>= 2
		shift += 1
	var x := 1 << shift
	while true:
		var y := (x + n / x) >> 1
		if y >= x:
			return x
		x = y
	return x


## Length of a fixed-point vector, in fixed point.
static func length(x: int, y: int) -> int:
	return isqrt(x * x + y * y)


static func from_float(v: float) -> int:
	return roundi(v * ONE)


static func to_float(v: int) -> float:
	return v / float(ONE)
