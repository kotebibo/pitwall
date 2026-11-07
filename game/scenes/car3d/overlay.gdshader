// Additive overlay drawn over one part group: hover highlight and the
// "part fitted" flash. Brighter toward the silhouette. It also marks the
// group's visible pixels in the stencil buffer so the halo pass (halo.gdshader)
// only draws outside the group.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back, shadows_disabled;
stencil_mode write, compare_always, 1;

uniform vec4 color : source_color = vec4(1.0);
uniform float amount = 0.0;
uniform float edge = 0.6;

void vertex() {
	VERTEX += NORMAL * 0.004;
}

void fragment() {
	float f = 1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	ALBEDO = color.rgb * amount * mix(1.0, 0.35 + 1.4 * f, edge);
	ALPHA = 1.0;
}
