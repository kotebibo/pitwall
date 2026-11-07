"""Race mode: start lights, grid and grandstand crowds, pit stop, race feedback, car contact.

    python tools/audio/gen_race.py

Crowds are many synthetic voices. Each voice is a glottal-like source (band-
limited saw, spectral tilt, breath noise) whose syllables are routed to one of
a few vowel buses; each bus is then filtered once through its formants, so a
few hundred voices cost a few dozen filters. Shouts glide between vowels
("yeah", "wooo"), chatter changes vowel per syllable with a few consonants.
Loops (grid_ambience, crowd_loop) are rendered circularly like everything else.
The engine and music building blocks come from gen_engine and gen_music.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

import numpy as np
from scipy import ndimage

import gen_engine as eng
from dsp import (SR, add_at, add_circ, additive, bp, env_adsr, env_exp, finish_loop, hp, hz, loop_bp, loop_lp, loop_peak, loop_reson,
                 loop_reverb, lp, n_of, osc, peak, phase_of, pink, reson, reverb, rng, sat, smooth_mod, svf_sweep,
                 tt, write_wav)
from gen_sfx import save
from instruments import IR_HALL, IR_ROOM, IR_SHORT, bell, blip, click, mix, nz, thud


def _norm(x: np.ndarray) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-12)


def save_bed(name: str, x: np.ndarray, desc: str, hp_hz: float, rms_db: float) -> None:
    """Like gen_sfx.save_loop, for dense ambiences: start in the quietest 40 ms on the gentlest
    upward zero crossing there (the loop is circular either way; this keeps a restart soft)."""
    y = finish_loop(x, -3.0, hp_hz, rms_db=rms_db, rotate=False)
    n, w = len(y), n_of(0.04)
    c = int(np.argmin(ndimage.uniform_filter1d(y * y, size=w, mode="wrap")))
    idx = np.arange(c - w // 2, c + w // 2) % n
    prev = y[idx - 1]  # index -1 wraps to the end
    up = idx[(prev <= 0) & (y[idx] > 0)]
    if len(up):
        y = np.roll(y, -int(up[np.argmin(y[up] - y[up - 1])]))
    write_wav(name, y, loop=True, desc=desc)


# ==========================================================================
# Voices and crowds
# ==========================================================================

# First three formants (Hz) of an adult male voice; female voices are scaled up 17 %.
VOWELS = {"a": (730, 1090, 2440), "e": (530, 1840, 2480), "i": (300, 2250, 2950), "o": (570, 840, 2410),
          "u": (330, 900, 2250), "ae": (660, 1720, 2410), "uh": (640, 1190, 2390)}
TALK_VOWELS = list(VOWELS)
SHOUTS = (("i", "e", "a"), ("u", "o", "u"), ("a",), ("a", "uh"), ("e", "i"), ("o", "u"), ("ae", "a"))


class Crowd:
    """Collects voice segments per (vowel, female) bus and filters each bus once."""

    def __init__(self, n: int, loop: bool, shout: float):
        self.n, self.loop, self.shout = n, loop, shout
        self.bus: dict = {}
        self.dry = np.zeros(n)  # consonants (no formants)

    def put(self, buf: np.ndarray, at: int, sig: np.ndarray) -> None:
        (add_circ if self.loop else add_at)(buf, int(at), sig)

    def vowel(self, v: str, female: bool, at: int, sig: np.ndarray) -> None:
        if (v, female) not in self.bus:
            self.bus[(v, female)] = np.zeros(self.n)
        self.put(self.bus[(v, female)], at, sig)

    def render(self) -> np.ndarray:
        out = np.zeros(self.n)
        for (v, female), b in self.bus.items():
            k = 1.17 if female else 1.0
            f1, f2, f3 = VOWELS[v]
            # shouting raises F1 (wider jaw) and a little F2
            fs = (f1 * k * (1 + 0.2 * self.shout), f2 * k * (1 + 0.06 * self.shout), f3 * k)
            for f, g, bw in zip(fs, (1.0, 0.6, 0.3), (90.0, 120.0, 170.0)):
                q = f / (bw * (1 + 0.4 * self.shout))
                out += g * (loop_reson(b, f, q) if self.loop else reson(b, f, q))
        return out + self.dry


def drift(m: int, r, fc: float) -> np.ndarray:
    """Smooth random wobble, peak 1, content below fc Hz."""
    pre = n_of(0.5)
    x = lp(r.standard_normal(m + pre), fc, 2)[pre:]
    return _norm(x)


def source(r, f: np.ndarray, effort: float) -> np.ndarray:
    """Voice source for a pitch contour: saw with glottal tilt, breath and shimmer."""
    m = len(f)
    x = _norm(lp(osc("saw", f, m, r.random()), 700 + 1600 * effort, 1))
    breath = hp(r.standard_normal(m), 1200, 1) * (0.05 + 0.12 * effort)
    return (x + breath) * (1 + 0.08 * drift(m, r, 40))


def talk(cr: Crowd, r, at: int, dur: float, f0: float, female: bool, gain: float,
         rate: float = 4.5, cons: float = 0.45) -> None:
    """Conversational speech: syllables at ~rate/s, a vowel each, declining pitch with accents."""
    m = n_of(dur)
    t = tt(m)
    sylls = []
    pos = 0.0
    while pos < dur - 0.06:
        ln = min(r.uniform(0.55, 1.45) / rate, dur - pos)
        sylls.append((pos, ln))
        pos += ln
        if r.random() < 0.18:
            pos += r.uniform(0.06, 0.3)  # word or breath gap
    f = f0 * (1.1 - 0.18 * t / dur) * (1 + 0.04 * drift(m, r, 3))
    for s0, ln in sylls:
        if r.random() < 0.35:  # stressed syllable
            a, b = n_of(s0), min(m, n_of(s0 + ln))
            f[a:b] *= 1 + r.uniform(0.06, 0.16) * np.sin(np.pi * np.linspace(0, 1, b - a))
    src = source(r, f, 0.0) * gain
    for s0, ln in sylls:
        a, b = n_of(s0), min(m, n_of(s0 + ln))
        if b - a < 16:
            continue
        env = np.sin(np.pi * np.linspace(0, 1, b - a)) ** 0.7 * r.uniform(0.6, 1.0)
        cr.vowel(TALK_VOWELS[int(r.integers(len(TALK_VOWELS)))], female, at + a, src[a:b] * env)
        if r.random() < cons:
            cm = n_of(r.uniform(0.02, 0.06))
            fric = hp(r.standard_normal(cm), r.uniform(2500, 5000), 2) * np.sin(np.pi * np.linspace(0, 1, cm)) ** 2
            cr.put(cr.dry, at + a - cm // 2, fric * gain * 0.18)


def shout(cr: Crowd, r, at: int, dur: float, f0: float, female: bool, gain: float) -> None:
    """A sustained cheer ("yeah", "wooo", "aah"): scoop up, arc, fall away, vowel glide."""
    m = n_of(dur)
    t = tt(m)
    seq = SHOUTS[int(r.integers(len(SHOUTS)))]
    f = f0 * (1 - 0.18 * np.exp(-t / 0.06))  # scoop into the note
    f = f * (1 + r.uniform(0.0, 0.12) * np.sin(np.pi * np.clip(t / dur, 0, 1)))
    f = f * (1 - r.uniform(0.05, 0.2) * np.clip((t - 0.7 * dur) / (0.3 * dur), 0, 1) ** 2)
    f = f * (1 + 0.012 * np.sin(2 * np.pi * r.uniform(4.5, 6.5) * t + r.random() * 6)) * (1 + 0.02 * drift(m, r, 6))
    src = source(r, f, 1.0)
    att, rel = r.uniform(0.02, 0.07), r.uniform(0.12, 0.3)
    env = np.clip(t / att, 0, 1) * np.clip((dur - t) / rel, 0, 1) ** 1.5 * (0.85 + 0.15 * drift(m, r, 4))
    sig = src * env * gain
    if len(seq) == 1:
        cr.vowel(seq[0], female, at, sig)
        return
    pos = np.clip(t / (dur * 0.6) * (len(seq) - 1), 0, len(seq) - 1)  # glide over the first 60 %
    for i, v in enumerate(seq):
        w = np.clip(1 - np.abs(pos - i), 0, 1)
        cr.vowel(v, female, at, sig * w)


def applause(n: int, r, count: int, loop: bool, window: tuple[int, int] | None = None) -> np.ndarray:
    """count claps (hand-cavity resonance on a short noise burst), spread over window."""
    out = np.zeros(n)
    lo, hi = window if window else (0, n)
    for _ in range(count):
        m = n_of(r.uniform(0.006, 0.014))
        c = r.standard_normal(m) * np.exp(-tt(m) / r.uniform(0.0012, 0.003))
        c = reson(c, r.uniform(700, 2600), r.uniform(1.5, 4)) * 1.5 + hp(c, 2000, 1) * 0.4
        (add_circ if loop else add_at)(out, int(r.uniform(lo, hi)), c * min(r.pareto(3.0) + 0.3, 2.5))
    return out


def whistle(r, dur: float, f0: float) -> np.ndarray:
    """Finger whistle: glides up into the note, warbles, sags at the end."""
    m = n_of(dur)
    t = tt(m)
    f = f0 * (0.9 + 0.1 * (1 - np.exp(-t / 0.05))) * (1 + 0.012 * np.sin(2 * np.pi * r.uniform(5, 9) * t))
    f = f * (1 - 0.06 * np.clip((t - 0.7 * dur) / (0.3 * dur), 0, 1))
    ph = phase_of(f, m)
    x = np.sin(2 * np.pi * ph) + 0.06 * np.sin(4 * np.pi * ph)
    air = bp(r.standard_normal(m), f0 * 0.8, f0 * 1.25, 2) * 0.12
    return (x + air) * np.clip(t / 0.025, 0, 1) * np.clip((dur - t) / 0.06, 0, 1)


def roar(n: int, r, loop: bool) -> np.ndarray:
    """Thousands of voices at once: noise shaped like a shouting crowd."""
    x = pink(n, r)
    if loop:
        x = loop_bp(x, 250, 3500, 2)
        for f, g in ((650, 5.0), (1150, 4.0), (2500, 3.0)):
            x = loop_peak(x, f, 1.2, g)
    else:
        x = bp(x, 250, 3500, 2)
        for f, g in ((650, 5.0), (1150, 4.0), (2500, 3.0)):
            x = peak(x, f, 1.2, g)
    return _norm(x)


def cheer_voices(cr: Crowd, r, count: int, onset, dur_range=(0.6, 2.2), end: float = 99.0) -> None:
    """count shouting voices whose start times come from onset(r)."""
    for _ in range(count):
        start = onset(r)
        if start > end - 0.3:
            continue
        d = min(r.uniform(*dur_range), end - start)
        female = r.random() < 0.35
        f0 = r.uniform(280, 520) if female else r.uniform(150, 330)
        shout(cr, r, n_of(start), d, f0, female, r.uniform(0.3, 1.0) * np.exp(-start / 2.5))


def chatter(cr: Crowd, r, n: int, per_s: float) -> None:
    """Conversations all over a loop of n samples."""
    for _ in range(int(n / SR * per_s)):
        female = r.random() < 0.4
        f0 = r.uniform(170, 260) if female else r.uniform(95, 150)
        talk(cr, r, int(r.uniform(0, n)), r.uniform(0.6, 2.6), f0, female, r.uniform(0.2, 1.0))


# ==========================================================================
# Start
# ==========================================================================

def start_light() -> None:
    r = rng(600)
    n = n_of(0.5)
    x = np.zeros(n)
    # the light module's contactor clunks in
    add_at(x, 0, thud(120, 58, 0.035, 0.2, 0.012, 1.4) * 0.55)
    add_at(x, 0, click(r, 1700, 6, 0.004, 0.03) * 0.5 + click(r, 3400, 10, 0.002, 0.03) * 0.25)
    m = n_of(0.04)
    add_at(x, 0, reson(nz(m, r), 760, 14) * env_exp(m, 0.008) * 0.4)  # housing ring
    # a short burst of mains buzz as the lamps energise
    m = n_of(0.16)
    buzz = lp(osc("square", 100.0, m) * 0.6 + osc("saw", 200.0, m) * 0.3, 1800, 2) * env_exp(m, 0.045, 0.002)
    add_at(x, n_of(0.004), buzz * 0.35)
    m = n_of(0.012)
    add_at(x, n_of(0.002), hp(nz(m, r), 5000, 2) * env_exp(m, 0.0015) * 0.25)
    # the beep
    b = blip(880.0, 880.0, 0.17, 0.09, harmonics=((1, 1.0), (2, 0.18), (3, 0.22)), attack=0.003)
    b *= np.clip((0.17 - tt(len(b))) / 0.02, 0, 1)
    add_at(x, n_of(0.012), b * 1.0)
    x = reverb(x, IR_ROOM, 0.1, tail=False)
    save("start_light", x, "One red start light on: low electric clunk + mains buzz + A5 beep.", hp_hz=35, fout=0.05)


def start_go() -> None:
    r = rng(610)
    dur = 2.7
    n = n_of(dur)
    t = tt(n)
    x = np.zeros(n)
    # lights out: the contactors drop out (softer than the light-on clunk)
    add_at(x, 0, mix(click(r, 1500, 5, 0.003, 0.03) * 0.3, thud(95, 60, 0.02, 0.08) * 0.25))
    # whoosh: the field launching away
    fc = np.where(t < 0.45, 300 * (3600 / 300) ** np.clip(t / 0.45, 0, 1), 3600 * (900 / 3600) ** np.clip((t - 0.45) / 0.8, 0, 1))
    wh = svf_sweep(nz(n, r), fc, 1.4, "bp") * np.clip(t / 0.4, 0, 1) ** 1.5 * np.exp(-np.maximum(t - 0.45, 0) / 0.3)
    x += _norm(wh) * 0.55
    # stinger: sub drop and a bright, airy swell
    add_at(x, n_of(0.03), thud(75, 34, 0.25, 1.2, 0.06, 1.3) * 0.7)
    m = n_of(1.3)
    tm = tt(m)
    shim = sum(np.sin(2 * np.pi * hz(nn) * tm + r.random() * 6) for nn in ("E5", "B5", "E6", "G#6")) / 4
    shim *= np.clip(tm / 0.12, 0, 1) * np.exp(-tm / 0.4) * (1 + 0.25 * np.sin(2 * np.pi * 11 * tm))
    add_at(x, n_of(0.05), shim * 0.3)
    # the crowd lifts
    cr = Crowd(n, False, 0.9)
    cheer_voices(cr, r, 110, lambda rr: 0.12 + rr.exponential(0.3), (0.6, 1.8), dur)
    crowd = _norm(cr.render())
    swell = np.clip((t - 0.1) / 0.6, 0, 1) ** 1.2 * np.clip((dur - t) / 1.5, 0, 1) ** 1.3
    crowd = crowd * 0.8 + roar(n, r, False) * swell * 0.45 + _norm(applause(n, r, 600, False, (n_of(0.25), n_of(2.0)))) * swell * 0.2
    crowd = reverb(lp(crowd, 6500, 2), IR_HALL, 0.3, tail=False)
    x += _norm(crowd) * 0.6
    save("start_go", x, "Lights out: contactor release, whoosh, sub drop and airy stinger as the crowd lifts.",
         hp_hz=30, fout=0.4)


def crowd_cheer() -> None:
    r = rng(500)
    dur = 3.0
    n = n_of(dur)
    t = tt(n)
    cr = Crowd(n, False, 1.0)
    cheer_voices(cr, r, 180, lambda rr: rr.exponential(0.12) if rr.random() < 0.75 else rr.uniform(0.1, 1.5),
                 (0.6, 2.2), dur)
    voices = _norm(cr.render())
    env = np.clip(t / 0.12, 0, 1) ** 0.8 * (0.75 + 0.25 * np.exp(-t / 0.6)) * np.clip((dur - t) / 1.6, 0, 1) ** 1.3
    claps = _norm(applause(n, r, 1400, False, (n_of(0.05), n_of(2.6))))
    claps *= np.clip(t / 0.25, 0, 1) * np.clip((dur - t) / 1.8, 0, 1)
    wh = np.zeros(n)
    for _ in range(8):
        start = r.uniform(0.1, 1.6)
        add_at(wh, n_of(start), whistle(r, r.uniform(0.35, 1.0), r.uniform(2100, 3400)) * r.uniform(0.4, 1.0))
    x = voices + roar(n, r, False) * env * 0.5 + claps * 0.35 + _norm(wh) * 0.2
    x = lp(x, 7500, 2)
    x = reverb(x, IR_HALL, 0.28, tail=False)
    save("crowd_cheer", x, "Big crowd cheer (3 s): shouting voices, roar, applause and whistles.", hp_hz=80, fout=0.5)


def crowd_loop() -> None:
    r = rng(510)
    n = n_of(8.0)
    cr = Crowd(n, True, 0.25)
    chatter(cr, r, n, 30)
    for _ in range(6):  # a few raised voices across the stand
        shout(cr, r, int(r.uniform(0, n)), r.uniform(0.4, 1.0), r.uniform(200, 380), r.random() < 0.4, r.uniform(0.3, 0.6))
    v = _norm(cr.render())
    bed = _norm(loop_bp(pink(n, r), 250, 2200, 2)) * (0.8 + 0.2 * smooth_mod(n, r, 0.1, 0.6))
    claps = np.zeros(n)
    for _ in range(3):  # little patches of applause
        a = int(r.uniform(0, n))
        claps += applause(n, r, int(r.uniform(10, 25)), True, (a, a + n_of(r.uniform(0.6, 1.4))))
    wh = np.zeros(n)
    for _ in range(2):
        add_circ(wh, int(r.uniform(0, n)), whistle(r, r.uniform(0.3, 0.6), r.uniform(2200, 3200)))
    x = v + bed * 0.35 + _norm(claps) * 0.15 + wh * 0.05
    x = loop_lp(x, 3200, 2)
    x = loop_reverb(x, IR_HALL, 0.45, 1.0)
    save_bed("crowd_loop", x, "Grandstand crowd loop: distant chatter, the odd shout, clap and whistle (quiet bed).",
              80, rms_db=-16)


def pa_voice(n: int, r) -> np.ndarray:
    """A distant PA announcer: speech through horn speakers along the straight, echoing."""
    cr = Crowd(n, True, 0.35)
    pos = r.uniform(0.3, 0.8)
    secs = n / SR
    while pos < secs - 1.0:
        d = r.uniform(1.4, 2.6)
        talk(cr, r, n_of(pos), d, r.uniform(105, 125), False, 1.0, rate=5.2, cons=0.6)
        pos += d + r.uniform(0.25, 0.6)
        if r.random() < 0.3:
            pos += r.uniform(1.0, 2.0)
    v = _norm(cr.render())
    v = loop_bp(v, 380, 3800, 2)
    v = loop_peak(v, 1800, 1.2, 6.0)
    v = sat(_norm(v) * 1.5, 2.0)
    y = v.copy()
    for d, g, fc in ((0.19, 0.55, 3200), (0.43, 0.38, 2400), (0.78, 0.25, 1800), (1.21, 0.14, 1400)):
        y += np.roll(loop_lp(v, fc, 2), n_of(d)) * g  # the next speaker towers down the straight
    y = loop_reverb(y, IR_HALL, 0.6, 0.6)
    return _norm(y)


def grid_ambience() -> None:
    r = rng(520)
    n = n_of(10.0)  # 441000 = 2^3 3^2 5^3 7^2: many whole-cycle idle speeds fit
    t = tt(n)
    # idling cars around the grid (samples per engine cycle, level, distance lowpass)
    cars = ((1260, 0.55, 2400), (1176, 0.35, 1600), (1225, 0.30, 1300), (1400, 0.22, 1000),
            (1125, 0.18, 900), (1470, 0.14, 800))
    engines = np.zeros(n)
    for i, (nc, g, fc) in enumerate(cars):
        assert n % nc == 0
        x = eng.engine_render(dict(eng.IDLE, seed=530 + i), nc, n // nc, time_mod=eng.hunt(540 + i, 0.025, 0.4, 2.0))
        engines += loop_lp(_norm(x), fc, 2) * g * (1 + 0.15 * smooth_mod(n, r, 0.1, 0.5))
    # the grandstands
    cr = Crowd(n, True, 0.2)
    chatter(cr, r, n, 26)
    crowd = loop_lp(_norm(cr.render()), 2400, 2)
    bed = _norm(loop_bp(pink(n, r), 200, 1800, 2)) * (0.8 + 0.2 * smooth_mod(n, r, 0.1, 0.5))
    crowd = loop_reverb(crowd + bed * 0.5, IR_HALL, 0.6, 1.0)
    pa = pa_voice(n, r)
    # tyre-blanket generators and a breath of wind
    hum = sum(a * np.sin(2 * np.pi * f * t + r.random() * 6) for f, a in ((100, 1.0), (150, 0.4), (200, 0.5), (300, 0.2)))
    hum = _norm(hum) * (0.85 + 0.15 * smooth_mod(n, r, 0.2, 1.0))
    wind = _norm(loop_lp(pink(n, r), 500, 2)) * (0.6 + 0.4 * smooth_mod(n, r, 0.1, 0.4))
    x = _norm(engines) * 1.0 + _norm(crowd) * 0.55 + pa * 0.16 + hum * 0.02 + wind * 0.08
    save_bed("grid_ambience", x, "Grid ambience loop: cars idling around you, grandstand murmur, distant PA, generators.",
              30, rms_db=-16)


# ==========================================================================
# Pit stop
# ==========================================================================

def pit_limiter_on() -> None:
    n = n_of(0.16)
    x = np.zeros(n)
    for when, f, ln in ((0.0, 1244.5, 0.06), (0.065, 1661.2, 0.075)):
        b = blip(f, f, ln, 0.2, harmonics=((1, 1.0), (3, 0.3), (5, 0.12)), attack=0.002)
        b *= np.clip((ln - tt(len(b))) / 0.008, 0, 1)
        add_at(x, n_of(when), b)
    save("pit_limiter_on", x, "Pit limiter engaged: short two-step dash beep.", hp_hz=200, fout=0.01)


def wheel_gun() -> None:
    r = rng(630)
    dur = 0.36
    n = n_of(dur)
    t = tt(n)
    t_on, t_off, t_hit = 0.012, 0.29, 0.15
    # air motor: spins up, bogs as the nut seats, winds down when the trigger is let go
    spin = np.clip((t - t_on) / 0.025, 0, 1) ** 0.7 * np.where(t < t_off, 1.0, np.exp(-(t - t_off) / 0.02))
    bog = 1 - 0.14 * np.clip((t - t_hit) / 0.1, 0, 1)
    f = 1450 * (0.45 + 0.55 * spin) * bog * (1 + 0.01 * np.sin(2 * np.pi * 70 * t))
    ph = phase_of(f, n)
    motor = sum(a * np.sin(2 * np.pi * k * ph) for k, a in ((1, 1.0), (2, 0.5), (3, 0.3), (5, 0.18), (7, 0.1)))
    motor *= spin
    air = bp(nz(n, r), 2500, 10000, 2) * spin
    # hammer: a light clutch rattle while spinning free, then heavy blows as it torques up
    bursts = np.zeros(n)
    knocks = np.zeros(n)
    dips = np.zeros(n)
    tb = t_on + 0.03
    while tb < t_off:
        heavy = tb >= t_hit
        a = (0.55 + 0.45 * min((tb - t_hit) / 0.1, 1.0)) if heavy else 0.25
        a *= r.uniform(0.85, 1.15)
        m = n_of(0.006)
        add_at(bursts, n_of(tb), r.standard_normal(m) * np.exp(-tt(m) / 0.0015) * a)
        add_at(dips, n_of(tb), np.exp(-tt(n_of(0.02)) / 0.005) * a)
        if heavy:
            add_at(knocks, n_of(tb), thud(330, 250, 0.006, 0.03, 0.003, 0) * a)
        tb += 1.0 / (r.uniform(58, 64) if heavy else r.uniform(105, 115))
    clack = sum(reson(bursts, f_, q) * g for f_, q, g in ((2400, 8, 1.0), (3900, 10, 0.8), (6100, 12, 0.6), (8200, 12, 0.35)))
    clack += hp(bursts, 2000, 2) * 0.3
    ring = sum(reson(bursts, f_, q) * g for f_, q, g in ((1270, 90, 0.5), (2210, 110, 0.35), (3420, 130, 0.25)))
    # every blow loads the motor and chokes the air for a moment: that flutter is the rattle
    load = 1 - 0.7 * np.clip(dips, 0, 1)
    body = sat(_norm(motor * load) * 0.55 + _norm(air * load) * 0.4, 1.2)
    x = _norm(body) * 0.45 + _norm(clack) * 1.0 + _norm(knocks) * 0.6 + _norm(ring) * 0.2
    x = reverb(x, IR_SHORT, 0.15, tail=False)
    save("wheel_gun", x, "Wheel gun: air motor whine, clutch rattle, then hammering blows as the nut torques up (0.36 s).",
         hp_hz=120, fout=0.03)


def jack_up() -> None:
    r = rng(640)
    n = n_of(0.6)
    t = tt(n)
    x = np.zeros(n)
    # jack nose meets the chassis
    add_at(x, 0, thud(160, 90, 0.04, 0.2, 0.012, 1.4) * 0.8)
    add_at(x, 0, mix(click(r, 900, 8, 0.01, 0.06) * 0.45, click(r, 2300, 5, 0.004, 0.03) * 0.35))
    # pneumatic lift
    m = n_of(0.3)
    tm = tt(m)
    hiss = bp(nz(m, r), 2000, 7000, 2) * np.clip(tm / 0.02, 0, 1) * np.exp(-tm / 0.11)
    add_at(x, n_of(0.03), _norm(hiss) * 0.5)
    lift = lp(nz(n_of(0.25), r), 200, 2) * np.sin(np.pi * np.clip(tt(n_of(0.25)) / 0.25, 0, 1))
    add_at(x, n_of(0.04), _norm(lift) * 0.35)
    # latch at the top, and the car settling on it
    add_at(x, n_of(0.21), mix(click(r, 2800, 10, 0.006, 0.04) * 0.55, thud(220, 150, 0.015, 0.06) * 0.4))
    add_at(x, n_of(0.24), thud(110, 70, 0.04, 0.15) * 0.3)
    x = reverb(x, IR_SHORT, 0.15, tail=False)
    save("jack_up", x, "Jack up: nose clunk, pneumatic hiss as the car lifts, latch click.", hp_hz=40, fout=0.06)


def jack_down() -> None:
    r = rng(641)
    n = n_of(0.65)
    x = np.zeros(n)
    # release valve and air dump
    add_at(x, 0, click(r, 2100, 6, 0.004, 0.03) * 0.5)
    m = n_of(0.35)
    tm = tt(m)
    dump = bp(nz(m, r), 1200, 8000, 2) * np.clip(tm / 0.006, 0, 1) * np.exp(-tm / 0.09)
    add_at(x, n_of(0.005), _norm(dump) * 0.6)
    # the car drops onto its tyres: heavy thud, carbon rattle, a small bounce
    add_at(x, n_of(0.06), thud(120, 48, 0.09, 0.4, 0.02, 1.7) * 0.9)
    add_at(x, n_of(0.06), reson(nz(n_of(0.08), r), 260, 3) * env_exp(n_of(0.08), 0.02) * 0.4)  # tyre squash
    for i in range(10):
        add_at(x, n_of(0.065 + r.exponential(0.03)), click(r, r.uniform(1800, 5000), r.uniform(5, 12), 0.003, 0.02)
               * r.uniform(0.1, 0.3))
    add_at(x, n_of(0.19), thud(100, 60, 0.04, 0.15) * 0.3)
    x = reverb(x, IR_SHORT, 0.15, tail=False)
    save("jack_down", x, "Jack down: release click, air dump and the car dropping onto its tyres.", hp_hz=35, fout=0.06)


def tyre_drop() -> None:
    r = rng(650)
    n = n_of(0.5)
    x = np.zeros(n)
    for when, a in ((0.0, 1.0), (0.14, 0.32), (0.235, 0.11)):
        add_at(x, n_of(when), thud(118, 70, 0.07, 0.25, 0.02, 1.3) * a)
        m = n_of(0.08)
        rub = reson(nz(m, r), 330, 4) * env_exp(m, 0.03, 0.001)
        add_at(x, n_of(when), _norm(rub) * 0.45 * a)
        m = n_of(0.01)
        slap = bp(nz(m, r), 500, 3000, 2) * env_exp(m, 0.002)
        add_at(x, n_of(when), _norm(slap) * 0.25 * a)
    m = n_of(0.25)
    add_at(x, 0, reson(nz(m, r), 1900, 40) * env_exp(m, 0.06) * 0.08)  # the rim rings faintly
    save("tyre_drop", x, "Tyre and rim dropped on the pit lane: rubbery thud with two small bounces.", hp_hz=40, fout=0.05)


def pit_release() -> None:
    r = rng(660)
    dur = 1.3
    n = n_of(dur)
    t = tt(n)
    x = np.zeros(n)
    # the "go" beep
    b = blip(1760.0, 1760.0, 0.13, 0.1, harmonics=((1, 1.0), (2, 0.15), (3, 0.2)), attack=0.002)
    b *= np.clip((0.13 - tt(len(b))) / 0.015, 0, 1)
    add_at(x, 0, b * 0.8)
    launch = 0.13

    def rpm(s: float) -> float:
        if s < launch:
            return 4200.0
        base = 4200 + 4800 * (1 - np.exp(-(s - launch) / 0.12))
        return base * (1 + 0.015 * np.sin(2 * np.pi * 4 * s)) if s > 0.5 else base

    def amp(s: float) -> float:
        a = 0.22 if s < launch else 1.0
        if s > 0.5 and ((s - 0.5) * 4) % 1.0 > 0.62:  # bouncing off the limiter
            a *= 0.1
        return a * float(np.clip((dur - 0.05 - s) / 0.45, 0, 1))

    rev = eng.colour_oneshot(eng.sweep_train(rpm, amp, dur, 661), eng.PIT, 662)
    x += _norm(rev) * 0.85
    # clutch bite and a little wheelspin chirp
    add_at(x, n_of(launch), thud(90, 60, 0.03, 0.12) * 0.3)
    m = n_of(0.25)
    tm = tt(m)
    chirp = np.sin(2 * np.pi * phase_of(1150 * (1 + 0.04 * np.sin(2 * np.pi * 23 * tm)), m))
    chirp = (chirp + bp(nz(m, r), 800, 4000, 2) * 0.3) * np.clip(tm / 0.02, 0, 1) * np.exp(-tm / 0.07)
    add_at(x, n_of(launch + 0.01), chirp * 0.18)
    save("pit_release", x, "Pit release: go beep, then the engine revs out of the box and bounces off the pit limiter.",
         hp_hz=30, fout=0.08)


def pit_radio() -> None:
    r = rng(670)
    n = n_of(0.32)
    x = np.zeros(n)
    # press-to-talk click
    add_at(x, 0, click(r, 1200, 2.5, 0.0015, 0.02) * 0.9)
    add_at(x, 0, thud(180, 120, 0.006, 0.03, drive=0) * 0.4)
    # static burst through a narrow, digitised radio channel
    m = n_of(0.27)
    tm = tt(m)
    s = bp(nz(m, r), 350, 3200, 3) * (1 + 0.5 * drift(m, r, 35))
    s = sat(_norm(s) * 2.5, 2.5)
    s = np.repeat(s[::5], 5)[:m]  # ~8.8 kHz sample and hold
    s = np.round(s * 24) / 24  # coarse quantiser
    s = bp(s, 300, 3400, 2)
    env = np.clip(tm / 0.006, 0, 1) * (0.25 + 0.75 * np.exp(-tm / 0.05)) * np.clip((0.27 - tm) / 0.05, 0, 1)
    add_at(x, n_of(0.006), _norm(s) * env * 0.75)
    save("pit_radio", x, "Team radio opens: press-to-talk click and a burst of digital static (put before engineer lines).",
         hp_hz=200, fout=0.03)


# ==========================================================================
# Race feedback and contact
# ==========================================================================

def overtake() -> None:
    r = rng(680)
    n = n_of(0.75)
    x = np.zeros(n)
    for when, nn, a in ((0.0, "D6", 0.75), (0.075, "A6", 1.0)):
        add_at(x, n_of(when), bell(hz(nn), 0.65, r, 0.5, 0.45) * a)
    m = n_of(0.18)
    tm = tt(m)
    sw = svf_sweep(nz(m, r), 1500 + 4500 * (tm / 0.18), 2.0, "bp") * np.sin(np.pi * tm / 0.18) ** 2
    add_at(x, 0, _norm(sw) * 0.12)
    x = reverb(x, IR_ROOM, 0.18, tail=False)
    save("overtake", x, "Position gained: soft rising D6-A6 chime.", hp_hz=200, fout=0.2)


def position_lost() -> None:
    n = n_of(0.6)
    t = tt(n)
    f = hz("E4") * (1 - 0.06 * np.clip((t - 0.08) / 0.4, 0, 1))  # sags a semitone
    ph = phase_of(f, n)
    x = np.sin(2 * np.pi * ph) + 0.25 * np.sin(4 * np.pi * ph) + 0.08 * np.sin(6 * np.pi * ph) + 0.3 * np.sin(np.pi * ph)
    x *= env_adsr(n, 0.012, 0.15, 0.55, 0.12, 0.36)
    x = reverb(x, IR_ROOM, 0.12, tail=False)
    save("position_lost", x, "Position lost: subtle low tone sagging a semitone (E4).", hp_hz=60, fout=0.1)


def last_lap() -> None:
    r = rng(690)
    n = n_of(2.2)
    x = np.zeros(n)
    # a hand bell: hum, prime, minor-third tierce, quint, nominal and a few uppers, struck twice
    partials = [(0.5, 0.35, 1.2), (1.0, 1.0, 0.9), (1.19, 0.45, 0.6), (1.5, 0.3, 0.5), (2.0, 0.5, 0.45),
                (2.52, 0.25, 0.3), (3.01, 0.18, 0.22), (4.2, 0.12, 0.14)]
    for when, a in ((0.0, 1.0), (0.3, 0.8)):
        m = n - n_of(when)
        s = additive(hz("G5"), m, partials, r) * env_exp(m, 10.0, 0.001)
        c = click(r, 5200, 3, 0.0015, 0.02)
        s[:len(c)] += c * 0.3  # the clapper
        add_at(x, n_of(when), s * a)
    x = reverb(x, IR_HALL, 0.2, tail=False)
    save("last_lap", x, "Last lap: hand bell struck twice (G5).", hp_hz=150, fout=0.5)


def car_contact() -> None:
    r = rng(700)
    n = n_of(0.38)
    t = tt(n)
    x = np.zeros(n)
    # hollow bodywork panel: higher, shorter modes than the monocoque in impact_*
    m = n_of(0.2)
    panel = sum(np.sin(2 * np.pi * f * tt(m) + r.random() * 6) * a * np.exp(-tt(m) / d)
                for f, a, d in ((640, 0.6, 0.035), (1110, 0.5, 0.03), (1760, 0.4, 0.022), (2630, 0.3, 0.016), (3900, 0.2, 0.01)))
    add_at(x, 0, panel * env_exp(m, 1.0, 0.0005) * 0.9)
    m = n_of(0.01)
    add_at(x, 0, hp(nz(m, r), 2500, 2) * env_exp(m, 0.0012) * 1.0)  # crack
    add_at(x, n_of(0.003), thud(150, 105, 0.02, 0.08, 0.008, 0.8) * 0.3)  # tyre on tyre
    # a brief rubber scuff with stick-slip
    m = n_of(0.09)
    tm = tt(m)
    scuff = bp(nz(m, r), 600, 3000, 2) * (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 45 * tm)))
    scuff += np.sin(2 * np.pi * phase_of(880 * (1 + 0.05 * np.sin(2 * np.pi * 31 * tm)), m)) * 0.3
    add_at(x, n_of(0.012), scuff * np.sin(np.pi * tm / 0.09) * 0.25)
    for _ in range(6):  # bits of carbon
        add_at(x, n_of(0.02 + r.exponential(0.05)), click(r, r.uniform(2500, 7000), r.uniform(6, 15), 0.004, 0.03)
               * r.uniform(0.05, 0.2))
    x = sat(_norm(x) * 1.2, 1.2)
    x = reverb(x, IR_SHORT, 0.1, tail=False)
    save("car_contact", x, "Car-to-car touch: plasticky panel knock, tyre thump and a short rubber scuff.",
         hp_hz=100, fout=0.05)


def main() -> None:
    start_light()
    start_go()
    crowd_cheer()
    crowd_loop()
    grid_ambience()
    pit_limiter_on()
    wheel_gun()
    jack_up()
    jack_down()
    tyre_drop()
    pit_release()
    pit_radio()
    overtake()
    position_lost()
    last_lap()
    car_contact()


if __name__ == "__main__":
    main()
