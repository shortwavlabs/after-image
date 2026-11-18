# SPDX-License-Identifier: AGPL-3.0-only
"""Numerical verification. Every check returns rows with measured values and a
PASS/FAIL against a threshold fixed here. These are numerical statements only;
none of them says anything about how a render sounds.

Threshold provenance (stated exactly, because it matters):
  * RECON_TARGET_DB comes from the brief and predates all code.
  * The other limits were written down after one exploratory probe of the
    engines had already shown the approximate values (seam ratios 0.04-0.98,
    frequency errors < 1e-3 Hz, sine ripple 0.000 dB). They were not derived
    from those values and have not been changed since, but they were not blind.
  * CLICK_RATIO_MAX = 1.25 is a judgement ("a seam may be 25 % steeper than the
    material"). Under a strict <= 1.0 limit the worst measured row passes at
    0.995, and one experiment render (loop_ep30, 1.001) would fail.
Rows marked "info" have no threshold and are reported as measured.
"""
import math
import time

import numpy as np
from scipy.signal import chirp

from . import capture as C
from . import engines as E
from . import fixtures
from . import metrics as Mx
from . import stft as S

RECON_TARGET_DB = -90.0
FREQ_TOL_HZ = 0.05  # for partials at least FREQ_MIN_BINS bin widths above DC
FREQ_MIN_BINS = 4.0
SUSTAIN_SINE_RIPPLE_DB = 0.5
SUSTAIN_LEVEL_TOL_DB = 0.1
CLICK_RATIO_MAX = 1.25  # seam step may be at most 25 % steeper than the material
CLICK_CONTROL_MIN = 2.0  # the hard-wrap control must be detected


def _row(check, case, value, unit, passed=None, limit=None):
    return {"check": check, "case": case, "value": value, "unit": unit, "limit": limit,
            "result": "info" if passed is None else ("PASS" if passed else "FAIL")}


def test_signals(fs, N):
    rng = np.random.default_rng(1234)
    L = 3 * N + 777  # deliberately not a multiple of the hop
    t = np.arange(L) / fs
    out = {}
    for pos in (0, 1, S.hop(N) - 1, S.hop(N), N, L // 2, L - 1):
        s = np.zeros(L)
        s[pos] = 1.0
        out[f"impulse@{pos}"] = s
    noise = rng.standard_normal(L) * 0.25
    out.update({
        "silence": np.zeros(L),
        "dc": np.full(L, 0.5),
        "sine_1k": 0.5 * np.sin(2 * np.pi * 1000 * t),
        "sine_offbin": 0.5 * np.sin(2 * np.pi * 441.37 * t + 0.3),
        "chirp": 0.5 * chirp(t, 20, t[-1], 0.45 * fs, method="logarithmic"),
        "noise": noise,
        "stereo": np.stack([noise, 0.5 * np.sin(2 * np.pi * 220 * t)], axis=1),
        "stereo_antiphase": np.stack([noise, -noise], axis=1),
    })
    return out


test_signals.__test__ = False  # not a pytest test


def make_capture(x, fs, N, t0=0.5, t1=1.25, low=0.0, high=None, dtype=np.complex64, **kw):
    x = S.as_2d(x)
    h = C.SpectralHistory(fs, N, x.shape[1], dtype)
    h.push_signal(x)
    first, last = C.frames_for_interval(t0, t1, fs, N)
    return C.capture(h, C.CaptureRequest(h.epoch, first, last, low, fs / 2 if high is None else high, **kw))


def reconstruction():
    """Worst-case STFT->ISTFT error per (fs, N, spectrum dtype) over all signals."""
    rows = []
    for fs in S.SAMPLE_RATES:
        for N in S.FFT_SIZES:
            for dtype in (np.complex128, np.complex64):
                worst, worst_name = -math.inf, ""
                for name, x in test_signals(fs, N).items():
                    e = Mx.error_db(S.istft(S.stft(x, N, dtype), N, len(x)), S.as_2d(x))
                    if e > worst:
                        worst, worst_name = e, name
                rows.append(_row("reconstruction", f"fs={fs} N={N} {np.dtype(dtype).name} worst={worst_name}",
                                 round(worst, 1), "dB re ref", worst < RECON_TARGET_DB, RECON_TARGET_DB))
    return rows


def frequency_estimation():
    rows = []
    for fs in S.SAMPLE_RATES:
        for N in S.FFT_SIZES:
            for f in (55.3, 110.7, 441.37, 1000.5, 3777.7, 9000.1):
                x = 0.5 * np.sin(2 * np.pi * f * np.arange(2 * fs) / fs + 0.4)
                omega, _ = E.bin_frequencies(make_capture(x, fs, N))
                est = omega[0, int(round(f * N / fs))] / (2 * np.pi * S.hop(N)) * fs
                bins = f * N / fs
                gated = bins >= FREQ_MIN_BINS
                rows.append(_row("frequency_estimate", f"fs={fs} N={N} f={f} Hz ({bins:.1f} bins)",
                                 float(f"{est - f:.3e}"), "Hz error",
                                 abs(est - f) < FREQ_TOL_HZ if gated else None, FREQ_TOL_HZ if gated else None))
    return rows


def sustain_sine():
    """A sustained off-bin sine must keep its frequency, level and a flat envelope."""
    rows = []
    for fs, N in ((48000, 2048), (48000, 4096), (48000, 8192), (44100, 4096), (96000, 8192)):
        f = 441.37
        x = 0.5 * np.sin(2 * np.pi * f * np.arange(2 * fs) / fs)
        y, _ = E.sustain(make_capture(x, fs, N), 5 * fs)
        tag = f"fs={fs} N={N}"
        fe = Mx.sine_frequency(y[fs:, 0], fs) - f
        rows.append(_row("sustain_sine_frequency", tag, float(f"{fe:.3e}"), "Hz error", abs(fe) < FREQ_TOL_HZ, FREQ_TOL_HZ))
        rip = Mx.envelope_ripple_db(y, fs)
        rows.append(_row("sustain_sine_ripple", tag, round(rip, 4), "dB p-p", rip < SUSTAIN_SINE_RIPPLE_DB, SUSTAIN_SINE_RIPPLE_DB))
        lv = Mx.db(Mx.rms(y[fs:]) / Mx.rms(x))
        rows.append(_row("sustain_sine_level", tag, round(lv, 4), "dB re source", abs(lv) < SUSTAIN_LEVEL_TOL_DB, SUSTAIN_LEVEL_TOL_DB))
    return rows


def _materials(fs):
    t = np.arange(3 * fs) / fs
    return {
        "sine": 0.5 * np.sin(2 * np.pi * 441.37 * t),
        "two_partials_26Hz_apart": 0.3 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 466.16 * t),
        "harmonic_110Hz": sum(0.3 / h * np.sin(2 * np.pi * 110.3 * h * t) for h in range(1, 30)),
        "noise": np.random.default_rng(0).standard_normal(len(t)) * 0.1,
    }


def loop_seams(fs=48000, N=4096):
    """Seam discontinuity and seam gain for each strategy and crossfade length."""
    rows = []
    for name, x in _materials(fs).items():
        cap = make_capture(x, fs, N)
        src_ripple = Mx.envelope_ripple_db(x[int(0.5 * fs):int(1.25 * fs)], fs, start_s=0)
        rows.append(_row("source_ripple", name, round(src_ripple, 3), "dB p-p"))
        y, info = E.loop(cap, 4 * fs, strategy="hard")
        r = Mx.click_ratio(y, info["seams"])
        tonal = name != "noise"  # a hard wrap in white noise is not a detectable step
        rows.append(_row("loop_click_control_hard_wrap", name, round(r, 2), "ratio",
                         r > CLICK_CONTROL_MIN if tonal else None, CLICK_CONTROL_MIN if tonal else None))
        for strategy in ("equal_power", "linear", "aligned"):
            for xf in (0.03, 0.08):
                y, info = E.loop(cap, 4 * fs, xf, strategy)
                tag = f"{name} {strategy} {int(xf * 1000)}ms"
                r = Mx.click_ratio(y, info["seams"])
                rows.append(_row("loop_click", tag, round(r, 3), "ratio", r <= CLICK_RATIO_MAX, CLICK_RATIO_MAX))
                rows.append(_row("loop_ripple", f"{tag} rho={info['seam_correlation']:.2f}",
                                 round(Mx.envelope_ripple_db(y, fs, start_s=0), 3), "dB p-p"))
    return rows


def sustain_variants(fs=48000, N=4096):
    """Envelope ripple and level of the sustain variants and the freeze baseline.
    This is the evidence used to decide whether phase locking is warranted."""
    rows = []
    for name, x in _materials(fs).items():
        cap = make_capture(x, fs, N)
        renders = {
            "freeze_delta": E.freeze(cap, 4 * fs)[0],
            "sustain_mean": E.sustain(cap, 4 * fs)[0],
            "sustain_mean_phase_lock": E.sustain(cap, 4 * fs, phase_lock=True)[0],
            "sustain_scan": E.sustain(cap, 4 * fs, magnitude="scan")[0],
        }
        for label, y in renders.items():
            rows.append(_row("ripple", f"{name} {label}", round(Mx.envelope_ripple_db(y, fs), 3), "dB p-p"))
            rows.append(_row("level", f"{name} {label}", round(Mx.db(Mx.rms(y) / Mx.rms(x)), 2), "dB re source"))
    return rows


def short_capture_fallback(fs=48000):
    """Minimum-length ROI at every FFT size: does Loop still have material?"""
    rows = []
    x = fixtures.make("drums", fs)
    for N in S.FFT_SIZES:
        cap = make_capture(x, fs, N, 0.95, 1.20)
        M = cap.frames.shape[0]
        for xf in (0.03, 0.08):
            try:
                _, info = E.loop(cap, fs, xf, "aligned")
                rows.append(_row("loop_short_roi", f"N={N} frames={M} xfade_req={int(xf * 1000)}ms",
                                 {"interior_ms": round(1000 * info["interior_samples"] / fs, 1),
                                  "period_ms": round(1000 * info["period_s"], 1),
                                  "xfade_ms": round(1000 * info["xfade_samples"] / fs, 1),
                                  "fallback_short_xfade": info["fallback_short_xfade"]}, ""))
            except E.EngineError as err:
                rows.append(_row("loop_short_roi", f"N={N} frames={M}", str(err), "", False))
    return rows


def stereo():
    fs, N = 48000, 4096
    rows = []
    rng = np.random.default_rng(5)
    t = np.arange(3 * fs) / fs
    mono = sum(0.2 / h * np.sin(2 * np.pi * 196 * h * t) for h in range(1, 12)) + 0.02 * rng.standard_normal(len(t))
    engines = {
        "freeze": lambda c: E.freeze(c, 4 * fs)[0],
        "freeze_random": lambda c: E.freeze(c, 4 * fs, phase_mode="random")[0],
        "loop_aligned": lambda c: E.loop(c, 4 * fs, 0.08, "aligned")[0],
        "loop_equal_power": lambda c: E.loop(c, 4 * fs, 0.08, "equal_power")[0],
        "sustain_shared": lambda c: E.sustain(c, 4 * fs)[0],
        "sustain_independent": lambda c: E.sustain(c, 4 * fs, stereo="independent")[0],
        "sustain_scan": lambda c: E.sustain(c, 4 * fs, magnitude="scan")[0],
    }
    centre = make_capture(np.stack([mono, mono], 1), fs, N)
    anti = make_capture(np.stack([mono, -mono], 1), fs, N)
    # near-centre: a centred source with -40 dB of independent noise per channel
    near_src = np.stack([mono, mono], 1) + 0.01 * Mx.rms(mono) * rng.standard_normal((len(t), 2))
    near = make_capture(near_src, fs, N)
    rows.append(_row("stereo_near_centre_source_corr", "centred harmonic + -40 dB independent noise",
                     round(Mx.interchannel_corr(near_src[int(0.5 * fs):int(1.25 * fs)]), 5), "corr"))
    wide_src = fixtures.make("synth", fs)
    wide = make_capture(wide_src, fs, N, 1.0, 1.75)
    src_corr = Mx.interchannel_corr(wide_src[int(1.0 * fs):int(1.75 * fs)])
    rows.append(_row("stereo_wide_source_corr", "synth fixture ROI", round(src_corr, 3), "corr"))
    for name, fn in engines.items():
        y = fn(centre)
        d = Mx.peak(y[:, 0] - y[:, 1]) / max(Mx.peak(y), Mx.EPS)
        rows.append(_row("stereo_centre_stays_centre", name, float(f"{d:.2e}"), "max |L-R| / peak", d < 1e-6, 1e-6))
        y = fn(anti)
        c = Mx.interchannel_corr(y)
        rows.append(_row("stereo_antiphase_preserved", name, round(c, 6), "corr", c < -0.999999, -0.999999))
        y = fn(near)
        rows.append(_row("stereo_near_centre_corr_early_late", name,
                         [round(Mx.interchannel_corr(y[:fs]), 4), round(Mx.interchannel_corr(y[3 * fs:]), 4)],
                         "corr 0-1s, 3-4s"))
        y = fn(wide)
        early, late = Mx.interchannel_corr(y[:fs]), Mx.interchannel_corr(y[3 * fs:])
        rows.append(_row("stereo_wide_corr_early_late", name, [round(early, 3), round(late, 3)], "corr 0-1s, 3-4s"))
        rows.append(_row("stereo_wide_mono_compat", name, round(Mx.mono_compat_db(y), 2), "dB (mono sum re channels)"))
    return rows


def safety():
    fs, N = 48000, 4096
    rows = []
    silent = make_capture(np.zeros((3 * fs, 2)), fs, N)
    hot = make_capture(np.random.default_rng(9).uniform(-1, 1, (3 * fs, 2)), fs, N)  # full-scale noise
    tiny = make_capture(np.random.default_rng(9).standard_normal((3 * fs, 2)) * 1e-30, fs, N, dtype=np.complex128)
    calls = {
        "freeze": lambda c: E.freeze(c, 2 * fs)[0],
        "freeze_random": lambda c: E.freeze(c, 2 * fs, phase_mode="random")[0],
        "loop_aligned": lambda c: E.loop(c, 2 * fs, 0.08, "aligned")[0],
        "loop_equal_power": lambda c: E.loop(c, 2 * fs, 0.08, "equal_power")[0],
        "sustain_mean": lambda c: E.sustain(c, 2 * fs)[0],
        "sustain_lock": lambda c: E.sustain(c, 2 * fs, phase_lock=True)[0],
        "sustain_scan": lambda c: E.sustain(c, 2 * fs, magnitude="scan")[0],
    }
    for name, fn in calls.items():
        y = fn(silent)
        ok = Mx.is_finite(y) and Mx.peak(y) == 0.0
        rows.append(_row("silent_capture_gives_silence", name, Mx.peak(y), "peak", ok, 0.0))
        y = fn(hot)
        rows.append(_row("full_scale_noise_finite", name, round(Mx.db(Mx.peak(y)), 2), "dBFS peak", Mx.is_finite(y)))
        y = fn(tiny)
        rows.append(_row("tiny_input_finite", name, float(f"{Mx.peak(y):.2e}"), "peak", Mx.is_finite(y)))
        # determinism: identical bits across two renders
        a, b = fn(hot), fn(hot)
        rows.append(_row("deterministic", name, Mx.sha256(a, np.float64)[:16], "sha256", np.array_equal(a, b)))
    # MEMORY envelope: long decay must retire to exact zeros, not denormals
    y = E.sustain(hot, 20 * fs)[0] * E.envelope(20 * fs, fs, 0.25)
    dn = Mx.denormal_count(y) + Mx.denormal_count(y, np.float64)
    rows.append(_row("decay_tail_denormals", "T60=0.25 s over 20 s", dn, "samples", dn == 0, 0))
    rows.append(_row("decay_tail_retires_to_zero", "T60=0.25 s over 20 s", Mx.peak(y[fs:]), "peak after 1 s",
                     Mx.peak(y[fs:]) == 0.0, 0.0))
    return rows


def memory_table():
    """Reproduces DSP-ARCHITECTURE 4.2 (float32 complex, stereo)."""
    rows = []
    expect = {44100: 12.35, 48000: 13.44, 88200: 24.69, 96000: 26.88}
    for fs, N in ((44100, 4096), (48000, 4096), (88200, 8192), (96000, 8192)):
        frame = (N // 2 + 1) * 2 * 8
        hist = C.history_capacity(fs, N)
        slot = math.ceil(C.MAX_ROI_SECONDS * fs / S.hop(N)) + 2
        total = (hist + 2 * slot) * frame / 2 ** 20
        rows.append(_row("memory_history_plus_two_slots", f"fs={fs} N={N} history={hist} slot={slot} frames",
                         round(total, 2), "MiB", abs(total - expect[fs]) < 0.01, expect[fs]))
        # Loop engine alternative: precomputed float32 time-domain loop instead of a spectral slot
        loop_mib = (slot - 3) * S.hop(N) * 2 * 4 / 2 ** 20
        rows.append(_row("memory_loop_time_domain_period", f"fs={fs} N={N} max ROI", round(loop_mib, 2), "MiB"))
    return rows


def cost_model():
    """Transform counts per hop (stereo) - an operation count, not a timing."""
    rows = []
    for fs, N in ((44100, 4096), (48000, 2048), (48000, 4096), (48000, 8192), (96000, 8192)):
        H = S.hop(N)
        unit = N * math.log2(N)  # ~ real-FFT work unit
        hops_per_s = fs / H
        rows.append(_row("cost_model", f"fs={fs} N={N}", {
            "hop_ms": round(1000 * H / fs, 2),
            "analysis_fft_per_hop": 2,
            "freeze_or_sustain_ifft_per_hop": 2,
            "sustain_replace_overlap_ifft_per_hop": 4,
            "loop_steady_state_ifft_per_hop": 0,
            "loop_prepare_ifft_total_max_roi": 2 * (math.ceil(C.MAX_ROI_SECONDS * fs / H) + 2),
            "nlog2n_units_per_second_analysis_plus_sustain": round(4 * unit * hops_per_s),
            "sustain_per_bin_ops_per_hop": 2 * (N // 2 + 1),
        }, "counts"))
    return rows


def python_timing(fs=48000, seconds=4):
    """Wall-clock of this NumPy reference. NOT a realtime indicator."""
    rows = []
    x = fixtures.make("synth", fs)
    for N in S.FFT_SIZES:
        cap = make_capture(x, fs, N, 1.0, 1.75)
        for name, fn in (("stft", lambda: S.stft(x, N)),
                         ("freeze", lambda: E.freeze(cap, seconds * fs)),
                         ("loop_aligned", lambda: E.loop(cap, seconds * fs, 0.08, "aligned")),
                         ("sustain_mean", lambda: E.sustain(cap, seconds * fs)),
                         ("sustain_scan", lambda: E.sustain(cap, seconds * fs, magnitude="scan"))):
            t0 = time.perf_counter()
            fn()
            rows.append(_row("python_wall_time", f"N={N} {name} ({seconds} s stereo)",
                             round(time.perf_counter() - t0, 4), "s (informational)"))
    return rows


CHECKS = (reconstruction, frequency_estimation, sustain_sine, loop_seams, sustain_variants,
          short_capture_fallback, stereo, safety, memory_table, cost_model)


def run_all():
    rows = [r for check in CHECKS for r in check()]
    summary = {k: sum(r["result"] == k for r in rows) for k in ("PASS", "FAIL", "info")}
    return {"summary": summary, "rows": rows}
