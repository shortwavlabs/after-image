# SPDX-License-Identifier: AGPL-3.0-only
"""P1-A reference: the realtime contract of docs/P1-A-REALTIME-ARCHITECTURE.md in NumPy.

Built from the P0 modules, which are not modified:
  frames         p0.stft.stft (frame m covers [(m+1)H - N, (m+1)H), zeros before sample 0)
  mask           p0.capture.frequency_mask
  loop + seam    p0.engines.loop_period(..., "aligned", period=R): the P0 seam gains with the period forced
  grains         p0.granular.render, nominal_gain, grain_length, dissolve_params
  MEMORY         p0.engines.envelope
New here, and anchored to P0 by tests/test_p1a_reference.py:
  reconstruct()  FILTERED reconstruction of an arbitrary sample range (== capture_buffer on the P0 grid)
  schedule()     P0's schedule() with an injectable uniform source (== granular.schedule with PCG64)
  SplitMix64     the generator the C++ engine uses
"""
import heapq
from dataclasses import replace

import numpy as np

from p0 import capture as C, engines as E, granular as G, stft as S

SEAM_S = 0.08
ONSET_FADE_S = 0.03
MASK64 = (1 << 64) - 1


class SplitMix64:
    """Uniform doubles in [0, 1) from SplitMix64: (z >> 11) * 2^-53. Same sequence as the C++ engine."""

    def __init__(self, seed):
        self.s = seed & MASK64

    def _next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & MASK64
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def random(self, n):
        return np.array([(self._next() >> 11) * 2.0 ** -53 for _ in range(n)])


def cloud_params(fs):
    """The CLOUD configuration: P0-B dissolve_params(1.0) with pitch and octave jumps off."""
    return replace(G.dissolve_params(1.0, fs), pitch_st=0.0, octave_prob=0.0)


def seam_samples(fs):
    return int(round(SEAM_S * fs))


def reconstruct(frames, mask, N, s0, length):
    """Samples [s0, s0 + length) from masked frames by WOLA. `frames` is (M, C, K) indexed by frame id;
    every frame overlapping the range is used, so every sample is covered by four frames."""
    H = S.hop(N)
    m_lo, m_hi = s0 // H, (s0 + length - 1 + N) // H - 1
    win = S.window(N) / S.WOLA_GAIN
    out = np.zeros((length, frames.shape[1]))
    for m in range(m_lo, m_hi + 1):
        td = np.fft.irfft(frames[m] * mask, n=N, axis=-1) * win  # (C, N)
        off = (m + 1) * H - N - s0
        a, b = max(off, 0), min(off + N, length)
        out[a:b] += td[:, a - off:b - off].T
    return out


def capture_loop(x, fs, N, s0, s1, source, low_hz=0.0, high_hz=None, feather_oct=1 / 6, frames=None):
    """(loop (R, C), info) for the selection [s0, s1) with an X-sample post-roll seam. R = s1 - s0 exactly."""
    R, X = s1 - s0, seam_samples(fs)
    if source == "full":
        seg = np.asarray(x, dtype=np.float64)[s0:s0 + R + X]
    else:
        high = fs / 2 if high_hz is None else high_hz
        frames = S.stft(x, N) if frames is None else frames
        seg = reconstruct(frames, C.frequency_mask(N, fs, low_hz, high, feather_oct), N, s0, R + X)
    if len(seg) != R + X:
        raise ValueError("post-roll not available")
    loop, info = E.loop_period(seg, fs, SEAM_S, "aligned", period=R)
    return loop, {"period_samples": R, "seam_samples": X, "seam_correlation": info["seam_correlation"]}


def schedule(R, fs, n_samples, params, rng, pos_cdf=None, max_grains=G.MAX_GRAINS):
    """p0.granular.schedule with the uniform source passed in (anything with .random(n))."""
    pf = params if callable(params) else (lambda _t: params)
    t = -float(G.grain_length(pf(0.0), fs))
    rows = []
    while t < n_samples:
        p = pf(max(t, 0.0) / fs)
        u = rng.random(8)
        L = G.grain_length(p, fs)
        interval = fs / p.density_hz
        onset = int(round(t + p.jitter * (u[0] - 0.5) * interval))
        octave = 12.0 if u[2] < 0.6 * p.octave_prob else (-12.0 if u[2] < p.octave_prob else 0.0)
        speed = 2.0 ** ((p.pitch_st * (2 * u[1] - 1) + octave) / 12)
        if pos_cdf is None:
            pos = onset * p.scan + p.spray * R * (u[6] - 0.5)
        else:
            pos = float(np.searchsorted(pos_cdf, u[6])) - 0.5 * L * speed
        a = (p.spread * (2 * u[4] - 1) + 1) * np.pi / 4
        rows.append((onset, L, pos % R, speed, u[3] < p.reverse_prob, 1 - p.amp_var * u[5], G.nominal_gain(p, fs),
                     np.sqrt(2) * np.cos(a), np.sqrt(2) * np.sin(a), False))
        t += interval
    g = np.array(rows, dtype=G.GRAIN_FIELDS)
    g = g[np.argsort(g["onset"], kind="stable")]
    ends = []
    for i in range(len(g)):
        while ends and ends[0] <= g["onset"][i]:
            heapq.heappop(ends)
        if len(ends) >= max_grains:
            g["dropped"][i] = True
        else:
            heapq.heappush(ends, g["onset"][i] + g["length"][i])
    return g


def ghost(loop, fs, n, dissolve, t60, seed, params=None):
    """Ghost of one voice from its first sample: env * (cos(pi D/2) trace + sin(pi D/2) cloud). Returns (audio, grains)."""
    p = cloud_params(fs) if params is None else params
    grains = schedule(len(loop), fs, n, p, SplitMix64(seed))
    trace = loop[np.arange(n) % len(loop)]
    cloud = G.render(loop, grains, n, p.window)
    env = E.envelope(n, fs, t60, ONSET_FADE_S)
    return env * (np.cos(0.5 * np.pi * dissolve) * trace + np.sin(0.5 * np.pi * dissolve) * cloud), grains
