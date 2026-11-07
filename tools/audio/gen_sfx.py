"""Driving loops, impacts, car systems, start lights, UI, feedback and pack-opening sounds
(race-mode sounds are in gen_race.py).

    python tools/audio/gen_sfx.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

import numpy as np

from instruments import IR_HALL, IR_ROOM, IR_SHORT, bell, blip, click, mix, nz, pluck, supersaw, thud
from dsp import (SR, add_at, add_circ, additive, bp, brown, db, delay, env_adsr, env_exp, fade, filt,
                 finish_loop, finish_oneshot, hp, hz, loop_bp, loop_hp, loop_lp, loop_peak, loop_reson, lp,
                 limiter, make_ir, n_of, normalize, to_db, osc, peak, phase_of, pink, reson, reverb, rng, sat, smooth_mod,
                 sos_reson, svf_sweep, tt, white, write_wav)

def save(name: str, x: np.ndarray, desc: str, peak_db: float = -3.0, hp_hz: float = 25.0, fin: float = 0.0008,
         fout: float = 0.015, max_crest: float = 18.0) -> None:
    """Finish a one-shot. Very spiky sounds are limited so the crest factor (peak/RMS) stays <= max_crest dB."""
    x = np.asarray(x, dtype=float)
    x = x / (np.max(np.abs(x)) + 1e-12)
    act = x[np.abs(x) > 1e-3]
    crest = to_db(1.0 / (np.sqrt(np.mean(act * act)) + 1e-12)) if len(act) else 0.0
    if crest > max_crest:
        x = limiter(x, -(crest - max_crest), 1.0, 60.0)
    write_wav(name, finish_oneshot(x, peak_db, hp_hz, fin, fout), desc=desc)


def save_loop(name: str, x: np.ndarray, desc: str, hp_hz: float = 25.0, rms_db: float | None = None) -> None:
    write_wav(name, finish_loop(x, -3.0, hp_hz, rms_db=rms_db), loop=True, desc=desc)


# ==========================================================================
# Tyres and surfaces (loops)
# ==========================================================================

def tyre_squeal() -> None:
    r = rng(51)
    n = n_of(2.0)
    x = np.zeros(n)
    for f_base, amp in ((1190, 1.0), (1770, 0.55), (2640, 0.32)):
        fb = round(f_base * n / SR) * SR / n
        fm = 1 + 0.045 * smooth_mod(n, r, 0.3, 3.0) + 0.012 * smooth_mod(n, r, 4, 14)
        ph = phase_of(fb * fm, n)
        v = np.sin(2 * np.pi * ph) + 0.22 * np.sin(4 * np.pi * ph + 0.5) + 0.08 * np.sin(6 * np.pi * ph + 1.3)
        am = np.clip(0.62 + 0.45 * smooth_mod(n, r, 0.4, 6.0), 0.05, 1.0) ** 1.4
        chatter = 1 + 0.18 * smooth_mod(n, r, 22, 55)
        x += amp * v * am * chatter
    hiss = loop_bp(white(n, r), 800, 4500, 2) * (0.6 + 0.4 * smooth_mod(n, r, 0.5, 5)) * 0.35
    x = x / np.max(np.abs(x)) + hiss
    x = sat(x / np.max(np.abs(x)), 1.3)
    save_loop("tyre_squeal", x, "Tyres at the limit: wavering tonal screech (1.2/1.8/2.6 kHz) over hiss.", 300, rms_db=-13)


def lockup() -> None:
    r = rng(52)
    n = n_of(1.5)
    scrub = loop_bp(white(n, r), 260, 2400, 2)
    rough = np.abs(smooth_mod(n, r, 25, 110))
    scrub *= 0.35 + 0.65 * rough / (rough.max() + 1e-9)
    f0 = round(410 * n / SR) * SR / n
    fm = 1 + 0.07 * smooth_mod(n, r, 3, 13) + 0.02 * smooth_mod(n, r, 20, 60)
    tone = osc("saw", f0 * fm, n)
    tone = loop_lp(tone, 1600, 2) * (0.6 + 0.4 * smooth_mod(n, r, 1, 7))
    flat = np.zeros(n)  # flat-spot thumps
    for k in range(int(1.5 * 17)):
        add_circ(flat, int(k * n / int(1.5 * 17)), thud(85, 60, 0.012, 0.05) * 0.4)
    x = scrub * 1.0 + tone * 0.55 + flat
    x = sat(x / np.max(np.abs(x)), 2.0)
    x = loop_peak(x, 700, 1.2, 4)
    save_loop("lockup", x, "Locked front tyre: harsh low scrub and juddering howl.", 60, rms_db=-13)


def kerb() -> None:
    r = rng(53)
    n = SR  # 1 s, 30 strips per second at nominal pitch
    x = np.zeros(n)
    count = 30
    for k in range(count):
        t0 = int(k * n / count + r.normal(0, 0.0012) * SR)
        a = 1.0 if k % 2 == 0 else 0.72
        th = thud(95, 55, 0.012, 0.045, 0.006) * a
        rat = bp(nz(n_of(0.02), r), 700, 3800, 2) * env_exp(n_of(0.02), 0.005) * r.uniform(0.6, 1.2)
        buzz = reson(nz(n_of(0.03), r), 230, 6) * env_exp(n_of(0.03), 0.009) * 0.6
        add_circ(x, t0, th)
        add_circ(x, t0, rat)
        add_circ(x, t0 + n_of(0.002), buzz)
    x += loop_bp(white(n, r), 1500, 6000, 2) * 0.03 * (1 + smooth_mod(n, r, 5, 20))  # suspension rattle bed
    x = sat(x / np.max(np.abs(x)), 1.8)
    save_loop("kerb", x, "Kerb rumble: 30 strip hits per second with chassis rattle (pitch with speed).", 25, rms_db=-14)


def gravel() -> None:
    r = rng(54)
    n = n_of(1.5)
    x = np.zeros(n)
    for _ in range(int(1.5 * 950)):
        m = n_of(r.uniform(0.002, 0.007))
        f = r.uniform(900, 6500)
        g = reson(nz(m, r), f, r.uniform(1.5, 5)) * env_exp(m, m / SR / 4, 0.0002)
        g /= np.max(np.abs(g)) + 1e-12
        add_circ(x, int(r.uniform(0, n)), g * r.pareto(2.5) * 0.25)
    for _ in range(int(1.5 * 45)):  # stones hitting the floor
        c = click(r, r.uniform(1400, 3200), 8, 0.006, 0.03) * r.uniform(0.3, 0.8)
        add_circ(x, int(r.uniform(0, n)), c)
    rumble = loop_lp(brown(n, r), 160, 2) * (0.6 + 0.4 * smooth_mod(n, r, 4, 16))
    x = x / np.max(np.abs(x)) + rumble / np.max(np.abs(rumble)) * 0.3
    x = sat(x / np.max(np.abs(x)), 1.4)
    save_loop("gravel", x, "Gravel trap: dense crunchy stone grains, floor hits and rumble.", 30, rms_db=-15)


def grass() -> None:
    r = rng(55)
    n = n_of(2.0)
    bumps = np.abs(smooth_mod(n, r, 3, 12))
    rumble = loop_lp(brown(n, r), 130, 2) * (0.5 + 0.8 * bumps)
    swish = loop_bp(pink(n, r), 1300, 5200, 2) * (0.55 + 0.45 * smooth_mod(n, r, 0.5, 4)) * 0.28
    whirr = loop_bp(white(n, r), 300, 900, 2) * 0.12
    thumps = np.zeros(n)
    for _ in range(12):
        add_circ(thumps, int(r.uniform(0, n)), thud(90, 60, 0.03, 0.12) * r.uniform(0.3, 0.7))
    x = rumble + swish + whirr + thumps * 0.6
    x = sat(x / np.max(np.abs(x)), 1.2)
    save_loop("grass", x, "Grass: soft rumble, bumps and swish.", 25, rms_db=-15)


def wind() -> None:
    r = rng(56)
    n = n_of(3.0)
    base = loop_hp(loop_lp(pink(n, r), 2200, 2), 260, 2)  # little low end: leave that to the engine
    b1 = loop_reson(white(n, r), 720, 2.5) * (0.6 + 0.4 * smooth_mod(n, r, 0.3, 2.0))
    b2 = loop_reson(white(n, r), 1600, 3.5) * (0.5 + 0.5 * smooth_mod(n, r, 0.4, 2.5))
    hiss = loop_bp(white(n, r), 3500, 9000, 2) * 0.10
    buffet = 1 + 0.28 * smooth_mod(n, r, 0.25, 3.0) + 0.08 * smooth_mod(n, r, 6, 14)
    x = (base * 1.0 + b1 * 0.45 + b2 * 0.25 + hiss) * buffet
    save_loop("wind", x, "Air rushing past the cockpit with buffeting (volume rises with speed^2).", 200, rms_db=-15)


def scrape() -> None:
    r = rng(57)
    n = n_of(1.5)
    grind = loop_bp(white(n, r), 1400, 7500, 2)
    stick = np.abs(smooth_mod(n, r, 35, 160))
    grind *= 0.25 + 0.75 * stick / (stick.max() + 1e-9)
    ring = np.zeros(n)
    for f, q, a in ((2270, 35, 1.0), (3610, 40, 0.7), (5150, 45, 0.5), (6880, 50, 0.3), (1130, 25, 0.5)):
        ring += loop_reson(white(n, r), f, q) * a * (0.5 + 0.5 * smooth_mod(n, r, 1, 8))
    rumble = loop_lp(brown(n, r), 140, 2)
    chips = np.zeros(n)
    for _ in range(int(1.5 * 70)):
        chips_click = click(r, r.uniform(2500, 7000), 4, 0.0015, 0.008) * r.uniform(0.2, 0.9)
        add_circ(chips, int(r.uniform(0, n)), chips_click)
    x = grind / np.max(np.abs(grind)) + ring / np.max(np.abs(ring)) * 0.55 + rumble / np.max(np.abs(rumble)) * 0.35 + chips * 0.5
    x = sat(x / np.max(np.abs(x)), 2.0)
    save_loop("scrape", x, "Bodywork grinding along a wall: metallic/carbon scrape with chips.", 40, rms_db=-13)


# ==========================================================================
# Impacts
# ==========================================================================

def impact(level: int) -> None:
    r = rng(60 + level)
    dur = (0.5, 1.0, 1.7)[level - 1]
    n = n_of(dur)
    x = np.zeros(n)
    th = thud((150, 130, 115)[level - 1], (62, 48, 38)[level - 1], (0.06, 0.11, 0.18)[level - 1], dur * 0.8,
              0.025, (1.5, 2.4, 3.4)[level - 1])
    add_at(x, 0, th * 0.75)
    knock = lp(nz(n_of(0.2), r), 700, 2) * env_exp(n_of(0.2), (0.02, 0.03, 0.045)[level - 1], 0.0003)
    add_at(x, 0, knock / np.max(np.abs(knock)) * 0.6)
    # carbon crunch: a burst of cracks that thins out
    crunch_len = (0.05, 0.13, 0.26)[level - 1]
    count = (35, 100, 220)[level - 1]
    for _ in range(count):
        when = r.exponential(crunch_len / 2.5)
        if when > crunch_len * 1.6:
            continue
        m = n_of(r.uniform(0.001, 0.006))
        c = hp(nz(m, r), r.uniform(1200, 3500), 2) * env_exp(m, m / SR / 3, 0.0001)
        c = reson(c, r.uniform(1800, 7000), r.uniform(2, 8)) * 2 + c
        add_at(x, n_of(when), c / (np.max(np.abs(c)) + 1e-12) * r.uniform(0.3, 1.0) * np.exp(-when / crunch_len))
    shatter = bp(nz(n, r), 2000, 9000, 2) * env_exp(n, (0.02, 0.045, 0.08)[level - 1], 0.0005)
    x += shatter / np.max(np.abs(shatter)) * (0.45, 0.6, 0.7)[level - 1]
    # hollow monocoque modes
    body = additive(1.0, n, [(f, a, d) for f, a, d in ((310, 0.5, 0.09), (523, 0.4, 0.06), (871, 0.3, 0.05),
                                                       (1342, 0.2, 0.035), (2093, 0.12, 0.02))], r)
    x += body * env_exp(n, 1.0, 0.001) * (0.25, 0.35, 0.4)[level - 1]
    # debris tail
    tail = (0.2, 0.6, 1.3)[level - 1]
    pieces = (6, 22, 55)[level - 1]
    for _ in range(pieces):
        when = crunch_len * 0.5 + r.exponential(tail / 3)
        if when > dur - 0.05:
            continue
        if r.random() < 0.25:
            c = thud(r.uniform(180, 320), r.uniform(120, 180), 0.02, 0.06) * 0.5
        else:
            c = click(r, r.uniform(2200, 7500), r.uniform(6, 20), r.uniform(0.003, 0.02), 0.06)
        add_at(x, n_of(when), c * r.uniform(0.08, 0.35) * np.exp(-when / tail))
    x = sat(x / np.max(np.abs(x)), (1.4, 1.8, 2.3)[level - 1])
    x = reverb(x, IR_SHORT, 0.12, tail=False)
    names = {1: "light tap", 2: "solid hit", 3: "heavy crash"}
    save(f"impact_{level}", x, f"Wall impact, {names[level]}: thud + carbon crunch + debris.", fin=0.0003, fout=0.06)


# ==========================================================================
# Car systems and start lights
# ==========================================================================

def boost_on() -> None:
    r = rng(70)
    n = n_of(0.75)
    t = tt(n)
    fc = 350 * (3600 / 350) ** np.clip(t / 0.45, 0, 1)
    whoosh = svf_sweep(nz(n, r), fc, 1.6, "bp")
    whoosh *= np.sin(np.pi * np.clip(t / 0.62, 0, 1)) ** 1.2
    f = 220 * (1180 / 220) ** np.clip(t / 0.4, 0, 1) ** 0.8
    ph = phase_of(f, n)
    elec = np.sin(2 * np.pi * ph) + 0.4 * np.sin(4 * np.pi * ph) + 0.3 * np.sin(6 * np.pi * ph) + 0.12 * np.sin(10 * np.pi * ph)
    elec *= np.clip(t / 0.03, 0, 1) * np.exp(-np.maximum(t - 0.35, 0) / 0.14)
    zap = hp(nz(n, r), 4000, 2) * env_exp(n, 0.012, 0.0005) * 0.5
    sub = thud(110, 55, 0.05, 0.25) * 0.5
    x = whoosh / np.max(np.abs(whoosh)) * 0.8 + elec * 0.45 + zap
    add_at(x, 0, sub)
    save("boost_on", x, "Boost engaged: whoosh + rising electric surge (0.75 s).", fout=0.08)


def straight_mode() -> None:
    r = rng(71)
    n = n_of(0.5)
    x = np.zeros(n)
    for when, a, f in ((0.0, 1.0, 1900), (0.055, 0.75, 2600)):
        c = click(r, f, 5, 0.004, 0.03) + 0.6 * click(r, f * 1.7, 9, 0.003, 0.03)
        k = thud(190, 140, 0.012, 0.05)
        add_at(x, n_of(when), mix(c * 0.8, k * 0.7) * a)
    t = tt(n)
    fc = 3200 * (500 / 3200) ** np.clip(t / 0.4, 0, 1)
    air = svf_sweep(nz(n, r), fc, 0.9, "lp") * np.sin(np.pi * np.clip(t / 0.48, 0, 1)) ** 1.5
    x += air / np.max(np.abs(air)) * 0.45
    save("straight_mode", x, "Straight Mode wings open: actuator clack-clack + drag falling away.", fout=0.06)


def battery_empty() -> None:
    r = rng(72)
    n = n_of(0.38)
    t = tt(n)
    f = 950 * (230 / 950) ** np.clip(t / 0.3, 0, 1)
    x = osc("square", f, n) * 0.6 + np.sin(2 * np.pi * phase_of(f, n)) * 0.4
    gate = np.where((t > 0.09) & (t < 0.12), 0.25, 1.0)
    gate = lp(gate, 200, 1)
    x = lp(x, 3500, 2) * gate * env_exp(n, 0.12, 0.003, 0.08)
    add_at(x, 0, thud(140, 60, 0.05, 0.2, drive=0) * 0.35)
    save("battery_empty", x, "Battery depleted: descending electric blip.", fout=0.05)


def lights_beep() -> None:
    n = n_of(0.16)
    x = blip(1046.5, 1046.5, 0.16, 0.08, harmonics=((1, 1.0), (2, 0.25), (3, 0.12)), attack=0.002)
    x *= np.clip((0.16 - tt(n)) / 0.02, 0, 1)
    save("lights_beep", x, "Start light on / countdown tick (C6 beep).", fout=0.01)


def lights_go() -> None:
    r = rng(73)
    n = n_of(0.6)
    t = tt(n)
    x = np.zeros(n)
    for f, a in ((1568.0, 1.0), (2093.0, 0.6), (784.0, 0.35)):
        ph = phase_of(f, n)
        x += a * (np.sin(2 * np.pi * ph) + 0.2 * np.sin(4 * np.pi * ph))
    x *= env_exp(n, 0.28, 0.003, 0.12)
    x += hp(nz(n, r), 5000, 2) * env_exp(n, 0.01) * 0.2
    save("lights_go", x, "Lights out, GO: bright two-tone chord.", fout=0.08)


# ==========================================================================
# UI
# ==========================================================================

def ui() -> None:
    r = rng(80)
    # hover: tiny soft tick
    n = n_of(0.03)
    x = blip(2600, 2300, 0.03, 0.004, attack=0.0008) + click(r, 5200, 3, 0.0008, 0.03) * 0.15
    save("ui_hover", x, "Button hover: tiny soft tick.", hp_hz=300, fin=0.0005, fout=0.008)
    # click
    x = blip(1500, 900, 0.06, 0.012, attack=0.0004, harmonics=((1, 1.0), (2, 0.3))) + click(r, 4200, 2.5, 0.0012, 0.06) * 0.6
    save("ui_click", x, "Button press: snappy click.", hp_hz=150, fin=0.0003, fout=0.01)
    # confirm: rising two-note
    n = n_of(0.32)
    x = np.zeros(n)
    for when, f in ((0.0, hz("E6")), (0.07, hz("B6"))):
        nn = blip(f, f, 0.24, 0.07, attack=0.002, harmonics=((1, 1.0), (2, 0.18), (3, 0.1)))
        add_at(x, n_of(when), nn)
    x = reverb(x, IR_ROOM, 0.12, tail=False)
    save("ui_confirm", x, "Confirm / accept: rising two-note blip.", hp_hz=150, fout=0.05)
    # back: falling two-note, softer
    n = n_of(0.26)
    x = np.zeros(n)
    for when, f in ((0.0, hz("B5")), (0.065, hz("E5"))):
        nn = blip(f, f * 0.98, 0.18, 0.05, attack=0.002, harmonics=((1, 1.0), (2, 0.12)))
        add_at(x, n_of(when), nn)
    save("ui_back", x, "Back / cancel: falling two-note blip.", hp_hz=150, fout=0.05)
    # error: low buzzy double blip
    n = n_of(0.3)
    x = np.zeros(n)
    for when in (0.0, 0.13):
        b = osc("square", 165.0, n_of(0.1)) * 0.6 + osc("square", 169.0, n_of(0.1)) * 0.4
        b = lp(b, 1800, 2) * env_adsr(n_of(0.1), 0.003, 0.05, 0.6, 0.02, 0.085)
        add_at(x, n_of(when), b)
    save("ui_error", x, "Error / not allowed: low buzzy double blip.", hp_hz=60, fout=0.03)
    # toggle: two-stage switch click
    n = n_of(0.07)
    x = np.zeros(n)
    add_at(x, 0, click(r, 2400, 4, 0.002, 0.03) * 0.7)
    add_at(x, n_of(0.018), blip(1900, 1500, 0.05, 0.01, attack=0.0005) * 0.9 + click(r, 3800, 3, 0.0015, 0.05) * 0.5)
    save("ui_toggle", x, "Toggle switch: two-stage click.", hp_hz=150, fin=0.0003, fout=0.01)
    # slider detent
    x = blip(3200, 3000, 0.012, 0.0018, attack=0.0003) + click(r, 6000, 3, 0.0006, 0.012) * 0.3
    save("ui_slider", x, "Slider detent tick (very short).", hp_hz=500, fin=0.0002, fout=0.004)
    # dial: rotary detent, two micro clicks with a small resonance
    n = n_of(0.035)
    x = np.zeros(n)
    add_at(x, 0, click(r, 2200, 10, 0.003, 0.03))
    add_at(x, n_of(0.006), click(r, 3300, 6, 0.002, 0.025) * 0.6)
    save("ui_dial", x, "Rotary dial click.", hp_hz=300, fin=0.0002, fout=0.006)


def equip() -> None:
    r = rng(81)
    n = n_of(0.55)
    x = np.zeros(n)
    clunk = mix(thud(160, 95, 0.05, 0.25, 0.015, 1.5), click(r, 620, 6, 0.04, 0.2) * 0.5, click(r, 1480, 10, 0.03, 0.2) * 0.35)
    add_at(x, 0, clunk)
    for i, when in enumerate((0.13, 0.17, 0.205, 0.235, 0.262)):
        c = click(r, 3600 + 300 * i, 12, 0.006, 0.03) + click(r, 5200, 6, 0.002, 0.03) * 0.5
        add_at(x, n_of(when), c * (0.55 - 0.05 * i))
    lock = mix(click(r, 2600, 14, 0.02, 0.12) * 0.7, thud(220, 160, 0.02, 0.08) * 0.6)
    add_at(x, n_of(0.31), lock)
    x = reverb(x, IR_ROOM, 0.1, tail=False)
    save("equip", x, "Part fitted to the car: clunk + ratchet + lock.", fout=0.05)


def unequip() -> None:
    r = rng(82)
    n = n_of(0.45)
    x = np.zeros(n)
    for i, when in enumerate((0.0, 0.03, 0.058)):
        add_at(x, n_of(when), click(r, 4200 - 300 * i, 12, 0.005, 0.03) * (0.45 + 0.1 * i))
    rel = mix(click(r, 1900, 9, 0.03, 0.2) * 0.7, thud(240, 180, 0.03, 0.12) * 0.55, click(r, 880, 7, 0.05, 0.2) * 0.4)
    add_at(x, n_of(0.09), rel)
    t = tt(n)
    sw = svf_sweep(nz(n, r), 900 + 2500 * np.clip((t - 0.09) / 0.2, 0, 1), 1.2, "bp") * np.exp(-np.maximum(t - 0.12, 0) / 0.06) * (t > 0.09)
    x += sw * 0.15
    x = reverb(x, IR_ROOM, 0.1, tail=False)
    save("unequip", x, "Part removed: ratchet release + lighter clank.", fout=0.05)


# ==========================================================================
# Lap feedback
# ==========================================================================

def lap_feedback() -> None:
    r = rng(90)
    # personal best: bright rising three-note chime
    n = n_of(1.4)
    x = np.zeros(n)
    for when, note in ((0.0, "E6"), (0.085, "G#6"), (0.17, "B6")):
        add_at(x, n_of(when), bell(hz(note), 1.2, r, bright=0.9, decay=0.9) * (0.8 if note != "B6" else 1.0))
    x = reverb(x, IR_ROOM, 0.25, tail=False)
    save("lap_pb", x, "Personal best lap: bright rising three-note chime.", hp_hz=150, fout=0.3)

    # purple (fastest overall): fanfare arpeggio into a big shimmering chord
    n = n_of(2.4)
    x = np.zeros(n)
    arp = ("C6", "E6", "G6", "C7")
    for i, note in enumerate(arp):
        add_at(x, n_of(i * 0.07), bell(hz(note), 1.0, r, 1.0, 0.6) * 0.55)
    chord_t = 0.3
    m = n - n_of(chord_t)
    tt_ = tt(m)
    brass = supersaw([hz("C5"), hz("E5"), hz("G5"), hz("C6")], m / SR, r, 5, 10)
    fc = 600 + 5200 * np.exp(-tt_ / 0.35) + 1200 * np.exp(-tt_ / 1.5)
    brass = svf_sweep(brass, fc, 0.9, "lp") * env_adsr(m, 0.02, 0.4, 0.55, 0.6, 1.1)
    add_at(x, n_of(chord_t), brass * 0.9)
    shimmer = sum(bell(hz(nn), m / SR, r, 1.2, 1.4) for nn in ("G7", "C8", "E7")) * 0.25
    trem = 1 + 0.3 * np.sin(2 * np.pi * 9 * tt_)
    add_at(x, n_of(chord_t), shimmer * trem)
    add_at(x, n_of(chord_t), thud(110, 50, 0.12, 0.5) * 0.6)
    x = reverb(x, IR_HALL, 0.3, tail=False)
    save("lap_purple", x, "Fastest overall (purple): fanfare arpeggio into a shimmering major chord.", hp_hz=40, fout=0.5)

    # sector green: tiny ding
    x = bell(hz("A6"), 0.5, r, 0.6, 0.5)
    x = reverb(x, IR_ROOM, 0.15, tail=False)
    save("sector_green", x, "Sector improved: tiny ding.", hp_hz=200, fout=0.15)

    # lap deleted: low negative buzz
    n = n_of(0.6)
    t = tt(n)
    x = np.zeros(n)
    for when, f in ((0.0, 123.5), (0.2, 110.0)):
        m = n_of(0.34 if when else 0.18)
        b = osc("saw", f, m) * 0.5 + osc("square", f * 1.007, m) * 0.5
        b = lp(b, 1300, 2) * env_adsr(m, 0.004, 0.1, 0.7, 0.05, m / SR - 0.06)
        add_at(x, n_of(when), b)
    x = sat(x / np.max(np.abs(x)), 1.6)
    save("lap_deleted", x, "Lap deleted / track limits: low negative buzz.", hp_hz=50, fout=0.06)

    # verified: crisp stamp + digital sparkle
    n = n_of(1.3)
    x = np.zeros(n)
    stamp = thud(170, 60, 0.04, 0.2, 0.012, 1.8) * 0.9
    slap = lp(nz(n_of(0.1), r), 3500, 2) * env_exp(n_of(0.1), 0.018, 0.0003) * 0.6
    snap = click(r, 3000, 2, 0.0025, 0.04) * 0.7
    add_at(x, 0, stamp)
    add_at(x, 0, slap / np.max(np.abs(slap)) * 0.6)
    add_at(x, 0, snap)
    notes = ("E6", "B6", "E7", "F#7", "B7", "E8")
    for i, nn in enumerate(notes):
        f = hz(nn)
        b = blip(f, f, 0.12, 0.03, attack=0.001, harmonics=((1, 1.0), (3, 0.12)))
        add_at(x, n_of(0.12 + i * 0.032), b * (0.32 - 0.02 * i))
    m = n_of(1.0)
    pad = sum(np.sin(2 * np.pi * hz(nn) * tt(m) + r.random() * 6) for nn in ("B6", "E7", "G#7")) / 3
    pad *= env_adsr(m, 0.05, 0.3, 0.4, 0.3, 0.5) * (1 + 0.4 * np.sin(2 * np.pi * 13 * tt(m)))
    add_at(x, n_of(0.14), pad * 0.18)
    x = delay(x, n_of(0.085), 0.35, 3, 6000, tail=False)
    x = reverb(x, IR_ROOM, 0.15, tail=False)
    save("verified", x, "Lap verified on Solana: crisp stamp + digital sparkle.", hp_hz=30, fout=0.3)


# ==========================================================================
# Pack opening
# ==========================================================================

def crinkle(n: int, r, density: float, lo: float = 2000, hi: float = 9000) -> np.ndarray:
    x = np.zeros(n)
    for _ in range(int(density * n / SR)):
        m = n_of(r.uniform(0.0005, 0.003))
        g = bp(nz(m, r), lo, hi, 1) * env_exp(m, m / SR / 3, 0.00005)
        add_at(x, int(r.uniform(0, n)), g * min(r.pareto(2.0), 3.0) * 0.3)
    return x


def pack() -> None:
    r = rng(100)
    # shake: three shakes of foil + cards rattling
    n = n_of(0.85)
    x = np.zeros(n)
    for i, when in enumerate((0.0, 0.27, 0.54)):
        m = n_of(0.24)
        e = np.sin(np.pi * np.clip(tt(m) / 0.22, 0, 1)) ** 1.5
        foil = crinkle(m, r, 1800) * e
        cards = crinkle(m, r, 300, 700, 2400) * e * 1.4
        thump = thud(140, 90, 0.02, 0.06) * 0.25
        add_at(x, n_of(when), foil + cards)
        add_at(x, n_of(when + 0.11), thump)
    save("pack_shake", x, "Pack shake: foil rustle and cards rattling.", hp_hz=150, fout=0.04)

    # open: tear (crackle accelerating, band rising) then burst
    n = n_of(1.4)
    x = np.zeros(n)
    m = n_of(0.42)
    t = tt(m)
    tear = np.zeros(m)
    pos = 0.0
    while pos < 0.42:
        rate = 120 + 900 * (pos / 0.42) ** 1.5
        mm = n_of(r.uniform(0.0006, 0.002))
        g = hp(nz(mm, r), 1500 + 3500 * pos / 0.42, 1) * env_exp(mm, mm / SR / 3, 0.00005)
        add_at(tear, n_of(pos), g * r.uniform(0.3, 1.0))
        pos += r.exponential(1.0 / rate)
    tear += svf_sweep(nz(m, r), 1200 + 4000 * (t / 0.42) ** 2, 2.0, "bp") * 0.25 * (t / 0.42)
    add_at(x, 0, tear)
    b0 = n_of(0.42)
    mb = n - b0
    tb = tt(mb)
    boom = thud(95, 38, 0.25, mb / SR, 0.05, 1.4)
    whoosh = svf_sweep(nz(mb, r), 5000 * (300 / 5000) ** np.clip(tb / 0.5, 0, 1), 0.8, "lp") * env_exp(mb, 0.18, 0.004)
    sparkle = np.zeros(mb)
    for i in range(10):
        f = hz(("E7", "G#7", "B7", "E8", "C#8")[i % 5]) * (1 + 0.003 * r.standard_normal())
        add_at(sparkle, n_of(0.03 + i * 0.045 + r.uniform(0, 0.02)), bell(f, 0.4, r, 0.5, 0.25) * (0.3 - 0.02 * i))
    add_at(x, b0, boom * 0.8 + whoosh / np.max(np.abs(whoosh)) * 0.6 + sparkle)
    x = reverb(x, IR_ROOM, 0.18, tail=False)
    save("pack_open", x, "Pack open: foil tear, burst and sparkle.", hp_hz=30, fout=0.2)

    # card flip: swish + snap
    n = n_of(0.16)
    t = tt(n)
    sw = svf_sweep(nz(n, r), 1200 + 3500 * np.sin(np.pi * np.clip(t / 0.1, 0, 1)), 1.5, "bp")
    sw *= np.sin(np.pi * np.clip(t / 0.1, 0, 1)) ** 2
    x = sw / np.max(np.abs(sw)) * 0.6
    add_at(x, n_of(0.095), click(r, 3800, 3, 0.002, 0.03) * 0.8 + click(r, 1400, 4, 0.004, 0.03) * 0.4)
    save("card_flip", x, "Card flip: swish + snap.", hp_hz=200, fout=0.02)

    reveals(r)
    coins(r)


def reveals(r) -> None:
    # common: soft pluck chord
    n = n_of(0.9)
    x = np.zeros(n)
    for i, note in enumerate(("A4", "C#5", "E5")):
        add_at(x, n_of(i * 0.012), pluck(hz(note), 0.88, r, 0.25, 0.7, 20) * 0.6)
    x = reverb(x, IR_ROOM, 0.18, tail=False)
    save("reveal_common", x, "Card reveal, common: soft pluck chord.", hp_hz=60, fout=0.2)

    # rare: brighter two-step + shimmer
    n = n_of(1.4)
    x = np.zeros(n)
    for i, note in enumerate(("E5", "A5", "C#6")):
        add_at(x, n_of(i * 0.015), pluck(hz(note), 1.2, r, 0.4, 1.0, 24) * 0.5)
    for i, note in enumerate(("E6", "A6")):
        add_at(x, n_of(0.12 + i * 0.09), bell(hz(note), 1.1, r, 0.8, 0.8) * 0.5)
    x = reverb(x, IR_ROOM, 0.25, tail=False)
    save("reveal_rare", x, "Card reveal, rare: brighter pluck + two chime notes.", hp_hz=60, fout=0.3)

    # epic: short riser into a wide chord hit
    n = n_of(2.2)
    x = np.zeros(n)
    rise_len = 0.35
    m = n_of(rise_len)
    t = tt(m)
    riser = svf_sweep(nz(m, r), 500 + 6000 * (t / rise_len) ** 2, 2.5, "bp") * (t / rise_len) ** 2
    add_at(x, 0, riser / np.max(np.abs(riser)) * 0.45)
    hit = n_of(rise_len)
    mh = n - hit
    th = tt(mh)
    chord = supersaw([hz(nn) for nn in ("D4", "A4", "D5", "F#5", "A5")], mh / SR, r, 5, 16)
    chord = svf_sweep(chord, 500 + 7000 * np.exp(-th / 0.25), 0.8, "lp") * env_adsr(mh, 0.005, 0.35, 0.4, 0.5, 0.9)
    add_at(x, hit, chord * 0.9)
    add_at(x, hit, thud(90, 42, 0.18, 0.6, 0.04, 1.5) * 0.7)
    for i, note in enumerate(("A6", "D7", "F#7")):
        add_at(x, hit + n_of(i * 0.06), bell(hz(note), 1.2, r, 0.9, 0.9) * 0.3)
    x = reverb(x, IR_HALL, 0.28, tail=False)
    save("reveal_epic", x, "Card reveal, epic: riser into a wide chord hit.", hp_hz=35, fout=0.4)

    # legendary: long riser, boom, synth chord + choir swell + shimmering bells
    n = n_of(4.2)
    x = np.zeros(n)
    rise_len = 0.9
    m = n_of(rise_len)
    t = tt(m)
    riser = svf_sweep(nz(m, r), 300 + 7000 * (t / rise_len) ** 2.2, 3.0, "bp") * (t / rise_len) ** 2.5
    f = hz("E3") * 2 ** (2 * (t / rise_len) ** 1.5)
    tone_r = osc("saw", f, m) * (t / rise_len) ** 2 * 0.3
    tone_r = lp(tone_r, 3000, 2)
    add_at(x, 0, riser / np.max(np.abs(riser)) * 0.5 + tone_r)
    hit = n_of(rise_len)
    mh = n - hit
    th = tt(mh)
    add_at(x, hit, thud(80, 34, 0.35, 1.2, 0.05, 1.8) * 0.8)
    crash = hp(nz(mh, r), 3000, 2) * env_exp(mh, 0.6, 0.002)
    add_at(x, hit, crash * 0.12)
    chord_notes = ("E3", "B3", "E4", "G#4", "B4", "E5")
    synth = supersaw([hz(nn) for nn in chord_notes], mh / SR, r, 7, 18)
    synth = svf_sweep(synth, 700 + 6500 * np.exp(-th / 0.5) + 1500 * (th / th[-1]), 0.8, "lp")
    synth *= env_adsr(mh, 0.01, 0.6, 0.55, 0.8, 2.4)
    add_at(x, hit, synth * 0.6)
    add_at(x, hit, choir([hz(nn) for nn in ("E4", "G#4", "B4", "E5")], mh / SR, r) * 0.75)
    bells = np.zeros(mh)
    seq = ("E6", "G#6", "B6", "E7", "G#7", "B7", "E8")
    for i in range(14):
        nn = seq[i % len(seq)]
        add_at(bells, n_of(0.05 + i * 0.11), bell(hz(nn), 1.4, r, 0.9, 0.7) * (0.28 - 0.012 * i))
    add_at(x, hit, bells * (1 + 0.25 * np.sin(2 * np.pi * 7 * th)))
    x = reverb(x, IR_HALL, 0.35, tail=False)
    save("reveal_legendary", x, "Card reveal, legendary: riser, boom, synth chord + choir swell + shimmering bells.",
         hp_hz=30, fout=0.6)


def choir(freqs, seconds: float, r) -> np.ndarray:
    """'Aah' ensemble: detuned pulse voices with vibrato through vowel formants."""
    m = n_of(seconds)
    t = tt(m)
    src = np.zeros(m)
    for f in freqs:
        for v in range(4):
            vib = 1 + 0.006 * np.sin(2 * np.pi * (5.0 + 0.4 * v) * t + r.random() * 6) * np.clip(t / 0.6, 0, 1)
            det = 2 ** ((r.uniform(-9, 9)) / 1200)
            src += osc("pulse", f * det * vib, m, r.random(), pw=0.3)
    src += white(m, r) * 0.08
    out = np.zeros(m)
    for fmt, q, g in ((750, 6, 1.0), (1150, 8, 0.6), (2600, 10, 0.25), (3300, 12, 0.12)):
        out += reson(src, fmt, q) * g
    env = env_adsr(m, 0.6, 0.8, 0.8, 1.0, seconds - 1.0)
    out = out * env
    return out / (np.max(np.abs(out)) + 1e-12)


def coins(r) -> None:
    n = n_of(1.0)
    x = np.zeros(n)
    when = 0.0
    for i in range(14):
        f0 = r.uniform(2300, 4300)
        m = n_of(0.3)
        c = additive(f0, m, [(1.0, 1.0, r.uniform(0.06, 0.18)), (2.41, 0.6, 0.07), (4.22, 0.35, 0.04),
                             (6.44, 0.2, 0.025), (0.62, 0.25, 0.05)], r)
        c *= env_exp(m, 10.0, 0.0003)
        add_at(x, n_of(when), c * r.uniform(0.35, 0.9) * (1.0 if i < 8 else 0.6))
        when += r.uniform(0.02, 0.07) * (1 + i * 0.08)
        if when > 0.7:
            break
    x += crinkle(n, r, 250, 3000, 9000) * env_exp(n, 0.25) * 0.4
    x = reverb(x, IR_ROOM, 0.15, tail=False)
    save("coins", x, "Coins: cascading metallic clinks.", hp_hz=400, fout=0.15)


def main() -> None:
    tyre_squeal()
    lockup()
    kerb()
    gravel()
    grass()
    wind()
    scrape()
    for lv in (1, 2, 3):
        impact(lv)
    boost_on()
    straight_mode()
    battery_empty()
    lights_beep()
    lights_go()
    ui()
    equip()
    unequip()
    lap_feedback()
    pack()


if __name__ == "__main__":
    main()
