// Coloured halo around one part group (hover highlight and fit flash): the
// part's back faces pushed outward a fixed number of screen pixels, so a thin
// rim shows just outside the part's dark outline. Drawn with a smooth-normal copy
// of the mesh, and only where the overlay has not marked the stencil (outside
// the group).
shader_type spatial;
render_mode unshaded, blend_mix, cull_front, depth_draw_never, shadows_disabled;
stencil_mode read, compare_not_equal, 1;

uniform vec4 color : source_color = vec4(1.0);
uniform float width_px = 2.0;

void vertex() {
	vec4 clip = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0));
	vec3 nv = mat3(MODELVIEW_MATRIX) * NORMAL;
	vec2 dir = (PROJECTION_MATRIX * vec4(nv, 0.0)).xy;
	float l = length(dir);
	if (l > 1e-5) {
		clip.xy += dir / l * width_px * 2.0 / VIEWPORT_SIZE * clip.w;
	}
	POSITION = clip;
}

void fragment() {
	ALBEDO = color.rgb;
	ALPHA = color.a;
}
