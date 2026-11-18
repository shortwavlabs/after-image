# SPDX-License-Identifier: AGPL-3.0-only
"""P0-C numerical verification of band decomposition and the SPLIT engine.

Threshold provenance: every limit below was committed in its own commit before
any SPLIT code existed (see the git history of this file). They were written
from the design and from two analytic predictions, not from measurements:
  * amplitude-complementary bands that decorrelate leave a hole of
    10*log10(1 - (1 - cos(delta_d*pi/2))/2) at the crossover centre (-3 dB at
    worst); the adopted design (power-complementary cloud bands) predicts
    -1.25 dB at worst, so CROSSOVER_HOLE_MAX_DB = 1.5 can fail;
  * the +13 dB coherent buildup measured in P0-B.
If a limit fails the algorithm is changed or the row is reported FAIL; the
constant is not edited. Rows marked "info" have no limit.
"""
MASK_SUM_TOL = 1e-12            # |sum of amplitude masks - 1| and |sum of squared cloud masks - 1|, every bin
BAND_RECON_DB = -120.0          # sum of spectral band buffers vs the source buffer
CONV_MAG_TOL_DB = 0.1           # magnitude of the summed conventional (LR4) crossover, 20 Hz - 20 kHz
ISOLATION_DB = -60.0            # spectral bands: tone one octave beyond a crossover, level in the wrong band
D0_ERR_DB = -120.0              # SPLIT at DISSOLVE 0 vs the TRACE loop of its source (spectral decomposition)
CROSSOVER_HOLE_MAX_DB = 1.5     # |1/6-octave long-term level re TRACE| at each crossover, any static SPLIT setting
DISSOLVE_STEP_MAX_DB = 1.0      # RMS change between DISSOLVE settings 0.05 apart, stationary material (as P0-B)
DISSOLVE_RANGE_MAX_DB = 3.0     # RMS range over DISSOLVE 0..1, stationary material (as P0-B)
TOTAL_GRAINS_MAX = 32           # simultaneous grains across ALL bands (the P0-B ceiling, not per band)
MONO_COMPAT_MIN_DB = -3.02      # dual-mono source through SPLIT (analytic floor of the balance law, as P0-B)
COHERENT_SAFE_DB = 0.5          # "assume coherent" gain policy: RMS re buffer at zero spray never above this
LOW_SIDEBAND_GAIN_MIN_DB = 6.0  # S1 vs unguided CLOUD: reduction of energy between partials below 400 Hz (guitar)
LOW_PITCH_TOL_CENTS = 1.0       # S1: median frequency of the lowest guitar partial re TRACE

import time

import numpy as np
from scipy.signal import hilbert, welch

from . import engines as E
from . import fixtures
from . import granular as G
from . import metrics as Mx
from . import split as SP
from . import stft as S
from . import verify_cloud as VC
from .verify import _row

FS, NFFT = 48000, 4096
XO = [250.0, 2000.0]  # default FULL-source crossovers (research setting, configurable)
GUITAR = (0.60, 1.35, 20, None)
STATIC = (("s1", 1.0), ("s2_keep", 0.5), ("s2_keep", 1.0), ("s2_fade", 0.5), ("s2_fade", 0.8), ("s2_fade", 1.0),
          ("s3", 0.5), ("s3", 1.0))


def decomp(x, fs=FS, N=NFFT, t0=1.0, t1=1.75, low=20, high=None, crossovers=XO, source="full", conventional=False, **kw):
    p = VC.prepare(x, fs, N, t0, t1, low, high, xfade_s=None)
    dec = SP.decompose_spectral(p["history"], p["cap"], fs, crossovers, source, **kw)
    if not conventional:
        return dec
    return dec, SP.decompose_iir(S.as_2d(x)[:int(t1 * fs) + N], p["info"]["start_sample"], p["info"]["samples"], fs, crossovers, dec.seam)


def tile(per, n):
    return np.tile(per, (-(-n // len(per)), 1))[:n]


def band_level_db(y, ref, fs, fc, frac_oct=1 / 6):
    """Long-term level of y re ref in a band of frac_oct octaves centred on fc."""
    f, py = welch(y, fs, nperseg=16384, axis=0)
    _, pr = welch(ref, fs, nperseg=16384, axis=0)
    m = (f >= fc * 2 ** (-frac_oct / 2)) & (f <= fc * 2 ** (frac_oct / 2))
    return float(10 * np.log10(py[m].sum() / pr[m].sum()))


def guitar_partials(fmax):
    """Partial frequencies of the guitar fixture below fmax (same formula as fixtures.guitar)."""
    out = []
    for f0 in (82.41, 123.47, 164.81, 207.65, 246.94, 329.63):
        h = 1
        while f0 * h * np.sqrt(1 + 2e-4 * h * h) < fmax:
            out.append(f0 * h * np.sqrt(1 + 2e-4 * h * h))
            h += 1
    return sorted(out)


def sideband_ratio_db(y, fs, partials, fmax, half_width_hz=4.0):
    """Energy below fmax that is NOT within half_width_hz of a known partial,
    relative to the energy that is. Lower = cleaner lows."""
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y))[:, None], axis=0)) ** 2
    f = np.fft.rfftfreq(len(y), 1 / fs)
    near = np.zeros(len(f), bool)
    for p in partials:
        near |= np.abs(f - p) <= half_width_hz
    lowband = (f > 30) & (f < fmax)
    return Mx.db(np.sqrt(Y[lowband & ~near].sum() / max(Y[lowband & near].sum(), Mx.EPS)))


def partial_track(y, fs, f0, rel_bw=0.08):
    """Follow one partial: (median frequency in cents re f0, inter-quartile range
    in cents, peak-to-peak level of its envelope in dB), middle 80 % of the render."""
    Y = np.fft.rfft(y.mean(axis=1))
    f = np.fft.rfftfreq(len(y), 1 / fs)
    Y[(f < f0 * (1 - rel_bw)) | (f > f0 * (1 + rel_bw))] = 0
    a = hilbert(np.fft.irfft(Y, len(y)))
    k = len(a) // 10
    inst = np.diff(np.unwrap(np.angle(a[k:-k]))) * fs / (2 * np.pi)
    env = np.abs(a[k:-k])
    blocks = env[:len(env) // 2400 * 2400].reshape(-1, 2400).mean(axis=1)  # 50 ms
    cents = 1200 * np.log2(np.maximum(inst, 1e-6) / f0)
    q1, med, q3 = np.percentile(cents, [25, 50, 75])
    return float(med), float(q3 - q1), float(Mx.db(blocks.max() / max(blocks.min(), Mx.EPS)))


def band_split(y, fs, crossovers):
    """Brick-wall analysis bands of a render (measurement only)."""
    Y = np.fft.rfft(y, axis=0)
    f = np.fft.rfftfreq(len(y), 1 / fs)
    edges = [0.0] + list(crossovers) + [fs]
    return [np.fft.irfft(Y * ((f >= lo) & (f < hi))[:, None], len(y), axis=0) for lo, hi in zip(edges[:-1], edges[1:])]


def period_autocorr(y, R):
    a, b = y[:-R], y[R:]
    d = np.sqrt(np.sum(a * a) * np.sum(b * b))
    return float(np.sum(a * b) / d) if d > 0 else float("nan")


# --------------------------------------------------------------------------
def masks_and_reconstruction():
    rows = []
    worst_a = worst_p = 0.0
    for fs, N in ((48000, 2048), (48000, 4096), (48000, 8192), (44100, 4096), (96000, 8192)):
        for xo in ([250, 2000], [1000], [120, 500, 2000, 8000], [20.5, 23000]):
            for w in (0.5, 1.0, 2.0):
                if xo[-1] >= fs / 2:
                    continue
                B = SP.band_masks(N, fs, xo, w)
                worst_a = max(worst_a, float(np.abs(B.sum(axis=0) - 1).max()))
                worst_p = max(worst_p, float(np.abs((np.sqrt(B) ** 2).sum(axis=0) - 1).max()))
    rows.append(_row("band_masks", "amplitude masks: |sum - 1|, 5 rate/FFT configs x 4 crossover sets x 3 widths", worst_a, "abs",
                     worst_a <= MASK_SUM_TOL, MASK_SUM_TOL))
    rows.append(_row("band_masks", "cloud masks sqrt(B): |sum of squares - 1|", worst_p, "abs", worst_p <= MASK_SUM_TOL, MASK_SUM_TOL))
    for fs, N in ((48000, 2048), (48000, 4096), (48000, 8192), (44100, 4096), (96000, 8192)):
        worst = -999.0
        for name in fixtures.NAMES:
            dec = decomp(fixtures.make(name, fs), fs, N)
            worst = max(worst, Mx.error_db(sum(dec.trace), dec.per_src))
        rows.append(_row("band_reconstruction", f"fs={fs} N={N} FULL source: sum of 3 TRACE bands vs source TRACE, 4 fixtures", round(worst, 1), "dB",
                         worst <= BAND_RECON_DB, BAND_RECON_DB))
    for xo, label in (([1000], "2 bands"), ([120, 500, 2000, 8000], "5 bands")):
        dec = decomp(fixtures.make("guitar", FS), crossovers=xo)
        e = Mx.error_db(sum(dec.trace), dec.per_src)
        rows.append(_row("band_reconstruction", f"{label}: sum of TRACE bands vs source TRACE", round(e, 1), "dB", e <= BAND_RECON_DB, BAND_RECON_DB))
    dec = decomp(fixtures.make("vocal", FS), low=350, high=5000, source="filtered",
                 crossovers=SP.resolve_crossovers({"mode": "relative", "fractions": [1 / 3, 2 / 3]}, 350, 5000, FS))
    e = Mx.error_db(sum(dec.trace), dec.per_src)
    rows.append(_row("band_reconstruction", f"FILTERED source 350-5000 Hz, relative crossovers {[round(c) for c in dec.crossovers]} Hz", round(e, 1), "dB",
                     e <= BAND_RECON_DB, BAND_RECON_DB))
    e = Mx.error_db(SP.apply_seam(dec.src, dec.seam), E.loop_period(dec.src, FS, 0.08, "aligned")[0])
    rows.append(_row("band_reconstruction", "shared linear seam equals engines.loop_period on the source", round(e, 1), "dB", e <= BAND_RECON_DB, BAND_RECON_DB))
    return rows


def conventional_crossover():
    rows = []
    fs, n = FS, 1 << 16
    imp = np.zeros((n, 1))
    imp[0] = 1.0
    f = np.fft.rfftfreq(n, 1 / fs)
    band = (f >= 20) & (f <= 20000)
    H = np.fft.rfft(sum(SP.iir_bands(imp, fs, XO, "lr4"))[:, 0])
    dev = float(np.max(np.abs(20 * np.log10(np.abs(H[band])))))
    rows.append(_row("conventional_crossover", "LR4 3-way with all-pass compensation: |sum| deviation from flat, 20 Hz - 20 kHz", round(dev, 4), "dB",
                     dev <= CONV_MAG_TOL_DB, CONV_MAG_TOL_DB))
    gd = -np.diff(np.unwrap(np.angle(H))) / np.diff(2 * np.pi * f)
    rows.append(_row("conventional_crossover", "LR4 sum: largest group delay, 20 Hz - 20 kHz (spectral bands: 0)", round(1000 * float(gd[band[1:]].max()), 2), "ms"))
    P = sum(np.abs(np.fft.rfft(b[:, 0])) ** 2 for b in SP.iir_bands(imp, fs, XO, "bw3"))
    rows.append(_row("conventional_crossover", "Butterworth-3 cloud bands: power-sum deviation from flat", round(float(np.max(np.abs(10 * np.log10(P[band])))), 4), "dB"))
    x = VC._noise(seconds=3.0, channels=1)
    rows.append(_row("conventional_crossover", "LR4 sum vs input, waveform error on noise (flat magnitude, shifted phase)",
                     round(Mx.error_db(sum(SP.iir_bands(x, fs, XO, "lr4")), x), 1), "dB"))
    return rows


def isolation():
    rows = []
    fs = FS
    t = np.arange(4 * fs) / fs
    tones = (125, 500, 1000, 4000)  # one octave either side of each crossover
    x = 0.2 * sum(np.sin(2 * np.pi * f * t) for f in tones)
    dec, conv = decomp(x, conventional=True)
    wrong = {125: 1, 500: 0, 1000: 2, 4000: 1}  # the band each tone must NOT appear in
    for f, band in wrong.items():
        for label, bufs, limit in (("spectral TRACE band", dec.trace, ISOLATION_DB), ("spectral CLOUD band", dec.cloud, ISOLATION_DB),
                                   ("LR4 band", conv.trace, None), ("Butterworth-3 band", conv.cloud, None)):
            v = VC._tone_level_db(bufs[band], f, fs) - Mx.db(0.2)
            rows.append(_row("isolation", f"{f} Hz tone in band {band} ({label})", round(v, 1), "dB re source",
                             v <= limit if limit is not None else None, limit))
    return rows


def transparency_and_holes():
    rows = []
    fs, n = FS, 6 * FS
    for name in fixtures.NAMES:
        dec = decomp(fixtures.make(name, fs))
        worst = max(Mx.error_db(SP.render_split(dec, fs, n, s, 0.0, seed=1)[0], tile(dec.per_src, n)) for s in ("s2_keep", "s2_fade", "s3"))
        rows.append(_row("dissolve_endpoint", f"{name}: S2/S3 at DISSOLVE 0 vs TRACE (spectral)", round(worst, 1), "dB", worst <= D0_ERR_DB, D0_ERR_DB))
    for fs2, N in ((44100, 4096), (96000, 8192)):
        dec = decomp(fixtures.make("guitar", fs2), fs2, N)
        e = Mx.error_db(SP.render_split(dec, fs2, 3 * fs2, "s3", 0.0, seed=1)[0], tile(dec.per_src, 3 * fs2))
        rows.append(_row("dissolve_endpoint", f"fs={fs2} N={N}: S3 at DISSOLVE 0 vs TRACE", round(e, 1), "dB", e <= D0_ERR_DB, D0_ERR_DB))
    dec, conv = decomp(fixtures.make("guitar", fs), conventional=True)
    y = SP.render_split(conv, fs, n, "s3", 0.0, seed=1)[0]
    rows.append(_row("dissolve_endpoint", "conventional (LR4) at DISSOLVE 0 vs spectral TRACE: waveform error", round(Mx.error_db(y, tile(dec.per_src, n)), 1), "dB"))
    rows.append(_row("dissolve_endpoint", "conventional (LR4) at DISSOLVE 0 vs spectral TRACE: third-octave spectrum distance",
                     round(Mx.log_spectral_distance_db(y, tile(dec.per_src, n), fs), 2), "dB"))
    # crossover holes on stationary noise, long renders
    n = 30 * fs
    dec, conv = decomp(VC._noise(seconds=4.0), t0=1.0, t1=2.4, conventional=True)
    ref = tile(dec.per_src, n)
    for label, d, naive, gated in (("spectral", dec, False, True), ("rejected design (amplitude masks, shared schedule)", dec, True, False),
                                   ("conventional LR4 + Butterworth-3", conv, False, False)):
        for strat, D in STATIC:
            y = SP.render_split(d, fs, n, strat, D, seed=1, naive=naive)[0]
            lv = [band_level_db(y, ref, fs, fc) for fc in XO]
            worst = max(abs(v) for v in lv)
            rows.append(_row("crossover_hole", f"{label}, {strat} D={D}: level re TRACE at {XO[0]:.0f} / {XO[1]:.0f} Hz",
                             f"{lv[0]:+.2f} / {lv[1]:+.2f}", "dB", worst <= CROSSOVER_HOLE_MAX_DB if gated else None,
                             CROSSOVER_HOLE_MAX_DB if gated else None))
    return rows


def continuity():
    rows = []
    fs, n = FS, 6 * FS
    Ds = np.linspace(0, 1, 201)
    for nb in (2, 3, 4):
        ok = all(np.all(np.diff(d) >= -1e-15) and d.min() >= 0 and d.max() <= 1
                 for s in SP.STRATEGIES for d in SP.amounts(s, Ds, nb))
        rows.append(_row("continuity", f"{nb} bands: every strategy's band amounts are non-decreasing in DISSOLVE and inside [0, 1]", ok, "bool", ok, True))
    step = max(float(np.max(np.abs(np.diff(d)))) for s in SP.STRATEGIES for d in SP.amounts(s, Ds, 3))
    rows.append(_row("continuity", "largest change of any band amount for a DISSOLVE step of 0.005", round(step, 4), "0..1"))
    mats = {"noise": (decomp(VC._noise(seconds=4.0), t0=1.0, t1=2.4), True)}
    for name in fixtures.NAMES:
        mats[name] = (decomp(fixtures.make(name, fs)), name == "synth")
    for name, (dec, stationary) in mats.items():
        r0 = Mx.rms(tile(dec.per_src, n))
        for strat in ("s2_keep", "s2_fade", "s3"):
            v = np.array([Mx.db(Mx.rms(SP.render_split(dec, fs, n, strat, D, seed=1)[0]) / r0) for D in np.linspace(0, 1, 21)])
            st, rg = float(np.max(np.abs(np.diff(v)))), float(np.ptp(v))
            rows.append(_row("continuity", f"{name} {strat}: largest RMS change between settings 0.05 apart / range over 0..1",
                             f"{st:.2f} / {rg:.2f}", "dB", (st <= DISSOLVE_STEP_MAX_DB and rg <= DISSOLVE_RANGE_MAX_DB) if stationary else None,
                             f"{DISSOLVE_STEP_MAX_DB} / {DISSOLVE_RANGE_MAX_DB}" if stationary else None))
    dec = mats["noise"][0]
    for strat in ("s2_keep", "s2_fade", "s3"):
        y = SP.render_split(dec, fs, 10 * fs, strat, G.ramp(1.0, 8.0), seed=1)[0]
        blk = np.array([Mx.db(Mx.rms(y[i * fs:(i + 1) * fs])) for i in range(10)])
        rows.append(_row("continuity", f"noise {strat}, 0->1 ramp over 8 s: largest change between 1 s RMS blocks", round(float(np.max(np.abs(np.diff(blk)))), 2), "dB"))
    return rows


def polyphony_and_determinism():
    rows = []
    fs, n = FS, 10 * FS
    ok = all(sum(SP.budgets(nb)) <= TOTAL_GRAINS_MAX for nb in range(2, 9))
    rows.append(_row("polyphony", "band budgets sum to at most the total ceiling, 2..8 bands", ok, "bool", ok, True))
    dec = decomp(fixtures.make("guitar", fs))
    for strat, D in (("s1", 1.0), ("s2_fade", 1.0), ("s3", 1.0)):
        y, info = SP.render_split(dec, fs, n, strat, D, seed=1, pitch="octaves")
        per = [(b["max_active"], b["budget"]) for b in info["bands"]]
        ok = info["max_active_total"] <= TOTAL_GRAINS_MAX and all(a <= b for a, b in per)
        rows.append(_row("polyphony", f"{strat} D={D}: simultaneous grains total / per band (budget {SP.BUDGET_3})",
                         f"{info['max_active_total']} / {[a for a, _ in per]}", "grains", ok, TOTAL_GRAINS_MAX))
        rows.append(_row("polyphony", f"{strat} D={D}: grains dropped per band", str([b["dropped"] for b in info["bands"]]), "grains"))
    R = len(dec.per_src)
    for i, (q, bud) in enumerate(zip(SP.band_params("s3", fs, 3, R), SP.BUDGET_3)):
        g = G.schedule(R, fs, n, G.CloudParams(**{**q.__dict__, "density_hz": 8 * q.density_hz}), seed=1, max_grains=bud)
        mx = int(G.active_count(g, n).max())
        rows.append(_row("polyphony", f"band {i} asked for 8x its density (32 grains of overlap), budget {bud}: max simultaneous / dropped",
                         f"{mx} / {int(g['dropped'].sum())} of {len(g)}", "grains", mx <= bud, bud))
    a, b = (Mx.sha256(SP.render_split(dec, fs, 3 * fs, "s3", 0.7, seed=4)[0], np.float64) for _ in range(2))
    c = Mx.sha256(SP.render_split(dec, fs, 3 * fs, "s3", 0.7, seed=5)[0], np.float64)
    rows.append(_row("determinism", "same seed -> identical render hash; different seed -> different", bool(a == b and a != c), "bool", a == b and a != c, True))
    return rows


def headroom_policies():
    """P0-B's +13 dB finding, against three gain policies. RMS and peak are re the
    source buffer; grains read a stationary buffer with the given position spray."""
    rows = []
    fs, n = FS, 12 * FS
    t = np.arange(fs) / fs
    bufs = {"noise": VC._noise(), "guitar": decomp(fixtures.make("guitar", fs)).per_src,
            "82 Hz sine": np.repeat((0.3 * np.sin(2 * np.pi * 82 * t))[:, None], 2, axis=1)}
    sprays = (0.0, 0.0005, 0.005, 0.05, None)  # seconds; None = whole buffer
    settings = ((0.1, 100), (0.3, 20), (0.3, 100))
    res = {}
    for bname, buf in bufs.items():
        r0, p0 = Mx.rms(buf), Mx.peak(buf)
        for dur, dens in settings:
            for sp in sprays:
                frac = 1.0 if sp is None else sp * fs / len(buf)
                for pol in ("none", "spray", "spray50", "coherent"):
                    c = {"none": 0.0, "coherent": 1.0, "spray": SP.coherence_from_spray(frac * len(buf) / fs),
                         "spray50": SP.coherence_from_spray(frac * len(buf) / fs, 0.05)}[pol]
                    y = G.cloud(buf, fs, n, G.CloudParams(grain_s=dur, density_hz=dens, spray=frac, coherence=c), seed=3)[0]
                    res[(bname, dur, dens, sp, pol)] = (Mx.db(Mx.rms(y[fs:]) / r0), Mx.db(Mx.peak(y) / p0))
    for pol, label in (("none", "no policy (P0-B law told coherence 0)"), ("spray", "coherence from spray (5 ms knee)"),
                       ("spray50", "coherence from spray (50 ms knee)"), ("coherent", "assume coherent (amplitude normalisation)")):
        for bname in bufs:
            v = [r for k, r in res.items() if k[0] == bname and k[4] == pol]
            rows.append(_row("headroom", f"{label}, {bname}: RMS re buffer max / min over 15 settings; peak max",
                             f"{max(a for a, _ in v):+.2f} / {min(a for a, _ in v):+.2f}; {max(b for _, b in v):+.2f}", "dB"))
    for sp in sprays:
        v = [r[0] for k, r in res.items() if k[3] == sp and k[4] == "spray50"]
        rows.append(_row("headroom", f"coherence from spray (50 ms knee), spray {'whole buffer' if sp is None else f'{sp * 1000:g} ms'}: RMS re buffer max / min, all buffers",
                         f"{max(v):+.2f} / {min(v):+.2f}", "dB"))
        v = [r[0] for k, r in res.items() if k[3] == sp and k[4] == "spray"]
        rows.append(_row("headroom", f"coherence from spray (5 ms knee), spray {'whole buffer' if sp is None else f'{sp * 1000:g} ms'}: RMS re buffer max / min, all buffers",
                         f"{max(v):+.2f} / {min(v):+.2f}", "dB"))
    worst = max(r[0] for k, r in res.items() if k[3] == 0.0 and k[4] == "coherent")
    rows.append(_row("headroom", "assume coherent, zero spray: largest RMS re buffer", round(worst, 2), "dB", worst <= COHERENT_SAFE_DB, COHERENT_SAFE_DB))
    quiet = min(r[0] for k, r in res.items() if k[3] is None and k[4] == "coherent")
    rows.append(_row("headroom", "assume coherent, full spray: quietest cloud (the price of that policy)", round(quiet, 2), "dB"))
    need = max(r[1] for k, r in res.items() if k[4] == "none")
    rows.append(_row("headroom", "fixed reservation needed to cover the worst peak with no policy", round(need, 2), "dB"))
    # TRACE + CLOUD of the same band also correlate when spray is small
    buf = bufs["guitar"]
    tr = tile(buf, n)
    for sp in (0.0, 0.005, None):
        frac = 1.0 if sp is None else sp * fs / len(buf)
        cl = G.cloud(buf, fs, n, G.CloudParams(grain_s=0.2, density_hz=20, spray=frac, coherence=SP.coherence_from_spray(frac * len(buf) / fs)), seed=3)[0]
        rows.append(_row("headroom", f"guitar: equal-power TRACE + CLOUD at d=0.5, spray {'whole buffer' if sp is None else f'{sp * 1000:g} ms'}: RMS re TRACE",
                         round(Mx.db(Mx.rms(G.parallel(tr, cl, 0.5)) / Mx.rms(tr)), 2), "dB"))
    dec = decomp(fixtures.make("guitar", fs))
    for strat, D in STATIC:
        y = SP.render_split(dec, fs, n, strat, D, seed=1)[0]
        rows.append(_row("headroom", f"guitar SPLIT {strat} D={D}: RMS / peak re TRACE",
                         f"{Mx.db(Mx.rms(y) / Mx.rms(tile(dec.per_src, n))):+.2f} / {Mx.db(Mx.peak(y) / Mx.peak(dec.per_src)):+.2f}", "dB"))
    return rows


def stereo():
    rows = []
    fs, n = FS, 10 * FS
    dec = decomp(VC._noise(seconds=4.0, dual_mono=True), t0=1.0, t1=2.4)
    for strat, D in (("s1", 1.0), ("s2_keep", 1.0), ("s2_fade", 1.0), ("s3", 1.0)):
        y = SP.render_split(dec, fs, n, strat, D, seed=4)[0]
        mc = Mx.mono_compat_db(y)
        rows.append(_row("stereo", f"dual-mono source, {strat} D={D}: mono compatibility / correlation", f"{mc:.3f} / {Mx.interchannel_corr(y):.3f}",
                         "dB / corr", mc >= MONO_COMPAT_MIN_DB, f">= {MONO_COMPAT_MIN_DB}"))
    for name in fixtures.NAMES:
        dec = decomp(fixtures.make(name, fs))
        for strat in ("s1", "s3"):
            y = SP.render_split(dec, fs, n, strat, 1.0, seed=4)[0]
            lowb = band_split(y, fs, XO)[0]
            rows.append(_row("stereo", f"{name} {strat}: correlation source -> first s / last s; mono compat source -> render; low band (<250 Hz) correlation source -> render",
                             f"{Mx.interchannel_corr(dec.per_src):.3f} -> {Mx.interchannel_corr(y[:fs]):.3f} / {Mx.interchannel_corr(y[-fs:]):.3f}; "
                             f"{Mx.mono_compat_db(dec.per_src):.2f} -> {Mx.mono_compat_db(y):.2f}; "
                             f"{Mx.interchannel_corr(band_split(tile(dec.per_src, n), fs, XO)[0]):.3f} -> {Mx.interchannel_corr(lowb):.3f}", "corr; dB; corr"))
    return rows


def low_frequency_fidelity():
    """Guitar chord, FULL source. Energy between the known partials below 400 Hz
    (through the 177-354 Hz crossover transition), and the lowest string (E2)."""
    rows = []
    fs, n = FS, 12 * FS
    dec, conv = decomp(fixtures.make("guitar", fs), t0=GUITAR[0], t1=GUITAR[1], conventional=True)
    parts = guitar_partials(400.0)
    nop = G.dissolve_params(1.0, fs)
    nop = G.CloudParams(**{**nop.__dict__, "pitch_st": 0.0, "octave_prob": 0.0})
    renders = {"TRACE": tile(dec.per_src, n), "CLOUD (unguided, no pitch)": G.cloud(dec.per_src, fs, n, nop, seed=1)[0]}
    for label, d in (("SPLIT", dec), ("conventional", conv)):
        for strat, D in (("s1", 1.0), ("s2_keep", 1.0), ("s2_fade", 1.0), ("s3", 1.0)):
            renders[f"{label} {strat} D={D}"] = SP.render_split(d, fs, n, strat, D, seed=1)[0]
    spr = {k: sideband_ratio_db(y, fs, parts, 400.0) for k, y in renders.items()}
    trk = {k: partial_track(y, fs, 82.41) for k, y in renders.items()}
    for k in renders:
        rows.append(_row("low_frequency", f"{k}: energy between partials below 400 Hz re partial energy", round(spr[k], 1), "dB"))
        rows.append(_row("low_frequency", f"{k}: E2 partial median frequency re TRACE / spread (IQR) / envelope peak-to-peak",
                         f"{trk[k][0] - trk['TRACE'][0]:+.3f} c / {trk[k][1]:.2f} c / {trk[k][2]:.1f} dB", "cents; cents; dB"))
    gain = spr["CLOUD (unguided, no pitch)"] - spr["SPLIT s1 D=1.0"]
    rows.append(_row("low_frequency", "S1 vs CLOUD: reduction of energy between partials below 400 Hz", round(gain, 1), "dB",
                     gain >= LOW_SIDEBAND_GAIN_MIN_DB, f">= {LOW_SIDEBAND_GAIN_MIN_DB}"))
    drift = abs(trk["SPLIT s1 D=1.0"][0] - trk["TRACE"][0])
    rows.append(_row("low_frequency", "S1: E2 partial median frequency re TRACE", round(drift, 4), "cents", drift <= LOW_PITCH_TOL_CENTS, LOW_PITCH_TOL_CENTS))
    R = len(dec.per_src)
    for k in ("TRACE", "CLOUD (unguided, no pitch)", "SPLIT s1 D=1.0", "SPLIT s2_keep D=1.0", "SPLIT s2_fade D=1.0", "SPLIT s3 D=1.0"):
        ac = [period_autocorr(b, R) for b in band_split(renders[k], fs, XO)]
        rows.append(_row("low_frequency", f"{k}: waveform repetition at the loop period, low / mid / high band (1 = coherent TRACE)",
                         " / ".join(f"{v:.2f}" for v in ac), "corr"))
    return rows


def transient_response():
    """A single click in the middle of a silent selection: how long each band
    rings and how much of it arrives BEFORE the click."""
    rows = []
    fs, N = FS, NFFT
    x = np.zeros((4 * fs, 1))
    x[int(1.4 * fs)] = 1.0
    dec, conv = decomp(x, t0=1.0, t1=1.75, conventional=True)
    k = int(np.argmax(np.abs(dec.per_src[:, 0])))
    for label, d in (("spectral", dec), ("LR4", conv)):
        for i, b in enumerate(d.trace):
            e = b[:, 0] ** 2
            c = np.cumsum(e) / e.sum()
            dur = (np.searchsorted(c, 0.995) - np.searchsorted(c, 0.005)) / fs
            rows.append(_row("transient", f"{label} band {i}: 99 % energy duration / share of energy before the click",
                             f"{1000 * dur:.2f} ms / {100 * e[:k].sum() / e.sum():.1f} %", "ms / %"))
        s = sum(d.trace)[:, 0]
        e = s ** 2
        c = np.cumsum(e) / e.sum()
        rows.append(_row("transient", f"{label} sum of unmodified bands: 99 % energy duration",
                         round(1000 * (np.searchsorted(c, 0.995) - np.searchsorted(c, 0.005)) / fs, 3), "ms"))
    return rows


def degenerate():
    rows = []
    fs = FS
    dec = decomp(np.zeros((4 * fs, 2)))
    z = all(bool(np.all(SP.render_split(dec, fs, fs, s, 1.0)[0] == 0)) for s in SP.STRATEGIES)
    rows.append(_row("degenerate", "silent capture -> exactly silent SPLIT, every strategy", z, "bool", z, True))
    dec = decomp(fixtures.make("synth", fs), fs, 8192, 1.0, 1.2)
    ok = all(Mx.is_finite(SP.render_split(dec, fs, 2 * fs, s, 1.0, pitch="octaves")[0]) for s in SP.STRATEGIES)
    rows.append(_row("degenerate", f"0.2 s selection at N=8192 (period {len(dec.per_src)} samples): finite, every strategy", ok, "bool", ok, True))
    bad = 0
    for xo in ([2000, 250], [250, 250], [0, 250], [250, 24000], [-5], [], [float("nan")]):
        try:
            SP.band_masks(NFFT, fs, xo)
        except ValueError:
            bad += 1
    rows.append(_row("degenerate", "invalid crossover lists refused (unsorted, equal, <= 0, >= Nyquist, empty, NaN)", f"{bad} of 7", "refused", bad == 7, 7))
    x = fixtures.make("guitar", fs)
    for xo, label in (([12.0, 2000], "crossover at 12 Hz (about one bin)"), ([250, 23500], "crossover at 23.5 kHz"),
                      ([1000], "2 bands"), ([120, 500, 2000, 8000], "5 bands")):
        dec = decomp(x, crossovers=xo)
        y0 = SP.render_split(dec, fs, 2 * fs, "s3", 0.0)[0]
        y1, info = SP.render_split(dec, fs, 2 * fs, "s2_fade", 1.0)
        ok = Mx.error_db(y0, tile(dec.per_src, 2 * fs)) <= D0_ERR_DB and Mx.is_finite(y1) and info["max_active_total"] <= TOTAL_GRAINS_MAX
        rows.append(_row("degenerate", f"{label}: exact at DISSOLVE 0, finite at 1, {info['max_active_total']} grains", ok, "bool", ok, True))
    dec = decomp(fixtures.make("synth", fs), low=2000, high=10000, source="filtered")  # absolute 250/2000 on a 2-10 kHz source
    y = SP.render_split(dec, fs, 2 * fs, "s1", 1.0)[0]
    ok = Mx.is_finite(y) and Mx.rms(y) > 0
    rows.append(_row("degenerate", "FILTERED 2-10 kHz source with absolute 250 / 2000 Hz crossovers (two nearly empty bands): finite", ok, "bool", ok, True))
    return rows


def source_semantics():
    """FULL vs FILTERED: where the source's energy falls among the bands."""
    rows = []
    fs = FS
    cases = {"guitar/long_sustain": ("guitar", 2.30, 3.80, 350, 5000), "vocal/mid_band_rfc": ("vocal", 1.00, 1.80, 350, 5000),
             "synth/upper_harmonics": ("synth", 1.00, 1.75, 2000, 10000)}
    for cname, (src, t0, t1, lo, hi) in cases.items():
        x = fixtures.make(src, fs)
        rel = SP.resolve_crossovers({"mode": "relative", "fractions": [1 / 3, 2 / 3]}, lo, hi, fs)
        for label, source, xo in (("FULL, absolute", "full", XO), ("FILTERED, absolute", "filtered", XO), ("FILTERED, relative", "filtered", rel)):
            dec = decomp(x, t0=t0, t1=t1, low=lo, high=hi, source=source, crossovers=xo)
            e = np.array([np.sum(b ** 2) for b in dec.cloud])
            rows.append(_row("source", f"{cname} {label} crossovers {[round(c) for c in xo]} Hz: energy share low / mid / high",
                             " / ".join(f"{v:.3f}" for v in e / e.sum()), "fraction"))
    return rows


def edge_leak():
    """P0-B K2 revisited per band: audio adjacent in time that rings into a band
    buffer, by superposition, before and after the seam crossfade."""
    rows = []
    fs, N = FS, NFFT
    x = fixtures.make("guitar", fs)
    t0, t1 = GUITAR[0], GUITAR[1]
    p = VC.prepare(x, fs, N, t0, t1, 0.0, None, xfade_s=None)
    s0, n = p["info"]["start_sample"], p["info"]["samples"]
    y = x.copy()
    y[s0:s0 + n] = 0
    q = VC.prepare(y, fs, N, t0, t1, 0.0, None, xfade_s=None)
    B = SP.band_masks(N, fs, XO)
    seam = E.loop_period(p["spectral"], fs, 0.08, "aligned")[1]
    e = int(0.02 * fs)
    from dataclasses import replace
    for i, name in enumerate(("low", "mid", "high")):
        whole = G.capture_buffer(p["history"], replace(p["cap"], freq_mask=B[i]))[0]
        leak = G.capture_buffer(q["history"], replace(q["cap"], freq_mask=B[i]))[0]
        own = whole - leak
        edge = lambda v: np.concatenate([v[:e], v[-e:]])
        pl, po = SP.apply_seam(leak, seam), SP.apply_seam(own, seam)
        rows.append(_row("edge_leak", f"FULL source, {name} band: neighbour audio re selected audio, whole buffer / within 20 ms of an edge",
                         f"{Mx.db(Mx.rms(leak) / Mx.rms(own)):.1f} / {Mx.db(Mx.rms(edge(leak)) / Mx.rms(edge(own))):.1f}", "dB"))
        rows.append(_row("edge_leak", f"FULL source, {name} band, after the 80 ms seam crossfade: whole periodic buffer / first 20 ms",
                         f"{Mx.db(Mx.rms(pl) / Mx.rms(po)):.1f} / {Mx.db(Mx.rms(pl[:e]) / Mx.rms(po[:e])):.1f}", "dB"))
    leak = sum(G.capture_buffer(q["history"], replace(q["cap"], freq_mask=b))[0] for b in B)
    rows.append(_row("edge_leak", "FULL source, sum of the three bands: neighbour audio (cancels when bands are unmodified)",
                     round(Mx.db(Mx.rms(leak) / Mx.rms(p["spectral"])), 1), "dB"))
    return rows


def aliasing():
    """Upward transposition has no anti-alias filter (P0-B K7). Two tones through
    the grain reader at +12 st, and how much of each fixture's high band is exposed."""
    rows = []
    fs = FS
    t = np.arange(fs) / fs
    buf = (0.25 * (np.sin(2 * np.pi * 5000 * t) + np.sin(2 * np.pi * 15000 * t)))[:, None]
    for st in (12, 7, 0.15):
        y = G.read(buf, 100.0, fs // 2, 2 ** (st / 12))
        r = 2 ** (st / 12)
        want, ali = 5000 * r, 15000 * r
        folded = ali if ali < fs / 2 else fs - ali
        rows.append(_row("aliasing", f"+{st} st: 5 kHz tone arrives at {want:.0f} Hz at / 15 kHz tone {'aliases to' if ali > fs / 2 else 'arrives at'} {folded:.0f} Hz at",
                         f"{VC._tone_level_db(y, want, fs) - Mx.db(0.25):+.1f} / {VC._tone_level_db(y, folded, fs) - Mx.db(0.25):+.1f}", "dB re source tone"))
    for name in fixtures.NAMES:
        dec = decomp(fixtures.make(name, fs))
        hb = dec.cloud[-1]
        fr = [Mx.band_energy_fraction(hb, fs, lo, fs / 2) for lo in (fs / 4, fs / 2 / 2 ** (7 / 12))]
        rows.append(_row("aliasing", f"{name}: share of high-band (>2 kHz) energy above fs/4 = 12 kHz (aliases at +12 st) / above 16 kHz (aliases at +7 st)",
                         f"{fr[0]:.4f} / {fr[1]:.4f}", "fraction"))
        y = G.cloud(hb, fs, 6 * fs, SP.band_params("s1", fs, 3, len(hb), "octaves")[-1], seed=1)[0]
        rows.append(_row("aliasing", f"{name}: high band with octave jumps, energy landing below the 2 kHz crossover",
                         round(Mx.band_energy_fraction(y, fs, 0, XO[1] * 2 ** -0.5), 4), "fraction"))
    return rows


def memory_and_cost():
    """Estimates for a C++ port. Counts, not measurements."""
    rows = []
    for fs, N in ((44100, 4096), (48000, 4096), (88200, 8192), (96000, 8192)):
        H = S.hop(N)
        M = int(np.ceil(1.5 * fs / H))
        one = M * H * 2 * 4 / 2 ** 20
        rows.append(_row("memory", f"fs={fs} N={N}: band buffers for 3 bands (3 TRACE + 3 CLOUD, stereo float32, max selection) vs one P0-B buffer",
                         f"{6 * one:.2f} / {one:.2f}", "MiB"))
        rows.append(_row("cost", f"fs={fs} N={N}: capture-time inverse FFTs, 6 band buffers vs P0-B (stereo, max selection)",
                         f"{6 * (M + 4) * 2} / {(M + 4) * 2}", "IFFT"))
        rows.append(_row("cost", f"fs={fs}: conventional alternative at capture time: biquad sections x samples (LR4 + Butterworth-3, 3 bands, stereo)",
                         f"{(12 + 8) * 2} x {M * H}", "sections x samples"))
        rows.append(_row("cost", f"fs={fs}: steady state at the total ceiling: 32 grains x 4 taps x 2 ch + 3 TRACE readers x 2 ch",
                         32 * 4 * 2 * fs + 3 * 2 * fs, "taps/s"))
    rows.append(_row("cost", "grain pools: one per band, budgets (6, 10, 16); measured use at defaults", "0-5 per band, 15 total", "grains"))
    rows.append(_row("cost", "shared-schedule alternative: one grain reading 3 band buffers costs 3 x the taps of one grain", 3, "x"))
    return rows


def python_timing():
    x = fixtures.make("guitar", FS)
    rows = []
    dec = decomp(x)
    for label, fn in (("spectral decomposition, 3 bands (7 reconstructions)", lambda: decomp(x)),
                      ("6 s SPLIT s3 at DISSOLVE 1", lambda: SP.render_split(dec, FS, 6 * FS, "s3", 1.0))):
        t = time.perf_counter()
        fn()
        rows.append({"case": label, "seconds": round(time.perf_counter() - t, 3)})
    return rows


CHECKS = (masks_and_reconstruction, conventional_crossover, isolation, transparency_and_holes, continuity,
          polyphony_and_determinism, headroom_policies, stereo, low_frequency_fidelity, transient_response, degenerate,
          source_semantics, edge_leak, aliasing, memory_and_cost)


def run_all():
    rows = [r for check in CHECKS for r in check()]
    summary = {k: sum(r["result"] == k for r in rows) for k in ("PASS", "FAIL", "info")}
    return {"summary": summary, "rows": rows}
