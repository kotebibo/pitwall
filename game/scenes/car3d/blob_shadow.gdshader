// Soft contact shadow under the car: a rounded rectangle in three hard steps.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;

uniform vec4 color : source_color = vec4(0.02, 0.02, 0.03, 1.0);
uniform vec2 half_size = vec2(2.6, 0.75);
uniform float softness = 0.55;
uniform float strength = 0.62;

varying vec3 lp;

void vertex() {
	lp = VERTEX;
}

void fragment() {
	vec2 q = abs(lp.xz) - half_size;
	float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
	float s = clamp(1.0 - (d + softness) / (softness * 2.0), 0.0, 1.0);
	float stepped = s > 0.66 ? 1.0 : (s > 0.33 ? 0.6 : (s > 0.04 ? 0.3 : 0.0));
	if (stepped <= 0.0) {
		discard;
	}
	ALBEDO = color.rgb;
	ALPHA = stepped * strength;
}
