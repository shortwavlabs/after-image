# SPDX-License-Identifier: AGPL-3.0-only
"""P0-C: SPLIT, frequency-dependent TRACE -> CLOUD dissolution.

  band_masks()          complementary log-frequency band masks (sum to exactly 1)
  decompose_spectral()  A: bands from the captured STFT frames (P0-B capture path)
  decompose_iir()       B: conventional Linkwitz-Riley / Butterworth crossover baseline
  amounts()             per-band dissolve amount for strategies s1 / s2_keep / s2_fade / s3
  band_params()         per-band grain settings (s3 varies them with frequency)
  render_split()        per band: equal-power TRACE/CLOUD crossfade, then sum

Each band has TWO buffers. The TRACE branch uses amplitude-complementary masks
B_i (sum B_i = 1), so unmodified bands add back to the source exactly. The CLOUD
branch uses power-complementary masks sqrt(B_i) (sum of squares = 1) and an
independent grain schedule per band, because decorrelated bands add in power:
with amplitude masks they would leave a 3 dB hole at every crossover.

Nothing here is a product parameter. All constants are research settings.
"""
from dataclasses import dataclass, replace

import numpy as np
from scipy.signal import butter, sosfilt

from . import engines as E
from . import granular as G

DEFAULT_WIDTH_OCT = 1.0   # crossover transition width
BUDGET_3 = (6, 10, 16)    # grain ceiling per band; totals G.MAX_GRAINS, NOT 32 per band
STRATEGIES = ("s1", "s2_keep", "s2_fade", "s3")


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------------------
# Band masks
# --------------------------------------------------------------------------
def band_masks(N, fs, crossovers, width_oct=DEFAULT_WIDTH_OCT):
    """(n_bands, K) amplitude masks. With T_j the raised-cosine step in
    log-frequency centred on crossover j (0 below fc*2^(-w/2), 1 above
    fc*2^(w/2)):  B_0 = 1 - T_0,  B_i = T_0..T_(i-1) * (1 - T_i),  B_last = T_0..T_last.
    The sum telescopes to exactly 1 at every bin, however the steps overlap."""
    c = [float(v) for v in crossovers]
    if not c or any(not np.isfinite(v) or v <= 0 or v >= fs / 2 for v in c) or any(b <= a for a, b in zip(c, c[1:])):
        raise ValueError(f"crossovers must be increasing and inside (0, fs/2): {crossovers}")
    if width_oct <= 0:
        raise ValueError("width_oct must be positive")
    lf = np.log2(np.maximum(np.arange(N // 2 + 1) * fs / N, 1e-9))
    steps = [0.5 - 0.5 * np.cos(np.pi * np.clip((lf - np.log2(fc)) / width_oct + 0.5, 0, 1)) for fc in c]
    masks, carry = [], np.ones_like(lf)
    for T in steps:
        masks.append(carry * (1 - T))
        carry = carry * T
    masks.append(carry)
    return np.array(masks)


def resolve_crossovers(spec, low_hz, high_hz, fs):
    """{"mode": "absolute", "hz": [...]} or {"mode": "relative", "fractions": [...]}
    (fractions of the log-frequency span of the available band)."""
    if spec["mode"] == "absolute":
        return [float(v) for v in spec["hz"]]
    lo, hi = max(low_hz, 20.0), min(high_hz, fs / 2)
    return [float(lo * (hi / lo) ** f) for f in spec["fractions"]]


# --------------------------------------------------------------------------
# Decompositions
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Decomp:
    kind: str          # "spectral" | "iir"
    source: str        # "full" | "filtered"
    crossovers: tuple
    src: np.ndarray    # the source selection, not periodic (samples, C)
    per_src: np.ndarray  # periodic source = the TRACE reference (R, C)
    trace: tuple       # per band (R, C): amplitude-complementary
    cloud: tuple       # per band (R, C): power-complementary
    seam: dict

    @property
    def n_bands(self):
        return len(self.trace)


def apply_seam(seg, seam):
    """The P0-A aligned seam with a GIVEN period, crossfade and correlation, so it
    is one linear operation shared by every band (band TRACEs then sum to the
    source TRACE). Equals engines.loop_period() on the buffer the seam came from."""
    R, X, rho = seam["period_samples"], seam["xfade_samples"], seam["seam_correlation"]
    per = seg[:R].copy()
    if X > 0:
        a = np.arange(X) / X
        b = 1 - a
        g = np.sqrt(a ** 2 + b ** 2 + 2 * max(rho, 0.0) * a * b)
        per[:X] = seg[:X] * (a / g)[:, None] + seg[R:R + X] * (b / g)[:, None]
    return per


def decompose_spectral(history, cap, fs, crossovers, source="full", width_oct=DEFAULT_WIDTH_OCT, xfade_s=0.08):
    """Approach A. SOURCE full = every bin of the selected frames; filtered = the
    capture's own frequency mask. Band masks multiply the source mask; each band is
    one P0-B context-frame reconstruction."""
    S = np.ones_like(cap.freq_mask) if source == "full" else cap.freq_mask
    B = band_masks(cap.N, fs, crossovers, width_oct)
    buf = lambda m: G.capture_buffer(history, replace(cap, freq_mask=m))[0]
    src = buf(S)
    per_src, seam = E.loop_period(src, fs, xfade_s, "aligned")
    if seam["period_samples"] < 8:
        raise E.EngineError(f"capture buffer of {len(src)} samples is too short to granulate")
    return Decomp("spectral", source, tuple(crossovers), src, per_src,
                  tuple(apply_seam(buf(S * b), seam) for b in B),
                  tuple(apply_seam(buf(S * np.sqrt(b)), seam) for b in B), seam)


def iir_bands(x, fs, crossovers, kind="lr4"):
    """Conventional crossover tree, causal, run over the whole stream.
    "lr4": Linkwitz-Riley 4th order with all-pass compensation of the earlier
           bands, so the bands sum to an all-pass (flat magnitude, shifted phase).
    "bw3": 3rd-order Butterworth, power-complementary (for decorrelated bands)."""
    def pair(fc):
        if kind == "lr4":
            lo, hi = (butter(2, fc, t, fs=fs, output="sos") for t in ("low", "high"))
            return (lambda v: sosfilt(lo, sosfilt(lo, v, axis=0), axis=0)), (lambda v: sosfilt(hi, sosfilt(hi, v, axis=0), axis=0))
        lo, hi = (butter(3, fc, t, fs=fs, output="sos") for t in ("low", "high"))
        return (lambda v: sosfilt(lo, v, axis=0)), (lambda v: sosfilt(hi, v, axis=0))
    bands, rest = [], np.asarray(x, dtype=np.float64)
    for fc in crossovers:
        lp, hp = pair(fc)
        if kind == "lr4":
            bands = [lp(b) + hp(b) for b in bands]
        bands.append(lp(rest))
        rest = hp(rest)
    return bands + [rest]


def decompose_iir(x, start, samples, fs, crossovers, seam):
    """Approach B: the same selection [start, start + samples) cut from a
    conventionally filtered stream, with the spectral decomposition's seam forced
    on it so both address the same source instants. FULL source only."""
    cut = lambda bands: tuple(apply_seam(b[start:start + samples], seam) for b in bands)
    trace = cut(iir_bands(x, fs, crossovers, "lr4"))
    return Decomp("iir", "full", tuple(crossovers), x[start:start + samples], sum(trace), trace,
                  cut(iir_bands(x, fs, crossovers, "bw3")), seam)


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------
def amounts(strategy, D, n_bands):
    """Per-band dissolve amount d_i in [0, 1]; D may be a number or an array.
    Band position p = 0 (lowest) .. 1 (highest).
      s1       static: d = p^1.5 (0, 0.35, 1 for three bands); D is ignored
      s2_keep  staggered: band i dissolves over D in [0.6 (1 - p), 0.6 (1 - p) + 0.4];
               the lowest band never dissolves
      s2_fade  the same, but the lowest band dissolves over D in [0.6, 1]
      s3       every band follows D (the bands differ in grain behaviour instead)
    Every mapping is continuous and non-decreasing in D."""
    D = np.clip(np.asarray(D, dtype=np.float64), 0, 1)
    p = np.linspace(0, 1, n_bands)
    if strategy == "s1":
        return [np.full(D.shape, v ** 1.5) for v in p]
    if strategy in ("s2_keep", "s2_fade"):
        d = [_smooth((D - 0.6 * (1 - v)) / 0.4) for v in p]
        if strategy == "s2_keep":
            d[0] = np.zeros(D.shape)
        return d
    if strategy == "s3":
        return [D.copy() for _ in p]
    raise ValueError(strategy)


def coherence_from_spray(spray_seconds, knee_s=0.005):
    """Gain-policy candidate: treat grains as coherent until position spray
    exceeds `knee_s`. Material-dependent in reality (noise decorrelates in one
    sample, a low sine only after about half its period)."""
    return float(1 - _smooth(spray_seconds / knee_s))


def band_params(strategy, fs, n_bands, R, pitch="none", policy="spray"):
    """CLOUD-branch settings per band. s1/s2: the P0-B cloud endpoint without
    pitch in every band. s3: grain length 300 -> 80 ms (geometric), 4x overlap,
    spray 50 -> 100 %, spread 20 -> 100 %, reverse 0 -> 50 % from low to high.
    pitch applies to the TOP band only: "none" | "detune" (+/-0.15 st) |
    "octaves" (detune plus P0-B's 20 % octave jumps)."""
    base = replace(G.dissolve_params(1.0, fs), pitch_st=0.0, octave_prob=0.0)
    out = []
    for i, p in enumerate(np.linspace(0, 1, n_bands)):
        q = base
        if strategy == "s3":
            L = 2 * round(0.30 * (0.08 / 0.30) ** p * fs / 2)
            q = replace(base, grain_s=L / fs, density_hz=4 * fs / L, spray=0.5 + 0.5 * p, spread=0.2 + 0.8 * p,
                        reverse_prob=0.5 * p)
        if i == n_bands - 1 and pitch != "none":
            q = replace(q, pitch_st=0.15, octave_prob=0.2 if pitch == "octaves" else 0.0)
        c = {"none": 0.0, "coherent": 1.0, "spray": coherence_from_spray(q.spray * R / fs)}[policy]
        out.append(replace(q, coherence=c))
    return out


def budgets(n_bands):
    if n_bands == 3:
        return BUDGET_3
    return tuple([G.MAX_GRAINS // n_bands] * n_bands)


def render_split(dec, fs, n_samples, strategy, D=1.0, seed=0, pitch="none", policy="spray", naive=False):
    """Sum over bands of cos(d_i pi/2) * TRACE_i + sin(d_i pi/2) * CLOUD_i.

    D is a number or a callable t_seconds -> D. The grain settings do not move
    with D: only the per-band crossfade does (the owner-preferred parallel morph).
    naive=True is the rejected first design, kept for measurement: amplitude
    masks and ONE shared schedule for every band's cloud.
    Returns (audio, info)."""
    R, nb = len(dec.per_src), dec.n_bands
    Dv = np.array([D(t) for t in np.arange(n_samples) / fs]) if callable(D) else np.asarray(float(D))
    d = amounts(strategy, Dv, nb)
    prm, bud = band_params(strategy, fs, nb, R, pitch, policy), budgets(nb)
    out = np.zeros((n_samples, dec.per_src.shape[1]))
    active = np.zeros(n_samples)
    info = {"strategy": strategy, "bands": [], "naive": naive, "pitch": pitch, "policy": policy}
    for i in range(nb):
        trace = np.tile(dec.trace[i], (-(-n_samples // R), 1))[:n_samples]
        b = {"d_min": float(np.min(d[i])), "d_max": float(np.max(d[i])), "budget": bud[i], "grains": 0, "dropped": 0, "max_active": 0}
        if b["d_max"] > 0:
            g = G.schedule(R, fs, n_samples, prm[i], seed if naive else seed + i, None, bud[i])
            cld = G.render(dec.trace[i] if naive else dec.cloud[i], g, n_samples, prm[i].window)
            act = G.active_count(g, n_samples)
            active += act
            b.update(grains=int(len(g)), dropped=int(g["dropped"].sum()), max_active=int(act.max(initial=0)))
            out += G.parallel(trace, cld, d[i])
        else:
            out += trace
        info["bands"].append(b)
    info["max_active_total"] = int(active.max(initial=0))
    info["trace_readers"] = nb
    return out, info
