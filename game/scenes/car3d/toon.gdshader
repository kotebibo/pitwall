// Toon shading for the 3D car: three hard light bands, a hard specular glint,
// and a rim light from any light behind the subject. Works in the Compatibility
// renderer (custom light() is evaluated per directional light).
shader_type spatial;
render_mode cull_back, depth_draw_opaque;

uniform vec4 albedo : source_color = vec4(1.0);
uniform vec4 emission : source_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform float emission_energy = 0.0;
// Strength and size of the hard specular glint (0 = matte).
uniform float gloss : hint_range(0.0, 2.0) = 0.0;
uniform float gloss_size : hint_range(0.0, 0.3) = 0.02;
uniform float rim_strength : hint_range(0.0, 3.0) = 0.8;
// Brightness of the middle light band.
uniform float band_mid : hint_range(0.0, 1.0) = 0.55;

void fragment() {
	ALBEDO = albedo.rgb;
	EMISSION = emission.rgb * emission_energy;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	vec3 col = LIGHT_COLOR / PI * ATTENUATION;
	float ndl = dot(NORMAL, LIGHT);
	if (dot(LIGHT, VIEW) < -0.2) {
		// Light from behind the subject: rim only, on edges turned away from the camera.
		float nv = dot(NORMAL, VIEW);
		float r = step(nv, 0.28) * step(0.3, ndl) * rim_strength;
		DIFFUSE_LIGHT += col * r * 0.7;
	} else {
		float band = ndl > 0.5 ? 1.0 : (ndl > 0.08 ? band_mid : 0.0);
		DIFFUSE_LIGHT += col * band;
		vec3 h = normalize(LIGHT + VIEW);
		SPECULAR_LIGHT += col * gloss * step(1.0 - gloss_size, dot(NORMAL, h)) * step(0.0, ndl);
	}
}
