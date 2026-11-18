# SPDX-License-Identifier: AGPL-3.0-only
"""P0-B: spectral capture feeding time-domain granular synthesis.

  capture_buffer()   selected T-F region -> time-domain buffer (context frames
                     reconstruct the whole selection, nothing outside it is kept)
  periodic_pair()    spectral and raw buffers made periodic with ONE shared seam
  schedule()/render()  deterministic polyphonic grain cloud reading a periodic buffer
  dissolve_params()  Approach B: structural DISSOLVE mapping, D in [0, 1]
  parallel()         Approach A: equal-power TRACE/CLOUD crossfade (control)
  position_cdf()     Approach C: spectrally guided grain positions

There is no per-grain FFT: one WOLA reconstruction at capture, then grains are
plain interpolated buffer reads. No limiter or compressor anywhere.
"""
import heapq
from dataclasses import dataclass

import numpy as np

from . import engines as E
from .capture import CaptureRejected
from .stft import hop, istft_buffer

CONTEXT_FRAMES = 2  # frames needed on each side so the selection is fully overlapped at H = N/4
MAX_GRAINS = 32     # fixed polyphony ceiling (300 ms grains at 100 grains/s overlap 30 deep)
GRAIN_FIELDS = [("onset", "i8"), ("length", "i8"), ("pos", "f8"), ("speed", "f8"), ("reverse", "?"),
                ("amp", "f8"), ("gain", "f8"), ("gl", "f8"), ("gr", "f8"), ("dropped", "?")]


# --------------------------------------------------------------------------
# Capture buffer
# --------------------------------------------------------------------------
def capture_buffer(history, cap):
    """Time-domain copy of the selected region with the capture's frequency mask.

    The selection of M frames `first..last` is defined as the M*H samples centred
    on those frames' window centres: [(first - 1.5) H, (last - 0.5) H). P0-A's
    loop used only the (M - 3) H samples that the M selected frames overlap
    fully. Here two extra frames per side are read from the history so the whole
    selection is fully overlapped, and the result is trimmed back to exactly the
    selection: context frames contribute only inside it.

    Context frames before the stream start are zeros (that audio is silence). A
    context frame that is not in the ring yet/any more shortens the buffer on
    that side instead of exposing partially overlapped audio.

    Returns (buffer (samples, channels), info). info["start_sample"] is the
    stream sample index of buffer[0].
    """
    N, H = cap.N, hop(cap.N)
    M, C, K = cap.frames.shape
    first = cap.first_frame
    frames = np.zeros((M + 2 * CONTEXT_FRAMES, C, K), np.complex128)
    missing = []
    for j, i in enumerate(range(first - CONTEXT_FRAMES, first + M + CONTEXT_FRAMES)):
        if i < 0:
            continue
        try:
            frames[j] = history.frame(i, history.epoch) * cap.freq_mask
        except CaptureRejected:
            missing.append(i)
    trim = {0: 0, 1: H // 2, 2: 3 * H // 2}
    head = trim[sum(i < first for i in missing)]
    tail = trim[sum(i >= first + M for i in missing)]
    b0 = 7 * H // 2  # buffer index of sample (first - 1.5) H; buffer[0] is sample (first - 5) H
    buf = istft_buffer(frames, N)[b0 + head:b0 + M * H - tail]
    info = {"start_sample": (2 * first - 3) * H // 2 + head, "samples": len(buf), "selection_samples": M * H,
            "p0a_interior_samples": max((M - 3) * H, 0), "context_missing": missing,
            "trimmed_head": head, "trimmed_tail": tail, "context_latency_samples": CONTEXT_FRAMES * H}
    return buf, info


def periodic_pair(spectral, raw, fs, xfade_s=0.08, max_lag_s=0.025):
    """Make the spectral buffer periodic with P0-A's aligned seam, then apply the
    SAME period and crossfade length to the raw buffer, so one grain schedule
    addresses the same source instants in both (spectral selection ON vs OFF)."""
    per_s, seam = E.loop_period(spectral, fs, xfade_s, "aligned", max_lag_s)
    if seam["period_samples"] < 8:
        raise E.EngineError(f"capture buffer of {len(spectral)} samples is too short to granulate")
    per_r, seam_r = E.loop_period(raw, fs, xfade_s, "aligned", max_lag_s, period=seam["period_samples"])
    seam["raw_seam_correlation"] = seam_r["seam_correlation"]
    return per_s, per_r, seam


# --------------------------------------------------------------------------
# Grains
# --------------------------------------------------------------------------
def grain_window(L, kind="hann"):
    """Grain envelope; w[0] is exactly 0. "rect" is a click control, not a product option."""
    n = np.arange(L)
    if kind == "hann":  # periodic: copies offset by L/2 sum to exactly 1
        return 0.5 - 0.5 * np.cos(2 * np.pi * n / L)
    if kind == "tukey":  # flat middle half, raised-cosine quarter at each end
        t = max(L // 4, 1)
        w = np.ones(L)
        w[:t] = 0.5 - 0.5 * np.cos(np.pi * np.arange(t) / t)
        w[L - t:] = w[:t][::-1]
        return w
    if kind == "rect":
        return np.ones(L)
    raise ValueError(kind)


def read(buf, pos, L, speed=1.0, reverse=False):
    """L samples of the periodic buffer starting at fractional `pos`, advancing
    `speed` source samples per output sample (4-point Catmull-Rom; exact at
    integer positions). Reverse plays the same source span backwards."""
    k = np.arange(L)
    p = pos + speed * (L - 1 - k if reverse else k)
    i = np.floor(p).astype(np.int64)
    f = (p - i)[:, None]
    R = len(buf)
    y0, y1, y2, y3 = (buf[(i + d) % R] for d in (-1, 0, 1, 2))
    return y1 + 0.5 * f * (y2 - y0 + f * (2 * y0 - 5 * y1 + 4 * y2 - y3 + f * (3 * (y1 - y2) + y3 - y0)))


@dataclass(frozen=True)
class CloudParams:
    grain_s: float = 0.2
    density_hz: float = 20.0    # grains per second
    spray: float = 1.0          # position randomisation, fraction of the buffer (0 = sequential)
    scan: float = 1.0           # sequential playhead speed through the buffer
    jitter: float = 1.0         # onset randomisation, fraction of the inter-onset interval
    pitch_st: float = 0.0       # uniform random transposition, +/- semitones
    octave_prob: float = 0.0    # probability of an octave jump (60 % up, 40 % down), on top of pitch_st
    reverse_prob: float = 0.0
    spread: float = 0.0         # stereo balance randomisation, 0..1
    amp_var: float = 0.0        # grain amplitude drawn from [1 - amp_var, 1]
    coherence: float = 0.0      # expected fraction of coherent (amplitude) summation, for gain only
    window: str = "hann"


def grain_length(p, fs):
    return max(2 * round(p.grain_s * fs / 2), 2)  # even, so 50 % overlap is sample-exact


S_REF = 0.75  # overlap power of the reference stream: Hann grains at 50 % overlap


def nominal_gain(p, fs):
    """Per-grain gain from the expected overlap power.

    P = coherence * (overlap E[w] E[amp])^2 + (1 - coherence) * overlap E[w^2] E[amp^2]
    g = 1 / sqrt(max(P, S_REF))

    Decorrelated grains add in power, sequential (coherent) grains add in
    amplitude; `coherence` says which regime the caller expects. A cloud with
    P >= S_REF therefore has the RMS of its buffer. Sparser clouds are NOT
    boosted further (grains stay at +1.25 dB, the cloud gets quieter), and the
    sequential 50 %-overlap Hann stream (P = 1) is left at exactly unity so it
    reconstructs its buffer. A cloud that is more coherent than declared is
    louder than this predicts (measured in verify_cloud)."""
    L = grain_length(p, fs)
    w, ov = grain_window(L, p.window), p.density_hz * L / fs
    inco = ov * float(np.mean(w ** 2)) * (1 - p.amp_var + p.amp_var ** 2 / 3)
    coh = (ov * float(np.mean(w)) * (1 - p.amp_var / 2)) ** 2
    return 1 / np.sqrt(max(p.coherence * coh + (1 - p.coherence) * inco, S_REF))


def schedule(R, fs, n_samples, params, seed=0, pos_cdf=None, max_grains=MAX_GRAINS):
    """Deterministic grain list for a periodic buffer of R samples.

    `params` is a CloudParams or a callable t_seconds -> CloudParams (evaluated
    once per grain at its nominal onset). Every grain consumes exactly eight
    uniform draws whatever the parameters, so the same seed gives the same
    underlying randomness at every setting and for every buffer.

    Scheduling starts one grain length before sample 0 so the overlap is already
    in steady state at the first output sample.

    Polyphony: grains are admitted in onset order; a grain that would be the
    (max_grains + 1)-th simultaneous grain is dropped whole (flagged, counted).
    Dropping never truncates a sounding grain, so it cannot click.
    """
    pf = params if callable(params) else (lambda _t: params)
    rng = np.random.default_rng(seed)
    t = -float(grain_length(pf(0.0), fs))
    rows = []
    while t < n_samples:
        p = pf(max(t, 0.0) / fs)
        u = rng.random(8)
        L = grain_length(p, fs)
        interval = fs / p.density_hz
        onset = int(round(t + p.jitter * (u[0] - 0.5) * interval))
        octave = 12.0 if u[2] < 0.6 * p.octave_prob else (-12.0 if u[2] < p.octave_prob else 0.0)
        speed = 2.0 ** ((p.pitch_st * (2 * u[1] - 1) + octave) / 12)
        if pos_cdf is None:
            pos = onset * p.scan + p.spray * R * (u[6] - 0.5)
        else:  # guided: the grain's centre lands on a position drawn from the weight
            pos = float(np.searchsorted(pos_cdf, u[6])) - 0.5 * L * speed
        a = (p.spread * (2 * u[4] - 1) + 1) * np.pi / 4  # balance, positive gains only, (1, 1) at centre
        rows.append((onset, L, pos % R, speed, u[3] < p.reverse_prob, 1 - p.amp_var * u[5], nominal_gain(p, fs),
                     np.sqrt(2) * np.cos(a), np.sqrt(2) * np.sin(a), False))
        t += interval
    g = np.array(rows, dtype=GRAIN_FIELDS)
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


def active_count(grains, n_samples):
    """Number of sounding grains at every output sample."""
    d = np.zeros(n_samples + 1)
    for g in grains[~grains["dropped"]]:
        a, b = max(g["onset"], 0), min(g["onset"] + g["length"], n_samples)
        if b > a:
            d[a] += 1
            d[b] -= 1
    return np.cumsum(d)[:-1]


def render(buf, grains, n_samples, window="hann"):
    """Sum the scheduled grains. Both channels of a grain read the same source
    position (the source's own stereo image is kept); spread is a positive-gain
    balance, so it can never create anti-phase content."""
    out = np.zeros((n_samples, buf.shape[1]))
    wins = {}
    for g in grains[~grains["dropped"]]:
        L, on = int(g["length"]), int(g["onset"])
        a, b = max(on, 0), min(on + L, n_samples)
        if b <= a:
            continue
        w = wins.setdefault(L, grain_window(L, window))
        y = read(buf, g["pos"], L, g["speed"], g["reverse"]) * (w * g["amp"] * g["gain"])[:, None]
        if y.shape[1] == 2:
            y = y * (g["gl"], g["gr"])
        out[a:b] += y[a - on:b - on]
    return out


def cloud(buf, fs, n_samples, params, seed=0, pos_cdf=None, max_grains=MAX_GRAINS):
    """schedule + render. Returns (audio, info)."""
    g = schedule(len(buf), fs, n_samples, params, seed, pos_cdf, max_grains)
    p0 = params(0.0) if callable(params) else params
    act = active_count(g, n_samples)
    info = {"grains": int(len(g)), "dropped": int(g["dropped"].sum()), "max_active": int(act.max(initial=0)),
            "mean_active": float(act.mean()) if n_samples else 0.0, "max_grains": max_grains, "seed": seed,
            "window": p0.window, "guided": pos_cdf is not None}
    return render(buf, g, n_samples, p0.window), info


# --------------------------------------------------------------------------
# DISSOLVE
# --------------------------------------------------------------------------
def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def dissolve_params(D, fs, octaves=True):
    """Approach B: one grain stream whose parameters are continuous in D.

    D = 0: 120 ms Hann grains, 50 % overlap, sequential, forward, unity speed,
           centred -> sample-exact playback of the periodic TRACE buffer.
    D = 1: 200 ms grains, 4x overlap, uniformly random positions and onsets,
           half reversed, +/-0.15 st detune, 20 % octave jumps, 80 % spread.
    The gain law moves from amplitude to power summation over D = 0..0.05 (a
    first version used 0..0.1 and failed the 1 dB step limit on white noise at
    1.52 dB, because noise decorrelates on the first sample of spray). Overlap
    stays at exactly 2 until D = 0.1; raising it earlier would add coherently.
    """
    D = float(np.clip(D, 0.0, 1.0))
    L = 2 * round((0.12 + 0.08 * D) * fs / 2)
    overlap = 2 + 2 * _smooth((D - 0.1) / 0.6)
    return CloudParams(grain_s=L / fs, density_hz=overlap * fs / L, spray=D * D, jitter=D, pitch_st=0.15 * D,
                       octave_prob=0.2 * _smooth((D - 0.4) / 0.6) if octaves else 0.0,
                       reverse_prob=0.5 * _smooth((D - 0.25) / 0.75), spread=0.8 * D,
                       coherence=1 - _smooth(D / 0.05))


def dissolve(buf, fs, n_samples, D, seed=0, octaves=True, pos_cdf=None):
    """Structural DISSOLVE. D is a number or a callable t_seconds -> D."""
    d = D if callable(D) else (lambda _t: D)
    return cloud(buf, fs, n_samples, lambda t: dissolve_params(d(t), fs, octaves), seed, pos_cdf)


def parallel(trace, cld, D):
    """Approach A (control): equal-power crossfade. D is a number or per-sample array."""
    D = np.clip(np.asarray(D, dtype=np.float64), 0, 1)
    D = D[:, None] if D.ndim else D
    return np.cos(0.5 * np.pi * D) * trace + np.sin(0.5 * np.pi * D) * cld


def ramp(hold0_s, ramp_s):
    """DISSOLVE trajectory: 0 for hold0_s, linear to 1 over ramp_s, then 1."""
    return lambda t: min(max((t - hold0_s) / ramp_s, 0.0), 1.0)


# --------------------------------------------------------------------------
# Approach C: spectrally guided grain positions
# --------------------------------------------------------------------------
def position_cdf(frames, R, H, mode="harmonic", bins=None):
    """CDF over buffer positions [0, R) from per-frame spectral features of the
    selection's frames (frame i is centred on buffer sample (i + 0.5) H).

      energy  e[m]   = sum |X|^2
      flux    f[m]   = sum max(|X[m]| - |X[m-1]|, 0)^2 / (e[m] + e[m-1])   (onset-ness, 0..1)
      tonal   t[m]   = 1 - spectral flatness of |X[m]|^2 over `bins`
      "harmonic":  sqrt(e) * t^2 * (1 - f)^2   stable, peaky, loud frames
      "transient": sqrt(e) * f                 frames where energy arrives

    Weights are floored at 0.1 % of their maximum so every position stays
    reachable; an all-zero weight falls back to uniform.
    """
    # ponytail: three hand-picked frame features; replace only if listening shows guidance matters
    P = np.sum(np.abs(frames.astype(np.complex128)) ** 2, axis=1)  # (M, K)
    if bins is not None:
        P = P[:, bins]
    e, mag = P.sum(axis=1), np.sqrt(P)
    f = np.zeros(len(e))
    if len(e) > 1:
        d = np.sum(np.maximum(mag[1:] - mag[:-1], 0) ** 2, axis=1)
        f[1:] = np.divide(d, e[1:] + e[:-1], out=np.zeros_like(d), where=(e[1:] + e[:-1]) > 0)
        f[0] = f[1]
    f = np.clip(f, 0, 1)
    tiny = 1e-30
    flat = np.exp(np.mean(np.log(P + tiny), axis=1)) / (np.mean(P, axis=1) + tiny)
    w = np.sqrt(e) * {"harmonic": (1 - flat) ** 2 * (1 - f) ** 2, "transient": f}[mode]
    ws = np.interp(np.arange(R), (np.arange(len(w)) + 0.5) * H, w)
    if not np.isfinite(ws).all() or ws.max() <= 0:
        ws = np.ones(R)
    ws = np.maximum(ws, 1e-3 * ws.max())
    return np.cumsum(ws) / ws.sum()
