"""Small instrument building blocks shared by the SFX and music generators."""
from __future__ import annotations

import numpy as np

from dsp import SR, additive, env_exp, make_ir, n_of, osc, phase_of, reson, sat, tt

IR_ROOM = make_ir(1.2, decays=(1.0, 0.8, 0.55, 0.3), predelay=0.006, seed=3)
IR_HALL = make_ir(2.6, decays=(2.8, 2.3, 1.6, 0.9), predelay=0.02, seed=5)
IR_SHORT = make_ir(0.35, decays=(0.25, 0.2, 0.15, 0.1), predelay=0.002, seed=9)


def mix(*parts: np.ndarray) -> np.ndarray:
    """Sum signals of different lengths (zero padded)."""
    out = np.zeros(max(len(p) for p in parts))
    for p in parts:
        out[:len(p)] += p
    return out


def nz(n: int, r) -> np.ndarray:
    return r.standard_normal(n)


def click(r, f: float, q: float, tau: float, length: float = 0.02) -> np.ndarray:
    m = n_of(length)
    c = reson(nz(m, r), f, q) * env_exp(m, tau, 0.0002)
    return c / (np.max(np.abs(c)) + 1e-12)


def thud(f0: float, f1: float, tau: float, length: float, sweep_tau: float = 0.03, drive: float = 1.0) -> np.ndarray:
    m = n_of(length)
    t = tt(m)
    f = f1 + (f0 - f1) * np.exp(-t / sweep_tau)
    x = np.sin(2 * np.pi * phase_of(f, m)) * env_exp(m, tau, 0.001)
    if drive <= 0:
        return x
    # saturation flattens the decay, so re-impose a tail to keep the boom tight
    return sat(x, drive) * np.exp(-t / (tau * 2.5))


def blip(f0: float, f1: float, length: float, tau: float, shape: str = "sine", attack: float = 0.002,
         harmonics=((1, 1.0),)) -> np.ndarray:
    m = n_of(length)
    t = tt(m)
    f = f0 * (f1 / f0) ** np.clip(t / length, 0, 1)
    ph = phase_of(f, m)
    if shape == "sine":
        x = sum(a * np.sin(2 * np.pi * k * ph) for k, a in harmonics)
    else:
        x = osc(shape, f, m)
    return x * env_exp(m, tau, attack)


def bell(f: float, length: float, r, bright: float = 1.0, decay: float = 1.0) -> np.ndarray:
    m = n_of(length)
    parts = [(1.0, 1.0, 0.8 * decay), (2.0, 0.42 * bright, 0.45 * decay), (2.76, 0.32 * bright, 0.32 * decay),
             (4.07, 0.18 * bright, 0.16 * decay), (5.43, 0.10 * bright, 0.09 * decay), (0.5, 0.10, 1.0 * decay)]
    x = additive(f, m, parts, r)
    return x * env_exp(m, 10.0, 0.0015)


def pluck(f: float, length: float, r, tau: float = 0.35, bright: float = 1.0, nh: int = 30) -> np.ndarray:
    m = n_of(length)
    parts = [(k, (1.0 / k) * (bright ** (k - 1) if bright < 1 else 1.0), tau / (1 + 0.45 * (k - 1) / bright)) for k in range(1, nh + 1)]
    x = additive(f, m, parts, r)
    return x * env_exp(m, 10.0, 0.002)


def supersaw(freqs, length: float, r, voices: int = 7, detune_cents: float = 14.0) -> np.ndarray:
    m = n_of(length)
    out = np.zeros(m)
    for f in freqs:
        for v in range(voices):
            c = detune_cents * (v - (voices - 1) / 2) / ((voices - 1) / 2)
            out += osc("saw", f * 2 ** (c / 1200), m, r.random())
    return out / (len(freqs) * voices) ** 0.5
