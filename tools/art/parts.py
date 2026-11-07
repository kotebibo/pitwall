"""Part-card illustrations (64 x 64, 3/4 view, brand-red paint).

Run:  python tools/art/parts.py
Writes game/assets/sprites/parts/{area}_{concept}.png

Each part is modelled from simple solids (lofted airfoils, boxes, cylinders)
and rendered by r3d.py into a quantised, outlined pixel-art sprite, then
touched up with a few deliberate highlight pixels.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from pxl import alpha_over, canvas, save  # noqa: E402
from r3d import (Camera, Model, box, cylinder, floor_shadow, loft, prism,  # noqa: E402
                 render, ring, rot_x, rot_y, rot_z, tube)

S = 64


# --------------------------------------------------------------------------
# shared shapes
# --------------------------------------------------------------------------

def airfoil(chord: float, thick: float, aoa_deg: float = 0.0, camber: float = 0.25):
    """Closed airfoil profile in (z, y): leading edge at z=+chord/2, rotated
    by aoa (positive = trailing edge up). 8 points, cambered."""
    c, t = chord, thick
    pts = [
        (0.50 * c, 0.00),
        (0.36 * c, 0.55 * t + camber * t),
        (0.05 * c, 0.75 * t + camber * t),
        (-0.30 * c, 0.45 * t + camber * t),
        (-0.50 * c, 0.05 * t),
        (-0.30 * c, 0.05 * t + camber * t * 0.6),
        (0.05 * c, -0.10 * t + camber * t * 0.4),
        (0.36 * c, -0.20 * t),
    ]
    a = math.radians(aoa_deg)
    out = []
    for z, y in pts:
        # rotate so trailing edge (negative z) goes up for positive aoa
        zz = z * math.cos(a) + y * math.sin(a)
        yy = -z * math.sin(a) + y * math.cos(a)
        out.append((zz, yy))
    return out


def wing_element(m: Model, x0, x1, zc, yc, chord, thick, aoa, mat, twist=None, segs=1,
                 sweep=None, dip=None, obj=None):
    """Spanwise element from x0 to x1 built from sections, allowing per-station
    offsets (sweep: f(t)->dz, dip: f(t)->dy, twist: f(t)->aoa delta)."""
    secs = []
    for i in range(segs + 1):
        t = i / segs
        x = x0 + (x1 - x0) * t
        a = aoa + (twist(t) if twist else 0.0)
        dz = sweep(t) if sweep else 0.0
        dy = dip(t) if dip else 0.0
        prof = airfoil(chord, thick, a)
        secs.append([(x, yc + y + dy, zc + z + dz) for z, y in prof])
    return loft(m, secs, mat, obj=obj)


def plate(m: Model, pts_zy, x, thick, mat, obj=None):
    """Flat plate in the (z, y) plane at span position x (endplates)."""
    return prism(m, pts_zy, "x", x - thick / 2, x + thick / 2, mat, obj=obj)


def finish(img, shadow=(32, 52, 26, 6), touch=None):
    out = canvas(S, S)
    if shadow:
        cx, cy, rx, ry = shadow
        alpha_over(out, floor_shadow(S, S, cx, cy, rx, ry))
    alpha_over(out, img)
    if touch:
        touch(out)
    return out


# --------------------------------------------------------------------------
# FRONT WINGS
# --------------------------------------------------------------------------

def front_wing(kind: str):
    m = Model()
    span = 25.0
    # mainplane (carbon), flaps (paint)
    wing_element(m, -span, span, 4.0, 0.0, 9.0, 1.6, 4, "carbon", segs=6,
                 dip=(lambda t: 1.2 * math.sin(math.pi * t) ** 2) if kind != "highnose" else None)
    if kind == "inwash":
        sw = lambda t: -3.0 * (1 - abs(2 * t - 1))  # flaps sweep back toward the centre
    elif kind == "outwash":
        sw = lambda t: 1.5 * (abs(2 * t - 1) ** 3)
    else:
        sw = None
    wing_element(m, -span + 1, span - 1, -3.5, 2.2, 6.0, 1.3, 22, "paint", segs=8, sweep=sw)
    wing_element(m, -span + 2, span - 2, -8.0, 5.0, 4.6, 1.1, 38, "paint", segs=8, sweep=sw)
    if kind != "highnose":
        wing_element(m, -span + 3, span - 3, -11.0, 8.2, 3.4, 1.0, 52, "paint", segs=8, sweep=sw)

    # endplates
    for sgn in (-1, 1):
        x = sgn * (span + 0.6)
        if kind == "outwash":
            ep = [(9, -1), (9, 4), (2, 9), (-9, 13), (-14, 13), (-14, -1)]
            plate(m, ep, x, 1.4, "paint")
            # footplate curling outward
            box(m, (sgn * (span + 3.2), -0.8, 0), (5.0, 1.0, 16), "carbon")
            box(m, (sgn * (span + 5.4), 1.2, -5), (1.0, 4.5, 8), "paint")
        elif kind == "inwash":
            ep = [(8, -1), (8, 3), (-3, 8), (-12, 8), (-12, -1)]
            plate(m, ep, x, 1.4, "paint")
        else:
            ep = [(10, -1), (10, 6), (-11, 10), (-11, -1)]
            plate(m, ep, x, 1.4, "paint")

    # nose
    if kind == "highnose":
        secs = []
        for z, w, h, y in ((10, 2.5, 2.0, 12.5), (6, 4.0, 3.2, 13.0), (-4, 5.5, 4.8, 13.6),
                           (-18, 6.5, 6.0, 14.2)):
            secs.append([(math.cos(a) * w, y + math.sin(a) * h, z) for a in
                         [i * math.pi / 4 for i in range(8)]])
        loft(m, secs, "paint")
        for sgn in (-1, 1):
            plate(m, [(6, 1.5), (6, 10.5), (-1, 11), (-3, 1.5)], sgn * 3.0, 1.0, "carbon")
    else:
        secs = []
        for z, w, h, y in ((13, 1.2, 1.0, 2.6), (10, 3.2, 2.2, 3.4), (2, 4.6, 3.6, 5.0),
                           (-8, 5.6, 4.6, 6.8), (-18, 6.4, 5.4, 8.4)):
            secs.append([(math.cos(a) * w, y + math.sin(a) * h, z) for a in
                         [i * math.pi / 4 for i in range(8)]])
        loft(m, secs, "paint")
    cam = Camera(yaw=-38, pitch=30, scale=1.0, cx=32, cy=33)
    img = render(m, cam)
    return finish(img, shadow=(32, 44, 28, 8))


# --------------------------------------------------------------------------
# REAR WINGS (seen from behind, 3/4)
# --------------------------------------------------------------------------

def rear_wing(kind: str):
    m = Model()
    span = 15.0
    yb = 20.0
    if kind == "highdf":
        wing_element(m, -span, span, 2.5, yb, 10.0, 1.8, 12, "paint", segs=4)
        wing_element(m, -span, span, -6.0, yb + 5.0, 9.0, 1.5, 50, "paint", segs=4)
        box(m, (0, yb + 9.8, -8.8), (2 * span, 1.6, 0.8), "carbon")          # gurney
        ep_top = 33
    elif kind == "spoon":
        wing_element(m, -span, span, 1.5, yb + 1, 8.0, 1.5, 8, "paint", segs=10,
                     dip=lambda t: -3.2 * math.sin(math.pi * t))
        wing_element(m, -span, span, -4.5, yb + 4.0, 4.5, 1.1, 24, "paint", segs=10,
                     dip=lambda t: -3.2 * math.sin(math.pi * t))
        ep_top = 29
    else:  # beam
        span = 13.0
        wing_element(m, -span, span, 1.5, yb + 3, 6.0, 1.3, 10, "paint", segs=4)
        wing_element(m, -span, span, -3.5, yb + 6.0, 4.5, 1.0, 34, "paint", segs=4)
        # beam wing low down, carbon, between the endplates
        wing_element(m, -span, span, 4.0, 8.0, 6.0, 1.3, 12, "carbon", segs=4)
        wing_element(m, -span + 1, span - 1, -0.5, 10.5, 4.0, 1.0, 30, "carbon", segs=4)
        ep_top = 31
    # endplates: carbon plate with a painted top band, rounded top corner
    for sgn in (-1, 1):
        x = sgn * (span + 0.7)
        plate(m, [(7, ep_top - 9), (7, ep_top - 5), (3, ep_top), (-9, ep_top), (-11, ep_top - 3),
                  (-11, ep_top - 9)], x, 1.4, "paint")
        plate(m, [(7, 6), (7, ep_top - 9), (-11, ep_top - 9), (-11, 6)], x, 1.4, "carbon")
        # endplate LED strip at the trailing edge
        box(m, (x, ep_top - 12, -11.3), (1.2, 4.0, 0.6), "lamp", flat=4)
    # central swan-neck pylon (from the crash structure up to the mainplane)
    plate(m, [(3, 4), (3, yb - 2), (0, yb + 1), (-2, yb + 1), (-2, 4)], 0, 1.6, "carbon")
    box(m, (0, 4.5, 1), (5, 3, 10), "carbon")                     # crash structure stub
    # DRS actuator pod on the flap
    box(m, (0, yb + 9 if kind == "highdf" else yb + 6, -3), (2.4, 2.0, 4.0), "carbon")
    # rain light at the back of the crash structure
    box(m, (0, 4.5, -4.3), (3.6, 2.4, 0.8), "lamp", flat=4)
    cam = Camera(yaw=150, pitch=44, scale=1.15, cx=32, cy=47)
    img = render(m, cam)
    return finish(img, shadow=(32, 52, 22, 6))


# --------------------------------------------------------------------------
# SIDEPODS (front-right 3/4, one pod with a chassis stub on a floor plate)
# --------------------------------------------------------------------------

def rrect(x0, x1, y0, y1, r, z, n=3):
    """Rounded rectangle ring in the (x, y) plane at depth z."""
    pts = []
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    for cx, cy, a0 in corners:
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts


def section_poly(poly, z):
    return [(x, y, z) for x, y in poly]


def sidepod(kind: str):
    m = Model()
    # floor plate
    box(m, (6, -0.6, -2), (34, 1.2, 46), "carbon")
    box(m, (22.6, 0.6, -2), (1.0, 1.2, 46), "carbon")   # edge lip
    # chassis stub (paint) along the centreline
    loft(m, [rrect(-8, 0, 0, 13, 3, z) for z in (24, -26)], "paint")
    box(m, (-4, 13.1, 8), (5, 0.4, 10), "dark")           # cockpit hint
    if kind == "downwash":
        # full height up front, then a long ramp sloping down to the rear
        prof = [(14, 15, 13.5), (11, 16.5, 14.5), (6, 17, 14.5), (0, 16.5, 13.5), (-6, 15, 11.5),
                (-12, 12.5, 9), (-18, 9.5, 6.5), (-24, 6.5, 4)]
        loft(m, [rrect(0, w, 1, h, 3.5 if h > 8 else 2, z) for z, w, h in prof], "paint")
        box(m, (8.6, 8.0, 14.2), (10.5, 8.0, 0.6), "dark")      # inlet mouth
        box(m, (8.6, 12.6, 14.1), (11.5, 1.2, 1.0), "paint")    # top lip
        box(m, (10, 14.6, 2), (5, 0.4, 6), "dark")               # louvre panel
    elif kind == "undercut":
        def uc(z, w, h, base):
            # deep undercut: a wide top shelf over a narrow waisted base
            return section_poly([(0, 1), (base, 1), (base + 1.5, h * 0.55), (w - 1, h * 0.72),
                                 (w, h * 0.85), (w, h), (w - 3, h + 1.5), (0, h + 1.5)], z)
        secs = [uc(14, 20, 12, 4), uc(10, 20, 12, 4), uc(4, 18, 11.5, 4.5), uc(-4, 15, 10, 5),
                uc(-12, 11, 7.5, 5), uc(-22, 6, 3.5, 3.5)]
        loft(m, secs, "paint")
        box(m, (11.0, 10.4, 14.2), (16.0, 3.6, 0.6), "dark")    # wide letterbox inlet
        box(m, (12, 0.1, 4), (14, 0.3, 22), "dark")             # undercut cavity shadow
    else:  # zeropod
        secs = [rrect(0, 6, 1, 15, 2.5, 13), rrect(0, 6.5, 1, 15, 2.5, 4),
                rrect(0, 6, 1, 12, 2.5, -10), rrect(0, 4.5, 1, 6, 2, -24)]
        loft(m, secs, "paint")
        box(m, (5.0, 9.0, 13.2), (2.4, 9.0, 0.6), "dark")       # tall slot inlet
        wing_element(m, 5, 18, 5, 8.5, 6.0, 1.2, 4, "carbon", segs=1)   # SIS wing
        box(m, (18.6, 7.4, 5), (1.0, 4.0, 7.0), "paint")
        for i in range(4):
            box(m, (6.2, 11.0, -1 - i * 3.4), (0.6, 4.0, 1.4), "dark")  # gills
    cam = Camera(yaw=-62, pitch=24 if kind != "undercut" else 15, scale=1.0, cx=31,
                 cy=36 if kind != "undercut" else 38)
    img = render(m, cam)
    return finish(img, shadow=None)


# --------------------------------------------------------------------------
# FLOORS (from above-front)
# --------------------------------------------------------------------------

def floor(kind: str):
    m = Model()
    if kind == "low_rake":
        prism(m, [(-22, 20), (22, 20), (24, 16), (24, -18), (-24, -18), (-24, 16)], "y", -1.2, 0, "carbon")
        prism(m, [(-12, -18), (12, -18), (12, -26), (-12, -26)], "y", -1.2, 0, "carbon")
        loft(m, [section_poly([(-12, 0), (12, 0), (12, 1.0), (-12, 1.0)], -18),
                 section_poly([(-12, 2.5), (12, 2.5), (12, 3.5), (-12, 3.5)], -26)], "carbon")
        for x in (-6, 0, 6):
            prism(m, [(-18, 0), (-18, 1.5), (-26, 4.5), (-26, 0)], "x", x - 0.5, x + 0.5, "carbon")
        box(m, (-23.4, 0.9, -1), (1.2, 1.8, 34), "paint")
        box(m, (23.4, 0.9, -1), (1.2, 1.8, 34), "paint")
        box(m, (0, 0.5, 19), (40, 1.0, 1.4), "paint")          # leading edge
        cam = Camera(yaw=-30, pitch=40, cx=32, cy=33)
    elif kind == "high_rake":
        Rk = rot_x(math.radians(-7))   # nose down, tail up
        sub = Model()
        prism(sub, [(-17, 20), (17, 20), (19, 14), (19, -16), (-19, -16), (-19, 14)], "y", -1.2, 0, "carbon")
        prism(sub, [(-10, -16), (10, -16), (10, -20), (-10, -20)], "y", -1.2, 0, "carbon")
        loft(sub, [section_poly([(-12, 0), (12, 0), (12, 1.0), (-12, 1.0)], -18),
                   section_poly([(-14, 7.5), (14, 7.5), (14, 8.5), (-14, 8.5)], -29)], "carbon")
        for x in (-8, -3, 3, 8):
            prism(sub, [(-18, 0), (-18, 1.5), (-29, 9.5), (-29, 0)], "x", x - 0.5, x + 0.5, "carbon")
        for s in (-1, 1):
            prism(sub, [(-16, 0), (-16, 2), (-29, 11), (-29, 0)], "x", s * 14 - 0.6, s * 14 + 0.6, "paint")
        for s in (-1, 1):
            for i, (x, z) in enumerate(((13, 17), (16, 13))):
                box(sub, (s * x, 3.5, z), (0.9, 7.0, 7.5), "paint" if i == 0 else "carbon",
                    R=rot_y(math.radians(s * 20)))
        m.extend(sub.transformed(lambda p: p @ Rk.T))
        cam = Camera(yaw=-30, pitch=40, cx=32, cy=31)
    else:  # venturi
        prism(m, [(-21, 20), (21, 20), (24, 14), (24, -18), (-24, -18), (-24, 14)], "y", -1.2, 0, "carbon")
        prism(m, [(-12, -18), (12, -18), (12, -24), (-12, -24)], "y", -1.2, 0, "carbon")
        loft(m, [section_poly([(-12, 0), (12, 0), (12, 1.0), (-12, 1.0)], -18),
                 section_poly([(-13, 5.0), (13, 5.0), (13, 6.0), (-13, 6.0)], -27)], "carbon")
        for x in (-5, 5):
            prism(m, [(-18, 0), (-18, 1.5), (-27, 7), (-27, 0)], "x", x - 0.5, x + 0.5, "carbon")
        for s in (-1, 1):
            for i, x in enumerate((4, 8, 12, 16)):
                box(m, (s * x, 2.5, 15), (0.8, 5.0 - i * 0.6, 9), "paint" if i % 2 == 0 else "carbon",
                    R=rot_y(math.radians(s * (6 + i * 5))))
            box(m, (s * 25.3, 2.0, -2), (2.2, 1.2, 30), "paint", R=rot_z(math.radians(s * -25)))
        cam = Camera(yaw=-30, pitch=42, cx=32, cy=33)
    img = render(m, cam, twill=True)
    return finish(img, shadow=None)


# --------------------------------------------------------------------------
# SUSPENSION
# --------------------------------------------------------------------------

def suspension(kind: str):
    m = Model()
    loft(m, [rrect(-30, -16, -10, 12, 3, z) for z in (14, -14)], "paint")   # chassis side
    box(m, (-23, 12.4, 0), (10, 0.6, 20), "dark")                            # cockpit hint
    cylinder(m, (13, 0, 0), (26, 0, 0), 13, "tyre", n=24)                    # tyre
    cylinder(m, (26, 0, 0), (26.6, 0, 0), 9.0, "metal", n=20)                # rim (outer)
    cylinder(m, (26.6, 0, 0), (27.6, 0, 0), 3.2, "carbon", n=10)             # wheel nut
    for i in range(24):                                                       # compound band
        a0 = 2 * math.pi * i / 24
        a1 = 2 * math.pi * (i + 1) / 24
        r0, r1 = 10.4, 11.6
        p = [(26.05, r0 * math.cos(a0), r0 * math.sin(a0)), (26.05, r1 * math.cos(a0), r1 * math.sin(a0)),
             (26.05, r1 * math.cos(a1), r1 * math.sin(a1)), (26.05, r0 * math.cos(a1), r0 * math.sin(a1))]
        m.add(p, "yellow", obj=m.new_obj())
    box(m, (10.5, 0, 0), (2.6, 15, 4), "metal")                              # upright
    for y, yo in ((7.0, 6.5), (-7.5, -6.8)):                                 # wishbones
        tube(m, (-16, yo, 9), (10, y, 0.5), 0.9, "carbon")
        tube(m, (-16, yo, -9), (10, y, -0.5), 0.9, "carbon")
    tube(m, (-16, -2, 6), (10, -2.5, 4), 0.6, "metal")                       # track rod
    if kind == "pushrod":
        tube(m, (9, -6.5, 0), (-15, 10, 0), 1.3, "yellow")
        box(m, (-17, 10.5, 0), (3, 4, 5), "metal")
        tube(m, (-17, 11.5, 0), (-20, 13, -11), 1.4, "metal")
    else:
        tube(m, (9, 6.5, 0), (-15, -9, 0), 1.3, "yellow")
        box(m, (-17, -9.5, 0), (3, 4, 5), "metal")
        tube(m, (-17, -10.5, 0), (-20, -12, -11), 1.4, "metal")
    cam = Camera(yaw=-34, pitch=16, scale=1.0, cx=31, cy=30)
    img = render(m, cam)
    return finish(img, shadow=(31, 49, 23, 5))


# --------------------------------------------------------------------------
# POWER UNITS
# --------------------------------------------------------------------------

def gear(m: Model, c, axis_len, r, teeth, mat, tooth=1.6):
    cx, cy, cz = c
    cylinder(m, (cx, cy, cz - axis_len / 2), (cx, cy, cz + axis_len / 2), r, mat, n=teeth * 2)
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        box(m, (cx + math.cos(a) * (r + tooth / 2), cy + math.sin(a) * (r + tooth / 2), cz),
            (tooth * 1.2, tooth * 1.1, axis_len), mat, R=rot_z(a))
    cylinder(m, (cx, cy, cz + axis_len / 2), (cx, cy, cz + axis_len / 2 + 0.6), r * 0.35, "metal", n=10)


def power_unit(kind: str):
    """V6 hybrid seen from the rear-left, above: red cam covers on a 90-degree
    V, carbon plenum, copper exhaust primaries into a gold turbo at the back,
    MGU-K and energy store on the left flank."""
    m = Model()
    box(m, (0, -3, 0), (13, 8, 24), "metal", bias=-1)                         # crankcase
    for s in (-1, 1):
        R = rot_z(math.radians(-s * 42))
        bank_c = np.array([s * 6.0, 4.5, 0])
        box(m, tuple(bank_c), (6.5, 9, 22), "metal", R=R)
        cover = bank_c + R @ np.array([0, 5.0, 0])
        box(m, tuple(cover), (5.6, 1.8, 21), "paint", R=R)                   # cam cover
        for zz in (-4, 4):                                                    # exhaust primaries
            p0 = bank_c + R @ np.array([s * 3.4, -1.5, zz])
            tube(m, p0, (s * 10.5, -2.5, zz - 3), 1.2, "copper", n=8)
        tube(m, (s * 10.5, -2.5, 1), (s * 10.5, -2.5, -8), 1.4, "copper", n=8)
        tube(m, (s * 10.5, -2.5, -8), (s * 4.5, 1.0, -13.0), 1.4, "copper", n=8)
    big = kind == "topend"
    if big:                                                                   # tall plenum + trumpets
        box(m, (0, 11.5, 0), (7, 5, 18), "carbon")
        for zz in (-6, 0, 6):
            cylinder(m, (0, 14, zz), (0, 16.5, zz), 1.6, "metal", n=10)
    else:
        box(m, (0, 10.5, 0), (5.5, 3.5, 17), "carbon")
    # turbo at the back: big gold turbine snail, dark compressor mouth
    tr = 7.0 if big else 4.8
    cylinder(m, (0, 2.5, -12), (0, 2.5, -16.5), tr, "gold", n=20)
    cylinder(m, (0, 2.5, -16.5), (0, 2.5, -17.5), tr * 0.62, "metal", n=16)
    cylinder(m, (0, 2.5, -17.5), (0, 2.5, -17.7), tr * 0.45, "dark", n=14)
    tube(m, (0, 2.5 + tr * 0.7, -14), (0, 2.5 + tr + 3.5, -14), 1.3, "gold", n=8)  # wastegate
    # MGU-K on the left flank, orange HV cable
    kr = 4.6 if kind == "torque" else 3.4
    cylinder(m, (-10.5, -5, 11), (-10.5, -5, 2), kr, "metal", n=16)
    cylinder(m, (-10.5, -5, 2), (-10.5, -5, 1.2), kr * 0.6, "carbon", n=12)
    tube(m, (-10.5, -5 + kr, 6), (-6, 2, 10), 0.7, "copper")
    # energy store below the left flank
    box(m, (-9.5, -10.5, -4), (10, 4.5, 14), "carbon")
    if kind == "efficiency":
        for i in range(2):
            for j in range(4):
                box(m, (-14.7, -11.6 + i * 2.4, -9.5 + j * 3.6), (0.5, 1.6, 2.8), "glow",
                    flat=6 if (i + j) % 2 == 0 else 5)
        tube(m, (-14.6, -8.6, 3.5), (-11, -3, 5), 0.6, "glow", flat=5)
        box(m, (-9.5, -8.1, -4), (8, 0.5, 11), "glow", flat=4)
    if kind == "torque":
        # exposed gear train on the back of the block, yellow torque ring on the MGU-K
        gear(m, (-10.5, -5.0, -0.2), 1.6, 5.2, 8, "gold", tooth=2.6)
        cylinder(m, (-10.5, -5, 8), (-10.5, -5, 6.5), kr + 0.4, "yellow", n=16)
    cam = Camera(yaw=148, pitch=34, scale=1.2, cx=32, cy=31)
    img = render(m, cam)
    return finish(img, shadow=(32, 51, 26, 7))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

PARTS = {
    "front_wing_outwash": lambda: front_wing("outwash"),
    "front_wing_inwash": lambda: front_wing("inwash"),
    "front_wing_highnose": lambda: front_wing("highnose"),
    "rear_wing_spoon": lambda: rear_wing("spoon"),
    "rear_wing_highdf": lambda: rear_wing("highdf"),
    "rear_wing_beam": lambda: rear_wing("beam"),
    "sidepods_downwash": lambda: sidepod("downwash"),
    "sidepods_zeropod": lambda: sidepod("zeropod"),
    "sidepods_undercut": lambda: sidepod("undercut"),
    "floor_high_rake": lambda: floor("high_rake"),
    "floor_low_rake": lambda: floor("low_rake"),
    "floor_venturi": lambda: floor("venturi"),
    "suspension_pushrod": lambda: suspension("pushrod"),
    "suspension_pullrod": lambda: suspension("pullrod"),
    "power_unit_torque": lambda: power_unit("torque"),
    "power_unit_topend": lambda: power_unit("topend"),
    "power_unit_efficiency": lambda: power_unit("efficiency"),
}


def main(only=None):
    out = {}
    for name, fn in PARTS.items():
        if only and not any(o in name for o in only):
            continue
        img = fn()
        save(img, "parts", f"{name}.png")
        out[name] = img
    return out


if __name__ == "__main__":
    main(sys.argv[1:] or None)
