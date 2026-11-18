# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic synthetic stereo fixtures (original code, no samples).

They are stand-ins with the *signal properties* of the target sources
(plucked decaying harmonics, vibrato + formants, percussive transients,
dense detuned sustain). They are not recordings and do not replace the
listening test on real guitar/voice/drums/synth.

Every fixture is 4.0 s, stereo, additive/bandlimited, peak-normalised to
-6 dBFS, and fully determined by (name, fs).
"""
from functools import lru_cache

import numpy as np
from scipy.signal import butter, sosfilt

DURATION_S = 4.0
PEAK = 10 ** (-6 / 20)
SEEDS = {"guitar": 101, "vocal": 202, "drums": 303, "synth": 404}


def _pan(mono, pan):
    """Constant-power pan, pan in [-1, 1]."""
    a = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(a), mono * np.sin(a)], axis=1)


def _finish(x):
    return x * (PEAK / np.max(np.abs(x)))


def guitar(fs, rng):
    """Two strummed six-string chords: inharmonic partials with frequency-
    dependent decay plus a short pick-noise burst per string."""
    n = int(DURATION_S * fs)
    out = np.zeros((n, 2))
    notes = [82.41, 123.47, 164.81, 207.65, 246.94, 329.63]  # E2 B2 E3 G#3 B3 E4
    for strum_t in (0.25, 2.0):
        for i, f0 in enumerate(notes):
            start = int((strum_t + 0.012 * i) * fs)
            t = np.arange(n - start) / fs
            s = np.zeros_like(t)
            for h in range(1, int(0.45 * fs / f0) + 1):
                f = f0 * h * np.sqrt(1 + 2e-4 * h * h)
                if f > 0.45 * fs or h > 60:
                    break
                amp = np.sin(np.pi * h * 0.18) / h  # pluck position comb
                s += amp * np.exp(-t * (0.8 + 0.25 * h)) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
            pick = rng.standard_normal(len(t)) * np.exp(-t / 0.004) * 0.3
            out[start:] += _pan(s + pick, -0.5 + i * 0.2)
    return _finish(out)


def vocal(fs, rng):
    """Sung vowel: harmonic source with vibrato and a slow pitch glide, shaped
    by three formants that morph from 'ah' to 'ee', plus faint breath noise."""
    n = int(DURATION_S * fs)
    t = np.arange(n) / fs
    f0 = 180 * 2 ** (t / DURATION_S * 2 / 12) * (1 + 0.01 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f0) / fs
    mix = np.clip((t - 1.5) / 1.5, 0, 1)
    formants = [(700, 300, 110), (1200, 2300, 140), (2600, 3000, 180)]  # (ah Hz, ee Hz, bandwidth)
    s = np.zeros(n)
    for h in range(1, int(0.45 * fs / 210) + 1):
        if h > 70:
            break
        fh = h * f0
        gain = sum(1 / (1 + ((fh - (a + (b - a) * mix)) / bw) ** 2) for a, b, bw in formants)
        s += gain / np.sqrt(h) * np.sin(h * phase)
    env = np.minimum(1, t / 0.08) * np.minimum(1, (DURATION_S - t) / 0.3)
    breath = sosfilt(butter(2, [2000, 7000], "bandpass", fs=fs, output="sos"), rng.standard_normal((n, 2)), axis=0)
    out = np.stack([s, s], axis=1) * env[:, None]
    out += 0.02 * np.max(np.abs(out)) * breath * env[:, None]
    return _finish(out)


def drums(fs, rng):
    """120 BPM pattern: kick (pitch-swept sine), snare (tone + band noise),
    closed hats (high-passed noise bursts)."""
    n = int(DURATION_S * fs)
    out = np.zeros((n, 2))

    def add(sig, at_s, pan):
        i = int(at_s * fs)
        m = min(len(sig), n - i)
        out[i:i + m] += _pan(sig[:m], pan)

    t = np.arange(int(0.5 * fs)) / fs
    kick = np.sin(2 * np.pi * (50 * t + (150 - 50) * 0.03 * (1 - np.exp(-t / 0.03)))) * np.exp(-t / 0.12)
    hp = butter(4, 6000, "highpass", fs=fs, output="sos")
    bp = butter(2, [1000, 6000], "bandpass", fs=fs, output="sos")
    for beat in range(8):
        at = beat * 0.5
        if beat % 2 == 0:
            add(kick, at, 0.0)
        else:
            sn = 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
            sn += sosfilt(bp, rng.standard_normal(len(t))) * np.exp(-t / 0.09) * 0.6
            add(sn, at, -0.2)
        for sub in (0.0, 0.25):
            hat = sosfilt(hp, rng.standard_normal(len(t))) * np.exp(-t / 0.025) * 0.35
            add(hat, at + sub, 0.4)
    return _finish(out)


def synth(fs, rng):
    """Cmaj7 pad: two detuned saws per note, hard-panned, with a slow low-pass
    sweep applied to the harmonic amplitudes."""
    n = int(DURATION_S * fs)
    t = np.arange(n) / fs
    cutoff = 1800 + 1400 * np.sin(2 * np.pi * 0.2 * t)
    out = np.zeros((n, 2))
    for f0 in (130.81, 164.81, 196.00, 246.94):
        for det, ch in ((-0.004, 0), (0.004, 1)):
            f = f0 * (1 + det)
            ph0 = rng.uniform(0, 2 * np.pi)
            for h in range(1, 61):
                if h * f > 0.45 * fs:
                    break
                out[:, ch] += np.sin(h * (2 * np.pi * f * t + ph0)) / h / (1 + (h * f / cutoff) ** 4)
    env = np.minimum(1, t / 0.2) * np.minimum(1, (DURATION_S - t) / 0.4)
    return _finish(out * env[:, None])


_BUILDERS = {"guitar": guitar, "vocal": vocal, "drums": drums, "synth": synth}
NAMES = tuple(_BUILDERS)


@lru_cache(maxsize=None)
def make(name, fs):
    x = _BUILDERS[name](fs, np.random.default_rng(SEEDS[name]))
    x.setflags(write=False)
    return x
