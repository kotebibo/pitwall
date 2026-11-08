# Art notes: car, parts, cards, packs

Everything here is generated. Edit the scripts in `tools/art/` and re-run them; never hand-edit the PNGs.

```
python tools/art/car.py     # car layers, anchors.json, car/preview_combos.png
python tools/art/parts.py   # parts/*.png (3/4 renders via tools/art/r3d.py)
python tools/art/cards.py   # cards/*.png + cards/layout.json
python tools/art/packs.py   # packs/*.png
python tools/art/sheet.py   # preview_all.png (run last)
```

Import settings: Filter = Nearest, Mipmaps off, lossless. All PNGs are RGBA.

## Car: how to assemble

- Scale 10 px per metre. Every full-car layer is **80 x 32**, nose pointing **+x**, car centre at the pixel corner **(40, 16)**, so with `Sprite2D.centered = true` all layers share one origin. The car is mirror-symmetric about the line between rows 15 and 16. Light is baked from the top-left.
- `_paint` layers are a near-grey ramp (#fdfcf8 highlight down to #6b6c74 shadow, #3b3c44 outline) with a hint of warm highlight / cool shadow. Tint them with the team colour through `modulate` (multiply). Draw each part's `_detail` layer **on top of** its `_paint` layer, untinted. It holds carbon, tyres, chrome, visor and inlets, plus small semi-transparent warm-white pixels that lift the brightest paint above the team colour (multiply alone cannot brighten).
- Helmet: tint `helmet_paint` with the secondary colour. `halo_detail`, drawn after it, carries the visor and helmet highlights.
- Stack (bottom to top):
  1. `shadow`
  2. `floor_<low_rake|high_rake|venturi>`
  3. `tyre_rear` (or `tyre_rear_<compound>`)
  4. `tyre_front` x2 at the front wheel anchors (rotate with steering; `flip_v` the +y wheel so the stripe stays outboard)
  5. `brake_disc_glow` (optional; fade its alpha in under hard braking)
  6. `sidepods_<downwash|zeropod|undercut>_paint`, then `_detail`
  7. `body_paint`, `body_detail`
  8. `front_wing_<outwash|inwash|highnose>_paint`, `_detail` (each variant carries its own nose tip)
  9. `rear_wing_<spoon|highdf|beam>[_open]_paint`, `_detail` (swap to `_open` in Straight Mode)
  10. `helmet_paint` (secondary tint), `halo_detail`
  11. `lights` (rain light; blink it)
- Anchors (`car/anchors.json`, px relative to the car centre, y down): front wheels (18, -8) and (18, 8); rear wheels (-18, -8) and (-18, 8); rain light (-30, 0); exhaust (-25, 0); helmet (4, 0). Wheelbase 3.6 m, track 1.6 m. The car measures about 6.0 x 2.2 m tip to tip (wings slightly oversized to read).
- Every floor / sidepod / front wing / rear wing combination stacks without gaps: pods tuck under the body, wings overlap the nose, floors only show at the edges. The shadow is the union of all variants, so a few shadow pixels can sit under a part that is not fitted; they read as floor shadow.

## Cards

- Card 112 x 152. Rects in `cards/layout.json` are [x, y, w, h]: art window (24, 18, 64, 64), rarity label (34, 5, 44, 9), name plate (8, 87, 96, 13), stats area (8, 104, 96, 38) split into 3 stat rows.
- The art window is transparent. Draw `window_bg_<rarity>` (optional) and the part art under the frame.
- Glows are 136 x 176: draw centred behind the card (card at +12, +12). No text is baked into frames; render name, rarity and stats with the UI font (ink #f1efea, ink-2 #a3a3ad).

## Files

### Car (top-down, layered)

- `car/shadow.png` (80x32): Car shadow, one alpha level (#000 @ 45%), already offset +2,+2; union of all part variants.
- `car/tyre_rear.png` (80x32): Both rear tyres in place (medium compound stripe).
- `car/tyre_front.png` (10x6): ONE front tyre centred on its own canvas (medium). Place 2 copies at the front_wheels anchors, rotate for steering, flip_v for the +y wheel.
- `car/tyre_rear_soft.png` (80x32): Rear tyres, soft compound (red sidewall stripe).
- `car/tyre_front_soft.png` (10x6): Front tyre, soft compound.
- `car/tyre_rear_medium.png` (80x32): Rear tyres, medium compound (yellow sidewall stripe).
- `car/tyre_front_medium.png` (10x6): Front tyre, medium compound.
- `car/tyre_rear_hard.png` (80x32): Rear tyres, hard compound (white sidewall stripe).
- `car/tyre_front_hard.png` (10x6): Front tyre, hard compound.
- `car/tyre_rear_inter.png` (80x32): Rear tyres, inter compound (green sidewall stripe, treaded).
- `car/tyre_front_inter.png` (10x6): Front tyre, inter compound.
- `car/tyre_rear_wet.png` (80x32): Rear tyres, wet compound (blue sidewall stripe, treaded).
- `car/tyre_front_wet.png` (10x6): Front tyre, wet compound.
- `car/floor_low_rake.png` (80x32): Floor, low rake: wide flat plank, straight edges, small diffuser (carbon only).
- `car/floor_high_rake.png` (80x32): Floor, high rake: narrower floor, bargeboard vanes, big diffuser poking out behind the rear wheels.
- `car/floor_venturi.png` (80x32): Floor, venturi: scalloped edge wings at the outer edge, floor fences ahead of the pods.
- `car/body_paint.png` (80x32): Monocoque, nose cone, engine cover, cockpit rim (tintable, team colour).
- `car/body_detail.png` (80x32): Body fixed colours: cockpit, airbox, T-cam, gearbox, exhaust, suspension, mirrors, highlights.
- `car/sidepods_downwash_paint.png` (80x32): Sidepods downwash: long pods ramping down and tapering to the rear (tintable).
- `car/sidepods_downwash_detail.png` (80x32): Sidepods downwash: inlets, fins, shadows, highlights.
- `car/sidepods_zeropod_paint.png` (80x32): Sidepods zeropod: slim flanks, slot inlet, exposed side-impact fins, gills (tintable).
- `car/sidepods_zeropod_detail.png` (80x32): Sidepods zeropod: inlets, fins, shadows, highlights.
- `car/sidepods_undercut_paint.png` (80x32): Sidepods undercut: wide letterbox inlet and shoulder, deep undercut behind it (tintable).
- `car/sidepods_undercut_detail.png` (80x32): Sidepods undercut: inlets, fins, shadows, highlights.
- `car/front_wing_outwash_paint.png` (80x32): Front wing + nose tip outwash: curved flaps, endplate foot curling outboard, low nose (tintable).
- `car/front_wing_outwash_detail.png` (80x32): Front wing outwash: carbon mainplane, slots, pylons, highlights.
- `car/front_wing_inwash_paint.png` (80x32): Front wing + nose tip inwash: flaps sweeping back toward the nose, short simple endplate (tintable).
- `car/front_wing_inwash_detail.png` (80x32): Front wing inwash: carbon mainplane, slots, pylons, highlights.
- `car/front_wing_highnose_paint.png` (80x32): Front wing + nose tip highnose: straight elements, short raised nose with two visible pylons (tintable).
- `car/front_wing_highnose_detail.png` (80x32): Front wing highnose: carbon mainplane, slots, pylons, highlights.
- `car/rear_wing_spoon_paint.png` (80x32): Rear wing spoon: curved main plane dipping in the middle, thin flap (tintable).
- `car/rear_wing_spoon_detail.png` (80x32): Rear wing spoon: slots, gurney, DRS pod, pylon.
- `car/rear_wing_spoon_open_paint.png` (80x32): Rear wing spoon, Straight Mode open: slimmer flap (tintable).
- `car/rear_wing_spoon_open_detail.png` (80x32): Rear wing spoon, Straight Mode open: blue-grey gap line.
- `car/rear_wing_highdf_paint.png` (80x32): Rear wing highdf: deep main plane, big flap, gurney (tintable).
- `car/rear_wing_highdf_detail.png` (80x32): Rear wing highdf: slots, gurney, DRS pod, pylon.
- `car/rear_wing_highdf_open_paint.png` (80x32): Rear wing highdf, Straight Mode open: slimmer flap (tintable).
- `car/rear_wing_highdf_open_detail.png` (80x32): Rear wing highdf, Straight Mode open: blue-grey gap line.
- `car/rear_wing_beam_paint.png` (80x32): Rear wing beam: smaller top wing plus a carbon beam wing below (tintable).
- `car/rear_wing_beam_detail.png` (80x32): Rear wing beam: slots, gurney, DRS pod, pylon.
- `car/rear_wing_beam_open_paint.png` (80x32): Rear wing beam, Straight Mode open: slimmer flap (tintable).
- `car/rear_wing_beam_open_detail.png` (80x32): Rear wing beam, Straight Mode open: blue-grey gap line.
- `car/halo_detail.png` (80x32): Halo hoop + centre pillar, helmet visor and helmet highlights (fixed colours).
- `car/helmet_paint.png` (80x32): Driver helmet top-down (tintable, secondary colour).
- `car/lights.png` (80x32): Rear rain light (centre) + endplate LEDs; toggle/blink in rain.
- `car/brake_disc_glow.png` (80x32): Four orange brake-disc glows at the hubs (fade in under hard braking).
- `car/anchors.json` (json): Canvas/centre/scale, wheel, rain-light, exhaust and helmet anchors, stack order.
- `car/preview_combos.png` (1008x712): Contact sheet: default combo in red/white/blue, 9 combos at 4x, plus steering, Straight Mode + rain light, braking glow.

### Part card art

- `parts/front_wing_outwash.png` (64x64): Part card art: front wing, outwash (endplate feet curling out). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/front_wing_inwash.png` (64x64): Part card art: front wing, inwash (flaps swept toward the nose). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/front_wing_highnose.png` (64x64): Part card art: front wing, high nose on pylons. 3/4 view, brand red, carbon weave, floor shadow.
- `parts/rear_wing_spoon.png` (64x64): Part card art: rear wing, spoon (dipped centre). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/rear_wing_highdf.png` (64x64): Part card art: rear wing, high downforce (big flap + gurney). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/rear_wing_beam.png` (64x64): Part card art: rear wing with beam wing. 3/4 view, brand red, carbon weave, floor shadow.
- `parts/sidepods_downwash.png` (64x64): Part card art: sidepod, downwash ramp. 3/4 view, brand red, carbon weave, floor shadow.
- `parts/sidepods_zeropod.png` (64x64): Part card art: sidepod, zero-pod (slot inlet, side-impact fin, gills). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/sidepods_undercut.png` (64x64): Part card art: sidepod, deep undercut under a wide inlet shelf. 3/4 view, brand red, carbon weave, floor shadow.
- `parts/floor_high_rake.png` (64x64): Part card art: floor, high rake (bargeboards, big diffuser). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/floor_low_rake.png` (64x64): Part card art: floor, low rake (flat, small diffuser). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/floor_venturi.png` (64x64): Part card art: floor, venturi (fences, edge wings). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/suspension_pushrod.png` (64x64): Part card art: suspension, pushrod (yellow rod runs up to a rocker high on the chassis). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/suspension_pullrod.png` (64x64): Part card art: suspension, pullrod (yellow rod runs down to a rocker low on the chassis). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/power_unit_torque.png` (64x64): Part card art: V6 hybrid PU, torque spec (gold gear train, big MGU-K with yellow ring). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/power_unit_topend.png` (64x64): Part card art: V6 hybrid PU, top-end spec (big turbo, tall plenum + trumpets). 3/4 view, brand red, carbon weave, floor shadow.
- `parts/power_unit_efficiency.png` (64x64): Part card art: V6 hybrid PU, efficiency spec (glowing blue battery cells). 3/4 view, brand red, carbon weave, floor shadow.

### Cards

- `cards/frame_common.png` (112x152): Card frame, common: transparent 64x64 art window, plates for label/name/stats, 1 rarity pip(s).
- `cards/frame_rare.png` (112x152): Card frame, rare: transparent 64x64 art window, plates for label/name/stats, 2 rarity pip(s).
- `cards/frame_epic.png` (112x152): Card frame, epic: transparent 64x64 art window, plates for label/name/stats, 3 rarity pip(s).
- `cards/frame_legendary.png` (112x152): Card frame, legendary: transparent 64x64 art window, plates for label/name/stats, 4 rarity pip(s).
- `cards/glow_rare.png` (136x176): Stepped, dithered rare glow; draw behind the card, card at (+12, +12).
- `cards/glow_epic.png` (136x176): Stepped, dithered epic glow; draw behind the card, card at (+12, +12).
- `cards/glow_legendary.png` (136x176): Stepped, dithered legendary glow; draw behind the card, card at (+12, +12).
- `cards/back.png` (112x152): Card back: PW monogram shield, racing stripes, chequered bands.
- `cards/window_bg_common.png` (64x64): Optional backdrop for the art window (common spotlight).
- `cards/window_bg_rare.png` (64x64): Optional backdrop for the art window (rare spotlight).
- `cards/window_bg_epic.png` (64x64): Optional backdrop for the art window (epic spotlight).
- `cards/window_bg_legendary.png` (64x64): Optional backdrop for the art window (legendary spotlight).
- `cards/layout.json` (json): Pixel rects: art_window, rarity_label, name_plate, stats_area (+ 3 stat_rows), glow offset.

### Development pack

- `packs/pack_closed.png` (96x112): Sealed DEV PACK foil pouch: red brand band, stencil DEV PACK, barcode/serial, hazard strip.
- `packs/pack_shake_1.png` (96x112): Anticipation frame: tilted right, squashed 3 rows (bottom anchored).
- `packs/pack_shake_2.png` (96x112): Anticipation frame: tilted left, squashed 1 row.
- `packs/pack_open.png` (96x112): Top seal torn off, strip curling away, light beams pouring out.
- `packs/burst.png` (64x64): Radial pixel burst for the reveal (centre it on the pack mouth / card).
- `packs/sparkle.png` (32x8): Sparkle, 4 frames of 8x8 in a horizontal strip (hframes = 4).

### Sheets

- `preview_all.png` (1640x3536): Contact sheet of everything at 3x on #141518.

### Generator scripts (tools/art/)

- `pxl.py`: shared pixel helpers, palettes (UI, paint, carbon, tyre, metal, visor), 3x5 and 5x7 bitmap fonts.
- `car.py`: top-down car layers, tyre compounds, shadow, lights, brake glow, anchors, combo preview.
- `r3d.py`: tiny flat-shaded 3D rasteriser that outputs palette-quantised, outlined pixel art (used by parts.py).
- `parts.py`: the 17 part-card illustrations.
- `cards.py`: frames, back, glows, window backdrops, layout.json.
- `packs.py`: pack frames, burst, sparkle.
- `sheet.py`: preview_all.png.
- `ranked.py`: ranked tier emblems, 32 px badges, medals, medal packs, PROMOTED banner, ranked/preview_ranked.png.

## Ranked (tier emblems, medals, medal packs)

```
python tools/art/ranked.py   # ranked/*.png + ranked/preview_ranked.png (also run by build_all.py)
```

Contact sheet: `ranked/preview_ranked.png` (3x on #141518, with a 1x strip at the bottom). `ranked.py` reuses `packs.py` (`make_pouch`, `tear_open`, `skew`) by swapping its foil ramp, so the medal packs stay pixel-identical in layout to `packs/pack_closed.png`.

- `ranked/emblem_<tier>.png` (64x64, transparent), tiers `iron bronze silver gold platinum emerald diamond master grandmaster challenger`, plus `emblem_unranked.png` (grey outline crest with "?", for placements). One family, more layers per tier: Iron is a plain chipped shield; Bronze adds the tyre ring (sidewall stripe in the tier colour); Silver adds a centre peak and a chequered band; Gold adds the helmet-visor crest and a laurel; Platinum adds wings; Emerald adds gems; Diamond adds 4 feathers and faceted rim; Master swaps the helmet for a crown; Grandmaster and Challenger get gold trim (crown, laurel; Challenger wings too), Challenger has a white-gold rim and a blue enamel field.
- **Division numeral:** the shield's centre is a plain recessed enamel field (the tier's dark tone) kept free for the UI. Safe box at 1x: x 22..41, y 24..40 (`Rect2(22, 24, 20, 17)`), optical centre (32, 32). Ink #f1efea with a 1 px #08090b drop shadow reads on every tier (see the mock row on the sheet). For a numeral *under* the emblem, the lowest opaque row is 62 (Challenger's laurel); draw it just below the 64 px box. The unranked crest's inner field is #1d1f23 at alpha 200 (smoked glass).
- `ranked/badge_<tier>.png` (32x32): the same emblems reduced 2:1 by block majority (keeps outlines and gems that a nearest 0.5 scale drops). Use these for 32 px badges instead of scaling the 64 px art by 0.5. They are too small for a numeral inside; put it beside or under.
- `ranked/medal_<bronze|silver|gold>.png` (24x24): disc medal with an engraved star on a brand-red ribbon with a chequered centre stripe.
- `ranked/pack_closed_<medal>.png`, `pack_shake_1_<medal>.png`, `pack_shake_2_<medal>.png`, `pack_open_<medal>.png` (96x112, same frames and anchors as `packs/`): the pouch in bronze/silver/gold foil, the DEV/PACK plate replaced by a medal plus "<MEDAL> PACK".
- `ranked/rank_up.png` (128x32): "PROMOTED" ribbon banner (brand red, chequered edges, folded tails) for the result screen.
- Ramps come from `tramp()` in `ranked.py`: six steps from each contract colour, shadows hue-shifted toward blue-violet, lights toward warm yellow.
