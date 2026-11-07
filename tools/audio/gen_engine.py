"""Power unit sounds: V6 turbo-hybrid engine layers, overrun, idle, pit limiter, turbo, MGU-K, shifts.

    python tools/audio/gen_engine.py

Each engine layer is a seamless loop "recorded" at one rpm. The game pitches a
layer by rpm / layer_rpm and crossfades neighbouring layers. A 4-stroke V6
fires 3 times per crank revolution, so the firing frequency is rpm / 60 * 3 Hz;
a full engine cycle (all six cylinders) is two revolutions. The loop length is
a whole number of cycles, every cylinder has its own small amplitude/timing
signature (that gives the half-order growl), each firing has a little random
variation on top, and everything is rendered circularly so the loop is exact.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

import numpy as np

from dsp import (SR, add_at, add_circ, db, env_exp, fade, finish_loop, finish_oneshot, hp, loop_bp,
                 loop_filt, loop_hp, loop_lp, loop_peak, lp, n_of, noise_shaped, peak, phase_of, pink, rng, sat,
                 smooth_mod, sos_peak, tt, white, write_wav, bp, reson)

# rpm each layer is rendered at (the exact value is chosen so that one engine
# cycle is a whole number of samples; car_audio.gd uses these numbers).
LAYERS = {
    "engine_low": dict(rpm=4000, seconds=1.5, seed=11, ta=0.20e-3, td=0.26, td_var=0.18, cyl_var=0.24, pulse_var=0.10,
                       jit=0.012, rebound=0.30, grit=0.30, intake=0.30, drive=1.8, lp_hz=5600, bank=0.16,
                       body=(160, 1.0, 4.0), pres=(1400, 1.2, 2.0), comb=(0.0024, 0.25)),
    "engine_mid": dict(rpm=7500, seconds=1.5, seed=12, ta=0.13e-3, td=0.24, td_var=0.15, cyl_var=0.19, pulse_var=0.07,
                       jit=0.008, rebound=0.30, grit=0.36, intake=0.22, drive=2.2, lp_hz=8500, bank=0.14,
                       body=(240, 1.0, 3.0), pres=(2200, 1.0, 3.0), comb=(0.0021, 0.25)),
    "engine_high": dict(rpm=11000, seconds=1.5, seed=13, ta=0.09e-3, td=0.22, td_var=0.12, cyl_var=0.15, pulse_var=0.05,
                        jit=0.006, rebound=0.30, grit=0.42, intake=0.18, drive=2.6, lp_hz=11000, bank=0.12,
                        body=(300, 1.0, 3.0), pres=(3000, 0.9, 3.5), comb=(0.0017, 0.25)),
}


def exact_rpm(rpm: float) -> tuple[int, float]:
    nc = int(round(SR * 120.0 / rpm))  # samples per engine cycle (720 deg)
    return nc, SR * 120.0 / nc


def pulse(tau: np.ndarray, ta: float, td: float) -> np.ndarray:
    """Exhaust pressure pulse: raised-cosine rise over ta samples, exponential decay td."""
    tc = np.maximum(tau, 0.0)
    rise = np.where(tc < ta, 0.5 - 0.5 * np.cos(np.pi * tc / ta), 1.0)
    v = rise * np.exp(-np.maximum(tc - ta, 0.0) / td)
    v[tau < 0] = 0.0
    return v


def render_train(n: int, times: np.ndarray, amps: np.ndarray, ta: float, td, span: int,
                 circular: bool = True, rebound: float = 0.0, rb_delay: float = 0.0, rb_td: float = 1.0) -> np.ndarray:
    """Sum of pulses at fractional sample times; td may be a scalar or one value per pulse."""
    out = np.zeros(n)
    tds = np.broadcast_to(np.asarray(td, dtype=float), (len(times),))
    for t0, a, d in zip(times, amps, tds):
        if a == 0:
            continue
        i0 = int(np.floor(t0))
        tau = np.arange(span) + i0 - t0
        v = pulse(tau, ta, d)
        if rebound:
            v = v - rebound * pulse(tau - rb_delay, rb_delay * 0.6, rb_td)
        if circular:
            add_circ(out, i0, a * v)
        else:
            add_at(out, i0, a * v)
    return out


def comb_response(x: np.ndarray, delay_s: float, g: float, damp_hz: float = 3500.0) -> np.ndarray:
    """Exhaust pipe reflection: circular feedback comb with a damped loop, exact in the FFT domain."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    loss = g / np.sqrt(1 + (f / damp_hz) ** 2)
    h = 1.0 / (1.0 - loss * np.exp(-2j * np.pi * f * delay_s))
    h /= np.max(np.abs(h))
    return np.fft.irfft(np.fft.rfft(x) * h, n)


def engine_render(cfg: dict, nc: int, k_cycles: int, amp_mod=None, time_mod=None) -> np.ndarray:
    """k_cycles engine cycles of nc samples each, with the layers' timbre (before finishing).

    amp_mod(times, n) -> a gain per firing (ignition cuts), time_mod(base_t, n) -> a time offset
    per firing in samples (rpm hunting / bouncing). The hooks bring their own random streams, so
    without them this renders exactly what it always has."""
    r = rng(cfg["seed"])
    n = nc * k_cycles
    tf = nc / 6.0  # samples between firings
    nf = 6 * k_cycles
    cyl = np.arange(nf) % 6
    bank = cyl % 2  # alternate banks of the 90 degree V

    cyl_amp = 1.0 + cfg["cyl_var"] * r.standard_normal(6)
    cyl_off = cfg["jit"] * 2.5 * tf * r.standard_normal(6)
    # slow combustion breathing, periodic over the loop
    breath = smooth_mod(n, r, 1.5, 7.0)
    warp = smooth_mod(n, r, 2.0, 9.0) * tf * 0.05
    base_t = np.arange(nf) * tf
    bi = (base_t.astype(int)) % n
    amps = cyl_amp[cyl] * (1.0 + cfg["pulse_var"] * r.standard_normal(nf)) * (1.0 + 0.07 * breath[bi])
    amps *= 1.0 + cfg["bank"] * (bank - 0.5)
    times = base_t + cyl_off[cyl] + cfg["jit"] * tf * r.standard_normal(nf) + warp[bi]
    if time_mod is not None:
        times = times + time_mod(base_t, n)
    if amp_mod is not None:
        amps = amps * amp_mod(times, n)

    ta = cfg["ta"] * SR
    cyl_td = 1.0 + cfg["td_var"] * r.standard_normal(6)
    td = cfg["td"] * tf * cyl_td[cyl]
    span = int(tf * 4)
    tone = render_train(n, times, amps, ta, td, span, rebound=cfg["rebound"], rb_delay=tf * 0.5, rb_td=tf * 0.4)
    # bank B exhaust runs are a touch longer: a slightly delayed echo of its own pulses
    echo_amps = np.where(bank == 1, amps * 0.22, amps * 0.12)
    tone += render_train(n, times + tf * 0.31, echo_amps, ta * 1.5, td * 0.8, span)
    tone -= tone.mean()
    tone = comb_response(tone, cfg["comb"][0], cfg["comb"][1])
    tone /= np.max(np.abs(tone))

    # combustion grit: noise bursts gated by each firing
    fire_env = render_train(n, times, amps ** 2, 0.00008 * SR, tf * 0.30, span)
    fire_env /= np.max(fire_env)
    grit_src = loop_bp(white(n, r), 1200, 7500, 2)
    grit = grit_src * fire_env
    grit /= np.max(np.abs(grit)) + 1e-12

    # intake roar: broadband pink noise pulsing with the firing
    intake = loop_bp(pink(n, r), 180, 2200, 2) * (0.55 + 0.45 * fire_env)
    intake /= np.max(np.abs(intake)) + 1e-12

    x = tone + cfg["grit"] * grit + cfg["intake"] * intake
    x = x / np.max(np.abs(x))
    # a pre-emphasis before the saturator so the upper mids fold into rasp
    x = loop_peak(x, 1800, 0.8, 4.0)
    x = x / np.max(np.abs(x))
    x = sat(x, cfg["drive"])
    f, q, g = cfg["body"]
    x = loop_peak(x, f, q, g)
    f, q, g = cfg["pres"]
    x = loop_peak(x, f, q, g)
    x = loop_lp(x, cfg["lp_hz"], 4)
    x = loop_hp(x, 32, 2)
    return x


def engine_layer(name: str, cfg: dict) -> dict:
    nc, rpm = exact_rpm(cfg["rpm"])
    k_cycles = int(round(cfg["seconds"] * SR / nc))
    x = engine_render(cfg, nc, k_cycles)
    x = finish_loop(x, -4.5, 25, rms_db=-13.0)  # crest ~8.5 dB: dense, leaves headroom in the mix
    write_wav(name, x, loop=True,
              desc=f"On-throttle engine layer at {rpm:.2f} rpm (firing {rpm / 20:.1f} Hz). Pitch = rpm / {rpm:.2f}.",
              extra={"rpm": round(rpm, 3)})
    return {"rpm": rpm, "frames": nc * k_cycles}


def engine_off() -> dict:
    """Overrun / lift-off: weak, irregular combustion with crackles and pops. Rendered at ~8000 rpm."""
    r = rng(21)
    nc, rpm = exact_rpm(8000)
    k_cycles = int(round(2.0 * SR / nc))
    n = nc * k_cycles
    tf = nc / 6.0
    nf = 6 * k_cycles
    cyl = np.arange(nf) % 6
    cyl_amp = 1.0 + 0.18 * r.standard_normal(6)
    amps = cyl_amp[cyl] * np.exp(0.45 * r.standard_normal(nf)) * 0.35
    miss = r.random(nf) < 0.22
    amps[miss] = 0.0
    breath = smooth_mod(n, r, 0.8, 5.0)
    bi = (np.arange(nf) * tf).astype(int) % n
    amps *= 1.0 + 0.35 * breath[bi]
    times = np.arange(nf) * tf + 0.03 * tf * r.standard_normal(nf)
    tone = render_train(n, times, amps, 0.5e-3 * SR, tf * 0.55, int(tf * 4), rebound=0.5, rb_delay=tf * 0.45, rb_td=tf * 0.6)
    tone -= tone.mean()
    tone = comb_response(tone, 0.0023, 0.45, 2000)
    tone = loop_lp(tone, 2200, 2)
    tone /= np.max(np.abs(tone))
    # low burble: sub-harmonic wobble from the irregular firing
    burble = loop_lp(tone, 380, 2) * 1.2

    # intake / exhaust whoosh, lower than on-throttle
    air = loop_bp(pink(n, r), 150, 1500, 2) * (0.6 + 0.4 * (1 + breath) / 2) * 0.22

    pops = np.zeros(n)
    pop_times = np.sort(r.uniform(0, n, 7))
    for i, pt in enumerate(pop_times):
        strength = r.uniform(0.5, 1.0)
        m = n_of(0.06)
        t = tt(m)
        crack = bp(r.standard_normal(m), 900, 6500, 2) * np.exp(-t / r.uniform(0.003, 0.007))
        crack = crack / (np.max(np.abs(crack)) + 1e-12)
        thump = np.sin(2 * np.pi * (95 * t - 300 * t * t)) * np.exp(-t / 0.018)
        p = (crack * 1.0 + thump * 0.55) * strength
        p *= np.clip(t / 0.0004, 0, 1)
        add_circ(pops, int(pt), p * 2.2)
        if r.random() < 0.5:  # double pop
            add_circ(pops, int(pt + r.uniform(0.018, 0.04) * SR), p * 1.1 * r.uniform(0.4, 0.8))
    # little crackle sprinkles between the pops
    crackle = np.zeros(n)
    for ct in r.uniform(0, n, 40):
        m = n_of(0.006)
        c = hp(r.standard_normal(m), 2500, 2) * np.exp(-tt(m) / 0.0012) * r.uniform(0.1, 0.5)
        add_circ(crackle, int(ct), c)

    x = tone * 0.8 + burble * 0.6 + air + pops * 0.9 + crackle * 0.6
    x = x / np.max(np.abs(x))
    x = sat(x, 1.4)
    x = loop_peak(x, 220, 1.0, 3.0)
    x = finish_loop(x, -3.0, 28, rms_db=-19.0)
    write_wav("engine_off", x, loop=True,
              desc=f"Overrun / lift-off burble with crackles and pops at {rpm:.2f} rpm. Pitch = rpm / {rpm:.2f}.",
              extra={"rpm": round(rpm, 3)})
    return {"rpm": rpm}


def turbo_whine() -> None:
    r = rng(31)
    n = SR  # 1 s: integer-Hz partials and LFOs repeat exactly
    t = tt(n)
    f0 = 3150.0
    wob = 0.0035 * np.sin(2 * np.pi * 5 * t) + 0.002 * smooth_mod(n, r, 1, 4) + 0.0012 * np.sin(2 * np.pi * 23 * t)
    ph = phase_of(f0 * (1 + wob), n)
    x = np.sin(2 * np.pi * ph) * 1.0
    x += 0.16 * np.sin(2 * np.pi * 2 * ph + 0.4)
    x += 0.05 * np.sin(2 * np.pi * 3 * ph + 1.1)
    # compressor blade-pass shimmer: narrow noise band around the whistle
    band = loop_bp(white(n, r), f0 * 0.93, f0 * 1.07, 2) * 0.35
    hiss = loop_bp(white(n, r), 1800, 9000, 2) * 0.12
    am = 1 + 0.06 * np.sin(2 * np.pi * 7 * t) + 0.04 * smooth_mod(n, r, 2, 9)
    x = (x + band + hiss) * am
    x = finish_loop(x, -3.0, 200)
    write_wav("turbo_whine", x, loop=True, desc=f"Turbo whistle ({f0:.0f} Hz) with wobble; pitch follows turbo speed.",
              extra={"hz": f0})


def electric_whine() -> None:
    r = rng(32)
    n = SR
    t = tt(n)
    f0 = 520.0
    ph = phase_of(f0 * (1 + 0.0015 * np.sin(2 * np.pi * 3 * t)), n)
    x = (np.sin(2 * np.pi * ph) + 0.42 * np.sin(2 * np.pi * 2 * ph + 0.3) + 0.55 * np.sin(2 * np.pi * 3 * ph + 1.0)
         + 0.18 * np.sin(2 * np.pi * 6 * ph + 2.0) + 0.10 * np.sin(2 * np.pi * 9 * ph + 0.7))
    # inverter PWM carrier with motor sidebands
    fc = 4160.0
    for k, a in ((0, 0.10), (-2, 0.07), (2, 0.07), (-4, 0.03), (4, 0.03)):
        x += a * np.sin(2 * np.pi * (fc * t + k * ph))
    x += loop_bp(white(n, r), 6000, 12000, 2) * 0.012
    x *= 1 + 0.03 * np.sin(2 * np.pi * 12 * t)
    x = finish_loop(x, -3.0, 120)
    write_wav("electric_whine", x, loop=True, desc=f"MGU-K / Boost electric whine ({f0:.0f} Hz fundamental); pitch follows speed.",
              extra={"hz": f0})


def burst(rpm0: float, rpm1: float, seconds: float, seed: int, amp_env, ta_ms=0.2, td_frac=0.42) -> np.ndarray:
    """Non-looping firing train sweeping rpm0 -> rpm1 (for blips)."""
    r = rng(seed)
    n = n_of(seconds)
    times, amps = [], []
    t = 0.0
    while t < n:
        frac = t / n
        rpm = rpm0 + (rpm1 - rpm0) * frac
        tf = SR * 20.0 / rpm
        times.append(t + r.normal(0, 0.01) * tf)
        amps.append(float(amp_env(frac)) * (1 + 0.1 * r.standard_normal()))
        t += tf
    tf_mid = SR * 20.0 / ((rpm0 + rpm1) / 2)
    x = render_train(n, np.array(times), np.array(amps), ta_ms * 1e-3 * SR, tf_mid * td_frac, int(tf_mid * 4), circular=False,
                     rebound=0.4, rb_delay=tf_mid * 0.42, rb_td=tf_mid * 0.5)
    return x - np.mean(x)


def shift_up() -> None:
    r = rng(41)
    n = n_of(0.085)
    t = tt(n)
    # ignition cut "bap": a hard pop as unburnt mixture lights in the exhaust
    crack = bp(r.standard_normal(n), 700, 5000, 2) * np.exp(-t / 0.006)
    crack /= np.max(np.abs(crack))
    thump = np.sin(2 * np.pi * (120 * t - 260 * t * t)) * np.exp(-t / 0.016)
    # dog-ring engagement click a few ms later
    click = np.zeros(n)
    m = n_of(0.01)
    c = reson(r.standard_normal(m), 3400, 6) * np.exp(-tt(m) / 0.0015)
    add_at(click, n_of(0.022), c / np.max(np.abs(c)))
    tail = burst(10500, 9300, 0.085, 42, lambda f: 0.25 * np.clip((f - 0.35) / 0.3, 0, 1))
    tail /= np.max(np.abs(tail)) + 1e-12
    x = crack * 1.0 + thump * 0.6 + click * 0.5 + tail * 0.2
    x = sat(x / np.max(np.abs(x)), 1.6)
    write_wav("shift_up", finish_oneshot(x, -3.0, 40, 0.0003, 0.012), desc="Upshift: ignition-cut bap + dog-ring click (85 ms).")


def shift_down() -> None:
    r = rng(43)
    n = n_of(0.3)
    blip = burst(8200, 10800, 0.16, 44, lambda f: np.sin(np.pi * min(f * 1.15, 1.0)) ** 0.7)
    blip = lp(blip, 7000, 2)
    blip /= np.max(np.abs(blip))
    x = np.zeros(n)
    add_at(x, 0, blip * 0.85)
    for when, s in ((0.15, 1.0), (0.205, 0.6), (0.245, 0.35)):
        m = n_of(0.05)
        t = tt(m)
        crack = bp(r.standard_normal(m), 900, 6500, 2) * np.exp(-t / 0.005)
        crack /= np.max(np.abs(crack))
        thump = np.sin(2 * np.pi * (100 * t - 200 * t * t)) * np.exp(-t / 0.015)
        add_at(x, n_of(when), (crack + 0.6 * thump) * s)
    x = sat(x / np.max(np.abs(x)), 1.5)
    write_wav("shift_down", finish_oneshot(x, -3.0, 40, 0.002, 0.02), desc="Downshift: throttle blip (rev match) and exhaust pops (300 ms).")


# --------------------------------------------------------------------------
# Idle, pit limiter and one-shot revs (race mode)
# --------------------------------------------------------------------------

# Idle: low load, so slower pulse decay, lumpier cylinders, less grit and intake, darker.
IDLE = dict(rpm=4000, seconds=3.0, seed=14, ta=0.30e-3, td=0.30, td_var=0.22, cyl_var=0.30, pulse_var=0.17,
            jit=0.02, rebound=0.34, grit=0.15, intake=0.15, drive=1.5, lp_hz=4300, bank=0.22,
            body=(125, 1.0, 5.0), pres=(1050, 1.2, 1.5), comb=(0.0027, 0.32))
# Pit limiter: the mid layer's character at 9000 rpm (a whole number of cycles in 2 s), a little less drive.
PIT = dict(LAYERS["engine_mid"], rpm=9000, seconds=2.0, seed=15, drive=2.0, intake=0.28, grit=0.32)
PIT_CUT_HZ = 4.0


def hunt(seed: int, depth: float, f_lo: float, f_hi: float):
    """time_mod hook: the rpm wanders by about +-depth (periodic over the loop)."""
    def fn(base_t: np.ndarray, n: int) -> np.ndarray:
        dev = smooth_mod(n, rng(seed), f_lo, f_hi) * depth
        dev -= dev.mean()
        off = -np.cumsum(dev)  # a faster engine fires earlier
        off -= off.mean()
        return off[base_t.astype(int) % n]
    return fn


def mech_layer(n: int, nc: int, r, hunt_fn, whine_hz: float) -> np.ndarray:
    """Valvetrain ticks (one per firing) and a faint gear-drive whine, audible at idle."""
    t = tt(n)
    tf = nc / 6.0
    base = np.arange(int(round(n / tf))) * tf
    ticks = np.zeros(n)
    when = base + 0.37 * tf + hunt_fn(base, n)
    for k, w in enumerate(when):
        m = n_of(0.004)
        c = reson(r.standard_normal(m), r.uniform(4200, 6800), 9) * np.exp(-tt(m) / 0.0007)
        add_circ(ticks, int(w), c * (0.6 + 0.4 * r.random()) * (1.3 if k % 6 == 0 else 1.0))
    ticks /= np.max(np.abs(ticks)) + 1e-12
    whine = np.sin(2 * np.pi * whine_hz * t) * (0.7 + 0.3 * smooth_mod(n, r, 0.4, 2.0))
    hyd = loop_bp(white(n, r), 5200, 8500, 2)
    hyd /= np.max(np.abs(hyd))
    return ticks * 0.10 + whine * 0.025 + hyd * 0.012


def engine_idle() -> dict:
    """Idling V6 for the grid and the pit box: lumpy, hunting idle with valvetrain noise."""
    nc, rpm = exact_rpm(IDLE["rpm"])
    k = int(round(IDLE["seconds"] * SR / nc))
    h = hunt(141, 0.022, 0.5, 2.2)
    x = engine_render(IDLE, nc, k, time_mod=h)
    x /= np.max(np.abs(x))
    # gear-drive whine at 27x crank speed: a whole number of cycles in the loop
    x += mech_layer(len(x), nc, rng(142), h, rpm / 60.0 * 27)
    x = finish_loop(x, -4.5, 25, rms_db=-13.0)
    write_wav("engine_idle", x, loop=True,
              desc=f"Idling V6 at {rpm:.2f} rpm: lumpy, slightly hunting idle with valvetrain ticks. Pitch = rpm / {rpm:.2f}.",
              extra={"rpm": round(rpm, 3)})
    return {"rpm": rpm}


def pit_limiter() -> dict:
    """Engine bouncing off the pit-lane speed limiter: the ignition is cut about 4 times a second."""
    nc, rpm = exact_rpm(PIT["rpm"])
    k = int(round(PIT["seconds"] * SR / nc))
    n = nc * k
    periods = int(round(n / SR * PIT_CUT_HZ))
    period = n / periods
    tf = nc / 6.0
    rr = rng(151)
    on_frac = rr.uniform(0.56, 0.68, periods)  # share of each period that fires

    def amp_mod(times: np.ndarray, n_: int) -> np.ndarray:
        tm = times % n_
        idx = np.minimum((tm // period).astype(int), periods - 1)
        ph = (tm - idx * period) / period
        on = ph < on_frac[idx]
        g = np.where(on, 1.0, 0.0)
        part = (~on) & (rr.random(len(times)) < 0.22)  # a few cylinders still light during the cut
        g[part] = rr.uniform(0.12, 0.4, int(part.sum()))
        g[on & (ph * period < 1.5 * tf)] *= 1.3  # first bang after the cut
        return g

    def time_mod(base_t: np.ndarray, n_: int) -> np.ndarray:
        # rpm climbs about 2 % through each burst and sags in the cut (zero mean per period)
        pos = np.arange(n_)
        idx = np.minimum((pos // period).astype(int), periods - 1)
        ph = (pos - idx * period) / period
        on = on_frac[idx]
        dev = np.where(ph < on, 0.02, -0.02 * on / (1 - on))
        dev = loop_lp(dev, 25, 1)
        dev -= dev.mean()
        off = -np.cumsum(dev)
        off -= off.mean()
        return off[base_t.astype(int) % n_]

    x = engine_render(PIT, nc, k, amp_mod=amp_mod, time_mod=time_mod)
    # intake and pipe ring would carry on through the cut; duck them so the stutter reads clearly
    pos = np.arange(n)
    idx = np.minimum((pos // period).astype(int), periods - 1)
    gate = np.where((pos - idx * period) / period < on_frac[idx], 1.0, 0.5)
    x = x * loop_lp(gate, 40, 1)
    x /= np.max(np.abs(x))
    pops = np.zeros(n)
    rp = rng(152)
    for p in range(periods):
        cut0 = (p + on_frac[p]) * period
        cut_len = (1 - on_frac[p]) * period
        if rp.random() < 0.7:
            m = n_of(0.05)
            t = tt(m)
            crack = bp(rp.standard_normal(m), 900, 6500, 2) * np.exp(-t / rp.uniform(0.003, 0.006))
            crack /= np.max(np.abs(crack)) + 1e-12
            thump = np.sin(2 * np.pi * (100 * t - 250 * t * t)) * np.exp(-t / 0.016)
            add_circ(pops, int(cut0 + rp.uniform(0.15, 0.6) * cut_len), (crack + 0.5 * thump) * rp.uniform(0.35, 0.7))
        for _ in range(int(rp.integers(2, 6))):
            m = n_of(0.005)
            c = hp(rp.standard_normal(m), 2500, 2) * np.exp(-tt(m) / 0.001) * rp.uniform(0.08, 0.3)
            add_circ(pops, int(cut0 + rp.uniform(0, cut_len)), c)
    x = sat(x + pops * 0.8, 1.2)
    # start mid-burst (steady firing) on an upward zero crossing rather than in the quietest spot,
    # which here would be inside a cut, where the spectrum is changing fastest
    start = int(0.3 * on_frac[0] * period)
    zc = np.nonzero((x[start:start + 2000] <= 0) & (x[start + 1:start + 2001] > 0))[0]
    start += int(zc[0]) + 1 if len(zc) else 0
    x = finish_loop(np.roll(x, -start), -3.0, 25, rms_db=-14.0, rotate=False)
    write_wav("pit_limiter", x, loop=True,
              desc=(f"Pit limiter: engine at {rpm:.0f} rpm bouncing off the speed limiter, ignition cut "
                    f"{PIT_CUT_HZ:.0f} times a second with pops. Pitch 1 at pit speed (or rpm / {rpm:.0f})."),
              extra={"rpm": round(rpm, 3), "cut_hz": PIT_CUT_HZ})
    return {"rpm": rpm}


def sweep_train(rpm_fn, amp_fn, seconds: float, seed: int, ta_ms: float = 0.14, td_frac: float = 0.25) -> np.ndarray:
    """One-shot firing train following rpm_fn(t) and amp_fn(t) (t in seconds); raw pulses."""
    r = rng(seed)
    n = n_of(seconds)
    cyl_amp = 1.0 + 0.16 * r.standard_normal(6)
    times, amps, tds = [], [], []
    t, i = 0.0, 0
    while t < n:
        tf = SR * 20.0 / rpm_fn(t / SR)
        times.append(t + r.normal(0, 0.008) * tf)
        amps.append(float(amp_fn(t / SR)) * cyl_amp[i % 6] * (1 + 0.07 * r.standard_normal()))
        tds.append(td_frac * tf)
        t += tf
        i += 1
    tf_ref = SR * 20.0 / rpm_fn(seconds * 0.5)
    span = int(SR * 20.0 / min(rpm_fn(0.0), rpm_fn(seconds * 0.5)) * 4)
    x = render_train(n, np.array(times), np.array(amps), ta_ms * 1e-3 * SR, np.array(tds), span, circular=False,
                     rebound=0.3, rb_delay=tf_ref * 0.5, rb_td=tf_ref * 0.4)
    return x - np.mean(x)


def colour_oneshot(x: np.ndarray, cfg: dict, seed: int = 0) -> np.ndarray:
    """The layers' exhaust and saturation chain for a one-shot firing train."""
    r = rng(seed)
    pad = n_of(0.08)
    y = np.concatenate([x, np.zeros(pad)])
    y = comb_response(y, cfg["comb"][0], cfg["comb"][1])[:len(x)]
    y /= np.max(np.abs(y)) + 1e-12
    env = lp(np.maximum(y, 0.0) ** 2, 400, 1)
    env /= np.max(env) + 1e-12
    grit = bp(r.standard_normal(len(y)), 1200, 7500, 2) * env
    grit /= np.max(np.abs(grit)) + 1e-12
    y = y + cfg["grit"] * grit
    y = peak(y / np.max(np.abs(y)), 1800, 0.8, 4.0)
    y = sat(y / np.max(np.abs(y)), cfg["drive"])
    f, q, g = cfg["body"]
    y = peak(y, f, q, g)
    f, q, g = cfg["pres"]
    y = peak(y, f, q, g)
    y = lp(y, cfg["lp_hz"], 4)
    return hp(y, 32, 2)


def main() -> None:
    info = {}
    for name, cfg in LAYERS.items():
        info[name] = engine_layer(name, cfg)
    info["engine_off"] = engine_off()
    info["engine_idle"] = engine_idle()
    info["pit_limiter"] = pit_limiter()
    turbo_whine()
    electric_whine()
    shift_up()
    shift_down()
    for k, v in info.items():
        print(f"{k}: {v['rpm']:.3f} rpm")


if __name__ == "__main__":
    main()
