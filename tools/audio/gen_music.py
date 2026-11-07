"""Music: menu loop (moody synthwave / garage, 105 BPM), drive loop (minimal, 126 BPM), and the
race-finish cues (chequered-flag stinger, podium fanfare) in the menu's style.

    python tools/audio/gen_music.py

Both are rendered circularly: every note, echo and reverb tail that runs past
the last bar wraps onto the first, so the loop has no seam. Tempos are chosen
so one beat is a whole number of samples (105 BPM = 25200, 126 BPM = 21000).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

import numpy as np

from dsp import (NYQ, SR, add_at, add_circ, compress, db, env_adsr, env_exp, fade, finish_oneshot, hp, hz, limiter,
                 loop_delay, loop_hp, loop_lp, loop_reverb, loop_tile_process, lp, lufs, make_ir, n_of, osc, peak,
                 phase_of, reverb, rng, sat, svf_sweep, to_db, trim_tail, tt, write_wav, bp, reson, peak_of)
from instruments import bell, supersaw

IR_MUSIC = make_ir(3.0, decays=(2.6, 2.2, 1.5, 0.8), predelay=0.025, seed=21)
IR_PLATE = make_ir(1.6, decays=(1.4, 1.2, 0.9, 0.5), predelay=0.01, seed=22)


# --------------------------------------------------------------------------
# Instruments (each returns peak-normalised audio)
# --------------------------------------------------------------------------

def _norm(x: np.ndarray) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-12)


def kick(r, tone: float = 48.0, punch: float = 1.0, length: float = 0.5) -> np.ndarray:
    m = n_of(length)
    t = tt(m)
    f = tone + 115 * punch * np.exp(-t / 0.028) + 60 * np.exp(-t / 0.004)
    body = np.sin(2 * np.pi * phase_of(f, m)) * env_exp(m, 0.15, 0.0006, 0.02)
    body = sat(body * 1.4, 1.6) * np.exp(-t / 0.5)
    clk = hp(r.standard_normal(m), 2500, 2) * np.exp(-t / 0.0018) * 0.22
    clk += np.sin(2 * np.pi * 3100 * t) * np.exp(-t / 0.0012) * 0.12
    return _norm(body + clk)


def clap(r) -> np.ndarray:
    m = n_of(0.45)
    t = tt(m)
    noise = bp(r.standard_normal(m), 850, 3600, 2)
    env = np.zeros(m)
    for i, d in enumerate((0.0, 0.0095, 0.0195)):
        tt_ = t - d
        env += np.where(tt_ >= 0, np.exp(-np.maximum(tt_, 0) / 0.0035), 0) * (0.8 + 0.1 * i)
    tt_ = t - 0.029
    env += np.where(tt_ >= 0, np.exp(-np.maximum(tt_, 0) / 0.12), 0)
    c = noise * env
    body = np.sin(2 * np.pi * phase_of(200 - 30 * np.exp(-t / 0.02), m)) * env_exp(m, 0.05, 0.0005) * 0.6
    snap = hp(r.standard_normal(m), 2200, 2) * env_exp(m, 0.11, 0.0005) * 0.45
    return _norm(c + body + lp(snap, 9000, 2))


def hat(r, open_: bool = False) -> np.ndarray:
    m = n_of(0.4 if open_ else 0.09)
    t = tt(m)
    metal = np.zeros(m)
    for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0):
        metal += osc("square", f * 1.9, m, r.random())
    metal = bp(metal, 7000, 13000, 2)
    noise = hp(r.standard_normal(m), 7500, 2)
    x = (_norm(metal) * 0.55 + _norm(noise) * 0.6) * env_exp(m, 0.17 if open_ else 0.022, 0.0004)
    return _norm(x)


def rim(r) -> np.ndarray:
    m = n_of(0.08)
    x = reson(r.standard_normal(m), 1750, 9) * env_exp(m, 0.012, 0.0003)
    x += np.sin(2 * np.pi * 520 * tt(m)) * env_exp(m, 0.008, 0.0003) * 0.3
    return _norm(x)


def shaker(r) -> np.ndarray:
    m = n_of(0.07)
    t = tt(m)
    x = bp(r.standard_normal(m), 4000, 11000, 2) * np.sin(np.pi * np.clip(t / 0.05, 0, 1)) ** 2
    return _norm(x)


def crash(r, length: float = 2.4) -> np.ndarray:
    m = n_of(length)
    metal = np.zeros(m)
    for f in (213.0, 317.0, 433.0, 551.0, 677.0, 913.0, 1171.0):
        metal += osc("square", f * 2.3, m, r.random())
    x = bp(metal, 4000, 14000, 2) * 0.5 + hp(r.standard_normal(m), 3500, 2)
    return _norm(x * env_exp(m, 0.7, 0.002))


def swell(r, length: float) -> np.ndarray:
    """Reverse-cymbal style swell that ends exactly at `length`."""
    m = n_of(length)
    t = tt(m)
    x = hp(r.standard_normal(m), 3000, 2) * (t / length) ** 3
    x = lp(x, 12000, 2)
    return _norm(x)


def tom(r, f: float) -> np.ndarray:
    m = n_of(0.35)
    t = tt(m)
    x = np.sin(2 * np.pi * phase_of(f + f * 0.6 * np.exp(-t / 0.03), m)) * env_exp(m, 0.11, 0.0008)
    x += bp(r.standard_normal(m), 400, 3000, 1) * env_exp(m, 0.012) * 0.25
    return _norm(sat(x, 1.3))


_BASS_CACHE: dict = {}


def bass(f: float, dur: float, bright: float = 1.0, seed: int = 0) -> np.ndarray:
    """Additive saw bass with a per-harmonic 'filter envelope' (upper harmonics fade first)."""
    key = (round(f, 3), round(dur, 4), bright, seed)
    if key in _BASS_CACHE:
        return _BASS_CACHE[key]
    m = n_of(dur + 0.05)
    t = tt(m)
    out = np.zeros(m)
    nh = min(40, int(NYQ * 0.8 / f))
    for k in range(1, nh + 1):
        sus = np.exp(-(k - 1) / (2.6 * bright))
        tau = 0.09 * bright / (1 + 0.22 * (k - 1))
        a = (1.0 / k) * (sus + (1 - sus) * np.exp(-t / tau))
        out += a * np.sin(2 * np.pi * k * f * t)
    out += 0.45 * np.sin(2 * np.pi * f * t)
    env = env_adsr(m, 0.003, 0.25, 0.75, 0.02, dur)
    out = sat(_norm(out * env) * 1.2, 1.2)
    _BASS_CACHE[key] = out
    return out


def pluck(f: float, dur: float, r, tau: float = 0.16, nh: int = 24, bright: float = 1.0) -> np.ndarray:
    m = n_of(dur)
    t = tt(m)
    out = np.zeros(m)
    for k in range(1, nh + 1):
        if k * f > NYQ * 0.9:
            break
        out += (1.0 / k) * np.exp(-t / (tau / (1 + 0.5 * (k - 1) / bright))) * np.sin(2 * np.pi * k * f * t + r.random() * 0.3)
    out *= env_exp(m, 10, 0.0015)
    return _norm(out)


def pad(freqs, dur: float, r, cutoff: float = 1700.0, attack: float = 0.35, release: float = 0.9) -> np.ndarray:
    m = n_of(dur + release * 1.5)
    x = supersaw(freqs, m / SR, r, 7, 15)
    x += supersaw([f * 2 for f in freqs[1:]], m / SR, r, 3, 8) * 0.25
    x = lp(x, cutoff, 2)
    x = peak(x, cutoff * 0.55, 0.9, 2.5)
    x *= env_adsr(m, attack, 1.2, 0.8, release, dur)
    return _norm(x)


def lead_phrase(notes, s16: int, r, glide: float = 0.03, octave_saw: float = 0.35) -> np.ndarray:
    """notes: list of (step, length_steps, note_hz or None). Returns audio starting at step 0."""
    last = max(st + ln for st, ln, _ in notes)
    m = last * s16 + n_of(0.4)
    f = np.zeros(m)
    gate = np.zeros(m)
    vib = np.zeros(m)
    prev = None
    for st, ln, fr in notes:
        a = st * s16
        b = min(m, (st + ln) * s16)
        seg = np.full(b - a, fr)
        if prev is not None:
            g = min(n_of(glide), b - a)
            seg[:g] = prev * (fr / prev) ** (np.arange(g) / g)
        f[a:b] = seg
        gl = b - a - n_of(0.02)
        e = env_adsr(b - a + n_of(0.25), 0.008, 0.18, 0.75, 0.07, gl / SR)
        end = min(m, a + len(e))
        gate[a:end] = np.maximum(gate[a:end], e[:end - a])
        tn = tt(b - a)
        vib[a:b] = np.clip((tn - 0.15) / 0.2, 0, 1)
        prev = fr
    # hold the last pitch through the release
    nz_ = np.nonzero(f)[0]
    f[nz_[-1]:] = f[nz_[-1]]
    for i in range(1, m):  # fill rests with the previous pitch (gate is closed there)
        if f[i] == 0:
            f[i] = f[i - 1]
    t = tt(m)
    f = f * (1 + 0.006 * vib * np.sin(2 * np.pi * 5.6 * t))
    x = osc("pulse", f, m, 0.0, pw=0.32) + osc("saw", f * 2 ** (7 / 1200), m, 0.3) * 0.45
    x += osc("saw", f / 2, m, 0.6) * octave_saw
    x = lp(x, 3400, 2)
    x = peak(x, 1200, 1.0, 2.0)
    return _norm(sat(_norm(x * gate) * 1.3, 1.2))


# --------------------------------------------------------------------------
# Arrangement helpers
# --------------------------------------------------------------------------

class Loop:
    def __init__(self, bpm: float, bars: int):
        spb = SR * 60.0 / bpm
        assert abs(spb - round(spb)) < 1e-9 and round(spb) % 4 == 0, "pick a tempo with an integer 16th"
        self.spb = int(round(spb))
        self.s16 = self.spb // 4
        self.bar = self.spb * 4
        self.bars = bars
        self.n = self.bar * bars
        self.tracks: dict[str, np.ndarray] = {}
        self.kicks: list[int] = []

    def pos(self, bar: int, step: float, swing: float = 0.0) -> int:
        st = step + (swing if int(step) % 2 == 1 else 0.0)
        return int(round(bar * self.bar + st * self.s16))

    def put(self, track: str, at: int, sig: np.ndarray, gain: float = 1.0) -> None:
        buf = self.tracks.setdefault(track, np.zeros(self.n))
        add_circ(buf, at, sig * gain)

    def duck(self, depth: float, release: float = 0.16) -> np.ndarray:
        """Sidechain gain curve from the kick positions (circular)."""
        g = np.zeros(self.n)
        m = n_of(release * 4)
        t = tt(m)
        shape = np.exp(-t / release) * np.clip(t / 0.004, 0, 1) ** 0.5
        shape[0] = 0.0
        for k in self.kicks:
            add_circ(g, k, shape)
        return 1.0 - depth * np.clip(g, 0, 1)

    def get(self, name: str) -> np.ndarray:
        return self.tracks.get(name, np.zeros(self.n))


def master(lp_: Loop, mix: np.ndarray, target_lufs: float, ceiling_db: float = -3.0) -> np.ndarray:
    x = loop_hp(mix, 28, 2)
    x = loop_tile_process(x / peak_of(x) * 0.5, lambda z: compress(z, -16, 2.2, 12, 180, 0.0), reps=2)
    x = sat(x / peak_of(x) * 1.1, 0.9)
    x = x - x.mean()
    for _ in range(3):  # loudness -> limit -> re-measure
        x = x * db(target_lufs - lufs(x))
        x = loop_tile_process(x, lambda z: limiter(z, ceiling_db - 0.15, 2.0, 90.0), reps=2)
    return x


# --------------------------------------------------------------------------
# Menu: A minor, 105 BPM, 16 bars
# --------------------------------------------------------------------------

def music_menu() -> None:
    r = rng(200)
    L = Loop(105, 16)
    s16 = L.s16

    chords = {  # pad voicings and bass roots
        "Am": (["A3", "C4", "E4", "B4"], "A1"),
        "F": (["F3", "A3", "C4", "E4"], "F1"),
        "C": (["G3", "C4", "E4", "B4"], "C2"),
        "G": (["G3", "B3", "D4", "A4"], "G1"),
        "Dm": (["F3", "A3", "D4", "E4"], "D2"),
        "E": (["E3", "G#3", "B3", "D4"], "E2"),
    }
    prog = ["Am", "Am", "F", "F", "C", "C", "G", "G", "Am", "Am", "F", "F", "Dm", "Dm", "E", "E"]
    arps = {"Am": ["A4", "C5", "E5", "A5"], "F": ["F4", "A4", "C5", "E5"], "Dm": ["D4", "F4", "A4", "D5"],
            "E": ["E4", "G#4", "B4", "D5"], "C": ["C5", "E5", "G5", "C6"], "G": ["B4", "D5", "G5", "B5"]}

    K = kick(r)
    CL = clap(r)
    HC = [hat(r) for _ in range(4)]
    HO = hat(r, True)
    RM = rim(r)
    SH = shaker(r)
    CR = crash(r)

    for b in range(16):
        # --- drums
        kick_steps = [0, 8] if b % 2 == 0 else [0, 8, 11]
        if b in (7, 15):
            kick_steps = [0, 8, 10, 14]
        for st in kick_steps:
            p = L.pos(b, st)
            L.kicks.append(p)
            L.put("kick", p, K, 1.0 if st in (0, 8) else 0.8)
        for st in (4, 12):
            L.put("clap", L.pos(b, st), CL, 1.0)
        if b in (7, 15):  # little fill
            for i, st in enumerate((13, 14, 15)):
                L.put("clap", L.pos(b, st), CL, 0.25 + 0.15 * i)
        for st in range(16):
            if b < 2 and st % 2 == 1:
                continue  # thinner opening bars
            vel = (1.0, 0.45, 0.7, 0.5)[st % 4] * (1 + 0.08 * r.standard_normal())
            jitter = r.normal(0, 0.0015) * SR
            L.put("hat", L.pos(b, st, 0.11) + int(jitter), HC[st % 4], vel)
        if b % 2 == 1:
            L.put("hat", L.pos(b, 14, 0.11), HO, 0.55)
        for st in (3, 7, 10) if b % 4 == 3 else (3, 10):
            L.put("perc", L.pos(b, st, 0.11), RM, 0.5)
        for st in range(2, 16, 4):
            L.put("perc", L.pos(b, st, 0.11), SH, 0.35)

        # --- bass: driving eighths, octave lift on the "a" of each beat pair
        ch = prog[b]
        root = hz(chords[ch][1])
        for st in range(0, 16, 2):
            f = root * (2 if st in (6, 14) else 1)
            bright = 1.25 if st in (0, 8) else 0.9
            L.put("bass", L.pos(b, st), bass(f, s16 * 2 * 0.82 / SR, bright), 0.9 if st % 4 == 0 else 0.75)

    # --- pads: one chord per two bars
    for b in range(0, 16, 2):
        ch = prog[b]
        freqs = [hz(n) for n in chords[ch][0]]
        L.put("pad", L.pos(b, 0) - n_of(0.04), pad(freqs, 2 * L.bar / SR - 0.1, r), 1.0)

    # --- arp: bars 9-16, 16th plucks
    for b in range(8, 16):
        notes = arps[prog[b]]
        for st in range(16):
            idx = (0, 1, 2, 3, 2, 1, 2, 3)[st % 8]
            f = hz(notes[idx]) * (2 if (b % 2 == 1 and st >= 12) else 1)
            acc = 1.0 if st % 4 == 0 else 0.7
            L.put("arp", L.pos(b, st), pluck(f, 0.5, r, 0.14), acc)

    # --- lead: bars 5-8 and 13-16 (sequence of one rhythmic motif)
    def motif(n1, n2, n3, n4, n5, hold, b0):
        a = [(0, 3, n1), (3, 1, n2), (4, 2, n1), (6, 2, n3), (8, 4, n4), (12, 2, n3), (14, 2, n5),
             (16, 6, hold)]
        return [(st, ln, hz(nn)) for st, ln, nn in a], b0

    phrases = [
        motif("E5", "G5", "D5", "C5", "E5", "C5", 4),
        motif("D5", "G5", "C5", "B4", "D5", "B4", 6),
        motif("F5", "A5", "E5", "D5", "F5", "A5", 12),
        motif("G#5", "B5", "E5", "D5", "G#5", "B5", 14),
    ]
    for notes, b0 in phrases:
        L.put("lead", L.pos(b0, 0), lead_phrase(notes, s16, r), 1.0)

    # --- transitions: crash on 1 and 9, swells into them
    L.put("fx", L.pos(0, 0), CR, 0.5)
    L.put("fx", L.pos(8, 0), CR, 0.5)
    sw = swell(r, L.bar / SR)
    L.put("fx", L.pos(15, 0), sw, 0.35)
    L.put("fx", L.pos(7, 0), sw, 0.3)

    # --- mix
    duck_hard = L.duck(0.55, 0.15)
    duck_soft = L.duck(0.3, 0.12)
    kick_t = L.get("kick")
    clap_t = L.get("clap")
    hat_t = lp(L.get("hat"), 14000, 1)
    perc_t = L.get("perc")
    bass_t = loop_lp(L.get("bass"), 2200, 2) * duck_hard
    pad_t = L.get("pad") * duck_soft
    arp_t = loop_lp(L.get("arp"), 5000, 2) * duck_soft
    lead_t = L.get("lead")
    fx_t = L.get("fx")

    def nrm(x):
        return x / (np.sqrt(np.mean(x * x)) + 1e-12)

    # balance by RMS so every part sits where intended regardless of note density
    bus = (nrm(kick_t) * db(-7) + nrm(clap_t) * db(-13) + nrm(hat_t) * db(-21) + nrm(perc_t) * db(-25)
           + nrm(bass_t) * db(-10) + nrm(pad_t) * db(-14) + nrm(arp_t) * db(-20) + nrm(lead_t) * db(-14)
           + nrm(fx_t) * db(-25))
    send = (nrm(clap_t) * db(-16) + nrm(pad_t) * db(-17) + nrm(lead_t) * db(-17) + nrm(arp_t) * db(-20)
            + nrm(perc_t) * db(-28))
    echo_src = nrm(lead_t) * db(-17) + nrm(arp_t) * db(-24)
    bus += loop_reverb(send, IR_MUSIC, 0.55, 0.0)
    bus += loop_delay(echo_src, int(L.spb * 0.75), 0.42, 5, 3800)

    out = master(L, bus, -16.0)
    write_wav("music_menu", out, loop=True,
              desc="Menu music: moody synthwave/garage, A minor, 105 BPM, 16 bars (Am F C G / Am F Dm E).",
              extra={"bpm": 105, "bars": 16, "lufs": round(lufs(out), 1)})


# --------------------------------------------------------------------------
# Drive: E minor, 126 BPM, 16 bars, minimal and percussive
# --------------------------------------------------------------------------

def music_drive() -> None:
    r = rng(300)
    L = Loop(126, 16)
    s16 = L.s16
    K = kick(r, tone=52, punch=0.8, length=0.35)
    CL = clap(r)
    HC = [hat(r) for _ in range(4)]
    HO = hat(r, True)
    RM = rim(r)
    SH = shaker(r)
    T1, T2 = tom(r, 110), tom(r, 82)
    roots = ["E1", "E1", "E1", "E1", "G1", "G1", "D1", "D1", "E1", "E1", "E1", "E1", "C1", "C1", "D1", "B0"]
    stabs = {"E1": ["E3", "G3", "B3", "F#4"], "G1": ["D3", "G3", "B3", "F#4"], "D1": ["D3", "F#3", "A3", "E4"],
             "C1": ["C3", "E3", "G3", "B3"], "B0": ["D#3", "F#3", "B3", "E4"]}

    for b in range(16):
        for st in (0, 4, 8, 12):
            p = L.pos(b, st)
            L.kicks.append(p)
            L.put("kick", p, K, 1.0)
        if b % 4 != 0:
            for st in (4, 12):
                L.put("clap", L.pos(b, st), CL, 0.8)
        for st in (2, 6, 10, 14):
            L.put("hat", L.pos(b, st), HO if (st == 14 and b % 4 == 3) else HC[st // 4], 0.9 if st != 14 else 0.7)
        for st in range(16):
            if st % 2 == 1:
                L.put("hat", L.pos(b, st, 0.08), SH, 0.3 + 0.1 * r.random())
        for st in ((3, 9, 13) if b % 2 else (3, 11)):
            L.put("perc", L.pos(b, st), RM, 0.6)
        if b % 4 == 3:
            L.put("perc", L.pos(b, 13), T1, 0.5)
            L.put("perc", L.pos(b, 15), T2, 0.55)
        root = hz(roots[b])
        low = root if root >= 40 else root * 2
        for st in (2, 6, 10, 14):  # off-beat bass
            L.put("bass", L.pos(b, st), bass(low * 2 if low < 60 else low, s16 * 1.6 / SR, 1.1), 0.9)
        if b % 2 == 0:
            L.put("bass", L.pos(b, 0), bass(low, s16 * 1.2 / SR, 0.8), 0.55)
        if b % 2 == 0:  # chord stab every two bars, on the off-beat of beat 2
            ch = stabs[roots[b]]
            st_sig = pad([hz(n) for n in ch], 0.18, r, cutoff=2400, attack=0.005, release=0.25)
            L.put("stab", L.pos(b, 6), st_sig, 1.0)
            L.put("stab", L.pos(b, 9), st_sig, 0.55)
    # filtered noise riser into bars 1 and 9
    sw = swell(r, L.bar / SR)
    L.put("fx", L.pos(7, 0), sw, 0.3)
    L.put("fx", L.pos(15, 0), sw, 0.3)
    # long drone for some body
    drone = np.zeros(L.n)
    t = tt(L.n)
    for f, a in ((hz("E2"), 1.0), (hz("B2"), 0.5), (hz("E3"), 0.3)):
        ff = round(f * L.n / SR) * SR / L.n
        drone += a * osc("saw", ff, L.n, r.random())
    drone = loop_lp(drone, 500, 2) * (0.7 + 0.3 * np.sin(2 * np.pi * t * 2 / (L.n / SR)))

    duck = L.duck(0.6, 0.12)

    def nrm(x):
        return x / (np.sqrt(np.mean(x * x)) + 1e-12)

    bus = (nrm(L.get("kick")) * db(-6) + nrm(L.get("clap")) * db(-16) + nrm(L.get("hat")) * db(-19)
           + nrm(L.get("perc")) * db(-20) + nrm(loop_lp(L.get("bass"), 1800, 2) * duck) * db(-11)
           + nrm(L.get("stab") * duck) * db(-19) + nrm(drone * duck) * db(-24) + nrm(L.get("fx")) * db(-24))
    send = nrm(L.get("stab")) * db(-18) + nrm(L.get("clap")) * db(-20) + nrm(L.get("perc")) * db(-24)
    bus += loop_reverb(send, IR_PLATE, 0.6, 0.0)
    bus += loop_delay(nrm(L.get("stab")) * db(-22), int(L.spb * 0.75), 0.4, 4, 3000)
    out = master(L, bus, -18.0)
    write_wav("music_drive", out, loop=True,
              desc="Drive music: minimal percussive loop, E minor, 126 BPM, 16 bars. Sits under the engine.",
              extra={"bpm": 126, "bars": 16, "lufs": round(lufs(out), 1)})


# --------------------------------------------------------------------------
# Race finish: chequered-flag stinger and podium fanfare (A major, the menu's key turned major)
# --------------------------------------------------------------------------

def brass(freqs, dur: float, r, bright: float = 1.0, release: float = 0.25) -> np.ndarray:
    """Synthwave 'brass': supersaw chord with a fast filter envelope."""
    m = n_of(dur + release * 2.5)
    t = tt(m)
    x = supersaw(freqs, m / SR, r, 7, 12)
    fc = 700 + 4800 * bright * np.exp(-t / 0.09) + 1200 * bright * np.exp(-t / 0.7)
    x = svf_sweep(x, fc, 1.1, "lp")
    x *= env_adsr(m, 0.006, 0.2, 0.7, release, dur)
    return _norm(x)


def boom(r, length: float = 1.6) -> np.ndarray:
    """Timpani-ish sub hit for the big downbeats."""
    m = n_of(length)
    t = tt(m)
    x = np.sin(2 * np.pi * phase_of(42 + 50 * np.exp(-t / 0.06), m)) * env_exp(m, 0.45, 0.002)
    x += bp(r.standard_normal(m), 80, 900, 2) * env_exp(m, 0.03, 0.001) * 0.4
    return _norm(sat(x * 1.3, 1.2))


def tail(x: np.ndarray, seconds: float) -> np.ndarray:
    """Fade the end of a note whose envelope is still open when its buffer ends (pad, brass, bell)."""
    return fade(x, 0.0, seconds)


def finish_music(x: np.ndarray, fade_s: float, max_s: float | None = None) -> np.ndarray:
    """Crop a mastered one-shot cue to its tail (or to max_s) and fade it out."""
    x = trim_tail(x, -60.0, 0.05)
    if max_s is not None and len(x) > n_of(max_s):
        x = x[:n_of(max_s)]
    return fade(x, 0.002, fade_s)


def chequered() -> None:
    """Finish stinger: two quick pickups on E, then a big A major hit with crash and bells."""
    r = rng(410)
    n = n_of(4.0)
    step = n_of(0.105)
    hit = 2 * step
    parts: dict[str, np.ndarray] = {k: np.zeros(n) for k in ("brass", "lead", "drums", "bells", "pad")}
    for i in range(2):
        add_at(parts["brass"], i * step, brass([hz(nn) for nn in ("B3", "E4", "G#4")], 0.07, r, 1.2, 0.07) * 0.75)
        add_at(parts["drums"], i * step, tom(r, 150.0 + 35 * i) * 0.6)
        add_at(parts["drums"], i * step, clap(r) * 0.35)
    lead = lead_phrase([(0, 1, hz("E5")), (1, 1, hz("E5")), (2, 17, hz("A5"))], step, r, glide=0.02)
    add_at(parts["lead"], 0, lead)
    add_at(parts["brass"], hit, tail(brass([hz(nn) for nn in ("A3", "C#4", "E4", "A4", "C#5")], 1.7, r, 1.3, 0.6), 0.6))
    add_at(parts["pad"], hit, tail(pad([hz(nn) for nn in ("A2", "E3", "A3", "C#4", "E4", "B4")], 1.9, r, 2200, 0.02, 0.8), 0.8))
    add_at(parts["drums"], hit, kick(r, 46, 1.2, 0.6))
    add_at(parts["drums"], hit, crash(r, 3.0) * 0.55)
    add_at(parts["drums"], hit, boom(r) * 0.8)
    add_at(parts["drums"], hit, clap(r) * 0.5)
    for i, nn in enumerate(("A6", "C#7", "E7", "A7", "E7", "C#7", "E7", "A7")):
        add_at(parts["bells"], hit + n_of(0.06 + i * 0.075), tail(bell(hz(nn), 1.4, r, 0.9, 0.8), 0.4) * (0.9 - 0.06 * i))

    def nrm(x):
        return x / (np.sqrt(np.mean(x * x)) + 1e-12)

    bus = (nrm(parts["brass"]) * db(-12) + nrm(parts["lead"]) * db(-13) + nrm(parts["drums"]) * db(-10)
           + nrm(parts["bells"]) * db(-21) + nrm(parts["pad"]) * db(-17))
    send = nrm(parts["brass"]) * db(-17) + nrm(parts["lead"]) * db(-17) + nrm(parts["bells"]) * db(-20)
    bus = bus + reverb(send, IR_MUSIC, 0.55, 0.0, tail=False)
    bus = compress(bus / peak_of(bus) * 0.5, -16, 2.0, 8, 200)
    write_wav("chequered", finish_oneshot(finish_music(bus, 0.6), -3.0, 30, 0.001, 0.05),
              desc="Chequered flag: two quick pickups into a big A major brass hit with crash and bells.")


def podium_music() -> None:
    """12.8 s fanfare: swell, four bars (A / E / F#m D / F G) and a held A major chord."""
    r = rng(400)
    L = Loop(105, 9)  # 20.6 s buffer: the cue uses ~13 s and the rest catches every tail (no wrap)
    s16 = L.s16
    off = L.spb  # one beat of swell before bar 0

    def P(bar: int, st: float = 0.0, swing: float = 0.0) -> int:
        return L.pos(bar, st, swing) + off

    K = kick(r)
    CL = clap(r)
    HC = [hat(r) for _ in range(4)]
    HO = hat(r, True)
    CR = crash(r, 3.0)
    T1, T2 = tom(r, 130), tom(r, 98)
    # name: (pad voicing, bass root, arp notes, brass voicing)
    CH = {
        "A": (["A3", "C#4", "E4", "B4"], "A1", ["A4", "C#5", "E5", "A5"], ["C#4", "E4", "A4"]),
        "E": (["G#3", "B3", "E4", "F#4"], "E2", ["G#4", "B4", "E5", "G#5"], ["B3", "E4", "G#4"]),
        "F#m": (["F#3", "A3", "C#4", "E4"], "F#1", ["F#4", "A4", "C#5", "F#5"], ["C#4", "F#4", "A4"]),
        "D": (["F#3", "A3", "D4", "E4"], "D2", ["D4", "F#4", "A4", "D5"], ["A3", "D4", "F#4"]),
        "F": (["F3", "A3", "C4", "G4"], "F1", ["F4", "A4", "C5", "F5"], ["A3", "C4", "F4"]),
        "G": (["G3", "B3", "D4", "A4"], "G1", ["G4", "B4", "D5", "G5"], ["B3", "D4", "G4"]),
    }
    plan = [(0, 0, 16, "A"), (1, 0, 16, "E"), (2, 0, 8, "F#m"), (2, 8, 8, "D"), (3, 0, 8, "F"), (3, 8, 8, "G")]

    # --- drums, bars 0-3
    for b in range(4):
        for st in (0, 4, 8, 12):
            p = P(b, st)
            L.kicks.append(p)
            L.put("kick", p, K, 1.0)
        for st in (4, 12):
            L.put("clap", P(b, st), CL, 1.0)
        for st in range(16):
            vel = (0.8, 0.35, 0.55, 0.4)[st % 4] * (1 + 0.08 * r.standard_normal())
            L.put("hat", P(b, st, 0.06), HC[st % 4], vel)
        for st in (2, 6, 10, 14):
            L.put("hat", P(b, st), HO, 0.35)
    for i, st in enumerate(range(8, 16)):  # clap roll into the last chord
        L.put("clap", P(3, st), CL, 0.25 + 0.09 * i)
    for st, tm in ((13, T1), (14, T1), (15, T2)):  # tom fill into bar 2
        L.put("perc", P(1, st), tm, 0.7)
    L.put("fx", P(0, 0), CR, 0.7)
    L.put("fx", P(2, 0), CR, 0.35)
    L.put("fx", P(0, 0) - off, swell(r, off / SR), 0.5)
    L.put("fx", P(3, 0), swell(r, L.bar / SR), 0.4)

    # --- harmony, bars 0-3
    for b, st, ln, name in plan:
        voicing, root, arp, brs = CH[name]
        L.put("pad", P(b, st) - n_of(0.03), pad([hz(nn) for nn in voicing], ln * s16 / SR - 0.05, r), 1.0)
        f = hz(root)
        for k in range(0, ln, 2):
            lift = 2 if (st + k) % 8 == 6 else 1
            bright = 1.25 if (st + k) % 8 == 0 else 0.9
            L.put("bass", P(b, st + k), bass(f * lift, s16 * 2 * 0.82 / SR, bright), 0.9 if k % 4 == 0 else 0.75)
        for k in range(ln):
            idx = (0, 1, 2, 3, 2, 1, 2, 3)[k % 8]
            L.put("arp", P(b, st + k), pluck(hz(arp[idx]), 0.45, r, 0.13), 1.0 if k % 4 == 0 else 0.7)
        stabs = ((0, 5), (6, 3), (10, 5)) if ln == 16 else ((0, 5), (6, 2))
        for s0, sl in stabs:
            L.put("brass", P(b, st + s0), brass([hz(nn) for nn in brs], sl * s16 / SR * 0.9, r, 0.9, 0.12),
                  1.0 if s0 == 0 else 0.75)

    # --- lead: the chequered motif (E E A) grows into the tune
    tune = [(0, 3, "E5"), (3, 1, "E5"), (4, 4, "A5"), (8, 4, "C#6"), (12, 2, "B5"), (14, 2, "A5"),
            (16, 6, "B5"), (22, 2, "G#5"), (24, 4, "E5"), (28, 4, "B5"),
            (32, 6, "C#6"), (38, 2, "B5"), (40, 4, "A5"), (44, 2, "F#5"), (46, 2, "A5"),
            (48, 6, "C6"), (54, 2, "A5"), (56, 6, "D6"), (62, 2, "B5"),
            (64, 20, "C#6")]
    L.put("lead", P(0, 0), lead_phrase([(st, ln, hz(nn)) for st, ln, nn in tune], s16, r, octave_saw=0.25), 1.0)

    # --- bar 4: the held A major chord
    hold = 2.0
    L.kicks.append(P(4, 0))
    L.put("kick", P(4, 0), K, 1.0)
    L.put("clap", P(4, 0), CL, 0.8)
    L.put("fx", P(4, 0), CR, 1.0)
    L.put("boom", P(4, 0), boom(r, 2.0), 1.0)
    L.put("boom", P(0, 0), boom(r, 1.4), 0.6)
    L.put("pad", P(4, 0) - n_of(0.03),
          tail(pad([hz(nn) for nn in ("A2", "E3", "A3", "C#4", "E4", "B4")], hold, r, 2000, 0.02, 1.0), 1.2), 1.3)
    L.put("brass", P(4, 0), tail(brass([hz(nn) for nn in ("A3", "C#4", "E4", "A4")], hold * 0.8, r, 1.3, 0.7), 0.8), 1.2)
    L.put("bass", P(4, 0), tail(bass(hz("A1"), hold + 1.0, 1.3), 1.3), 1.0)
    for i, nn in enumerate(("A6", "C#7", "E7", "A7", "E7", "C#7", "E7", "A7", "C#8", "A7")):
        L.put("bells", P(4, 0) + n_of(0.08 + i * 0.09), tail(bell(hz(nn), 1.5, r, 0.9, 0.9), 0.4), 0.9 - 0.05 * i)

    # --- mix
    duck_hard = L.duck(0.5, 0.15)
    duck_soft = L.duck(0.25, 0.12)

    def nrm(x):
        return x / (np.sqrt(np.mean(x * x)) + 1e-12)

    bus = (nrm(L.get("kick")) * db(-8) + nrm(L.get("clap")) * db(-14) + nrm(lp(L.get("hat"), 14000, 1)) * db(-23)
           + nrm(L.get("perc")) * db(-20) + nrm(loop_lp(L.get("bass"), 2200, 2) * duck_hard) * db(-11)
           + nrm(L.get("pad") * duck_soft) * db(-15) + nrm(loop_lp(L.get("arp"), 5000, 2) * duck_soft) * db(-21)
           + nrm(L.get("brass") * duck_soft) * db(-15) + nrm(L.get("lead")) * db(-13)
           + nrm(L.get("bells")) * db(-22) + nrm(L.get("boom")) * db(-16) + nrm(L.get("fx")) * db(-22))
    send = (nrm(L.get("clap")) * db(-17) + nrm(L.get("pad")) * db(-17) + nrm(L.get("lead")) * db(-17)
            + nrm(L.get("brass")) * db(-19) + nrm(L.get("bells")) * db(-19) + nrm(L.get("arp")) * db(-22))
    bus += loop_reverb(send, IR_MUSIC, 0.55, 0.0)
    bus += loop_delay(nrm(L.get("lead")) * db(-19) + nrm(L.get("arp")) * db(-26), int(L.spb * 0.75), 0.4, 4, 3800)
    out = finish_music(master(L, bus, -16.0), 1.4, 12.8)
    write_wav("podium_music", out,
              desc=("Podium fanfare (not a loop): synthwave in A major, 105 BPM, swell + 4 bars "
                    "(A / E / F#m D / F G) into a held A major chord."),
              extra={"bpm": 105, "lufs": round(lufs(out), 1)})


def main() -> None:
    music_menu()
    music_drive()
    chequered()
    podium_music()


if __name__ == "__main__":
    main()
