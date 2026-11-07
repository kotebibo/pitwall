"""Pit Wall top-down F1 car, layered, 10 px per metre.

Run:  python tools/art/car.py
Writes every car layer to game/assets/sprites/car/ plus anchors.json and
preview_combos.png.

Canvas is 80 x 32 for every full-car layer, nose to +x. The geometric centre
of the car is the pixel corner (40, 16): the car is mirror-symmetric about
the line between rows 15 and 16. In this file a lateral position is written
as `d` = 1..16, the distance in pixel rows from that centre line:
    top half    row = 16 - d      (d=1 -> row 15)
    bottom half row = 15 + d      (d=1 -> row 16)
Light comes from the top-left, so the top half is the lit side.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from pxl import (CARBON, DARK, HI, METAL, PAINT, SPEC, TYRE, VISOR, alpha_over,  # noqa: E402
                 canvas, dilate, hx, mix, multiply, put, save, save_json, scale)

W, H = 80, 32
CX, CY = 40, 16

# axle / wheel geometry (pixel corners, relative to centre)
FRONT_AXLE = 18     # x = 58
REAR_AXLE = -18     # x = 22
WHEEL_Y = 8         # wheel centres at y = +-8 (d 7..10 is the tyre)
TYRE_LEN, TYRE_W = 8, 4


def T(d):
    return CY - d


def B(d):
    return CY - 1 + d


class Part:
    """A car part with a tintable paint layer and a fixed-colour detail layer."""

    def __init__(self, w=W, h=H):
        self.paint = canvas(w, h)
        self.detail = canvas(w, h)

    # ---- raw pixel ops
    def p(self, x, y, lvl):
        put(self.paint, x, y, PAINT[lvl])
        put(self.detail, x, y, HI if lvl == 5 else (0, 0, 0, 0))

    def c(self, x, y, lvl, ramp=CARBON):
        put(self.detail, x, y, ramp[lvl])
        put(self.paint, x, y, (0, 0, 0, 0))

    def col(self, x, y, rgba):
        put(self.detail, x, y, rgba)
        put(self.paint, x, y, (0, 0, 0, 0))

    def over(self, x, y, rgba):
        """Detail overlay that keeps the paint underneath (specular etc)."""
        put(self.detail, x, y, rgba)

    def clear(self, x, y):
        put(self.detail, x, y, (0, 0, 0, 0))
        put(self.paint, x, y, (0, 0, 0, 0))

    # ---- symmetric helpers: (x, d) with separate top / bottom values
    def ps(self, x, d, top, bot=None):
        bot = top if bot is None else bot
        if top is not None:
            self.p(x, T(d), top)
        if bot is not None:
            self.p(x, B(d), bot)

    def cs(self, x, d, top, bot=None, ramp=CARBON):
        bot = top if bot is None else bot
        if top is not None:
            self.c(x, T(d), top, ramp)
        if bot is not None:
            self.c(x, B(d), bot, ramp)

    def ks(self, x, d, top=DARK, bot=None):
        bot = top if bot is None else bot
        if top is not None:
            self.col(x, T(d), top)
        if bot is not None:
            self.col(x, B(d), bot)

    def overs(self, x, d, top, bot=None):
        if top is not None:
            self.over(x, T(d), top)
        if bot is not None:
            self.over(x, B(d), bot)

    def clears(self, x, d):
        self.clear(x, T(d))
        self.clear(x, B(d))

    def merged(self, tint=None):
        out = canvas(self.paint.shape[1], self.paint.shape[0])
        pl = self.paint if tint is None else multiply(self.paint, tint)
        alpha_over(out, pl)
        alpha_over(out, self.detail)
        return out


# cylinder-ish cross-section recipes for paint (top list = d=w..1,
# bottom list = d=1..w). Highlight ridge just above the centre line.
RP = {
    1: ([4], [2]),
    2: ([3, 5], [3, 1]),
    3: ([2, 4, 5], [3, 2, 0]),
    4: ([1, 3, 4, 5], [3, 2, 1, 0]),
}
RC = {
    1: ([3], [1]),
    2: ([2, 4], [2, 0]),
    3: ([1, 3, 4], [2, 1, 0]),
}


def section(part: Part, x: int, w: int, mat: str = "P"):
    rec = RP if mat == "P" else RC
    top, bot = rec[w]
    for i, lvl in enumerate(top):
        d = w - i
        if mat == "P":
            part.p(x, T(d), lvl)
        else:
            part.c(x, T(d), lvl)
    for i, lvl in enumerate(bot):
        d = i + 1
        if mat == "P":
            part.p(x, B(d), lvl)
        else:
            part.c(x, B(d), lvl)


# ===========================================================================
# BODY: monocoque, nose cone (to the front wing), engine cover, cockpit,
# gearbox, crash structure, suspension, mirrors.
# ===========================================================================

BODY_PROFILE = [  # (x0, x1, hw, material)
    (14, 16, 1, "C"),   # rear crash structure (under the rear wing)
    (17, 22, 2, "C"),   # gearbox
    (23, 26, 2, "P"),   # engine cover tail
    (27, 36, 3, "P"),   # engine cover / coke bottle
    (37, 52, 4, "P"),   # airbox, cockpit, front chassis
    (53, 57, 3, "P"),   # front bulkhead
    (58, 61, 2, "P"),   # nose cone (front wing layer carries the tip)
]


def body_hw(x):
    for x0, x1, hw, _ in BODY_PROFILE:
        if x0 <= x <= x1:
            return hw
    return 0


def make_body() -> Part:
    b = Part()
    for x0, x1, hw, mat in BODY_PROFILE:
        for x in range(x0, x1 + 1):
            section(b, x, hw, mat)

    # --- taper steps: edges where the body narrows toward the rear face the
    # light (brighter), edges narrowing toward the front face away (darker)
    b.ps(36, 3, 3, 1)          # step 4->3 at the airbox back
    b.ps(26, 2, 4, 1)
    b.ps(53, 3, 2, 1)          # bulkhead step facing forward
    b.ps(58, 2, 3, 1)

    # --- engine cover spine (shark fin): sharp ridge line
    for x in range(24, 37):
        b.p(x, T(1), 5)
        b.p(x, B(1), 2)
    b.p(23, T(1), 4)
    # fin trailing edge into the gearbox
    b.c(22, T(1), 4)
    b.c(22, B(1), 1)

    # --- airbox / roll hoop inlet right behind the helmet
    b.ks(39, 1, DARK)
    b.ks(40, 1, DARK)
    b.ps(39, 2, 5, 3)
    b.ps(40, 2, 5, 3)
    b.ps(38, 1, 4, 2)
    b.ps(37, 2, 4, 2)
    b.ps(38, 2, 4, 2)
    # T-cam on top of the roll hoop (fixed black bar)
    b.cs(38, 1, 3, 1)
    b.cs(38, 2, 2, 1)

    # --- cockpit opening x 41..48, d 1..2 (interior: far walls catch light)
    for x in range(41, 49):
        b.col(x, T(2), CARBON[0])
        b.col(x, T(1), DARK)
        b.col(x, B(1), CARBON[1])
        b.col(x, B(2), CARBON[2])
    b.col(48, T(1), CARBON[2])
    b.col(48, B(1), CARBON[2])
    b.col(48, T(2), CARBON[1])
    b.col(48, B(2), CARBON[3])
    b.col(47, T(1), CARBON[1])     # steering wheel hint
    b.col(47, B(1), CARBON[2])
    # cockpit rim lip
    for x in range(41, 49):
        b.p(x, T(3), 4)
        b.p(x, B(3), 2)
    b.p(49, T(2), 3)
    b.p(49, B(2), 2)
    b.p(49, T(1), 4)
    b.p(49, B(1), 3)

    # --- chassis top in front of the cockpit: subtle centre highlight
    for x in range(50, 58):
        b.p(x, T(1), 5)
    for x in range(58, 62):
        b.p(x, T(1), 5)
    # specular glints on the nose and engine cover
    b.over(55, T(1), SPEC)
    b.over(33, T(1), SPEC)


    # --- gearbox detail: lit top edge, exhaust tip
    for x in range(17, 23):
        b.c(x, T(2), 3)
    b.c(16, T(1), 4)
    b.c(15, T(1), 3)
    b.c(14, T(1), 3)
    # exhaust (single centre tailpipe, metal) at x 15..16
    b.col(16, T(1), METAL[2])
    b.col(16, B(1), METAL[1])
    b.col(15, T(1), METAL[1])
    b.col(15, B(1), METAL[0])

    # --- front suspension (upper wishbone legs + pushrod), both sides
    fr_top = [(61, 3, 3), (60, 4, 3), (59, 5, 2), (58, 6, 2),
              (54, 4, 2), (55, 4, 3), (56, 5, 2), (57, 6, 1)]
    for x, d, lvl in fr_top:
        b.c(x, T(d), lvl + 1)
        b.c(x, B(d), lvl)
    # rear suspension
    # (lighter than the front: they sit over the dark diffuser)
    rr = [(18, 3, 3), (19, 4, 3), (20, 5, 3), (21, 6, 2),
          (26, 3, 3), (25, 4, 3), (24, 5, 3), (23, 6, 2)]
    for x, d, lvl in rr:
        b.c(x, T(d), lvl + 1)
        b.c(x, B(d), lvl)
    # drive shafts (metal, between the wishbones)
    for d in (3, 4, 5, 6):
        b.col(22, T(d), METAL[2] if d < 6 else METAL[1])
        b.col(22, B(d), METAL[0])

    # --- mirrors on stalks at the cockpit sides
    b.cs(46, 5, 2, 1)
    b.p(45, T(6), 5)
    b.p(46, T(6), 4)
    b.c(44, T(6), 2)          # housing back (glass faces the rear)
    b.p(45, B(6), 3)
    b.p(46, B(6), 1)
    b.c(44, B(6), 0)
    b.cs(45, 7, None, None)
    return b


# ===========================================================================
# FRONT WINGS (each carries its own nose tip x >= 62)
# ===========================================================================

def wing_span(f: Part, d: int, le: int, slots: list, te: int):
    """One spanwise station of a front wing: carbon mainplane from le back to
    the first slot, then painted flaps separated by dark slots, down to te.
    Each flap: front pixels mid, trailing-edge pixel bright (it sits highest)."""
    edges = [le] + list(slots) + [te - 1]
    # mainplane (carbon)
    for x in range(slots[0] + 1, le + 1):
        if x == le:
            f.c(x, T(d), 3)
            f.c(x, B(d), 1)
        else:
            f.c(x, T(d), 4)
            f.c(x, B(d), 2)
    for s in slots:
        f.c(s, T(d), 0)
        f.c(s, B(d), 0)
    bounds = list(slots) + [te - 1]
    for i in range(len(slots)):
        hi = bounds[i] - 1
        lo = bounds[i + 1] + 1
        for x in range(lo, hi + 1):
            if x == lo:
                f.p(x, T(d), 5)
                f.p(x, B(d), 3)
            else:
                f.p(x, T(d), 3)
                f.p(x, B(d), 1)


def endplate(f: Part, d: int, x0: int, x1: int):
    for x in range(x0, x1 + 1):
        f.ps(x, d, 4, 1)
    f.ps(x1, d, 3, 0)
    f.ps(x0, d, 5, 2)


def nose_tip(f: Part, x0: int, x_hw1: int, x_end: int):
    """Nose from x0, hw2 until x_hw1-1, hw1 until x_end."""
    for x in range(x0, x_hw1):
        section(f, x, 2, "P")
    for x in range(x_hw1, x_end + 1):
        f.p(x, T(1), 4)
        f.p(x, B(1), 2)
    f.p(x_hw1 - 1, T(2), 2)
    f.p(x_end, T(1), 3)
    f.p(x_end, B(1), 1)
    f.over(x0 + 1, T(1), SPEC)


def make_front_wing_outwash() -> Part:
    f = Part()
    #      d: (le, slot1, slot2, te) - flaps bow forward near the nose and
    # sweep forward again into the curled endplate
    st = {2: (69, 67, 65, 64), 3: (69, 67, 64, 63), 4: (69, 67, 64, 62),
          5: (69, 67, 64, 62), 6: (69, 67, 64, 62), 7: (69, 67, 64, 62),
          8: (69, 67, 64, 62), 9: (68, 67, 65, 63)}
    for d, (le, s1, s2, te) in st.items():
        wing_span(f, d, le, [s1, s2], te)
    endplate(f, 10, 62, 69)
    # outwash: endplate trailing foot curls outboard
    f.ps(61, 11, 5, 2)
    f.ps(62, 11, 4, 1)
    f.ps(63, 11, 3, 0)
    f.ps(62, 10, 4, 1)
    f.overs(65, 10, SPEC)
    nose_tip(f, 62, 65, 70)
    return f


def make_front_wing_inwash() -> Part:
    f = Part()
    #      d: (le, slot1, slot2, te)
    st = {2: (69, 66, 63, 61), 3: (69, 66, 63, 61), 4: (69, 66, 63, 62),
          5: (69, 66, 64, 62), 6: (69, 67, 64, 63), 7: (69, 67, 65, 63),
          8: (69, 67, 65, 64), 9: (68, 67, 65, 64)}
    for d, (le, s1, s2, te) in st.items():
        wing_span(f, d, le, [s1, s2], te)
    endplate(f, 10, 64, 68)
    f.overs(66, 10, SPEC)
    nose_tip(f, 62, 65, 70)
    return f


def make_front_wing_highnose() -> Part:
    f = Part()
    for d in range(1, 10):
        le = 69 if d <= 8 else 68
        wing_span(f, d, le, [67, 65], 63)
    endplate(f, 10, 63, 69)
    f.overs(66, 10, SPEC)
    # short, high nose (ends at x=66) casting a shadow onto the wing
    nose_tip(f, 62, 64, 66)
    f.c(67, B(1), 0)
    f.c(67, B(2), 1)
    f.c(66, B(2), 0)
    # two visible pylons at d=2 dropping onto the mainplane
    for x in (64, 65):
        f.c(x, T(2), 4)
        f.c(x, B(2), 1)
    f.c(66, T(2), 3)
    return f


# ===========================================================================
# REAR WINGS
# ===========================================================================

GAP = hx("#5a86a6")
GAP_D = hx("#34495c")


def rear_endplate(r: Part, d: int, x0: int, x1: int):
    for x in range(x0, x1 + 1):
        r.ps(x, d, 4, 1)
    r.ps(x1, d, 3, 0)
    r.ps(x0, d, 5, 2)
    r.overs(x0 + 2, d, SPEC)


def make_rear_wing_highdf(open_=False) -> Part:
    r = Part()
    for d in range(1, 6):
        # mainplane x 15..17 (LE at 17), slot 14, big flap 11..13
        r.ps(17, d, 3, 1)
        r.ps(16, d, 4, 2)
        r.ps(15, d, 3, 2)
        if open_:
            r.col(14, T(d), GAP)
            r.col(14, B(d), GAP_D)
            r.col(13, T(d), GAP)
            r.col(13, B(d), GAP_D)
            r.ps(12, d, 5, 3)
            r.ps(11, d, 3, 1)
        else:
            r.cs(14, d, 0, 0)
            r.ps(13, d, 4, 2)
            r.ps(12, d, 5, 3)
            r.ps(11, d, 4, 2)
            r.cs(10, d, 1, 0)       # gurney
    rear_endplate(r, 6, 10, 18)
    # DRS actuator pod + swan-neck pylon at the centre
    r.cs(13 if not open_ else 12, 1, 3, 1)
    r.cs(16, 1, 2, 1)
    r.over(12, T(3), SPEC)
    return r


def make_rear_wing_spoon(open_=False) -> Part:
    r = Part()
    le = {1: 16, 2: 16, 3: 17, 4: 17, 5: 18}
    for d in range(1, 6):
        l = le[d]
        dip = d <= 2
        for x in range(15, l + 1):
            if x == l:
                r.ps(x, d, 3 if not dip else 2, 1)
            else:
                r.ps(x, d, 3 if dip else 4, 2 if not dip else 1)
        if open_:
            r.col(14, T(d), GAP)
            r.col(14, B(d), GAP_D)
            r.ps(13, d, 4, 2)
            r.ps(12, d, 3, 1)
        else:
            r.cs(14, d, 0, 0)
            r.ps(13, d, 4 if dip else 5, 2)
            r.ps(12, d, 3, 1)
    rear_endplate(r, 6, 11, 18)
    r.cs(13, 1, 2, 1)
    r.over(16, T(4), SPEC)
    return r


def make_rear_wing_beam(open_=False) -> Part:
    r = Part()
    # smaller top wing, span d<=4, endplates at d=5
    for d in range(1, 5):
        r.ps(15, d, 3, 1)
        r.ps(14, d, 4, 2)
        if open_:
            r.col(13, T(d), GAP)
            r.col(13, B(d), GAP_D)
            r.ps(12, d, 4, 2)
        else:
            r.cs(13, d, 0, 0)
            r.ps(12, d, 5, 3)
            r.ps(11, d, 3, 1)
    rear_endplate(r, 5, 10, 16)
    # beam wing below, ahead of the top wing (carbon), span d<=3
    for d in range(1, 4):
        r.cs(19, d, 3, 1)
        r.cs(18, d, 2, 1)
    r.cs(19, 4, 2, 0)
    r.cs(18, 4, 1, 0)
    r.cs(12 if open_ else 12, 1, None, None)
    r.cs(16, 1, 2, 1)   # pylon
    r.cs(17, 1, 1, 0)
    r.over(12, T(2), SPEC)
    return r


# ===========================================================================
# SIDEPODS
# ===========================================================================

def pod_surface(s: Part, x: int, hw: int, ramp: bool = False, front: bool = False):
    """Rounded sidepod top surface for d = 2..hw (inner part hides under the
    body). Lit side: soft edge, bright shoulder, mid top. Shadow side: dark
    outline, dim shoulder, mid top. The downwash ramp faces the light."""
    for d in range(2, hw + 1):
        k = hw - d
        if k == 0:
            t, b_ = 3, 0
        elif k == 1:
            t, b_ = (5 if front else 4), 2
        else:
            t, b_ = (4 if ramp else 3), 3
        s.p(x, T(d), t)
        s.p(x, B(d), b_)


def inlet(s: Part, x: int, d0: int, d1: int):
    """Inlet mouth at column x (dark), lit top lip one column behind."""
    for d in range(d0, d1 + 1):
        s.col(x, T(d), DARK)
        s.col(x, B(d), DARK)
    s.c(x, T(d1 + 1), 2)
    s.c(x, B(d1 + 1), 0)
    for d in range(d0, d1 + 2):
        last = d == d1 + 1
        s.p(x - 1, T(d), 3 if last else 5)
        s.p(x - 1, B(d), 0 if last else 3)


def make_sidepods_downwash() -> Part:
    """Long pods, full height up front, ramping down and tapering to the rear."""
    s = Part()
    prof = {}
    for x in range(26, 49):
        if x >= 37:
            hw = 7
        elif x >= 33:
            hw = 6
        elif x >= 30:
            hw = 5
        elif x >= 28:
            hw = 4
        else:
            hw = 3
        prof[x] = hw
    for x, hw in prof.items():
        pod_surface(s, x, hw, ramp=x < 38, front=x >= 41)
    inlet(s, 48, 5, 6)
    s.over(43, T(6), SPEC)
    return s


def make_sidepods_undercut() -> Part:
    """Wide letterbox inlet and shoulder, then a deep undercut that pulls the
    bodywork in hard behind it."""
    s = Part()
    prof = {}
    for x in range(26, 50):
        if x >= 46:
            hw = 8
        elif x >= 44:
            hw = 7
        elif x >= 41:
            hw = 6
        elif x >= 33:
            hw = 5
        elif x >= 29:
            hw = 4
        else:
            hw = 3
        prof[x] = hw
    for x, hw in prof.items():
        pod_surface(s, x, hw, ramp=x < 44, front=x >= 45)
    inlet(s, 49, 5, 7)
    # undercut cavity: the floor under the overhang sits in deep shadow
    for x in range(36, 46):
        for d in range(prof[x] + 1, 9):
            s.c(x, B(d), 0)
    for x in range(40, 46):
        s.c(x, T(prof[x] + 1), 0)
    s.over(47, T(7), SPEC)
    return s


def make_sidepods_zeropod() -> Part:
    """Barely-there pods: slim body flank, slot inlet, exposed impact-spar
    fins sticking out over a lot of visible floor."""
    s = Part()
    prof = {}
    for x in range(26, 48):
        if x >= 30:
            hw = 5
        elif x >= 28:
            hw = 4
        else:
            hw = 3
        prof[x] = hw
    for x, hw in prof.items():
        pod_surface(s, x, hw, ramp=x < 34, front=False)
    # narrow vertical slot inlet
    s.col(47, T(5), DARK)
    s.col(47, B(5), DARK)
    s.p(46, T(5), 5)
    s.p(46, B(5), 2)
    # exposed side-impact spar fins (carbon blades) sticking out
    for d in (6, 7, 8):
        s.c(44, T(d), 5 if d == 7 else 4)
        s.c(44, B(d), 3)
        s.c(43, B(d), 0)
    s.c(45, T(8), 3)
    s.c(45, B(8), 2)
    # cooling gill slots: one neat row
    for x in (33, 35, 37):
        s.c(x, T(5), 1)
        s.c(x, B(5), 0)
    return s


# ===========================================================================
# FLOORS (carbon only)
# ===========================================================================

def floor_fill(f: Part, prof: dict):
    """Flat floor plate: dark top surface, lit leading/outer edge on the top
    side, hard dark edge on the shadow side."""
    for x, hw in prof.items():
        for d in range(1, hw + 1):
            f.c(x, T(d), 1)
            f.c(x, B(d), 1)
        f.c(x, T(hw), 4)
        f.c(x, B(hw), 0)
        if hw > 3:
            f.c(x, T(hw - 1), 2)
    xs = sorted(prof)
    fx = xs[-1]
    for d in range(1, prof[fx] + 1):
        f.c(fx, T(d), 3)
        f.c(fx, B(d), 2)
    f.c(fx, B(prof[fx]), 0)
    rx = xs[0]
    for d in range(1, prof[rx]):
        f.c(rx, T(d), 2)


def diffuser(f: Part, x0: int, x1: int, hw: int, strakes=(3,), throat=True):
    for x in range(x0, x1 + 1):
        for d in range(1, hw + 1):
            f.c(x, T(d), 1)
            f.c(x, B(d), 1)
        f.c(x, T(hw), 3)
        f.c(x, B(hw), 0)
        for s in strakes:
            f.c(x, T(s), 2)
            f.c(x, B(s), 0)
    if throat:
        for d in range(1, hw):
            if d not in strakes:
                f.c(x0, T(d), 0)
                f.c(x0, B(d), 0)


def make_floor_low_rake() -> Part:
    """Wide, flat, simple floor: straight edges, small diffuser."""
    f = Part()
    prof = {}
    for x in range(27, 53):
        if x == 52 or x == 28:
            hw = 8
        elif x == 27:
            hw = 7
        else:
            hw = 9
        prof[x] = hw
    floor_fill(f, prof)
    diffuser(f, 17, 26, 5, strakes=(3,))
    return f


def make_floor_high_rake() -> Part:
    """Narrow floor, bargeboards, and a big deep diffuser that sticks out."""
    f = Part()
    prof = {}
    for x in range(28, 53):
        if x >= 49 or x <= 29:
            hw = 7
        else:
            hw = 8
        prof[x] = hw
    floor_fill(f, prof)
    # bargeboards: curved vanes ahead of the sidepods
    vanes = [[(52, 6), (51, 7), (50, 8), (49, 9)],
             [(50, 4), (49, 5), (48, 6), (47, 7)]]
    for vane in vanes:
        for x, d in vane:
            f.c(x, T(d), 5)
            f.c(x, B(d), 3)
            f.c(x - 1, B(d), 0)
    # big diffuser: wide, deep, sticks out behind the rear wheels
    diffuser(f, 13, 27, 5, strakes=(2, 4))
    for x in range(12, 18):
        f.c(x, T(6), 0)
        f.c(x, B(6), 0)
        f.c(x, T(7), 4 if x > 12 else 3)
        f.c(x, B(7), 1)
    return f


def make_floor_venturi() -> Part:
    """Ground-effect floor: edge wings with scallops, fences up front."""
    f = Part()
    prof = {}
    for x in range(27, 54):
        if x == 53:
            hw = 7
        elif x == 52 or x == 28:
            hw = 8
        elif x == 27:
            hw = 7
        else:
            hw = 9
        prof[x] = hw
    floor_fill(f, prof)
    # edge wing: thin blade at d=10 with scallops
    for x in range(30, 48):
        if x in (36, 42):
            continue
        f.c(x, T(10), 5 if x in (31, 37, 43) else 4)
        f.c(x, B(10), 2)
    for x in range(30, 48):
        f.c(x, T(9), 2)
    # floor fences ahead of the sidepods, curling outward at the front
    for d0 in (3, 5, 7):
        for x in range(47, 53):
            d = d0 + (1 if x >= 51 else 0)
            f.c(x, T(d), 4)
            f.c(x, B(d), 2)
            f.c(x, B(d + 1), 0)
    diffuser(f, 17, 26, 5, strakes=(2, 4))
    return f


# ===========================================================================
# TYRES, HALO, HELMET, LIGHTS, GLOW, SHADOW
# ===========================================================================

COMPOUNDS = {
    "soft": hx("#e8352b"),
    "medium": hx("#f2c230"),
    "hard": hx("#f1efea"),
    "inter": hx("#3ecf6a"),
    "wet": hx("#3a8ee8"),
}


def tyre_block(compound="medium", grooves=False) -> np.ndarray:
    """One tyre 8 long x 4 wide, outer sidewall at the top row.
    x=0 is the rear end, x=7 the front end; light from the top-left."""
    t = canvas(TYRE_LEN, TYRE_W)
    stripe = COMPOUNDS[compound]
    sd = mix(stripe, TYRE[1], 0.45)
    rows = [
        [None, 3, "s", "S", "S", "s", 3, None],
        [3, 5, 5, 4, 4, 3, 2, 1],
        [2, 3, 3, 2, 2, 2, 1, 0],
        [None, 2, 2, 1, 1, 1, 0, None],
    ]
    for y, rr in enumerate(rows):
        for x, v in enumerate(rr):
            if v is None:
                continue
            if v == "S":
                t[y, x] = stripe
            elif v == "s":
                t[y, x] = sd
            else:
                t[y, x] = TYRE[v]
    if grooves:
        for x in (2, 5):
            t[1, x] = TYRE[1]
            t[2, x] = TYRE[0]
    return t


def make_tyres(compound="medium"):
    g = compound == "wet" or compound == "inter"
    blk = tyre_block(compound, grooves=g)
    blk_low = blk[::-1].copy()  # lower wheel: stripe on the outside (bottom)
    # darken the lower tyre a touch: it is on the shadow side
    rear = canvas(W, H)
    x0 = CX + REAR_AXLE - TYRE_LEN // 2
    rear[T(10):T(10) + 4, x0:x0 + 8] = blk
    rear[B(7):B(7) + 4, x0:x0 + 8] = blk_low
    front = canvas(10, 6)
    front[1:5, 1:9] = blk
    return rear, front


def make_halo_helmet():
    halo = Part()
    helmet = Part()
    # helmet 4x4 rounded at x 42..45, d 1..2 (centred on the line)
    hel = {  # (x, d): (top lvl, bottom lvl)
        (42, 1): (3, 1), (43, 1): (5, 3), (44, 1): (5, 3), (45, 1): (4, 2),
        (43, 2): (4, 1), (44, 2): (4, 1),
    }
    for (x, d), (tl, bl) in hel.items():
        helmet.p(x, T(d), tl)
        helmet.p(x, B(d), bl)
    # visor across the front of the helmet + glint (detail layer, on top)
    halo.col(45, T(1), VISOR[3])
    halo.col(45, B(1), VISOR[1])
    halo.col(45, T(2), VISOR[1])
    halo.col(45, B(2), VISOR[0])
    halo.over(43, T(1), SPEC)
    # halo: centre pillar at the front, hoop around the head at d=3
    halo.cs(50, 1, 4, 2)
    halo.cs(49, 1, 5, 2)
    halo.cs(48, 2, 4, 1)
    halo.cs(47, 3, 4, 1)
    for x in range(41, 47):
        halo.c(x, T(3), 4)
        halo.c(x, B(3), 1)
    halo.c(44, T(3), 5)
    halo.c(45, T(3), 5)
    halo.c(40, T(3), 3)
    halo.c(40, B(3), 0)
    return halo, helmet


def make_lights():
    li = canvas(W, H)
    red = hx("#ff3b2e")
    core = hx("#ffd2b8")
    # central rain light at the very back of the crash structure
    put(li, 9, T(1), red)
    put(li, 9, B(1), red)
    put(li, 10, T(1), core)
    put(li, 10, B(1), hx("#ff8a6a"))
    # endplate LEDs at the back of each endplate
    put(li, 10, T(6), red)
    put(li, 10, B(6), red)
    return li


def make_brake_glow():
    g = canvas(W, H)
    hot = hx("#ffb347")
    mid = hx("#ff6a1f", 230)
    rim = hx("#e8352b", 120)
    for axle in (FRONT_AXLE, REAR_AXLE):
        x = CX + axle  # pixel corner; disc pixels at x-1, x
        for top in (True, False):
            r_in = T(6) if top else B(6)
            r_t = T(7) if top else B(7)
            put(g, x - 1, r_in, hot)
            put(g, x, r_in, mid)
            put(g, x - 1, r_t, mid)
            put(g, x, r_t, rim)
            put(g, x - 2, r_in, rim)
    return g


# ===========================================================================
# BUILD + COMPOSE
# ===========================================================================

def build():
    layers = {}
    layers["body"] = make_body()
    layers["front_wing_outwash"] = make_front_wing_outwash()
    layers["front_wing_inwash"] = make_front_wing_inwash()
    layers["front_wing_highnose"] = make_front_wing_highnose()
    for name, fn in (("spoon", make_rear_wing_spoon),
                     ("highdf", make_rear_wing_highdf),
                     ("beam", make_rear_wing_beam)):
        layers[f"rear_wing_{name}"] = fn(False)
        layers[f"rear_wing_{name}_open"] = fn(True)
    layers["sidepods_downwash"] = make_sidepods_downwash()
    layers["sidepods_zeropod"] = make_sidepods_zeropod()
    layers["sidepods_undercut"] = make_sidepods_undercut()
    layers["floor_low_rake"] = make_floor_low_rake()
    layers["floor_high_rake"] = make_floor_high_rake()
    layers["floor_venturi"] = make_floor_venturi()
    halo, helmet = make_halo_helmet()
    # helmet highlights live in halo_detail so the helmet stays a single
    # tintable layer
    hm = (helmet.detail[..., 3] > 0) & (halo.detail[..., 3] == 0)
    halo.detail[hm] = helmet.detail[hm]
    helmet.detail[...] = 0
    layers["halo"] = halo
    layers["helmet"] = helmet
    return layers


def shadow_from(layers, tyres_rear, front_tyre) -> np.ndarray:
    m = np.zeros((H, W), bool)
    for k, part in layers.items():
        if k.endswith("_open"):
            continue
        m |= part.paint[..., 3] > 0
        m |= part.detail[..., 3] > 0
    m |= tyres_rear[..., 3] > 0
    for y0 in (T(10) - 1, B(7) - 1):
        x0 = CX + FRONT_AXLE - 5
        m[y0:y0 + 6, x0:x0 + 10] |= front_tyre[..., 3] > 0
    # close 1px gaps so the shadow reads as one soft shape
    m = ~dilate(~dilate(m, 1, diag=False), 1, diag=False)
    sh = canvas(W, H)
    shifted = np.zeros_like(m)
    shifted[2:, 2:] = m[:-2, :-2]
    sh[shifted] = (0, 0, 0, 115)
    return sh


def compose(layers, tyres_rear, front_tyre, shadow, combo, tint, helmet_tint=None,
            open_wing=False, lights=None, glow=None, steer=0):
    fl, sp, fw, rw = combo
    out = canvas(W, H)
    alpha_over(out, shadow)
    alpha_over(out, layers[f"floor_{fl}"].merged())
    alpha_over(out, tyres_rear)
    ft = front_tyre
    if steer:
        from pxl import rotate_nearest
        ft = rotate_nearest(front_tyre, steer)
    x0 = CX + FRONT_AXLE - 5
    alpha_over(out, ft, x0, T(10) - 1)
    alpha_over(out, ft[::-1].copy(), x0, B(7) - 1)
    if glow is not None:
        alpha_over(out, glow)
    alpha_over(out, layers[f"sidepods_{sp}"].merged(tint))
    alpha_over(out, layers["body"].merged(tint))
    alpha_over(out, layers[f"front_wing_{fw}"].merged(tint))
    rkey = f"rear_wing_{rw}" + ("_open" if open_wing else "")
    alpha_over(out, layers[rkey].merged(tint))
    alpha_over(out, layers["helmet"].merged(helmet_tint or hx("#f2c230")))
    alpha_over(out, layers["halo"].merged())
    if lights is not None:
        alpha_over(out, lights)
    return out


def asphalt(w, h):
    """Preview background: the track artist's asphalt tile if present."""
    from pxl import SPRITES
    p = os.path.join(SPRITES, "track", "asphalt.png")
    bg = canvas(w, h)
    bg[...] = hx("#2f3136")
    if os.path.exists(p):
        from PIL import Image
        tile = np.array(Image.open(p).convert("RGBA"))
        th, tw = tile.shape[:2]
        reps = (h // th + 1, w // tw + 1, 1)
        bg = np.tile(tile, reps)[:h, :w].copy()
    return bg


def main():
    out_dir = "car"
    layers = build()
    tyres_rear, front_tyre = make_tyres("medium")
    for comp in COMPOUNDS:
        r, f = make_tyres(comp)
        save(r, out_dir, f"tyre_rear_{comp}.png")
        save(f, out_dir, f"tyre_front_{comp}.png")
    save(tyres_rear, out_dir, "tyre_rear.png")
    save(front_tyre, out_dir, "tyre_front.png")

    for name, part in layers.items():
        if name in ("halo",):
            save(part.detail, out_dir, "halo_detail.png")
            continue
        if name == "helmet":
            save(part.paint, out_dir, "helmet_paint.png")
            if part.detail[..., 3].any():
                save(part.detail, out_dir, "helmet_detail.png")
            continue
        if name.startswith("floor_"):
            save(part.detail, out_dir, f"{name}.png")
            continue
        save(part.paint, out_dir, f"{name}_paint.png")
        save(part.detail, out_dir, f"{name}_detail.png")

    shadow = shadow_from(layers, tyres_rear, front_tyre)
    save(shadow, out_dir, "shadow.png")
    lights = make_lights()
    save(lights, out_dir, "lights.png")
    glow = make_brake_glow()
    save(glow, out_dir, "brake_disc_glow.png")

    anchors = {
        "canvas": [W, H],
        "center": [CX, CY],
        "px_per_m": 10,
        "front_wheels": [[FRONT_AXLE, -WHEEL_Y], [FRONT_AXLE, WHEEL_Y]],
        "rear_wheels": [[REAR_AXLE, -WHEEL_Y], [REAR_AXLE, WHEEL_Y]],
        "front_tyre_canvas": [10, 6],
        "front_tyre_note": "tyre_front.png is centred on its wheel anchor; compound stripe is on the top edge (outer side of the left/upper wheel): use flip_v for the lower (+y) wheel.",
        "rain_light": [10 - CX, 0],
        "exhaust": [15 - CX, 0],
        "helmet": [44 - CX, 0],
        "stack": [
            "shadow", "floor_*", "tyre_rear", "tyre_front x2", "brake_disc_glow",
            "sidepods_*_paint", "sidepods_*_detail", "body_paint", "body_detail",
            "front_wing_*_paint", "front_wing_*_detail", "rear_wing_*[_open]_paint",
            "rear_wing_*[_open]_detail", "helmet_paint", "halo_detail", "lights"],
    }
    save_json(anchors, out_dir, "anchors.json")

    preview(layers, tyres_rear, front_tyre, shadow, lights, glow)
    return layers


COMBOS = [
    ("low_rake", "downwash", "outwash", "highdf"),     # default
    ("high_rake", "undercut", "inwash", "spoon"),
    ("venturi", "zeropod", "highnose", "beam"),
    ("low_rake", "undercut", "highnose", "spoon"),
    ("high_rake", "zeropod", "outwash", "beam"),
    ("venturi", "downwash", "inwash", "highdf"),
    ("low_rake", "zeropod", "inwash", "beam"),
    ("high_rake", "downwash", "highnose", "highdf"),
    ("venturi", "undercut", "outwash", "spoon"),
]
TEAMS = [hx("#e8352b"), hx("#f1efea"), hx("#3a6fd8")]
HELMETS = [hx("#f2c230"), hx("#e8352b"), hx("#f1efea")]


def preview(layers, tyres_rear, front_tyre, shadow, lights, glow):
    """Contact sheet: row 0 default combo in 3 liveries, rows 1-3 the nine
    combos (team colour cycling), row 4 states: steering, Straight Mode open
    + rain light, hard braking glow."""
    k = 4
    pad = 12
    cw, ch = W * k + pad, H * k + pad
    sheet = asphalt(3 * cw + pad, 5 * ch + pad)

    def place(img, col, row):
        alpha_over(sheet, scale(img, k), pad + col * cw, pad + row * ch)

    for j in range(3):
        place(compose(layers, tyres_rear, front_tyre, shadow, COMBOS[0], TEAMS[j], HELMETS[j]), j, 0)
    for i, combo in enumerate(COMBOS):
        j = i % 3
        place(compose(layers, tyres_rear, front_tyre, shadow, combo, TEAMS[(i + i // 3) % 3],
                      HELMETS[(i + i // 3) % 3]), j, 1 + i // 3)
    place(compose(layers, tyres_rear, front_tyre, shadow, COMBOS[0], TEAMS[0], HELMETS[0],
                  steer=20), 0, 4)
    place(compose(layers, tyres_rear, front_tyre, shadow, COMBOS[0], TEAMS[2], HELMETS[2],
                  open_wing=True, lights=lights), 1, 4)
    place(compose(layers, tyres_rear, front_tyre, shadow, COMBOS[2], TEAMS[1], HELMETS[1],
                  glow=glow), 2, 4)
    save(sheet, "car", "preview_combos.png")


if __name__ == "__main__":
    main()
