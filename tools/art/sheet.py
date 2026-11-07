"""Contact sheet of every sprite at 3x on #141518 -> sprites/preview_all.png

Run:  python tools/art/sheet.py   (after car.py, parts.py, cards.py, packs.py)
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import car  # noqa: E402
from pxl import (FONT5, SPRITES, alpha_over, canvas, draw_text, hx, load,  # noqa: E402
                 save, scale)

K = 3
BG = hx("#141518")
INK = hx("#f1efea")
INK2 = hx("#a3a3ad")
RED = hx("#e8352b")


class Sheet:
    def __init__(self, w):
        self.w = w
        self.blocks = []   # (img, x, y)
        self.y = 12
        self.x = 12
        self.row_h = 0

    def title(self, text):
        self.newline()
        t = canvas(len(text) * 6 + 2, 8)
        draw_text(t, 0, 0, text, INK, FONT5)
        t = scale(t, 2)
        self.blocks.append((t, 12, self.y))
        bar = canvas(self.w - 24, 2)
        bar[...] = RED
        self.blocks.append((bar, 12, self.y + 18))
        self.y += 28

    def add(self, img, label=None, gap=12):
        h, w = img.shape[:2]
        if self.x + w > self.w - 12:
            self.newline()
        self.blocks.append((img, self.x, self.y))
        lh = 0
        if label:
            t = canvas(len(label) * 4 + 2, 6)
            draw_text(t, 0, 0, label.upper(), INK2)
            t = scale(t, 2)
            self.blocks.append((t, self.x, self.y + h + 4))
            lh = 16
        lw = (len(label) * 4 + 2) * 2 if label else 0
        self.x += max(w, lw) + gap
        self.row_h = max(self.row_h, h + lh)

    def newline(self):
        if self.row_h:
            self.y += self.row_h + 14
        self.x = 12
        self.row_h = 0

    def render(self):
        self.newline()
        out = canvas(self.w, self.y + 12)
        out[...] = BG
        for img, x, y in self.blocks:
            alpha_over(out, img, x, y)
        return out


def checker(w, h):
    c = canvas(w, h)
    for y in range(h):
        for x in range(w):
            c[y, x] = hx("#1d1f23") if ((x // 4 + y // 4) % 2) else hx("#202227")
    return c


def on(bg_img, img):
    b = bg_img.copy()
    alpha_over(b, img)
    return b


def main():
    s = Sheet(1640)
    layers = car.build()
    tr, tf = car.make_tyres("medium")
    sh = car.shadow_from(layers, tr, tf)
    lights, glow = car.make_lights(), car.make_brake_glow()

    s.title("CAR - COMBOS")
    for i, combo in enumerate(car.COMBOS):
        img = car.compose(layers, tr, tf, sh, combo, car.TEAMS[i % 3], car.HELMETS[i % 3])
        s.add(scale(on(car.asphalt(80, 32), img), K), " ".join(c.replace("_", "") for c in combo))
    img = car.compose(layers, tr, tf, sh, car.COMBOS[0], car.TEAMS[2], car.HELMETS[2],
                      open_wing=True, lights=lights, glow=glow, steer=15)
    s.add(scale(on(car.asphalt(80, 32), img), K), "straight mode + rain + brakes")

    s.title("CAR - LAYERS")
    names = sorted(f for f in os.listdir(os.path.join(SPRITES, "car"))
                   if f.endswith(".png") and f != "preview_combos.png"
                   and not any(c in f for c in ("_soft", "_medium", "_hard", "_inter", "_wet")))
    for n in names:
        img = load("car", n)
        h, w = img.shape[:2]
        s.add(scale(on(checker(w, h), img), K), n[:-4])
    s.newline()
    for comp in car.COMPOUNDS:
        img = load("car", f"tyre_front_{comp}.png")
        s.add(scale(on(checker(10, 6), img), K * 2), comp)

    s.title("PARTS")
    for n in sorted(os.listdir(os.path.join(SPRITES, "parts"))):
        if n.endswith(".png"):
            s.add(scale(on(checker(64, 64), load("parts", n)), K), n[:-4])

    s.title("CARDS")
    for n in ("frame_common", "frame_rare", "frame_epic", "frame_legendary", "back"):
        s.add(scale(load("cards", n + ".png"), K), n)
    for n in ("glow_rare", "glow_epic", "glow_legendary"):
        g = load("cards", n + ".png")
        alpha_over(g, load("cards", "back.png"), 12, 12)
        s.add(scale(g, K), n + " + back")
    for n in ("window_bg_common", "window_bg_rare", "window_bg_epic", "window_bg_legendary"):
        s.add(scale(load("cards", n + ".png"), K), n)

    s.title("PACKS")
    for n in ("pack_closed", "pack_shake_1", "pack_shake_2", "pack_open", "burst", "sparkle"):
        s.add(scale(load("packs", n + ".png"), K), n)
    save(s.render(), "preview_all.png")


if __name__ == "__main__":
    main()
