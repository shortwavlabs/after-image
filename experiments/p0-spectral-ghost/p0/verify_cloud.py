# SPDX-License-Identifier: AGPL-3.0-only
"""P0-B numerical verification of the capture buffer, CLOUD engine and DISSOLVE.

Threshold provenance: every limit below was committed in its own commit before
the granular engine existed (see git history of this file), so none of them was
chosen after seeing a measurement. If a limit fails, the algorithm is changed or
the row is reported as FAIL; the constant is not edited. Rows marked "info"
have no limit. Nothing here says how a render sounds.
"""
CAPTURE_RECON_DB = -90.0       # full-band capture buffer vs the source samples of the selected region
MASK_REJECT_DB = -60.0         # tone two octaves outside the selected band, level in buffer re its source level
WINDOW_END_MAX = 1e-4          # last sample of a grain window (first sample must be exactly 0)
GRAIN_CLICK_RATIO_MAX = 1.25   # same judgement as P0-A CLICK_RATIO_MAX
GRAIN_CLICK_CONTROL_MIN = 2.0  # the rectangular-window control must be detected
PITCH_TOL_CENTS = 1.0
REVERSE_ERR_DB = -200.0        # reversed read vs time-flipped forward read of the same span
DENSITY_COUNT_TOL = 0.02       # relative error of scheduled grain count vs density * duration
OVERLAP_TOL = 0.05             # relative error of mean simultaneous grains vs density * grain duration
MONO_COMPAT_MIN_DB = -3.02     # mono source at 100 % stereo spread (analytic floor of the balance law is -3.01 dB)
DENSITY_RMS_TOL_DB = 1.5       # decorrelated cloud RMS re buffer RMS, wherever nominal overlap power >= 1
D0_ERR_DB = -120.0             # structural DISSOLVE at 0 vs the TRACE loop it is built on
DISSOLVE_STEP_MAX_DB = 1.0     # RMS change between adjacent DISSOLVE settings 0.05 apart, stationary material
DISSOLVE_RANGE_MAX_DB = 3.0    # RMS range over DISSOLVE 0..1, stationary material

import time
from dataclasses import replace

import numpy as np

from . import capture as C
from . import engines as E
from . import fixtures
from . import granular as G
from . import metrics as Mx
from . import stft as S
from .verify import _row

FS, NFFT = 48000, 4096
CASES = {  # P0-A regions: name -> (t0, t1, low_hz, high_hz)
    "guitar": (0.60, 1.35, 20, None), "vocal": (1.00, 1.80, 350, 5000),
    "drums": (0.90, 1.65, 20, None), "synth": (1.00, 1.75, 2000, 10000),
}


def prepare(x, fs, N, t0, t1, low, high, xfade_s=0.08, feed_until=None):
    """History -> validated capture -> spectral and raw buffers -> shared-seam periodic pair."""
    x = S.as_2d(x)
    h = C.SpectralHistory(fs, N, x.shape[1], np.complex64)
    h.push_signal(x[:int(t1 * fs) + N if feed_until is None else feed_until])
    first, last = C.frames_for_interval(t0, t1, fs, N)
    cap = C.capture(h, C.CaptureRequest(h.epoch, first, last, float(low), float(fs / 2 if high is None else min(high, fs / 2))))
    spec, info = G.capture_buffer(h, cap)
    raw = x[info["start_sample"]:info["start_sample"] + info["samples"]]
    out = {"history": h, "cap": cap, "spectral": spec, "raw": raw, "info": info, "first": first, "last": last}
    if xfade_s is not None:
        out["per_s"], out["per_r"], out["seam"] = G.periodic_pair(spec, raw, fs, xfade_s)
    return out


def _noise(fs=FS, seconds=1.0, seed=7, channels=2, dual_mono=False):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((int(seconds * fs), 1 if dual_mono else channels)) * 0.1
    return np.repeat(x, channels, axis=1) if dual_mono else x


def _tone_level_db(x, f, fs):
    """Amplitude (dB re 1) of the component at f Hz, by least squares on channel 0."""
    t = np.arange(len(x)) / fs
    A = np.stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t)], axis=1)
    return Mx.db(np.hypot(*np.linalg.lstsq(A, x[:, 0], rcond=None)[0]))


# --------------------------------------------------------------------------
def capture_reconstruction():
    rows = []
    for fs, N in ((48000, 2048), (48000, 4096), (48000, 8192), (44100, 4096), (96000, 8192)):
        worst, gain = -999.0, []
        for name, (t0, t1, _lo, _hi) in CASES.items():
            p = prepare(fixtures.make(name, fs), fs, N, t0, t1, 0.0, None, xfade_s=None)
            worst = max(worst, Mx.error_db(p["spectral"], p["raw"]))
            gain.append(p["info"]["samples"] - p["info"]["p0a_interior_samples"])
        rows.append(_row("capture_reconstruction", f"fs={fs} N={N} full band, 4 fixtures", round(worst, 1), "dB",
                         worst <= CAPTURE_RECON_DB, CAPTURE_RECON_DB))
        rows.append(_row("capture_reconstruction", f"fs={fs} N={N} usable samples gained over P0-A interior",
                         int(gain[0]), "samples"))
    # 0.25 s selection: how much loop material each method leaves
    for N in S.FFT_SIZES:
        p = prepare(fixtures.make("synth", FS), FS, N, 1.0, 1.25, 350, 5000)
        p0a = E.loop(p["cap"], FS, 0.08, "aligned")[1]  # what P0-A's loop_aligned80 actually does with this capture
        rows.append(_row("capture_reconstruction", f"0.25 s selection N={N}: loop period P0-B (context) / P0-A loop_aligned80",
                         f"{p['seam']['period_samples']} / {p0a['period_samples']}", "samples"))
        rows.append(_row("capture_reconstruction", f"0.25 s selection N={N}: crossfade P0-B / P0-A (80 ms requested = 3840)",
                         f"{p['seam']['xfade_samples']} / {p0a['xfade_samples']}", "samples"))
    return rows


def neighbour_isolation():
    rows = []
    fs, N, H = FS, NFFT, S.hop(NFFT)
    x = fixtures.make("guitar", fs)
    t0, t1 = 0.60, 1.35
    ref = prepare(x, fs, N, t0, t1, 0.0, None, xfade_s=None)
    s0, n = ref["info"]["start_sample"], ref["info"]["samples"]
    lo, hi = (ref["first"] - 5) * H, (ref["last"] + 3) * H  # samples the frames first-2..last+2 can see
    rng = np.random.default_rng(3)
    y = x.copy()
    y[:lo] = rng.standard_normal(y[:lo].shape)
    y[hi:] = rng.standard_normal(y[hi:].shape)
    d = np.max(np.abs(prepare(y, fs, N, t0, t1, 0.0, None, xfade_s=None)["spectral"] - ref["spectral"]))
    rows.append(_row("neighbour_isolation", "audio outside the context frames replaced by noise: buffer change",
                     float(d), "abs", d == 0.0, 0.0))
    y = x.copy()
    y[:s0] = rng.standard_normal(y[:s0].shape)
    y[s0 + n:] = rng.standard_normal(y[s0 + n:].shape)
    e = Mx.error_db(prepare(y, fs, N, t0, t1, 0.0, None, xfade_s=None)["spectral"], x[s0:s0 + n])
    rows.append(_row("neighbour_isolation", "full band, 0 dBFS-scale noise right up to both selection edges: buffer vs source",
                     round(e, 1), "dB", e <= CAPTURE_RECON_DB, CAPTURE_RECON_DB))
    # Band-limited mask: the mask is a filter, so neighbouring audio rings into the
    # selection. The capture is linear, so the leak is exactly the buffer obtained
    # from the source with the selected samples zeroed.
    x = fixtures.make("guitar", fs)
    for N in S.FFT_SIZES:
        for low, high in ((1000, 2000), (100, 200)):
            ref = prepare(x, fs, N, t0, t1, low, high, xfade_s=None)
            s0, n = ref["info"]["start_sample"], ref["info"]["samples"]
            y = x.copy()
            y[s0:s0 + n] = 0
            leak = prepare(y, fs, N, t0, t1, low, high, xfade_s=None)["spectral"]
            own = ref["spectral"] - leak
            e = int(0.02 * fs)
            edge = np.concatenate([leak[:e], leak[-e:]]), np.concatenate([own[:e], own[-e:]])
            rows.append(_row("neighbour_isolation", f"N={N} band {low}-{high} Hz, guitar: neighbour audio in buffer, whole / within 20 ms of an edge / deeper than 50 ms",
                             f"{Mx.db(Mx.rms(leak) / Mx.rms(own)):.1f} / {Mx.db(Mx.rms(edge[0]) / Mx.rms(edge[1])):.1f} / "
                             f"{Mx.db(Mx.rms(leak[int(0.05 * fs):-int(0.05 * fs)]) / Mx.rms(own[int(0.05 * fs):-int(0.05 * fs)])):.1f}",
                             "dB re selected audio"))
    # Selection that reaches the newest frame: no future context yet.
    x = fixtures.make("guitar", fs)
    N, H = NFFT, S.hop(NFFT)
    _, last = C.frames_for_interval(0.60, 1.35, fs, N)
    p = prepare(x, fs, N, 0.60, 1.35, 0.0, None, xfade_s=None, feed_until=(last + 1) * H)
    i = p["info"]
    e = Mx.error_db(p["spectral"], p["raw"])
    rows.append(_row("neighbour_isolation", f"no future context (selection ends at newest frame): tail trimmed {i['trimmed_tail']} samples, buffer vs source",
                     round(e, 1), "dB", e <= CAPTURE_RECON_DB and i["trimmed_tail"] == 3 * H // 2, CAPTURE_RECON_DB))
    return rows


def mask_integrity():
    rows = []
    fs = FS
    t = np.arange(4 * fs) / fs
    x = 0.25 * (np.sin(2 * np.pi * 1500 * t) + np.sin(2 * np.pi * 250 * t) + np.sin(2 * np.pi * 8000 * t))
    for N in S.FFT_SIZES:
        b = prepare(x, fs, N, 1.0, 1.75, 1000, 2000, xfade_s=None)["spectral"]
        for f in (250, 8000):
            v = _tone_level_db(b, f, fs) - Mx.db(0.25)
            rows.append(_row("mask_integrity", f"N={N} band 1-2 kHz: {f} Hz tone (2 octaves outside)", round(v, 1), "dB re source",
                             v <= MASK_REJECT_DB, MASK_REJECT_DB))
        rows.append(_row("mask_integrity", f"N={N} band 1-2 kHz: 1500 Hz tone (in band)",
                         round(_tone_level_db(b, 1500, fs) - Mx.db(0.25), 3), "dB re source"))
    return rows


def grain_windows():
    rows = []
    for kind in ("hann", "tukey"):
        worst_end, start_ok = 0.0, True
        for fs in (44100, 96000):
            for dur in (0.02, 0.3):
                w = G.grain_window(G.grain_length(G.CloudParams(grain_s=dur), fs), kind)
                start_ok &= bool(w[0] == 0.0 and w.max() <= 1.0 and w.min() >= 0.0)
                worst_end = max(worst_end, float(w[-1]))
        rows.append(_row("grain_window", f"{kind}: first sample exactly 0, values in [0, 1]", start_ok, "bool", start_ok, True))
        rows.append(_row("grain_window", f"{kind}: largest last sample, 20-300 ms at 44.1/96 kHz", worst_end, "abs",
                         worst_end <= WINDOW_END_MAX, WINDOW_END_MAX))
    w = G.grain_window(5760, "hann")
    rows.append(_row("grain_window", "hann: deviation of 50 %-overlap sum from 1", float(np.max(np.abs(w[:2880] + w[2880:] - 1))), "abs"))
    return rows


def grain_clicks():
    """Single grains cut out of a loud, smooth buffer with a DC offset: the step at
    the grain edges relative to the steepest step inside the grain."""
    rows = []
    fs, R = FS, FS
    t = np.arange(R) / fs
    buf = (0.5 + 0.4 * np.sin(2 * np.pi * 100 * t))[:, None]
    rng = np.random.default_rng(11)
    for kind in ("hann", "tukey", "rect"):
        worst = 0.0
        for _ in range(40):
            L = int(rng.integers(960, 14400))
            g = np.zeros(1, dtype=G.GRAIN_FIELDS)
            g["onset"], g["length"], g["pos"], g["speed"] = 1000, L, rng.uniform(0, R), 2 ** rng.uniform(-1, 1)
            g["reverse"], g["amp"], g["gain"], g["gl"], g["gr"] = rng.random() < 0.5, 1, 1, 1, 1
            y = G.render(buf, g, L + 2000, kind)
            worst = max(worst, Mx.click_ratio(y, [1000, 1000 + L], guard=2))
        if kind == "rect":
            rows.append(_row("grain_clicks", "rect window control: edge step / steepest interior step", round(worst, 2), "ratio",
                             worst >= GRAIN_CLICK_CONTROL_MIN, f">= {GRAIN_CLICK_CONTROL_MIN}"))
        else:
            rows.append(_row("grain_clicks", f"{kind}: worst edge step / steepest interior step, 40 random grains", round(worst, 3),
                             "ratio", worst <= GRAIN_CLICK_RATIO_MAX, GRAIN_CLICK_RATIO_MAX))
    return rows


def determinism():
    rows = []
    p = G.dissolve_params(1.0, FS)
    a, b, c = (G.schedule(30000, FS, 6 * FS, p, seed=s) for s in (5, 5, 6))
    rows.append(_row("determinism", "same seed -> identical schedule", bool(a.tobytes() == b.tobytes()), "bool", a.tobytes() == b.tobytes(), True))
    rows.append(_row("determinism", "different seed -> different schedule", bool(a.tobytes() != c.tobytes()), "bool", a.tobytes() != c.tobytes(), True))
    pr = prepare(fixtures.make("vocal", FS), FS, NFFT, *CASES["vocal"])
    y1, y2 = (G.dissolve(pr["per_s"], FS, 3 * FS, 0.7, seed=9)[0] for _ in range(2))
    same = Mx.sha256(y1, np.float64) == Mx.sha256(y2, np.float64)
    rows.append(_row("determinism", "two renders of the same cloud: float64 sha256 equal", same, "bool", same, True))
    ok = len(pr["per_s"]) == len(pr["per_r"])
    rows.append(_row("determinism", "spectral and raw buffers share one period (same schedule addresses both)", ok, "bool", ok, True))
    # time-varying DISSOLVE consumes the same random stream as a fixed setting
    g1 = G.schedule(30000, FS, FS, lambda t: G.dissolve_params(t, FS), seed=5)
    rows.append(_row("determinism", "grains in 1 s of a 0->1 DISSOLVE ramp", int(len(g1)), "grains"))
    return rows


def pitch_and_reverse():
    rows = []
    fs = FS
    buf = (0.5 * np.sin(2 * np.pi * 440 * np.arange(fs) / fs))[:, None]  # 440 whole cycles: periodic
    for st in (-12, -7, -1, 0, 1, 7, 12):
        y = G.read(buf, 123.4, fs, 2 ** (st / 12))[:, 0]
        cents = 1200 * np.log2(Mx.sine_frequency(y, fs) / (440 * 2 ** (st / 12)))
        rows.append(_row("pitch", f"{st:+d} st: measured vs intended frequency", round(float(cents), 4), "cents",
                         abs(cents) <= PITCH_TOL_CENTS, PITCH_TOL_CENTS))
    # Reverse, checked independently of read(): on a ramp buffer (value = index) a
    # rendered grain must equal (pos + speed * (L - 1 - k)) * window, i.e. the same
    # source span as the forward grain, traversed backwards.
    R, L = 60000, 9600
    ramp = np.arange(R, dtype=np.float64)[:, None]
    w = G.grain_window(L, "hann")
    for speed in (1.0, 2 ** (7 / 12), 0.5):
        g = np.zeros(1, dtype=G.GRAIN_FIELDS)
        g["onset"], g["length"], g["pos"], g["speed"], g["reverse"] = 0, L, 1000.25, speed, True
        g["amp"], g["gain"], g["gl"], g["gr"] = 1, 1, 1, 1
        want = (1000.25 + speed * (L - 1 - np.arange(L))) * w
        e = Mx.error_db(G.render(ramp, g, L, "hann")[:, 0], want)
        rows.append(_row("reverse", f"speed {speed:.3f}: rendered reversed grain vs analytic ramp", round(e, 1), "dB",
                         e <= REVERSE_ERR_DB, REVERSE_ERR_DB))
    return rows


def density_and_polyphony():
    rows = []
    fs, n = FS, 20 * FS
    for dur in (0.02, 0.1, 0.3):
        for dens in (2, 10, 20, 50, 100):
            p = G.CloudParams(grain_s=dur, density_hz=dens)
            g = G.schedule(fs, fs, n, p, seed=1, max_grains=1000)
            count = int(np.sum((g["onset"] >= 0) & (g["onset"] < n)))
            err = count / (dens * n / fs) - 1
            rows.append(_row("density", f"{dur * 1000:.0f} ms, {dens}/s: scheduled grains in 20 s", count, "grains",
                             abs(err) <= DENSITY_COUNT_TOL, f"{dens * 20} +/- {DENSITY_COUNT_TOL:.0%}"))
            act = G.active_count(g, n)
            oerr = act[fs:].mean() / (dens * G.grain_length(p, fs) / fs) - 1
            rows.append(_row("overlap", f"{dur * 1000:.0f} ms, {dens}/s: mean / max simultaneous grains (no ceiling)",
                             f"{act[fs:].mean():.2f} / {int(act.max())}", "grains", abs(oerr) <= OVERLAP_TOL,
                             f"{dens * dur:.2f} +/- {OVERLAP_TOL:.0%}"))
    p = G.CloudParams(grain_s=0.3, density_hz=100)  # demands 30 grains on average, more at times
    for ceiling in (8, 16, 32):
        g = G.schedule(fs, fs, n, p, seed=1, max_grains=ceiling)
        mx = int(G.active_count(g, n).max())
        rows.append(_row("polyphony", f"300 ms at 100/s, ceiling {ceiling}: max simultaneous", mx, "grains", mx <= ceiling, ceiling))
        rows.append(_row("polyphony", f"300 ms at 100/s, ceiling {ceiling}: grains dropped", f"{int(g['dropped'].sum())} of {len(g)}", "grains"))
    g = G.schedule(fs, fs, n, G.dissolve_params(1.0, fs), seed=1)
    d = int(g["dropped"].sum())
    rows.append(_row("polyphony", "DISSOLVE = 1 default cloud, ceiling 32: grains dropped", d, "grains", d == 0, 0))
    return rows


def degenerate():
    rows = []
    fs = FS
    y, _ = G.dissolve(np.zeros((fs // 2, 2)), fs, 2 * fs, 1.0)
    z = bool(np.all(y == 0))
    rows.append(_row("degenerate", "silent buffer -> exactly silent cloud", z, "bool", z, True))
    p = prepare(fixtures.make("synth", fs), fs, 8192, 1.0, 1.2, 350, 5000)  # P0-A minimum selection at the largest FFT
    y, info = G.cloud(p["per_s"], fs, 3 * fs, G.CloudParams(grain_s=0.3, density_hz=100, pitch_st=12, reverse_prob=0.5, spread=1))
    ok = Mx.is_finite(y) and Mx.rms(y) > 0
    rows.append(_row("degenerate", f"0.2 s selection at N=8192 (period {len(p['per_s'])} samples), 300 ms grains +/-12 st: finite, non-silent",
                     ok, "bool", ok, True))
    try:
        G.periodic_pair(np.zeros((6, 2)), np.zeros((6, 2)), fs)
        raised = False
    except E.EngineError:
        raised = True
    rows.append(_row("degenerate", "6-sample buffer is refused", raised, "bool", raised, True))
    return rows


def safety():
    rows = []
    fs, n = FS, 6 * FS
    env = E.envelope(n, fs, 5.0)
    bad = den = 0
    for name, c in CASES.items():
        p = prepare(fixtures.make(name, fs), fs, NFFT, *c)
        for D in (0.0, 0.5, 1.0):
            for buf in (p["per_s"], p["per_r"]):
                y = G.dissolve(buf, fs, n, D, seed=2)[0] * env
                bad += not Mx.is_finite(y)
                den += Mx.denormal_count(y)
    rows.append(_row("safety", "24 clouds (4 fixtures x D 0/0.5/1 x spectral/raw): non-finite renders", bad, "count", bad == 0, 0))
    rows.append(_row("safety", "same, after MEMORY envelope: float32 denormal samples", den, "count", den == 0, 0))
    return rows


def stereo():
    rows = []
    fs, n = FS, 10 * FS
    mono = _noise(dual_mono=True)
    for spread in (0.0, 0.5, 1.0):
        y, _ = G.cloud(mono, fs, n, replace(G.dissolve_params(1.0, fs), spread=spread), seed=4)
        mc = Mx.mono_compat_db(y)
        rows.append(_row("stereo", f"dual-mono source, spread {spread:.0%}: mono compatibility", round(mc, 3), "dB",
                         mc >= MONO_COMPAT_MIN_DB, f">= {MONO_COMPAT_MIN_DB}"))
        rows.append(_row("stereo", f"dual-mono source, spread {spread:.0%}: interchannel correlation", round(Mx.interchannel_corr(y), 3), "corr"))
    anti = mono * (1, -1)
    y, _ = G.cloud(anti, fs, n, G.dissolve_params(1.0, fs), seed=4)
    rows.append(_row("stereo", "anti-phase source stays anti-phase (the balance law cannot repair a source): correlation",
                     round(Mx.interchannel_corr(y), 3), "corr"))
    for name, c in CASES.items():
        p = prepare(fixtures.make(name, fs), fs, NFFT, *c)
        y, _ = G.dissolve(p["per_s"], fs, n, 1.0, seed=4)
        rows.append(_row("stereo", f"{name}: correlation source buffer -> cloud first s / last s",
                         f"{Mx.interchannel_corr(p['per_s']):.3f} -> {Mx.interchannel_corr(y[:fs]):.3f} / {Mx.interchannel_corr(y[-fs:]):.3f}", "corr"))
        rows.append(_row("stereo", f"{name}: mono compatibility source buffer -> cloud",
                         f"{Mx.mono_compat_db(p['per_s']):.2f} -> {Mx.mono_compat_db(y):.2f}", "dB"))
    return rows


def amplitude_buildup():
    """Level against density for decorrelated grains (what the gain law assumes)
    and for the coherent worst case (zero spray and jitter: every grain reads the
    same instant), on a stationary noise buffer. True peaks, no limiter."""
    rows = []
    fs, n = FS, 20 * FS
    buf = _noise()
    r0, p0 = Mx.rms(buf), Mx.peak(buf)
    for dur in (0.02, 0.1, 0.3):
        for dens in (2, 5, 10, 20, 50, 100):
            p = G.CloudParams(grain_s=dur, density_hz=dens)
            L = G.grain_length(p, fs)
            power = dens * L / fs * float(np.mean(G.grain_window(L) ** 2))
            y, info = G.cloud(buf, fs, n, p, seed=3)
            lvl = Mx.db(Mx.rms(y[fs:]) / r0)
            gated = power >= 1.0
            rows.append(_row("amplitude_buildup", f"decorrelated {dur * 1000:.0f} ms, {dens}/s (overlap power {power:.2f}): RMS re buffer",
                             round(lvl, 2), "dB", abs(lvl) <= DENSITY_RMS_TOL_DB if gated else None,
                             f"+/- {DENSITY_RMS_TOL_DB}" if gated else None))
            rows.append(_row("amplitude_buildup", f"decorrelated {dur * 1000:.0f} ms, {dens}/s: peak re buffer peak / max active / dropped",
                             f"{Mx.db(Mx.peak(y) / p0):+.2f} / {info['max_active']} / {info['dropped']}", "dB / grains"))
    for dur, dens in ((0.1, 20), (0.1, 100), (0.3, 20), (0.3, 100)):
        for coh in (0.0, 1.0):
            p = G.CloudParams(grain_s=dur, density_hz=dens, spray=0.0, jitter=0.0, coherence=coh)
            y, info = G.cloud(buf, fs, n, p, seed=3)
            rows.append(_row("amplitude_buildup", f"coherent worst case {dur * 1000:.0f} ms, {dens}/s, gain law told coherence={coh:.0f}: RMS / peak re buffer",
                             f"{Mx.db(Mx.rms(y[fs:]) / r0):+.2f} / {Mx.db(Mx.peak(y) / p0):+.2f}", "dB"))
    # analytic ceiling: every one of max_grains voices at full window, gain, balance and interpolator overshoot
    y, info = G.cloud(buf, fs, n, G.CloudParams(grain_s=0.3, density_hz=100, spread=1.0, pitch_st=12), seed=3)
    bound = G.MAX_GRAINS * (1 / np.sqrt(G.S_REF)) * np.sqrt(2) * 1.25 * p0
    rows.append(_row("amplitude_buildup", f"hard bound max_grains*g_max*sqrt(2)*1.25 = {Mx.db(bound / p0):+.1f} dB re buffer peak; measured dense cloud peak",
                     round(Mx.db(Mx.peak(y) / p0), 2), "dB re buffer peak", Mx.peak(y) <= bound, round(Mx.db(bound / p0), 1)))
    return rows


def _sweep(per, fs, n, seed, steps=21):
    """Native (unmatched) RMS in dB re the TRACE loop for B and A over DISSOLVE 0..1."""
    reps = -(-n // len(per))
    trace = np.tile(per, (reps, 1))[:n]
    cld = G.dissolve(per, fs, n, 1.0, seed)[0]
    r0 = max(Mx.rms(trace), Mx.EPS)
    Ds = np.linspace(0, 1, steps)
    b = [Mx.db(Mx.rms(G.dissolve(per, fs, n, D, seed)[0]) / r0) for D in Ds]
    a = [Mx.db(Mx.rms(G.parallel(trace, cld, D)) / r0) for D in Ds]
    return Ds, np.array(b), np.array(a), trace, cld


def dissolve_endpoints_and_continuity():
    rows = []
    fs, n = FS, 6 * FS
    materials = {"noise": (_noise(), True)}
    for name, c in CASES.items():
        materials[name] = (prepare(fixtures.make(name, fs), fs, NFFT, *c)["per_s"], name == "synth")
    for name, (per, stationary) in materials.items():
        Ds, b, a, trace, cld = _sweep(per, fs, n, seed=1)
        e = Mx.error_db(G.dissolve(per, fs, n, 0.0, seed=1)[0], trace)
        rows.append(_row("dissolve_endpoint", f"{name}: structural D=0 vs TRACE loop", round(e, 1), "dB", e <= D0_ERR_DB, D0_ERR_DB))
        ex = bool(np.array_equal(G.parallel(trace, cld, 0.0), trace))
        rows.append(_row("dissolve_endpoint", f"{name}: parallel D=0 equals TRACE exactly", ex, "bool", ex, True))
        e = Mx.error_db(G.parallel(trace, cld, 1.0), cld)
        rows.append(_row("dissolve_endpoint", f"{name}: parallel D=1 vs CLOUD", round(e, 1), "dB", e <= D0_ERR_DB, D0_ERR_DB))
        for label, v in (("structural", b), ("parallel", a)):
            step, rng = float(np.max(np.abs(np.diff(v)))), float(np.ptp(v))
            rows.append(_row("dissolve_continuity", f"{name} {label}: largest RMS change between settings 0.05 apart", round(step, 2), "dB",
                             step <= DISSOLVE_STEP_MAX_DB if stationary else None, DISSOLVE_STEP_MAX_DB if stationary else None))
            rows.append(_row("dissolve_continuity", f"{name} {label}: RMS range over D 0..1", round(rng, 2), "dB",
                             rng <= DISSOLVE_RANGE_MAX_DB if stationary else None, DISSOLVE_RANGE_MAX_DB if stationary else None))
        # a moving DISSOLVE: 1 s RMS blocks through a 0 -> 1 ramp over 8 s
        y = G.dissolve(per, fs, 10 * fs, G.ramp(1.0, 8.0), seed=1)[0]
        blk = np.array([Mx.db(Mx.rms(y[i * fs:(i + 1) * fs])) for i in range(10)])
        rows.append(_row("dissolve_continuity", f"{name} structural 0->1 ramp over 8 s: largest change between 1 s RMS blocks",
                         round(float(np.max(np.abs(np.diff(blk)))), 2), "dB"))
    return rows


def spectral_selection():
    """What the mask still controls once grains are transposed, and what the
    spectral guide sees that a broadband guide does not."""
    rows = []
    fs, n = FS, 6 * FS
    ft = 2 ** (1 / 6)
    for name, c in CASES.items():
        if c[3] is None:
            continue
        p = prepare(fixtures.make(name, fs), fs, NFFT, *c)
        lo, hi = c[2] / ft, c[3] * ft
        end = G.dissolve_params(1.0, fs)
        for label, prm in (("no pitch", replace(end, pitch_st=0, octave_prob=0)), ("detune + octaves (default)", end),
                           ("+/-12 st uniform", replace(end, pitch_st=12, octave_prob=0))):
            fr = [Mx.band_energy_fraction(G.cloud(b, fs, n, prm, seed=1)[0], fs, lo, hi) for b in (p["per_s"], p["per_r"])]
            rows.append(_row("spectral_selection", f"{name} {c[2]}-{c[3]} Hz, {label}: in-band energy fraction spectral / conventional",
                             f"{fr[0]:.4f} / {fr[1]:.4f}", "fraction"))
    guide_cases = dict(CASES, **{"guitar 2-10 kHz": (0.60, 1.35, 2000, 10000), "drums 5-16 kHz": (0.90, 1.65, 5000, 16000)})
    for name, c in guide_cases.items():
        p = prepare(fixtures.make(name.split()[0], fs), fs, NFFT, *c)
        R, H, cap = len(p["per_s"]), S.hop(NFFT), p["cap"]
        rawf = np.stack([p["history"].frame(i, p["history"].epoch) for i in range(p["first"], p["last"] + 1)])
        for mode in ("harmonic", "transient"):
            cm = G.position_cdf(cap.frames, R, H, mode, cap.freq_mask >= 0.5)
            cb = G.position_cdf(rawf, R, H, mode)
            pm, pb = np.diff(cm, prepend=0), np.diff(cb, prepend=0)
            rows.append(_row("guided", f"{name} {mode}: share of position weight in the top 20 % of the buffer (uniform = 0.20)",
                             round(float(np.sort(pm)[-R // 5:].sum()), 3), "fraction"))
            rows.append(_row("guided", f"{name} {mode}: total-variation distance, in-band weights vs broadband weights (0 = same guide)",
                             round(float(0.5 * np.abs(pm - pb).sum()), 3), "0..1"))
    return rows


def memory_and_cost():
    """Estimates for a C++ port. Counts, not measurements."""
    rows = []
    for fs, N in ((44100, 4096), (48000, 4096), (88200, 8192), (96000, 8192)):
        H = S.hop(N)
        M = int(np.ceil(C.MAX_ROI_SECONDS * fs / H))
        buf = M * H * 2 * 4  # stereo float32, largest selection
        rows.append(_row("memory", f"fs={fs} N={N}: capture buffer for a maximum selection ({M} frames)", round(buf / 2 ** 20, 3), "MiB"))
        rows.append(_row("memory", f"fs={fs} N={N}: reconstruction scratch ({M + 4} frames WOLA, stereo float32)",
                         round((M + 7) * H * 2 * 4 / 2 ** 20, 3), "MiB"))
        rows.append(_row("cost", f"fs={fs} N={N}: capture-time inverse FFTs (stereo, maximum selection)", (M + 4) * 2, "IFFT"))
        rows.append(_row("cost", f"fs={fs} N={N}: seam search correlations (25 ms lag x 80 ms window)", f"{int(0.025 * fs) + 1} x {int(0.08 * fs)}", "lags x MAC"))
        rows.append(_row("cost", f"fs={fs}: grain reads per second at the ceiling ({G.MAX_GRAINS} grains, stereo, 4-tap)",
                         G.MAX_GRAINS * fs * 2 * 4, "taps/s"))
        rows.append(_row("cost", f"fs={fs} N={N}: added capture latency for future context", round(1000 * G.CONTEXT_FRAMES * H / fs, 1), "ms"))
    rows.append(_row("memory", "grain voice state (10 fields) x ceiling", G.MAX_GRAINS * 64, "bytes"))
    rows.append(_row("cost", "per active grain per output sample (stereo): 8 buffer taps, ~14 mul, 1 window lookup, 2 balance gains", 1, "unit"))
    rows.append(_row("cost", "per grain start: 8 uniform draws, 1 pow2, 1 sin/cos pair, 1 sqrt", 1, "unit"))
    return rows


def python_timing():
    """NumPy wall-clock, kept out of verification.json because it is not reproducible."""
    p = prepare(fixtures.make("guitar", FS), FS, NFFT, *CASES["guitar"])
    rows = []
    for label, fn in (("capture buffer + shared seam", lambda: prepare(fixtures.make("guitar", FS), FS, NFFT, *CASES["guitar"])),
                      ("6 s structural DISSOLVE = 1", lambda: G.dissolve(p["per_s"], FS, 6 * FS, 1.0)),
                      ("6 s cloud at ceiling (300 ms, 100/s)", lambda: G.cloud(p["per_s"], FS, 6 * FS, G.CloudParams(grain_s=0.3, density_hz=100)))):
        t = time.perf_counter()
        fn()
        rows.append({"case": label, "seconds": round(time.perf_counter() - t, 3)})
    return rows


CHECKS = (capture_reconstruction, neighbour_isolation, mask_integrity, grain_windows, grain_clicks, determinism,
          pitch_and_reverse, density_and_polyphony, degenerate, safety, stereo, amplitude_buildup,
          dissolve_endpoints_and_continuity, spectral_selection, memory_and_cost)


def run_all():
    rows = [r for check in CHECKS for r in check()]
    summary = {k: sum(r["result"] == k for r in rows) for k in ("PASS", "FAIL", "info")}
    return {"summary": summary, "rows": rows}
