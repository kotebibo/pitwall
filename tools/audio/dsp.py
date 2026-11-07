"""Shared DSP helpers for Pit Wall's synthesized audio (numpy + scipy only).

Everything here is deterministic: generators pass explicit seeds, so running
the build twice writes the same files.

Two kinds of output:
  * one-shots: rendered in the time domain, faded in/out, peak-normalised.
  * loops: rendered *circularly*. Every event that runs past the end wraps to
    the start, noise is synthesised in the frequency domain (so it is
    periodic), and filters/reverb/delay are applied with circular (FFT)
    convolution. The last sample therefore flows into the first one exactly,
    which is what makes the loops seamless without a crossfade.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
from scipy import signal as sg
from scipy import ndimage

SR = 44100
NYQ = SR / 2
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "game" / "assets" / "audio"


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def n_of(seconds: float) -> int:
    return int(round(seconds * SR))


def tt(n: int) -> np.ndarray:
    return np.arange(n) / SR


def db(x: float) -> float:
    return 10 ** (x / 20.0)


def to_db(x: float) -> float:
    return 20 * np.log10(max(float(x), 1e-12))


def midi(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12.0)


_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def nm(name: str) -> float:
    """'A4' / 'C#5' / 'Bb3' -> midi number."""
    base = _NOTE[name[0]]
    i = 1
    while i < len(name) and name[i] in "#b":
        base += 1 if name[i] == "#" else -1
        i += 1
    octave = int(name[i:])
    return base + 12 * (octave + 1)


def hz(name: str) -> float:
    return midi(nm(name))


# --------------------------------------------------------------------------
# Filters (time domain, for one-shots)
# --------------------------------------------------------------------------

def _clampf(f: float) -> float:
    return float(min(max(f, 5.0), NYQ * 0.98))


def sos_lp(f: float, order: int = 2):
    return sg.butter(order, _clampf(f), "lowpass", fs=SR, output="sos")


def sos_hp(f: float, order: int = 2):
    return sg.butter(order, _clampf(f), "highpass", fs=SR, output="sos")


def sos_bp(lo: float, hi: float, order: int = 2):
    return sg.butter(order, [_clampf(lo), _clampf(hi)], "bandpass", fs=SR, output="sos")


def _rbj(kind: str, f: float, q: float, gain_db: float = 0.0):
    f = _clampf(f)
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * a, -2 * cw, 1 - alpha * a]
        aa = [1 + alpha / a, -2 * cw, 1 - alpha / a]
    elif kind == "bpf":  # constant 0 dB peak gain
        b = [alpha, 0.0, -alpha]
        aa = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(a) * alpha
        b = [a * ((a + 1) - (a - 1) * cw + sa), 2 * a * ((a - 1) - (a + 1) * cw), a * ((a + 1) - (a - 1) * cw - sa)]
        aa = [(a + 1) + (a - 1) * cw + sa, -2 * ((a - 1) + (a + 1) * cw), (a + 1) + (a - 1) * cw - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(a) * alpha
        b = [a * ((a + 1) + (a - 1) * cw + sa), -2 * a * ((a - 1) + (a + 1) * cw), a * ((a + 1) + (a - 1) * cw - sa)]
        aa = [(a + 1) - (a - 1) * cw + sa, 2 * ((a - 1) - (a + 1) * cw), (a + 1) - (a - 1) * cw - sa]
    else:
        raise ValueError(kind)
    b = np.array(b) / aa[0]
    aa = np.array(aa) / aa[0]
    return np.hstack([b, aa])[None, :]


def sos_peak(f: float, q: float, gain_db: float):
    return _rbj("peak", f, q, gain_db)


def sos_reson(f: float, q: float):
    return _rbj("bpf", f, q)


def sos_lowshelf(f: float, gain_db: float, q: float = 0.707):
    return _rbj("lowshelf", f, q, gain_db)


def sos_highshelf(f: float, gain_db: float, q: float = 0.707):
    return _rbj("highshelf", f, q, gain_db)


def filt(x: np.ndarray, sos) -> np.ndarray:
    return sg.sosfilt(sos, x)


def lp(x, f, order=2):
    return filt(x, sos_lp(f, order))


def hp(x, f, order=2):
    return filt(x, sos_hp(f, order))


def bp(x, lo, hi, order=2):
    return filt(x, sos_bp(lo, hi, order))


def reson(x, f, q):
    return filt(x, sos_reson(f, q))


def peak(x, f, q, gain_db):
    return filt(x, sos_peak(f, q, gain_db))


def svf_sweep(x: np.ndarray, fc: np.ndarray, q: float = 0.707, mode: str = "lp") -> np.ndarray:
    """Time-varying state-variable filter (TPT/Zavalishin). fc is per-sample Hz."""
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape)
    g = np.tan(np.pi * np.clip(fc, 10, NYQ * 0.95) / SR)
    k = 1.0 / q
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    out = np.empty_like(x)
    ic1 = ic2 = 0.0
    xs = x.tolist()
    a1l, a2l, a3l = a1.tolist(), a2.tolist(), a3.tolist()
    kk = k
    if mode == "lp":
        for i, v0 in enumerate(xs):
            v3 = v0 - ic2
            v1 = a1l[i] * ic1 + a2l[i] * v3
            v2 = ic2 + a2l[i] * ic1 + a3l[i] * v3
            ic1 = 2 * v1 - ic1
            ic2 = 2 * v2 - ic2
            out[i] = v2
    elif mode == "bp":
        for i, v0 in enumerate(xs):
            v3 = v0 - ic2
            v1 = a1l[i] * ic1 + a2l[i] * v3
            v2 = ic2 + a2l[i] * ic1 + a3l[i] * v3
            ic1 = 2 * v1 - ic1
            ic2 = 2 * v2 - ic2
            out[i] = v1 * kk  # unity peak gain
    elif mode == "hp":
        for i, v0 in enumerate(xs):
            v3 = v0 - ic2
            v1 = a1l[i] * ic1 + a2l[i] * v3
            v2 = ic2 + a2l[i] * ic1 + a3l[i] * v3
            ic1 = 2 * v1 - ic1
            ic2 = 2 * v2 - ic2
            out[i] = v0 - kk * v1 - v2
    else:
        raise ValueError(mode)
    return out


# --------------------------------------------------------------------------
# Circular (loop) processing
# --------------------------------------------------------------------------

def _freqs(n: int) -> np.ndarray:
    return np.fft.rfftfreq(n, 1.0 / SR)


def loop_filt(x: np.ndarray, sos) -> np.ndarray:
    """Steady-state response of an IIR filter to the periodic extension of x."""
    n = len(x)
    f = _freqs(n)
    _, h = sg.freqz_sos(sos, worN=f, fs=SR)
    return np.fft.irfft(np.fft.rfft(x) * h, n)


def loop_lp(x, f, order=2):
    return loop_filt(x, sos_lp(f, order))


def loop_hp(x, f, order=2):
    return loop_filt(x, sos_hp(f, order))


def loop_bp(x, lo, hi, order=2):
    return loop_filt(x, sos_bp(lo, hi, order))


def loop_reson(x, f, q):
    return loop_filt(x, sos_reson(f, q))


def loop_peak(x, f, q, g):
    return loop_filt(x, sos_peak(f, q, g))


def loop_conv(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Circular convolution; an IR longer than the loop is folded onto it."""
    n = len(x)
    if len(ir) > n:
        folded = np.zeros(n)
        for i in range(0, len(ir), n):
            seg = ir[i:i + n]
            folded[:len(seg)] += seg
        ir = folded
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir, n), n)


def loop_tile_process(x: np.ndarray, fn, reps: int = 3) -> np.ndarray:
    """Run a stateful time-domain process on a tiled loop and keep the last copy."""
    n = len(x)
    y = fn(np.tile(x, reps))
    return np.asarray(y[(reps - 1) * n: reps * n])


def add_circ(buf: np.ndarray, start: int, sig: np.ndarray) -> None:
    """Mix sig into buf at start, wrapping past the end (for loops)."""
    n = len(buf)
    start %= n
    i = 0
    while i < len(sig):
        pos = (start + i) % n
        take = min(len(sig) - i, n - pos)
        buf[pos:pos + take] += sig[i:i + take]
        i += take


def add_at(buf: np.ndarray, start: int, sig: np.ndarray) -> None:
    """Mix sig into buf at start, clipped at the end (for one-shots)."""
    if start >= len(buf):
        return
    if start < 0:
        sig = sig[-start:]
        start = 0
    end = min(len(buf), start + len(sig))
    buf[start:end] += sig[:end - start]


# --------------------------------------------------------------------------
# Noise and modulation sources
# --------------------------------------------------------------------------

def noise_shaped(n: int, r: np.random.Generator, shape) -> np.ndarray:
    """Periodic noise with magnitude spectrum shape(freqs). Unit RMS."""
    f = _freqs(n)
    spec = (r.standard_normal(len(f)) + 1j * r.standard_normal(len(f))) * shape(np.maximum(f, 1e-3))
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    s = np.sqrt(np.mean(x * x))
    return x / s if s > 0 else x


def white(n, r):
    return noise_shaped(n, r, lambda f: np.ones_like(f))


def pink(n, r):
    return noise_shaped(n, r, lambda f: 1 / np.sqrt(np.maximum(f, 20)))


def brown(n, r):
    return noise_shaped(n, r, lambda f: 1 / np.maximum(f, 20))


def smooth_mod(n: int, r: np.random.Generator, f_lo: float, f_hi: float) -> np.ndarray:
    """Periodic smooth random modulation, zero mean, peak ~1, content in [f_lo, f_hi] Hz."""
    def shape(f):
        return ((f >= f_lo) & (f <= f_hi)).astype(float) / np.sqrt(np.maximum(f, 0.1))
    f = _freqs(n)
    if not np.any((f >= f_lo) & (f <= f_hi)):
        return np.zeros(n)
    x = noise_shaped(n, r, shape)
    return x / (np.max(np.abs(x)) + 1e-12)


# --------------------------------------------------------------------------
# Oscillators
# --------------------------------------------------------------------------

def phase_of(freq, n: int, phase0: float = 0.0) -> np.ndarray:
    """Phase in cycles for a frequency (scalar or per-sample array)."""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    ph = np.concatenate([[0.0], np.cumsum(f[:-1])]) / SR
    return ph + phase0


def sine(freq, n, phase0=0.0):
    return np.sin(2 * np.pi * phase_of(freq, n, phase0))


_TABLES: dict = {}


def wavetable(shape: str, f_top: float, size: int = 4096, pw: float = 0.5) -> np.ndarray:
    """Band-limited single cycle with harmonics below Nyquist for f_top."""
    nh = max(1, int(NYQ * 0.92 / max(f_top, 1.0)))
    nh = min(nh, size // 2 - 1)
    key = (shape, nh, size, round(pw, 3))
    if key in _TABLES:
        return _TABLES[key]
    k = np.arange(1, nh + 1)
    ph = np.arange(size) / size
    if shape == "saw":
        amps = 1.0 / k
        sig = np.zeros(size)
        for kk, a in zip(k, amps):
            sig += a * np.sin(2 * np.pi * kk * ph)
    elif shape == "square":
        sig = np.zeros(size)
        for kk in k[::2]:
            sig += np.sin(2 * np.pi * kk * ph) / kk
    elif shape == "pulse":
        sig = np.zeros(size)
        for kk in k:
            sig += np.sin(np.pi * kk * pw) / kk * np.cos(2 * np.pi * kk * ph)
    elif shape == "tri":
        sig = np.zeros(size)
        for kk in k[::2]:
            sig += ((-1) ** ((kk - 1) // 2)) * np.sin(2 * np.pi * kk * ph) / (kk * kk)
    else:
        raise ValueError(shape)
    sig -= sig.mean()
    sig /= np.max(np.abs(sig))
    _TABLES[key] = sig
    return sig


def table_read(table: np.ndarray, phase_cycles: np.ndarray) -> np.ndarray:
    size = len(table)
    p = (phase_cycles % 1.0) * size
    i0 = np.floor(p).astype(int)
    fr = p - i0
    i0 %= size
    i1 = (i0 + 1) % size
    return table[i0] * (1 - fr) + table[i1] * fr


def osc(shape: str, freq, n: int, phase0: float = 0.0, pw: float = 0.5) -> np.ndarray:
    f = np.asarray(freq, dtype=float)
    f_top = float(np.max(f)) if f.ndim else float(f)
    return table_read(wavetable(shape, f_top, pw=pw), phase_of(freq, n, phase0))


def additive(f0: float, n: int, partials, r: np.random.Generator | None = None, freq_mod=None) -> np.ndarray:
    """partials: iterable of (ratio, amp, tau_seconds or None). Skips partials above Nyquist."""
    t = tt(n)
    out = np.zeros(n)
    for ratio, amp, tau in partials:
        f = f0 * ratio
        if f >= NYQ * 0.95:
            continue
        ph0 = r.random() if r is not None else 0.0
        if freq_mod is not None:
            s = np.sin(2 * np.pi * phase_of(f * freq_mod, n, ph0))
        else:
            s = np.sin(2 * np.pi * (f * t + ph0))
        if tau is not None:
            s = s * np.exp(-t / tau)
        out += amp * s
    return out


def sat(x: np.ndarray, drive: float = 1.0) -> np.ndarray:
    if drive <= 1e-6:
        return x
    return np.tanh(drive * x) / np.tanh(drive)


# --------------------------------------------------------------------------
# Envelopes
# --------------------------------------------------------------------------

def env_exp(n: int, tau: float, attack: float = 0.0005, hold: float = 0.0) -> np.ndarray:
    t = tt(n)
    e = np.exp(-np.maximum(t - attack - hold, 0) / tau)
    if attack > 0:
        a = np.clip(t / attack, 0, 1)
        e = e * (0.5 - 0.5 * np.cos(np.pi * a))
    return e


def env_adsr(n: int, a: float, d: float, s: float, r: float, gate: float) -> np.ndarray:
    t = tt(n)
    e = np.zeros(n)
    a = max(a, 1e-4)
    att = t < a
    e[att] = t[att] / a
    dec = (t >= a) & (t < gate)
    e[dec] = s + (1 - s) * np.exp(-(t[dec] - a) / max(d, 1e-4))
    level_at_gate = s + (1 - s) * np.exp(-(max(gate - a, 0)) / max(d, 1e-4)) if gate > a else min(gate / a, 1.0)
    rel = t >= gate
    e[rel] = level_at_gate * np.exp(-(t[rel] - gate) / max(r, 1e-4))
    return e


def fade(x: np.ndarray, fin: float = 0.001, fout: float = 0.01) -> np.ndarray:
    y = x.copy()
    ni, no = n_of(fin), n_of(fout)
    if ni > 0:
        y[:ni] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(ni) / ni)
    if no > 0:
        y[-no:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, no + 1) / no)
    return y


# --------------------------------------------------------------------------
# Space: reverb and delay
# --------------------------------------------------------------------------

def make_ir(seconds: float = 2.0, decays=(2.4, 1.9, 1.3, 0.7), predelay: float = 0.012,
            seed: int = 7, early: int = 8) -> np.ndarray:
    """Synthetic room/plate: band-split noise with frequency dependent decay."""
    r = rng(seed)
    n = n_of(seconds)
    t = tt(n)
    bands = [(20, 400), (400, 2500), (2500, 7000), (7000, 18000)]
    ir = np.zeros(n)
    for (lo, hi), t60 in zip(bands, decays):
        nz = bp(r.standard_normal(n), lo, hi, 2)
        ir += nz * np.exp(-6.91 * t / t60)
    ir *= np.clip(t / 0.03, 0, 1)  # soft onset
    pd = n_of(predelay)
    ir = np.concatenate([np.zeros(pd), ir])[:n]
    for _ in range(early):
        i = pd + int(r.uniform(0.002, 0.04) * SR)
        if i < n:
            ir[i] += r.uniform(-1, 1) * 3.0
    ir = fade(ir, 0, 0.05)
    return ir / np.sqrt(np.sum(ir * ir))


def reverb(x: np.ndarray, ir: np.ndarray, wet: float, dry: float = 1.0, tail: bool = True) -> np.ndarray:
    w = sg.fftconvolve(x, ir)
    if not tail:
        w = w[:len(x)]
        return dry * x + wet * w
    y = wet * w
    y[:len(x)] += dry * x
    return y


def loop_reverb(x: np.ndarray, ir: np.ndarray, wet: float, dry: float = 1.0) -> np.ndarray:
    return dry * x + wet * loop_conv(x, ir)


def delay(x: np.ndarray, d: int, fb: float, taps: int = 5, lp_hz: float = 5000.0, tail: bool = True) -> np.ndarray:
    n = len(x) + (d * taps if tail else 0)
    y = np.zeros(n)
    y[:len(x)] += x
    tap = x.copy()
    for k in range(1, taps + 1):
        tap = lp(tap, lp_hz, 1)
        add_at(y, d * k, tap * fb ** k)
    return y


def loop_delay(x: np.ndarray, d: int, fb: float, taps: int = 6, lp_hz: float = 5000.0) -> np.ndarray:
    """Wet-only circular feedback delay (echoes only)."""
    y = np.zeros_like(x)
    tap = x.copy()
    for k in range(1, taps + 1):
        tap = loop_lp(tap, lp_hz, 1)
        y += np.roll(tap, d * k) * fb ** k
    return y


# --------------------------------------------------------------------------
# Dynamics
# --------------------------------------------------------------------------

def limiter(x: np.ndarray, ceiling_db: float = -1.0, look_ms: float = 2.0, release_ms: float = 80.0) -> np.ndarray:
    """Lookahead brickwall: gain never exceeds what keeps |y| <= ceiling."""
    c = db(ceiling_db)
    a = np.abs(x)
    g = np.minimum(1.0, c / np.maximum(a, 1e-12))
    w = max(1, n_of(look_ms / 1000.0))
    gm = ndimage.minimum_filter1d(g, size=2 * w + 1, mode="nearest")
    gs = ndimage.uniform_filter1d(gm, size=w, mode="nearest")
    gs = np.minimum(gs, g)
    # release: limit how fast the gain may recover
    step = 1.0 / max(1, n_of(release_ms / 1000.0))
    out = np.empty_like(gs)
    prev = 1.0
    gl = gs.tolist()
    for i, v in enumerate(gl):
        prev = min(v, prev + step * (1.0 - prev + 1e-3))
        out[i] = prev
    return x * out


def compress(x: np.ndarray, thresh_db: float = -18.0, ratio: float = 3.0, attack_ms: float = 5.0,
             release_ms: float = 120.0, makeup_db: float = 0.0, key: np.ndarray | None = None) -> np.ndarray:
    """Feed-forward RMS-ish compressor (one-pole envelope on |key|)."""
    k = np.abs(x if key is None else key)
    aa = np.exp(-1.0 / max(1, n_of(attack_ms / 1000.0)))
    ar = np.exp(-1.0 / max(1, n_of(release_ms / 1000.0)))
    env = np.empty_like(k)
    e = 0.0
    for i, v in enumerate(k.tolist()):
        coef = aa if v > e else ar
        e = coef * e + (1 - coef) * v
        env[i] = e
    lvl = 20 * np.log10(np.maximum(env, 1e-9))
    over = np.maximum(lvl - thresh_db, 0)
    gain_db = -over * (1 - 1 / ratio) + makeup_db
    return x * 10 ** (gain_db / 20)


# --------------------------------------------------------------------------
# Loudness (ITU-R BS.1770 K-weighted, gated), for mono
# --------------------------------------------------------------------------

def _k_weight(x: np.ndarray) -> np.ndarray:
    # High shelf +4 dB @ ~1681 Hz and RLB high-pass @ ~38 Hz (pyloudnorm's analog prototypes)
    shelf = _rbj("highshelf", 1681.974450955533, 0.7071752369554196, 3.999843853973347)
    hpf = sg.butter(2, 38.13547087602444, "highpass", fs=SR, output="sos")
    return sg.sosfilt(hpf, sg.sosfilt(shelf, x))


def lufs(x: np.ndarray) -> float:
    y = _k_weight(x)
    blk, hop = n_of(0.4), n_of(0.1)
    if len(y) < blk:
        y = np.pad(y, (0, blk - len(y)))
    ms = np.array([np.mean(y[i:i + blk] ** 2) for i in range(0, len(y) - blk + 1, hop)])
    l = -0.691 + 10 * np.log10(np.maximum(ms, 1e-12))
    ms = ms[l > -70]
    if len(ms) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(ms)) - 10
    l = -0.691 + 10 * np.log10(np.maximum(ms, 1e-12))
    ms = ms[l > rel]
    return float(-0.691 + 10 * np.log10(np.mean(ms)))


# --------------------------------------------------------------------------
# Finishing and output
# --------------------------------------------------------------------------

def peak_of(x):
    return float(np.max(np.abs(x))) if len(x) else 0.0


def rms_of(x):
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def normalize(x: np.ndarray, peak_db: float = -3.0) -> np.ndarray:
    p = peak_of(x)
    return x * (db(peak_db) / p) if p > 0 else x


def trim_tail(x: np.ndarray, floor_db: float = -66.0, keep: float = 0.01) -> np.ndarray:
    a = np.abs(x)
    thr = peak_of(x) * db(floor_db)
    idx = np.nonzero(a > thr)[0]
    if len(idx) == 0:
        return x
    end = min(len(x), idx[-1] + n_of(keep))
    return x[:end]


def finish_oneshot(x: np.ndarray, peak_db: float = -3.0, hp_hz: float = 20.0, fin: float = 0.0008,
                   fout: float = 0.015, trim: bool = True) -> np.ndarray:
    y = hp(np.asarray(x, dtype=float), hp_hz, 2) if hp_hz else np.asarray(x, dtype=float)
    if trim:
        y = trim_tail(y)
    y = fade(y, fin, min(fout, len(y) / SR * 0.5))
    return normalize(y, peak_db)


def rotate_quiet(x: np.ndarray, win: float = 0.04) -> np.ndarray:
    """Roll a loop so it starts at its quietest moment, on an upward zero crossing.

    A circular loop stays seamless under rotation; starting quietly means a
    loop that is (re)started from 0 fades in naturally."""
    w = max(1, n_of(win))
    e = ndimage.uniform_filter1d(x * x, size=w, mode="wrap")
    y = np.roll(x, -int(np.argmin(e)))  # centre of the quietest window -> sample 0
    zc = np.nonzero((y[:w // 4] <= 0) & (y[1:w // 4 + 1] > 0))[0]
    if len(zc):
        y = np.roll(y, -int(zc[0]) - 1)
    return y


def finish_loop(x: np.ndarray, peak_db: float = -3.0, hp_hz: float = 20.0, rms_db: float | None = None,
                rotate: bool = True) -> np.ndarray:
    y = np.asarray(x, dtype=float)
    if hp_hz:
        y = loop_hp(y, hp_hz, 2)
    y = y - y.mean()
    if rotate:
        y = rotate_quiet(y)
    if rms_db is not None:
        y = y * (db(rms_db) / max(rms_of(y), 1e-12))
        if peak_of(y) > db(peak_db):
            # soft-limit the few peaks above the ceiling, circularly
            y = loop_tile_process(y, lambda z: limiter(z, peak_db, 1.5, 40.0), reps=2)
            y = y - y.mean()
        return y
    return normalize(y, peak_db)


def write_wav(name: str, x: np.ndarray, loop: bool = False, desc: str = "", extra: dict | None = None,
              dither_seed: int = 1) -> Path:
    """16-bit mono PCM. Loops get a RIFF 'smpl' chunk (Godot's importer reads it as
    the loop points). The description and stats ride along in a LIST/INFO 'ICMT'
    comment so the notes can be rebuilt from the files alone."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.wav"
    x = np.asarray(x, dtype=float)
    r = rng(dither_seed)
    d = (r.random(len(x)) - r.random(len(x)))  # TPDF, +-1 LSB
    pcm = np.clip(np.round(x * 32767.0 + d * 0.5), -32768, 32767).astype("<i2")
    if not loop:
        pcm[0] = 0
        pcm[-1] = 0
    meta = {"desc": desc, "loop": bool(loop)}
    if extra:
        meta.update(extra)
    text = json.dumps(meta).encode("ascii") + b"\0"
    if len(text) % 2:
        text += b"\0"
    info = b"INFO" + b"ICMT" + struct.pack("<I", len(text)) + text
    data = pcm.tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, SR, SR * 2, 2, 16)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if loop:
        smpl = struct.pack("<9I", 0, 0, int(1e9 / SR), 60, 0, 0, 0, 1, 0)
        smpl += struct.pack("<6I", 0, 0, 0, len(pcm), 0, 0)  # forward loop over the whole file
        chunks += b"smpl" + struct.pack("<I", len(smpl)) + smpl
    chunks += b"LIST" + struct.pack("<I", len(info)) + info
    chunks += b"data" + struct.pack("<I", len(data)) + data
    riff = b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks
    path.write_bytes(riff)
    return path


def read_meta(path: Path) -> dict:
    b = Path(path).read_bytes()
    i = b.find(b"ICMT")
    if i < 0:
        return {}
    size = struct.unpack("<I", b[i + 4:i + 8])[0]
    try:
        return json.loads(b[i + 8:i + 8 + size].rstrip(b"\0").decode("ascii"))
    except ValueError:
        return {}


def read_wav(path: Path) -> tuple[np.ndarray, int, bool]:
    b = Path(path).read_bytes()
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE"
    i = 12
    data = None
    sr = SR
    loop = False
    while i < len(b) - 8:
        cid = b[i:i + 4]
        size = struct.unpack("<I", b[i + 4:i + 8])[0]
        body = b[i + 8:i + 8 + size]
        if cid == b"fmt ":
            sr = struct.unpack("<I", body[4:8])[0]
        elif cid == b"data":
            data = np.frombuffer(body, dtype="<i2").astype(float) / 32768.0
        elif cid == b"smpl":
            loop = True
        i += 8 + size + (size & 1)
    return data, sr, loop
