// Full-screen pass in the showcase's SubViewport: draws a 1-pixel dark outline
// on the near side of every depth edge (silhouettes and overlaps). Assumes an
// orthographic camera, so depth is linear. The floor and shadow do not write
// depth, so the car is outlined against them too.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, depth_test_disabled, cull_disabled, shadows_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform vec4 color : source_color = vec4(0.035, 0.038, 0.05, 1.0);
// Depth jump (metres) that counts as an edge.
uniform float threshold = 0.12;
// Camera far - near.
uniform float depth_range = 40.0;

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 0.0, 1.0);
}

float lin(vec2 uv) {
	float d = texture(depth_tex, uv).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return d * depth_range;
#else
	return (1.0 - d) * depth_range;
#endif
}

void fragment() {
	vec2 px = 1.0 / VIEWPORT_SIZE;
	float d = lin(SCREEN_UV);
	float l = lin(SCREEN_UV - vec2(px.x, 0.0));
	float r = lin(SCREEN_UV + vec2(px.x, 0.0));
	float u = lin(SCREEN_UV - vec2(0.0, px.y));
	float b = lin(SCREEN_UV + vec2(0.0, px.y));
	float e = max(l + r - 2.0 * d, u + b - 2.0 * d);
	if (e < threshold || d >= depth_range * 0.999) {
		discard;
	}
	ALBEDO = color.rgb;
	ALPHA = color.a;
}
