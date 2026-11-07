"""brand/brand_sheet.png: a contact sheet of the whole kit.

    python tools/brand/contact_sheet.py

Every element is shown at a whole-number scale of its own pixels (large
files are shown at their native pixel size: a 3x image sampled every 3rd
pixel), so nothing on the sheet is resampled.
"""
from __future__ import annotations

import numpy as np

import brandkit as bk
from brandkit import (BG, BLACK, BLUE, GREEN, INK, INK_2, INK_3, LINE, PANEL, PURPLE, RED, RED_DEEP, YELLOW, canvas,
                      display_mask, load, over, save_rgb, style_letters, text_img, up)
import marks
import icons

B = bk.BRAND
W = 2400
PAD = 48


def label(s, c=INK_3, k=2):
    return up(text_img(s, c), k)


def on(img, bg, pad=16, k=1):
    a = up(img, k) if k > 1 else img
    c = canvas(a.shape[1] + 2 * pad, a.shape[0] + 2 * pad, bg)
    over(c, a, pad, pad)
    return c


def native(path, k):
    a = load(path)
    return a[::k, ::k].copy()


def circle(img, bg=PANEL):
    n = img.shape[0]
    m = icons.circle_mask(n)
    out = img.copy()
    out[~m] = bg
    return out


class Sheet:
    def __init__(self):
        self.parts = []  # (y, x, img)
        self.y = PAD
        self.x = PAD
        self.row_h = 0

    def header(self, title, sub=None):
        self.newline(28)
        t = style_letters(display_mask(title, 16, 4, 5, 2, space=6), ext=1)
        t = up(t, 2)
        self.parts.append((self.y, PAD, t))
        rule = canvas(W - 2 * PAD, 2, RED)
        self.parts.append((self.y + t.shape[0] + 10, PAD, rule))
        if sub:
            s = label(sub, INK_3)
            self.parts.append((self.y + t.shape[0] - s.shape[0], PAD + t.shape[1] + 24, s))
        self.y += t.shape[0] + 32
        self.x = PAD
        self.row_h = 0

    def add(self, img, cap=None, gap=28):
        cap_img = label(cap) if cap else None
        w = max(img.shape[1], cap_img.shape[1] if cap_img is not None else 0)
        h = img.shape[0] + (cap_img.shape[0] + 10 if cap_img is not None else 0)
        if self.x + w > W - PAD and self.x > PAD:
            self.newline()
        self.parts.append((self.y, self.x, img))
        if cap_img is not None:
            self.parts.append((self.y + img.shape[0] + 10, self.x, cap_img))
        self.x += w + gap
        self.row_h = max(self.row_h, h)

    def newline(self, extra=24):
        if self.row_h:
            self.y += self.row_h + extra
        self.x = PAD
        self.row_h = 0

    def render(self):
        self.newline(PAD)
        H = self.y
        out = canvas(W, H, BG)
        for y, x, img in self.parts:
            over(out, img, x, y)
        return out


def build():
    L, I, S, K, R = B / "logo", B / "icons", B / "social", B / "keyart", B / "renders"
    sh = Sheet()
    # title block
    sh.add(on(load(L / "logo_wordmark_4x.png"), BG, 0), None, gap=80)
    t = label("BRAND KIT  /  HIGH-RES PIXEL ART  /  DRIVE IT. RUN IT. PROVE IT.", INK_2)
    sh.add(t, None)
    sh.newline(16)
    for name, c in (("BG 141518", BG), ("PANEL 1D1F23", PANEL), ("LINE 34363C", LINE), ("INK F1EFEA", INK),
                    ("RED E8352B", RED), ("YELLOW F2C230", YELLOW), ("PURPLE A855F7", PURPLE),
                    ("BLUE 5EC8E5", BLUE), ("GREEN 3ECF6A", GREEN)):
        sw = canvas(220, 90, c)
        sw[0, :] = LINE[:4]
        sw[-1, :] = LINE[:4]
        sw[:, 0] = LINE[:4]
        sw[:, -1] = LINE[:4]
        sh.add(sw, name, gap=24)

    sh.header("LOGO", "wordmark / stacked / tagline lockup, 1x-8x, colour + one-colour")
    sh.add(on(load(L / "logo_wordmark_2x.png"), PANEL, 24), "logo_wordmark (colour, 2x)")
    sh.add(on(load(L / "logo_wordmark_white_2x.png"), RED, 24), "logo_wordmark_white")
    sh.add(on(load(L / "logo_wordmark_black_2x.png"), INK, 24), "logo_wordmark_black")
    sh.newline()
    sh.add(on(load(L / "logo_stacked_2x.png"), PANEL, 24), "logo_stacked (2x)")
    sh.add(on(load(L / "logo_stacked_black_2x.png"), INK, 24), "logo_stacked_black")
    sh.add(on(load(L / "logo_tagline_2x.png"), PANEL, 24), "logo_tagline (2x)")
    sh.add(on(load(L / "logo_tagline_black_2x.png"), INK, 24), "logo_tagline_black")
    sh.add(on(load(L / "logo_wordmark_small_2x.png"), PANEL, 24), "logo_wordmark_small (2x)")

    sh.header("MARK", "primary: PW monogram badge  /  alternates: head-on car, P + stripe")
    for n in (16, 24, 32, 48, 64, 128):
        sh.add(on(load(L / f"logo_mark_{n}.png"), PANEL, 12), f"{n}", gap=20)
    sh.add(on(load(L / "logo_mark_16.png"), PANEL, 12, k=8), "16 px, zoomed 8x", gap=20)
    sh.add(on(load(L / "logo_mark_32.png"), PANEL, 12, k=4), "32 px, zoomed 4x", gap=20)
    sh.newline()
    lt = canvas(560, 180, INK)
    x = 16
    for n in (16, 24, 32, 48, 64):
        over(lt, load(L / f"logo_mark_{n}.png"), x, 16)
        x += n + 16
    over(lt, load(L / "logo_mark_128.png"), x + 8, 16)
    sh.add(lt, "on light", gap=40)
    for alt, nm in (("alt1_car", "ALT 1: head-on car"), ("alt2_p", "ALT 2: P + stripe")):
        c = canvas(330, 180, PANEL)
        over(c, load(L / f"logo_mark_{alt}_16.png"), 16, 16)
        over(c, load(L / f"logo_mark_{alt}_32.png"), 44, 16)
        over(c, up(load(L / f"logo_mark_{alt}_64.png"), 2), 90, 16)
        over(c, load(L / f"logo_mark_{alt}_64.png"), 16, 64)
        sh.add(c, nm, gap=40)

    sh.header("ICONS", "favicons (exact 16/32/48 frames in favicon.ico), app icons, profile pictures")
    tab = canvas(420, 120, hx_("dee1e6"))
    tab[40:120, 0:420] = INK
    tab[8:40, 12:300] = INK
    over(tab, load(I / "favicon_16.png"), 24, 16)
    over(tab, text_img("Pit Wall", BG), 48, 20)
    over(tab, load(I / "favicon_32.png"), 24, 60)
    over(tab, load(I / "favicon_48.png"), 72, 56)
    sh.add(tab, "favicon_16 / 32 / 48 in a tab")
    dtab = canvas(420, 120, hx_("202124"))
    dtab[8:40, 12:300] = hx_("35363a")
    over(dtab, load(I / "favicon_16.png"), 24, 16)
    over(dtab, text_img("Pit Wall", INK), 48, 20)
    over(dtab, load(I / "favicon_32.png"), 24, 60)
    over(dtab, load(I / "favicon_48.png"), 72, 56)
    sh.add(dtab, "dark tab")
    small = canvas(120, 120, PANEL)
    over(small, circle(marks.mark_pw_fullbleed(48, 34)), 12, 12)
    over(small, circle(marks.mark_pw_fullbleed(32, 24)), 72, 20)
    over(small, marks.mark_pw(16), 80, 72)
    over(small, marks.mark_pw(24), 20, 80)
    sh.add(small, "tiny sizes")
    sh.newline()
    sh.add(load(I / "app_icon_192.png"), "app_icon_192")
    sh.add(load(I / "apple_touch_icon_180.png"), "apple_touch_icon_180")
    sh.add(circle(load(S / "avatar_400.png")), "avatar_400 (circle crop)")
    sh.add(circle(load(S / "avatar_car_400.png")), "avatar_car_400 (alt)")

    sh.header("SOCIAL", "shown at native pixels (the files are 3x / 4x)")
    sh.add(up(native(S / "og_image_1200x630.png", 3), 2), "og_image_1200x630")
    sh.add(up(native(S / "youtube_thumb_1280x720.png", 4), 2), "youtube_thumb_1280x720")
    sh.newline()
    sh.add(up(native(S / "x_banner_1500x500.png", 3), 2), "x_banner_1500x500")
    sh.add(up(native(S / "discord_banner_960x540.png", 3), 2), "discord_banner_960x540")

    sh.header("KEY ART", "title screen 1920x1080 (and 640x360 for the game), boot splash, loading")
    sh.add(up(load(K / "title_keyart_640x360.png"), 2), "title_keyart_1920x1080")
    sp = native(K / "boot_splash_1280x720.png", 2)
    fr = canvas(sp.shape[1] + 2, sp.shape[0] + 2, LINE)
    over(fr, sp, 1, 1)
    sh.add(fr, "boot_splash_1280x720 (native 640x360)")
    sh.add(on(load(L / "loading_logo.png"), BG, 8), "loading_logo (384x96)")
    sh.add(on(load(L / "loading_logo_128.png"), BG, 8), "loading_logo_128")

    sh.header("3D CAR RENDERS", "transparent, native pixels + 3x; red, white, purple liveries")
    for nm in ("car_hero_red", "car_hero_left_red", "car_rear34_red", "car_side_red", "car_low_front_red",
               "car_hero_white", "car_rear34_white", "car_side_white", "car_hero_purple", "car_rear34_purple",
               "car_side_purple", "car_top_red"):
        a = load(R / f"{nm}_shadow.png")
        over(a, load(R / f"{nm}.png"))
        if nm == "car_top_red":
            a = np.rot90(a, 1).copy()
        sh.add(on(a, PANEL, 10), nm, gap=24)
    img = sh.render()
    save_rgb(img, B / "brand_sheet.png")
    return img


def hx_(s):
    return bk.hx(s)


if __name__ == "__main__":
    im = build()
    print("wrote", B / "brand_sheet.png", im.shape[1], "x", im.shape[0])
