"""Makes the static UI fonts from Pixelify Sans, with clearer B, 5 and C.

    python tools/fonts/patch_pixelify.py

Playtesters read Pixelify Sans' "B" as a "G" (its middle bar does not touch the
stem, and both left corners are cut) and its "5" as an "S" (rounded top-left,
hooked top-right); its "C" can pass for an "O" (a one-pixel opening). This script
instances the variable font at Regular (400) and Bold (700), then redraws them:
  B: square left corners, middle bar joined to the stem;
  5: a flat top bar with square corners, no hook;
  C: a wider opening on the right.
Point counts never change; points are only moved (sometimes onto each other), so
every other glyph and all metrics stay exactly as they were.

Writes game/assets/fonts/PitWallPixel-Regular.ttf and PitWallPixel-Bold.ttf.
Pixelify Sans is under the SIL Open Font License 1.1 (OFL.txt); the modified
fonts are renamed, as the licence asks of modified versions.
"""
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONTS = Path(__file__).resolve().parents[2] / "game" / "assets" / "fonts"
SRC = FONTS / "PixelifySans.ttf"
FAMILY = "Pit Wall Pixel"


def contours(glyph):
    out, start = [], 0
    for end in glyph.endPtsOfContours:
        out.append(list(range(start, end + 1)))
        start = end + 1
    return out


def fix_b(glyph):
    c = glyph.coordinates
    outer, inner = contours(glyph)
    p = [c[i] for i in outer]
    # outer: 0..2 cut bottom-left corner, 3..5 cut top-left corner
    left = p[2][0]
    bottom, top = p[0][1], p[5][1]
    for k in (0, 1, 2):
        c[outer[k]] = (left, bottom)
    for k in (3, 4, 5):
        c[outer[k]] = (left, top)
    # inner: points 3 and 4 are the left end of the middle bar; join it to the stem
    q = [c[i] for i in inner]
    stem_inner = q[0][0]
    c[inner[3]] = (stem_inner, q[3][1])
    c[inner[4]] = (stem_inner, q[4][1])


def fix_5(glyph):
    c = glyph.coordinates
    (outer,) = contours(glyph)
    p = [c[i] for i in outer]
    # points 13..15: cut top-left corner; 16..21: the hook down the right side
    left, top = p[13][0], p[15][1]
    right = p[18][0]
    bar_bottom = p[21][1]
    for k in (13, 14, 15):
        c[outer[k]] = (left, top)
    for k in (16, 17, 18):
        c[outer[k]] = (right, top)
    for k in (19, 20, 21):
        c[outer[k]] = (right, bar_bottom)


def fix_c(glyph, s_glyph):
    """Opens the C: its right-hand arms stop where the S's do, so it no longer reads as an O."""
    c = glyph.coordinates
    (outer,) = contours(glyph)
    sc = s_glyph.coordinates
    low, high = sc[3][1], sc[17][1]  # the S's lower and upper terminals (the pixel grid of this weight)
    for k in (9, 10):
        c[outer[k]] = (c[outer[k]][0], high)
    for k in (15, 16):
        c[outer[k]] = (c[outer[k]][0], low)


def build(weight: int, style: str) -> Path:
    font = instantiateVariableFont(TTFont(SRC), {"wght": weight}, updateFontNames=False)
    cmap = font.getBestCmap()
    glyf = font["glyf"]
    fix_b(glyf[cmap[ord("B")]])
    fix_5(glyf[cmap[ord("5")]])
    fix_c(glyf[cmap[ord("C")]], glyf[cmap[ord("S")]])
    for name in ("B", "five", "C"):
        glyf[name].recalcBounds(glyf)
    names = font["name"]
    for rec in list(names.names):
        if rec.nameID in (1, 3, 4, 6, 16, 17):
            names.removeNames(nameID=rec.nameID)
    ps = FAMILY.replace(" ", "") + "-" + style
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        names.setName(FAMILY, 1, pid, eid, lid)
        names.setName(style, 2, pid, eid, lid)
        names.setName(f"1.000;{ps}", 3, pid, eid, lid)
        names.setName(f"{FAMILY} {style}", 4, pid, eid, lid)
        names.setName(ps, 6, pid, eid, lid)
    font["OS/2"].usWeightClass = weight
    if weight >= 700:
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection | 0x20) & ~0x40
        font["head"].macStyle |= 1
    out = FONTS / f"{ps}.ttf"
    font.save(out)
    return out


if __name__ == "__main__":
    for w, s in ((400, "Regular"), (700, "Bold")):
        print("wrote", build(w, s))
