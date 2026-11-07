// Turntable floor: dark disc, fine grid, rings, a brand-red arc and an
// expanding pulse ring when a part is fitted. Pixel-crisp lines (fwidth).
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;

uniform vec4 base : source_color = vec4(0.115, 0.12, 0.135, 0.92);
uniform vec4 line : source_color = vec4(1.0, 1.0, 1.0, 0.07);
uniform vec4 ring : source_color = vec4(1.0, 1.0, 1.0, 0.16);
uniform vec4 accent : source_color = vec4(0.91, 0.21, 0.17, 0.75);
uniform float radius = 3.6;
uniform float grid = 0.5;
// Seconds since a part was fitted (negative: no pulse).
uniform float pulse = -1.0;
uniform vec4 pulse_color : source_color = vec4(0.95, 0.76, 0.19, 1.0);

varying vec3 lp;

void vertex() {
	lp = VERTEX;
}

float hline(float d, float w) {
	return 1.0 - step(w, abs(d));
}

void fragment() {
	float r = length(lp.xz);
	float pr = max(fwidth(r), 1e-4);
	if (r > radius) {
		discard;
	}
	// Banded fade toward the rim, pixel-art style.
	float k = r / radius;
	float fade = k < 0.62 ? 1.0 : (k < 0.82 ? 0.7 : 0.42);
	vec3 c = base.rgb;
	float a = base.a * fade;
	// Grid, fading out with the disc.
	vec2 g = abs(fract(lp.xz / grid + 0.5) - 0.5) * grid;
	vec2 pg = max(fwidth(lp.xz), vec2(1e-4));
	float gl = max(hline(g.x, pg.x * 0.6), hline(g.y, pg.y * 0.6)) * (1.0 - k);
	c = mix(c, line.rgb, gl * line.a * 3.0);
	// Rings.
	float ang = atan(lp.z, lp.x);
	float rim = hline(r - (radius - pr * 1.5), pr * 0.75);
	float r2 = hline(r - radius * 0.74, pr * 0.6) * step(0.5, fract(ang * 36.0 / 6.2831853));
	c = mix(c, ring.rgb, max(rim, r2) * ring.a * 2.5);
	a = max(a, rim * 0.95);
	// Brand arc on the outer ring (turns with the table).
	float arc = hline(r - radius * 0.88, pr * 1.1) * step(ang, -0.4) * step(-2.3, ang);
	c = mix(c, accent.rgb, arc * accent.a);
	a = max(a, arc * accent.a);
	// Fit pulse.
	if (pulse >= 0.0) {
		float pr2 = pulse * 7.0 + 1.2;
		float p = hline(r - pr2, pr * 1.2) * clamp(1.0 - pulse * 1.6, 0.0, 1.0);
		c = mix(c, pulse_color.rgb, p);
		a = max(a, p);
	}
	ALBEDO = c;
	ALPHA = a;
}
