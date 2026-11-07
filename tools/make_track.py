"""Builds a circuit file for the driving physics from a list of straights and corners.

The physics runs in whole numbers, so everything it reads is written here as
integers in 16.16 fixed point (1 metre = 65536). Floats are only used in this
offline tool; the game and the server read the same integers.

    python tools/make_track.py            # writes game/tracks/*.json and a preview PNG
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

FP = 65536
SPACING = 4.0  # metres between centreline points
ROOT = Path(__file__).resolve().parent.parent

# Mtkvari Circuit: fictional, about 3.7 km, anticlockwise. Built like a real
# circuit from straights and corners: ("S", metres) or ("C", radius, degrees),
# negative degrees turn left. Two straights named "close_x"/"close_y" are solved
# so the lap closes exactly.
MTKVARI = {
    "id": "mtkvari",
    "name": "Mtkvari Circuit",
    "half_width": 7.0,
    "runoff": 13.0,
    "layout": [
        ("S", "close_x"),         # main straight, heading east
        ("C", 32, -90),           # T1 left, heavy braking
        ("S", "close_y"),
        ("C", 90, 35),            # T2-T3 kink
        ("S", 60),
        ("C", 90, -35),
        ("S", 140),
        ("C", 55, -90),           # T4 left onto the back straight
        ("S", 620),               # back straight, heading west
        ("C", 24, -150),          # T5 hairpin
        ("S", 150),
        ("C", 70, 60),            # T6 right
        ("S", 100),
        ("C", 110, -50),          # T7-T8 fast esses
        ("C", 110, 50),
        ("S", 120),
        ("C", 45, 90),            # T9 right
        ("S", 200),
        ("C", 75, -180),          # T10 long final corner onto the main straight
    ],
    # Straight Mode zones as (from, to) metres after the start/finish line.
    "straight_zones": "auto",
    "start_at": 420.0,       # start/finish line, metres along the main straight
    "spawn_before": 260.0,   # flying start this far before the line
    "spawn_speed": 58.0,     # m/s at the flying start
}


def turtle(layout, close_x, close_y):
    x, y, h = 0.0, 0.0, 0.0
    pts, straights = [], []
    for seg in layout:
        if seg[0] == "S":
            ln = {"close_x": close_x, "close_y": close_y}.get(seg[1], seg[1])
            start_d = len(pts) * 0.25
            n = max(1, round(ln / 0.25))
            for _ in range(n):
                pts.append((x, y))
                x += math.cos(h) * ln / n
                y += math.sin(h) * ln / n
            straights.append((start_d, len(pts) * 0.25, ln))
        else:
            r, deg = seg[1], seg[2]
            ang = math.radians(deg)
            n = max(1, round(r * abs(ang) / 0.25))
            for _ in range(n):
                pts.append((x, y))
                h += ang / n / 2
                x += math.cos(h) * r * abs(ang) / n
                y += math.sin(h) * r * abs(ang) / n
                h += ang / n / 2
    return pts, (x, y), straights


def solve_layout(layout):
    # end position is linear in the two free straights: solve for zero gap
    _, e0, _ = turtle(layout, 0.0, 0.0)
    _, ex, _ = turtle(layout, 1.0, 0.0)
    _, ey, _ = turtle(layout, 0.0, 1.0)
    a, b = ex[0] - e0[0], ey[0] - e0[0]
    c, d = ex[1] - e0[1], ey[1] - e0[1]
    det = a * d - b * c
    lx = (-e0[0] * d + e0[1] * b) / det
    ly = (-e0[1] * a + e0[0] * c) / det
    assert lx > 0 and ly > 0, (lx, ly)
    pts, end, straights = turtle(layout, lx, ly)
    print(f"closing straights: {lx:.0f} m and {ly:.0f} m, gap {math.dist(end, (0, 0)):.3f} m")
    return pts, straights


def resample(poly, spacing):
    cum = [0.0]
    for i in range(len(poly)):
        cum.append(cum[-1] + math.dist(poly[i], poly[(i + 1) % len(poly)]))
    total = cum[-1]
    n = round(total / spacing)
    step = total / n
    out, j = [], 0
    for k in range(n):
        d = k * step
        while cum[j + 1] < d:
            j += 1
        a, b = poly[j], poly[(j + 1) % len(poly)]
        t = (d - cum[j]) / (cum[j + 1] - cum[j])
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out, total


def build(spec):
    raw, straights = solve_layout(spec["layout"])
    pts, total = resample(raw, SPACING)
    if spec["straight_zones"] == "auto":
        # Straight Mode on every straight over 400 m, from 60 m after the corner to 140 m before the next
        spec = dict(spec, straight_zones=[(a + 60, b - 140) for a, b, ln in straights if ln > 400])
    n = len(pts)
    # rotate so point 0 is the start/finish line
    start = round(spec["start_at"] / (total / n)) % n
    pts = pts[start:] + pts[:start]
    zones = [(((a - spec["start_at"]) % total), ((b - spec["start_at"]) % total)) for a, b in spec["straight_zones"]]

    seg_len = [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]
    heading = [math.atan2(pts[(i + 1) % n][1] - pts[i][1], pts[(i + 1) % n][0] - pts[i][0]) for i in range(n)]
    curv = []
    for i in range(n):
        d = (heading[i] - heading[i - 1] + math.pi) % (2 * math.pi) - math.pi
        curv.append(d / seg_len[i])
    # smooth curvature for kerb placement
    sm = [sum(curv[(i + k) % n] for k in range(-3, 4)) / 7 for i in range(n)]
    kerb = []  # 1 = right side (inside of a right turn), -1 = left, 0 none
    for i in range(n):
        k = sm[i]
        kerb.append(0 if abs(k) < 1 / 260 else (1 if k > 0 else -1))

    dist = [0.0]
    for i in range(n - 1):
        dist.append(dist[-1] + seg_len[i])

    def in_zone(d):
        for a, b in zones:
            if (a <= b and a <= d <= b) or (a > b and (d >= a or d <= b)):
                return True
        return False

    flags = []
    for i in range(n):
        f = 0
        if kerb[i] == 1:
            f |= 1
        if kerb[i] == -1:
            f |= 2
        if in_zone(dist[i]):
            f |= 4
        flags.append(f)

    sectors = [round(n / 3), round(2 * n / 3)]
    spawn = round((total - spec["spawn_before"]) / (total / n)) % n

    xs = [round(p[0] * FP) for p in pts]
    ys = [round(p[1] * FP) for p in pts]
    # direction and length are derived from the integer points so the game never re-derives them
    dirs, lens = [], []
    for i in range(n):
        dx = xs[(i + 1) % n] - xs[i]
        dy = ys[(i + 1) % n] - ys[i]
        ln = math.hypot(dx, dy)
        dirs += [round(dx / ln * FP), round(dy / ln * FP)]
        lens.append(round(ln))

    line_off, line_kmh, brake_flags, boards = racing_line(pts, spec["half_width"])
    for i in range(n):
        if brake_flags[i]:
            flags[i] |= 8

    radii = sorted((1 / abs(c), i) for i, c in enumerate(sm) if abs(c) > 1e-6)[:5]
    print(f"{spec['name']}: {total:.0f} m, {n} points, tightest radii "
          + ", ".join(f"{r:.0f} m @{i * total / n:.0f}" for r, i in radii))

    return {
        "id": spec["id"],
        "name": spec["name"],
        "format": 1,
        "length_m": round(total),
        "half_width": round(spec["half_width"] * FP),
        "runoff": round(spec["runoff"] * FP),
        "sectors": sectors,
        "spawn_index": spawn,
        "spawn_speed": round(spec["spawn_speed"] * FP),
        "x": xs,
        "y": ys,
        "dir": dirs,
        "len": lens,
        "flags": flags,
        # Practice aids and trackside boards (presentation only; the physics never reads them)
        "line_cm": line_off,
        "line_kmh": line_kmh,
        "boards": boards,
    }, pts, kerb


def preview(spec, data, pts, kerb, path):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = 60
    scale = 0.7
    w = int((max(xs) - min(xs)) * scale) + 2 * pad
    h = int((max(ys) - min(ys)) * scale) + 2 * pad
    img = Image.new("RGB", (w, h), (20, 21, 24))
    d = ImageDraw.Draw(img)
    to = lambda p: ((p[0] - min(xs)) * scale + pad, (p[1] - min(ys)) * scale + pad)
    loop = [to(p) for p in pts] + [to(pts[0])]
    d.line(loop, fill=(52, 54, 60), width=int((spec["half_width"] + spec["runoff"]) * 2 * scale))
    d.line(loop, fill=(90, 92, 100), width=max(2, int(spec["half_width"] * 2 * scale)))
    for i, p in enumerate(pts):
        if data["flags"][i] & 4:
            d.point(to(p), fill=(80, 160, 255))
        if kerb[i]:
            d.point(to(p), fill=(232, 53, 43))
    for idx, col in [(0, (255, 255, 255)), (data["sectors"][0], (242, 194, 48)), (data["sectors"][1], (242, 194, 48)),
                     (data["spawn_index"], (0, 255, 0))]:
        x, y = to(pts[idx])
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=col)
    img.save(path)


# Car numbers used to estimate a racing line and speeds (match game/sim/car_sim.gd baseline)
MASS, MU, K_DOWN, K_DRAG, P_ICE, F_DRIVE, G = 800.0, 2.0, 3.0, 0.80, 400000.0, 8500.0, 9.81


def racing_line(pts, half_width):
    """Minimum-curvature line inside the track (elastic band), then a speed profile
    from grip, power and braking. Returns per-point offsets (cm), speeds (km/h),
    braking flags and the trackside braking boards."""
    n = len(pts)
    normals = []
    for i in range(n):
        a, b = pts[i - 1], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy)
        normals.append((-dy / ln, dx / ln))
    limit = half_width - 1.3
    off = [0.0] * n
    for span in (12, 8, 5, 3, 2):
        for _ in range(500):
            for i in range(n):
                j, k = (i - span) % n, (i + span) % n
                ax = pts[j][0] + normals[j][0] * off[j]
                ay = pts[j][1] + normals[j][1] * off[j]
                bx = pts[k][0] + normals[k][0] * off[k]
                by = pts[k][1] + normals[k][1] * off[k]
                tx, ty = (ax + bx) / 2 - pts[i][0], (ay + by) / 2 - pts[i][1]
                off[i] = max(-limit, min(limit, tx * normals[i][0] + ty * normals[i][1]))
    line = [(pts[i][0] + normals[i][0] * off[i], pts[i][1] + normals[i][1] * off[i]) for i in range(n)]
    ds = [math.dist(line[i], line[(i + 1) % n]) for i in range(n)]
    kappa = []
    for i in range(n):
        a, b, c = line[i - 1], line[i], line[(i + 1) % n]
        h1 = math.atan2(b[1] - a[1], b[0] - a[0])
        h2 = math.atan2(c[1] - b[1], c[0] - b[0])
        d = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi
        kappa.append(abs(d) / max(1e-6, (ds[i - 1] + ds[i]) / 2))
    kappa = [sum(kappa[(i + k) % n] for k in range(-2, 3)) / 5 for i in range(n)]
    vmax = []
    for i in range(n):
        lim = kappa[i] - MU * K_DOWN / MASS * 0.92
        vmax.append(95.0 if lim <= 0 else min(95.0, math.sqrt(MU * G * 0.92 / lim)))
    v = vmax[:]
    for _ in range(3):  # forward (acceleration) and backward (braking) passes, wrapped twice
        for i in range(n):
            j = (i + 1) % n
            drive = min(P_ICE / max(v[i], 10.0), F_DRIVE) - K_DRAG * v[i] ** 2
            v[j] = min(v[j], math.sqrt(max(0.0, v[i] ** 2 + 2 * drive / MASS * ds[i])))
        for i in range(n - 1, -1, -1):
            j = (i + 1) % n
            brake = MU * (MASS * G + K_DOWN * v[j] ** 2) * 0.85 + K_DRAG * v[j] ** 2
            v[i] = min(v[i], math.sqrt(v[j] ** 2 + 2 * brake / MASS * ds[i]))
    braking = [v[(i + 1) % n] < v[i] - 0.05 and v[i] < vmax[i] + 0.5 and v[(i + 1) % n] < 0.995 * v[i] for i in range(n)]
    # Braking boards: before every stop that loses more than 60 km/h
    boards = []
    i = 0
    while i < n:
        if braking[i] and not braking[i - 1]:
            j = i
            while braking[j % n] and j < i + n:
                j += 1
            drop = (v[i % n] - v[j % n]) * 3.6
            if drop > 60:
                side = 1 if off[j % n] < 0 else -1  # boards on the outside of the corner
                d = 0.0
                k = j
                marks = [50, 100, 150]
                while marks and k > j - 80:
                    k -= 1
                    d += ds[k % n]
                    if d >= marks[0]:
                        boards.append([k % n, marks.pop(0), side])
            i = j
        i += 1
    print(f"racing line: {len(boards)} braking boards, min {min(v) * 3.6:.0f} km/h, max {max(v) * 3.6:.0f} km/h")
    return [round(o * 100) for o in off], [round(x * 3.6) for x in v], braking, boards


def write_sine_table(path):
    values = [round(math.sin(2 * math.pi * i / 4096) * FP) for i in range(4097)]
    rows = ["\t" + ", ".join(str(v) for v in values[i:i + 16]) + "," for i in range(0, 4097, 16)]
    header = [
        "class_name SineTable",
        "## sin(2*pi*i/4096) in 16.16 fixed point, i = 0..4096. Written by tools/make_track.py",
        "## and stored, so every platform reads identical values (no libm in the physics).",
        "",
        "const VALUES: Array[int] = [",
    ]
    path.write_text("\n".join(header + rows + ["]", ""]), encoding="utf8", newline="\n")


if __name__ == "__main__":
    write_sine_table(ROOT / "game" / "sim" / "sine_table.gd")
    out_dir = ROOT / "game" / "tracks"
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in [MTKVARI]:
        data, pts, kerb = build(spec)
        (out_dir / f"{spec['id']}.json").write_text(json.dumps(data, separators=(",", ":")))
        preview(spec, data, pts, kerb, ROOT / "art" / f"track-{spec['id']}-preview.png")
