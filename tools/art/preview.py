"""Contact sheet for the environment + UI art, at 3x on the UI background.

Every tileable texture is shown tiled 3x3 (strips 4x along u) so seams would
show. A small track mock puts the textures and props together at 1 px = 0.25 m.

    python tools/art/preview.py      # writes game/assets/sprites/preview_env_ui.png
"""

from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image

from pixel import SPRITES, UI, blend, canvas, draw_text, hx, load, save, scale, text_width, tile

T = SPRITES / "track"
D = SPRITES / "deco"
U = SPRITES / "ui"
OUT = SPRITES / "preview_env_ui.png"
BG = UI["bg"]
LABEL = UI["ink2"]
HEAD = UI["ink"]


def L(path):
    return load(path)


def on_bg(img, color=BG, pad=0):
    c = canvas(img.shape[1] + pad * 2, img.shape[0] + pad * 2, color)
    blend(c, img, pad, pad)
    return c


def nine_slice(img, m, w, h):
    """Stretch a 9-slice texture with equal margins m to w x h (nearest)."""
    ih, iw = img.shape[:2]
    out = canvas(w, h)
    xs = [0, m, iw - m, iw]
    ys = [0, m, ih - m, ih]
    xd = [0, m, w - m, w]
    yd = [0, m, h - m, h]
    for j in range(3):
        for i in range(3):
            src = img[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            tw, th = xd[i + 1] - xd[i], yd[j + 1] - yd[j]
            if tw <= 0 or th <= 0:
                continue
            part = np.array(Image.fromarray(src).resize((tw, th), Image.NEAREST))
            out[yd[j]:yd[j + 1], xd[i]:xd[i + 1]] = part
    return out


def nine_slice_xy(img, mx, my, w, h):
    ih, iw = img.shape[:2]
    out = canvas(w, h)
    xs, ys = [0, mx, iw - mx, iw], [0, my, ih - my, ih]
    xd, yd = [0, mx, w - mx, w], [0, my, h - my, h]
    for j in range(3):
        for i in range(3):
            src = img[ys[j]:ys[j + 1], xs[i]:xs[i + 1]]
            tw, th = xd[i + 1] - xd[i], yd[j + 1] - yd[j]
            if tw > 0 and th > 0:
                out[yd[j]:yd[j + 1], xd[i]:xd[i + 1]] = np.array(Image.fromarray(src).resize((tw, th), Image.NEAREST))
    return out


# --------------------------------------------------------------------------
# Track mock (1 px = 0.25 m)
# --------------------------------------------------------------------------


def sample_world(tex, X, Y):
    th, tw = tex.shape[:2]
    return tex[np.mod(Y, th).astype(int), np.mod(X, tw).astype(int)]


def sample_strip(tex, u, v):
    th, tw = tex.shape[:2]
    return tex[np.clip(v, 0, th - 1).astype(int), np.mod(u, tw).astype(int)]


def track_mock():
    Wm, Hm = 480, 400
    cx, cy, Rc = 250, 250, 70
    half = 28
    yy, xx = np.mgrid[0:Hm, 0:Wm].astype(float) + 0.5
    L1 = cx
    # (u along the lap, d lateral: + outside) for: top straight -> right-hand corner -> straight down
    d = np.zeros((Hm, Wm))
    u = np.zeros((Hm, Wm))
    A = (xx <= cx) & (yy <= cy)
    B = (xx > cx) & (yy < cy)
    Cr = (xx >= cx) & (yy >= cy)
    Dr = (xx < cx) & (yy > cy)
    d[A] = (cy - Rc) - yy[A]
    u[A] = xx[A]
    r = np.hypot(xx - cx, yy - cy)
    ang = np.arctan2(yy - cy, xx - cx)
    d[B] = r[B] - Rc
    u[B] = L1 + Rc * (ang[B] + math.pi / 2)
    d[Cr] = xx[Cr] - (cx + Rc)
    u[Cr] = L1 + Rc * math.pi / 2 + (yy[Cr] - cy)
    d[Dr] = -np.minimum(yy[Dr] - (cy - Rc), (cx + Rc) - xx[Dr])
    u[Dr] = xx[Dr]
    u_corner0, u_corner1 = L1 - 40, L1 + Rc * math.pi / 2 + 40

    img = canvas(Wm, Hm, BG)
    grass = L(T / "grass.png")
    grass_dark = L(T / "grass_dark.png")
    X, Y = xx.astype(int), yy.astype(int)
    img[:] = sample_world(grass, X, Y)
    far = (d > 112) | (d < -150)
    img[far] = sample_world(grass_dark, X, Y)[far]
    run = (d > 40) & (d <= 60)
    img[run] = sample_world(L(T / "runoff.png"), X, Y)[run]
    grv = (d > 60) & (d <= 84) & (u > u_corner0 - 60) & (u < u_corner1 + 40)
    img[grv] = sample_world(L(T / "gravel.png"), X, Y)[grv]
    trk = np.abs(d) <= half
    img[trk] = sample_world(L(T / "asphalt.png"), X, Y)[trk]
    # racing line: outside, apex, outside
    mid = (u_corner0 + u_corner1) / 2
    off = np.clip(np.abs(u - mid) / (mid - u_corner0 + 30), 0, 1) * 18 - 14
    v_rl = d - off + 8
    rl_m = trk & (v_rl >= 0) & (v_rl < 16)
    rlt = sample_strip(L(T / "racing_line.png"), u, v_rl)
    tmp = img.copy()
    blend_mask(tmp, rlt, rl_m)
    img = tmp
    # white edge lines
    edge = trk & (np.abs(d) > half - 1)
    img[edge] = hx("dcdad4")
    # kerbs (u along, v from the track edge outwards)
    in_corner = (u > u_corner0) & (u < u_corner1)
    ko = in_corner & (d > half) & (d <= half + 12)
    img[ko] = sample_strip(L(T / "kerb.png"), u, d - half - 0.5)[ko]
    ki = in_corner & (d < -half) & (d >= -half - 12) & (u > u_corner0 + 30) & (u < u_corner1 - 30)
    img[ki] = sample_strip(L(T / "kerb_inside.png"), u, -d - half - 0.5)[ki]
    # barriers: tyre wall at the corner, armco elsewhere, then fence and crowd
    tw = (d > 84) & (d <= 94)
    tw_c = tw & (u > u_corner0 - 60) & (u < u_corner1 + 40)
    tmp = img.copy()
    blend_mask(tmp, sample_strip(L(T / "tyre_wall.png"), u, d - 84.5), tw_c)
    tec = (d > 86) & (d <= 94) & ~tw_c & (np.abs(d) < 200)
    blend_mask(tmp, sample_strip(L(T / "tecpro.png"), u, d - 86.5), tec)
    fe = (d > 96) & (d <= 102)
    blend_mask(tmp, sample_strip(L(T / "fence.png"), u, d - 96.5), fe)
    cr = (d > 102) & (d <= 114) & (u < L1 + 60)
    blend_mask(tmp, sample_strip(L(D / "crowd_strip.png"), u, d - 102.5), cr)
    am = (d < -half - 44) & (d >= -half - 48) & (yy > cy + 20) & (xx < 180)
    img = tmp
    # inside armco along the bottom-left grass edge (just to show it)
    armco = L(T / "armco.png")
    for x in range(10, 170):
        for k in range(4):
            c = armco[k, x % 16]
            if c[3]:
                blend(img, c.reshape(1, 1, 4), x, 300 + k)
    # start line and grid on the straight down
    sl = L(T / "start_line.png")
    for x in range(cx + Rc - half, cx + Rc + half):
        for y in range(330, 336):
            img[y, x] = sl[y % 16, x % 16]
    grid = np.rot90(L(T / "start_grid.png"), k=-1)
    blend(img, grid, cx + Rc - half + 2, 338)
    blend(img, grid, cx + Rc + 2, 346)
    for (sx, sy) in [(cx + Rc - 10, 200), (cx + Rc + 4, 215), (cx + Rc - 2, 232)]:
        blend(img, L(T / "skid.png"), sx, sy)
    # props
    gs = L(D / "grandstand_long.png")
    blend(img, L(D / "grandstand_long_shadow.png"), 14 + 4, 2 + 4)
    blend(img, gs, 14, 2)
    for i, x in enumerate([214, 314]):
        bb = L(D / f"billboard_{i + 1}.png")
        blend(img, L(D / f"billboard_{i + 1}_shadow.png"), x + 4, 50 + 4)
        blend(img, bb, x, 50)
    for n, x in [(150, 60), (100, 110), (50, 160)]:
        blend(img, L(D / f"brake_board_{n}.png"), x, 116)
    g = L(D / "gantry.png")
    gx0 = cx + Rc - 64
    blend(img, L(D / "gantry_shadow.png"), gx0 + 4, 312 + 4)
    blend(img, g, gx0, 312)
    light = L(D / "gantry_light.png")
    for p in [44, 54, 64, 74, 84][:3]:
        blend(img, light, gx0 + p - 2, 312 + 7)
        blend(img, light, gx0 + p - 2, 312 + 11)
    pit = L(D / "pit_building.png")
    blend(img, L(D / "pit_building_shadow.png")[:, :200], 0 + 4, 336 + 4)
    blend(img, pit[:, :200], 0, 336)
    trees = [("tree_3.png", 60, 190), ("tree_1.png", 120, 220), ("tree_4.png", 30, 250), ("tree_2.png", 170, 270),
             ("tree_5.png", 420, 300), ("tree_1.png", 440, 360), ("bush_1.png", 100, 270), ("bush_2.png", 200, 300),
             ("bush_3.png", 150, 300), ("tree_4.png", 400, 250)]
    for name, x, y in trees:
        blend(img, L(D / name), x, y)
    blend(img, L(D / "tent_1.png"), 150, 200)
    blend(img, L(D / "tent_2.png"), 10, 290)
    blend(img, L(D / "marshal_post.png"), 392, 170)
    blend(img, L(D / "tv_tower.png"), 400, 200)
    lt = L(D / "light_tower.png")
    glow = L(D / "light_glow.png")
    blend(img, glow, 216 - 16, 236 - 16)
    blend(img, lt, 216, 246)
    return img


def blend_mask(dst, src, mask):
    sa = src[..., 3:4].astype(np.float32) / 255.0
    out = dst[..., :3] * (1 - sa) + src[..., :3] * sa
    dst[mask, :3] = out[mask].astype(np.uint8)


# --------------------------------------------------------------------------
# Sheet layout
# --------------------------------------------------------------------------


class Sheet:
    def __init__(self, width):
        self.W = width
        self.items = []  # (x, y, img)
        self.x = 8
        self.y = 8
        self.row_h = 0

    def heading(self, text):
        self.newline(6)
        img = canvas(text_width(text) + 2, 7)
        draw_text(img, 0, 0, text, HEAD)
        rect_line = canvas(self.W - 16, 1, UI["line"])
        self.items.append((8, self.y, img))
        self.items.append((8, self.y + 7, rect_line))
        self.y += 12

    def add(self, label, img, gap=10):
        lw = text_width(label)
        w = max(img.shape[1], lw)
        h = img.shape[0] + 8
        if self.x + w > self.W - 8:
            self.newline()
        lab = canvas(lw + 1, 6)
        draw_text(lab, 0, 0, label, LABEL)
        self.items.append((self.x, self.y, lab))
        self.items.append((self.x, self.y + 8, img))
        self.x += w + gap
        self.row_h = max(self.row_h, h)

    def newline(self, extra=4):
        if self.row_h:
            self.y += self.row_h + extra
        self.x = 8
        self.row_h = 0

    def render(self):
        self.newline()
        c = canvas(self.W, self.y + 8, BG)
        for x, y, img in self.items:
            blend(c, img, x, y)
        return c


def tile_test(path, n=3, color=BG):
    return on_bg(tile(L(path), n, n), color)


def strip_test(path, n=4, bg=hx("2f3136")):
    a = L(path)
    return on_bg(tile(a, n, 1), bg, 2)


def build():
    sh = Sheet(1240)
    sh.heading("PIT WALL - ENVIRONMENT + UI ART (3X). TILEABLE TEXTURES SHOWN 3X3, STRIPS 4X ALONG U")
    sh.heading("TRACK SURFACES")
    for n in ["grass", "grass_dark", "asphalt"]:
        sh.add(f"{n}.png 128 3x3", tile_test(T / f"{n}.png"))
    sh.newline()
    for n in ["runoff", "gravel"]:
        sh.add(f"{n}.png 64 3x3", tile_test(T / f"{n}.png"))
    sh.add("racing_line.png 16 3x3 on asphalt", on_bg(tile(L(T / "racing_line.png"), 3, 3), hx("2f3136")))
    sh.add("start_line.png 16 3x3", tile_test(T / "start_line.png"))
    sh.add("start_grid.png x2", strip_test(T / "start_grid.png", 2))
    sh.add("skid.png", strip_test(T / "skid.png", 1))
    sh.newline()
    sh.heading("KERBS + BARRIERS (U ALONG THE TRACK, V=0 TRACK SIDE)")
    for n in ["kerb", "kerb_inside", "tyre_wall", "tecpro", "armco", "fence"]:
        sh.add(f"{n}.png", strip_test(T / f"{n}.png", 4 if n != "armco" and n != "fence" else 8,
                                     hx("30503a") if n in ("fence", "armco") else hx("2f3136")))
    sh.add("crowd_strip.png 3x", strip_test(D / "crowd_strip.png", 3))
    sh.newline()
    sh.heading("DECORATIONS (1 PX = 0.25 M) ON GRASS")
    grass_bg = hx("30503a")
    for n in ["tree_1", "tree_2", "tree_3", "tree_4", "tree_5", "bush_1", "bush_2", "bush_3", "tent_1", "tent_2",
              "marshal_post", "tv_tower", "light_tower"]:
        sh.add(n, on_bg(L(D / f"{n}.png"), grass_bg, 2))
    sh.add("light_glow", on_bg(L(D / "light_glow.png"), hx("1a2a20"), 2))
    sh.newline()
    for n in ["brake_board_150", "brake_board_100", "brake_board_50"]:
        sh.add(n, on_bg(L(D / f"{n}.png"), grass_bg, 2))
    for i in range(1, 5):
        b = on_bg(L(D / f"billboard_{i}.png"), grass_bg, 2)
        sh.add(f"billboard_{i}", b)
    sh.newline()
    gl = on_bg(L(D / "gantry.png"), hx("2f3136"), 2)
    lit = L(D / "gantry.png").copy()
    light = L(D / "gantry_light.png")
    for p in [44, 54, 64, 74, 84]:
        blend(lit, light, p - 2, 7)
        blend(lit, light, p - 2, 11)
    sh.add("gantry.png", gl)
    sh.add("gantry + gantry_light x10", on_bg(lit, hx("2f3136"), 2))
    sh.add("grandstand_short + _shadow", with_shadow(D / "grandstand_short.png", grass_bg))
    sh.newline()
    sh.add("grandstand_long + _shadow", with_shadow(D / "grandstand_long.png", grass_bg))
    sh.add("pit_building + _shadow", with_shadow(D / "pit_building.png", hx("2f3136")))
    sh.newline()
    sh.heading("SCENES: TRACK MOCK (ALL OF THE ABOVE TOGETHER) + MENU BACKGROUND 640X360")
    sh.add("mock corner, 1 px = 0.25 m", track_mock())
    sh.add("bg_menu.png with logo, buttons, icons, panel", menu_demo())
    sh.newline()
    sh.heading("UI CHROME")
    sh.add("logo.png", L(U / "logo.png"))
    sh.add("logo_small.png", L(U / "logo_small.png"))
    sh.add("logo on panel", on_bg(L(U / "logo_small.png"), UI["panel"], 4))
    for n in ["panel", "panel_accent", "panel_hover"]:
        sh.add(f"{n} 24", L(U / f"{n}.png"))
        sh.add("9-slice 96x48", nine_slice(L(U / f"{n}.png"), 8, 96, 48))
    sh.newline()
    for n in ["button", "button_hover", "button_pressed", "button_primary", "button_primary_hover"]:
        b = L(U / f"{n}.png")
        big = nine_slice(b, 6, 64, 16)
        txt = "RACE" if "primary" in n else "GARAGE"
        col = UI["ink"]
        tx = (64 - text_width(txt)) // 2
        ty = 5 + (1 if n == "button_pressed" else 0)
        draw_text(big, tx, ty, txt, col)
        sh.add(n, on_bg(np.concatenate([on_bg(b, BG), canvas(4, 16, BG), on_bg(big, BG)], axis=1)))
    sh.newline()
    for n in ["tab", "tab_active"]:
        t = L(U / f"{n}.png")
        sh.add(n, on_bg(np.concatenate([t, canvas(4, 14, BG), nine_slice(t, 6, 56, 14)], axis=1)))
    icons = ["flag", "stopwatch", "wrench", "car", "pack", "trophy", "bolt", "lock", "chain", "settings", "play",
             "back", "gamepad", "keyboard", "sound", "mute", "coin", "user"]
    row = canvas(len(icons) * 20, 16, BG)
    for i, n in enumerate(icons):
        blend(row, L(U / f"icon_{n}.png"), i * 20, 0)
    sh.add("icons 16x16: " + " ".join(icons[:9]), row)
    tinted = canvas(len(icons) * 20, 16, BG)
    for i, n in enumerate(icons):
        ic = L(U / f"icon_{n}.png").copy()
        m = ic[..., 3] > 0
        ic[m, :3] = np.array(UI["yellow"][:3], np.uint8)
        blend(tinted, ic, i * 20, 0)
    sh.add("icons modulated (yellow)", tinted)
    sh.newline()
    wheel = L(U / "steering_wheel.png")
    info = json.loads((U / "steering_wheel.json").read_text())
    wc = wheel.copy()
    ring, knob = L(U / "rotary_ring.png"), L(U / "rotary.png")
    for r in info["rotaries"]:
        cxr, cyr = r["center"]
        blend(wc, ring, cxr - 14, cyr - 14)
        blend(wc, knob, cxr - 10, cyr - 10)
    s = info["screen"]
    draw_text(wc, s["x"] + 4, s["y"] + 4, "LAP 12/58", UI["ink"])
    draw_text(wc, s["x"] + 4, s["y"] + 13, "P3 +0.412", UI["green"])
    draw_text(wc, s["x"] + 4, s["y"] + 22, "BBAL 56.5", UI["yellow"])
    for i, led in enumerate(info["shift_lights"][:9]):
        c = {"green": UI["green"], "red": UI["red"], "blue": UI["blue"]}[led["color"]]
        wc[led["y"]:led["y"] + led["h"], led["x"]:led["x"] + led["w"]] = c
    sh.add("steering_wheel.png", on_bg(wheel))
    sh.add("+ rotary_ring, rotary, screen text, lit LEDs", on_bg(wc))
    sh.add("rotary 20", L(U / "rotary.png"))
    sh.add("rotary_ring 28", L(U / "rotary_ring.png"))
    sh.newline()
    sh.add("wing_side_main + flap", L(U / "wing_side_main.png"))
    sh.add("wing_side_flap", L(U / "wing_side_flap.png"))
    sh.add("front_wing_side", L(U / "front_wing_side.png"))
    sh.add("front_wing_side_flap", L(U / "front_wing_side_flap.png"))
    sh.add("assembled: default / drs", wings_assembled())
    sh.newline()
    sh.add("garage_wall.png", L(U / "garage_wall.png"))
    sh.add("garage_floor.png 128 tiled 2x2", tile_test(U / "garage_floor.png", 2))
    v = canvas(96, 54, hx("5d626d"))
    blend(v, nine_slice_xy(L(U / "vignette.png"), 32, 32, 96, 54))
    sh.add("vignette (stretched)", v)
    sheet = sh.render()
    out = scale(sheet, 3)
    save(out, OUT)
    return out


def with_shadow(path, bg):
    a = L(path)
    s = L(str(path).replace(".png", "_shadow.png"))
    c = canvas(a.shape[1] + 8, a.shape[0] + 8, bg)
    blend(c, s, 6, 6)
    blend(c, a, 2, 2)
    return c


def wings_assembled():
    meta = json.loads((U / "wings.json").read_text())
    out = []
    for key, state in [("rear", "default"), ("rear", "drs_open"), ("front", "default")]:
        m = meta[key]
        main = L(U / m["main"])
        flap = Image.open(U / m["flap"]).convert("RGBA")
        c = canvas(main.shape[1] + 12, main.shape[0] + 16, UI["panel"])
        blend(c, main, 4, 12)
        pv, pm = m["flap_pivot"], m["flap_pivot_in_main"]
        big = Image.new("RGBA", (flap.width * 3, flap.height * 3))
        big.paste(flap, (flap.width, flap.height))
        ang = m["flap_angle_deg"][state]
        rot = np.array(big.rotate(-ang, resample=Image.NEAREST, center=(flap.width + pv[0], flap.height + pv[1])))
        blend(c, rot, 4 + pm[0] - (flap.width + pv[0]), 12 + pm[1] - (flap.height + pv[1]))
        out.append(c)
    hmax = max(o.shape[0] for o in out)
    row = canvas(sum(o.shape[1] + 4 for o in out), hmax, BG)
    x = 0
    for o in out:
        row[:o.shape[0], x:x + o.shape[1]] = o
        x += o.shape[1] + 4
    return row


def menu_demo():
    bg = L(U / "bg_menu.png").copy()
    blend(bg, L(U / "logo.png"), 24, 40)
    for i, (label, n) in enumerate([("RACE", "button_primary"), ("GARAGE", "button"), ("PACKS", "button"),
                                    ("SETTINGS", "button")]):
        b = nine_slice(L(U / f"{n}.png"), 6, 112, 18)
        draw_text(b, 22, 6, label, UI["ink"])
        icon = {"RACE": "flag", "GARAGE": "wrench", "PACKS": "pack", "SETTINGS": "settings"}[label]
        blend(b, L(U / f"icon_{icon}.png"), 4, 1)
        blend(bg, b, 40, 120 + i * 24)
    p = nine_slice(L(U / "panel_accent.png"), 8, 150, 52)
    draw_text(p, 10, 10, "NEXT RACE", UI["ink2"])
    draw_text(p, 10, 22, "MTKVARI CIRCUIT", UI["ink"])
    draw_text(p, 10, 34, "SAT 18:00  3.7 KM", UI["ink3"])
    blend(bg, p, 40, 228)
    return bg


if __name__ == "__main__":
    build()
    print("wrote", OUT)
