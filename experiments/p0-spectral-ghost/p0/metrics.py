# SPDX-License-Identifier: AGPL-3.0-only
"""Measurement definitions shared by tests, verification and experiments.

All dB values are 20*log10 of amplitude ratios; dBFS is relative to 1.0.
"""
import hashlib

import numpy as np

EPS = 1e-300


def db(x):
    return float(20 * np.log10(max(float(x), EPS)))


def rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0


def peak(x):
    return float(np.max(np.abs(x))) if np.size(x) else 0.0


def error_db(test, ref):
    """Reconstruction error: RMS(test - ref) relative to RMS(ref), in dB.

    For an all-zero reference the result is the absolute error RMS in dBFS.
    """
    r = rms(ref)
    return db(rms(np.asarray(test) - np.asarray(ref)) / (r if r > 0 else 1.0))


def is_finite(x):
    return bool(np.all(np.isfinite(x)))


def denormal_count(x, dtype=np.float32):
    """Non-zero samples that are subnormal when stored as `dtype`."""
    a = np.abs(np.asarray(x, dtype=np.float64))
    return int(np.sum((a > 0) & (a < np.finfo(dtype).tiny)))


def crest_db(x):
    return db(peak(x) / max(rms(x), EPS))


def interchannel_corr(x):
    """Pearson correlation of L and R (1.0 for mono/identical, nan if silent)."""
    if x.ndim == 1 or x.shape[1] == 1:
        return 1.0
    l, r = x[:, 0], x[:, 1]
    d = np.sqrt(np.sum(l * l) * np.sum(r * r))
    return float(np.sum(l * r) / d) if d > 0 else float("nan")


def mono_compat_db(x):
    """RMS of the mono sum (L+R)/2 relative to pooled channel RMS, in dB.

    0 dB = fully correlated, about -3 dB = uncorrelated, -inf = anti-phase.
    """
    if x.ndim == 1 or x.shape[1] == 1:
        return 0.0
    return db(rms(x.mean(axis=1)) / max(rms(x), EPS))


def short_time_rms_db(x, fs, win_s=0.05, hop_s=0.01):
    """Hann-weighted short-time RMS (all channels pooled), in dB."""
    x = np.atleast_2d(x.T).T
    n, h = int(win_s * fs), int(hop_s * fs)
    w = np.hanning(n)
    w /= w.sum()
    p = np.mean(x ** 2, axis=1)
    out = [np.sum(p[i:i + n] * w) for i in range(0, len(p) - n + 1, h)]
    return 10 * np.log10(np.maximum(out, EPS))


def envelope_ripple_db(x, fs, start_s=0.5, **kw):
    """Peak-to-peak variation of the short-time RMS after `start_s`."""
    e = short_time_rms_db(x[int(start_s * fs):], fs, **kw)
    return float(e.max() - e.min()) if len(e) else 0.0


def click_ratio(x, seams, guard=8):
    """Largest sample-to-sample step near seam indices / largest step elsewhere.

    <= 1 means the seams are no steeper than the material itself. A hard
    discontinuity in smooth material gives a ratio far above 1.
    """
    d = np.max(np.abs(np.diff(np.atleast_2d(x.T).T, axis=0)), axis=1)
    near = np.zeros(len(d), bool)
    for s in seams:
        near[max(0, s - guard):s + guard] = True
    if not near.any() or near.all():
        return float("nan")
    return float(d[near].max() / max(d[~near].max(), EPS))


def band_energy_fraction(x, fs, low_hz, high_hz):
    """Fraction of total energy inside [low_hz, high_hz]."""
    x = np.atleast_2d(x.T).T
    p = np.sum(np.abs(np.fft.rfft(x, axis=0)) ** 2, axis=1)
    f = np.fft.rfftfreq(x.shape[0], 1 / fs)
    tot = p.sum()
    return float(p[(f >= low_hz) & (f <= high_hz)].sum() / tot) if tot > 0 else float("nan")


def log_spectral_distance_db(a, b, fs, bands_per_oct=3, fmin=40.0):
    """RMS level difference (dB) between the long-term fractional-octave band
    spectra of two signals, each normalised to its own total energy.

    Only bands holding at least -30 dB of the total energy in either signal are
    compared, and band levels are floored at -40 dB, so near-empty bands cannot
    dominate. A coarse timbre distance: 0 = same average spectral shape. It is
    blind to temporal structure.
    """
    def bands(x):
        x = np.atleast_2d(x.T).T
        p = np.sum(np.abs(np.fft.rfft(x * np.hanning(x.shape[0])[:, None], axis=0)) ** 2, axis=1)
        f = np.fft.rfftfreq(x.shape[0], 1 / fs)
        edges = fmin * 2 ** (np.arange(0, np.log2(fs / 2 / fmin) * bands_per_oct + 1) / bands_per_oct)
        e = np.array([p[(f >= lo) & (f < hi)].sum() for lo, hi in zip(edges[:-1], edges[1:])])
        return e / max(e.sum(), EPS)
    ea, eb = bands(a), bands(b)
    keep = (ea > 1e-3) | (eb > 1e-3)
    if not keep.any():
        return float("nan")
    la, lb = 10 * np.log10(np.maximum(ea[keep], 1e-4)), 10 * np.log10(np.maximum(eb[keep], 1e-4))
    return float(np.sqrt(np.mean((la - lb) ** 2)))


def sine_frequency(x, fs):
    """Frequency of a single dominant sinusoid via phase regression (mono)."""
    x = np.asarray(x, dtype=np.float64)
    X = np.fft.rfft(x * np.hanning(len(x)))
    k = int(np.argmax(np.abs(X)))
    f0 = k * fs / len(x)
    n = np.arange(len(x))
    z = x * np.exp(-2j * np.pi * f0 * n / fs)  # demodulate, then low-pass by block mean
    blk = max(int(fs * 0.01), 1)
    zb = z[:len(z) // blk * blk].reshape(-1, blk).mean(axis=1)
    ph = np.unwrap(np.angle(zb))
    slope = np.polyfit(np.arange(len(ph)) * blk / fs, ph, 1)[0]
    return float(f0 + slope / (2 * np.pi))


def sha256(x, dtype=np.float32):
    return hashlib.sha256(np.ascontiguousarray(x, dtype=dtype).tobytes()).hexdigest()
