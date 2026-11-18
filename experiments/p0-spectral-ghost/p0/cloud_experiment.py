# SPDX-License-Identifier: AGPL-3.0-only
"""P0-B listening matrix: one capture per case, every engine rendered from it
with the same seed, level window and MEMORY envelope. Writes renders/p0b/ plus
p0b-manifest.json / p0b-metrics.json (no timestamps: reruns are byte-identical)."""
import json
import platform
import random
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import scipy

from . import capture as C
from . import engines as E
from . import experiment as X
from . import granular as G
from . import metrics as Mx
from . import stft as S

ROOT = X.ROOT
SWEEP = [round(0.1 * i, 1) for i in range(11)]
BLIND_SETS = {  # set name -> (render names, band-limited selections only?)
    "engine": (("trace_loop_p0a", "cloud_spectral", "cloud_guided_harmonic"), False),
    "onoff": (("cloud_conventional", "cloud_spectral", "cloud_prefiltered_iir"), True),
    "dissolve": (("progression_parallel", "progression_structural"), False),
}


def character_variants(fs):
    end = G.dissolve_params(1.0, fs)
    return {
        "var_nopitch": replace(end, pitch_st=0.0, octave_prob=0.0),
        "var_wide_pitch": replace(end, pitch_st=12.0, octave_prob=0.0),
        "var_short_dense": replace(end, grain_s=0.04, density_hz=75.0),
        "var_long_sparse": replace(end, grain_s=0.30, density_hz=6.0),
        "var_tukey": replace(end, window="tukey"),
    }


def period_autocorr(y, R):
    """Normalised correlation of the render with itself one loop period later:
    1 for an exact loop, near 0 once the temporal order is gone."""
    a, b = y[:-R], y[R:]
    d = np.sqrt(np.sum(a * a) * np.sum(b * b))
    return float(np.sum(a * b) / d) if d > 0 else float("nan")


def envelope_period_corr(y, fs, R, win_s=0.02, hop_s=0.005):
    """Correlation of the short-time RMS envelope with itself one loop period
    later: does the captured *sequence of events* still repeat? Only meaningful
    when the capture has an envelope (decays, hits); near-flat sources give noise."""
    n, h = int(win_s * fs), int(hop_s * fs)
    p = np.mean(y ** 2, axis=1)
    c = np.concatenate([[0.0], np.cumsum(p)])
    env = np.sqrt((c[n::h] - c[:-n:h]) / n)
    lag = int(round(R / h))
    a, b = env[:-lag] - env[:-lag].mean(), env[lag:] - env[lag:].mean()
    d = np.sqrt(np.sum(a * a) * np.sum(b * b))
    return float(np.sum(a * b) / d) if d > 0 else float("nan")


def iir_bandpass(x, fs, low_hz, high_hz, order=4):
    """Ordinary causal Butterworth pre-filter covering the same band as the mask:
    what a conventional granular delay with a filter in front would granulate."""
    from scipy.signal import butter, sosfilt
    lo, hi = low_hz > 20, high_hz is not None and high_hz < 0.49 * fs
    if lo and hi:
        sos = butter(order, [low_hz, high_hz], "bandpass", fs=fs, output="sos")
    elif lo or hi:
        sos = butter(order, low_hz if lo else high_hz, "highpass" if lo else "lowpass", fs=fs, output="sos")
    else:
        return x
    return sosfilt(sos, x, axis=0)


def build_case(x, fs, N, case, rcfg):
    high = fs / 2 if case["high_hz"] is None else min(case["high_hz"], fs / 2)
    h = C.SpectralHistory(fs, N, x.shape[1], np.complex64)
    h.push_signal(x[:int(case["t1"] * fs) + N])  # as in P0-A: only audio up to just after the selection
    first, last = C.frames_for_interval(case["t0"], case["t1"], fs, N)
    cap = C.capture(h, C.CaptureRequest(h.epoch, first, last, float(case["low_hz"]), float(high),
                                        rcfg["freq_feather_oct"], rcfg["time_feather_s"]))
    spec, info = G.capture_buffer(h, cap)
    raw = x[info["start_sample"]:info["start_sample"] + info["samples"]]
    per_s, per_r, seam = G.periodic_pair(spec, raw, fs, rcfg["xfade_s"])
    raw_frames = np.stack([h.frame(i, h.epoch) for i in range(first, last + 1)])
    filt = iir_bandpass(x[:int(case["t1"] * fs) + N], fs, case["low_hz"], case["high_hz"])
    per_f = E.loop_period(filt[info["start_sample"]:info["start_sample"] + info["samples"]], fs, rcfg["xfade_s"], "aligned",
                          period=seam["period_samples"])[0]
    return {"per_f": per_f, "cap": cap, "spec": spec, "raw": raw, "per_s": per_s, "per_r": per_r, "seam": seam, "info": info,
            "raw_frames": raw_frames, "band_limited": case["low_hz"] > 20 or case["high_hz"] is not None}


def render_case(c, fs, N, rcfg, seed, with_variants):
    """name -> (raw audio, info, kind); kind is "ghost" or "progression"."""
    n, npg = int(rcfg["ghost_seconds"] * fs), int(rcfg["progression_seconds"] * fs)
    R, H, cap, per_s, per_r = len(c["per_s"]), S.hop(N), c["cap"], c["per_s"], c["per_r"]
    tile = lambda m: np.tile(per_s, (-(-m // R), 1))[:m]
    out = {}
    out["trace_loop_p0a"] = (*E.loop(cap, n, rcfg["xfade_s"], "aligned"), "ghost")
    out["freeze_delta"] = (*E.freeze(cap, n), "ghost")
    out["dissolve_000"] = (*G.dissolve(per_s, fs, n, 0.0, seed), "ghost")
    out["dissolve_050"] = (*G.dissolve(per_s, fs, n, 0.5, seed), "ghost")
    out["cloud_spectral"] = (*G.dissolve(per_s, fs, n, 1.0, seed), "ghost")  # = structural DISSOLVE at 1
    out["cloud_conventional"] = (*G.dissolve(per_r, fs, n, 1.0, seed), "ghost")  # same schedule, unmasked buffer
    if c["band_limited"]:  # same schedule again, ordinary IIR band-pass in front instead of the spectral mask
        out["cloud_prefiltered_iir"] = (*G.dissolve(c["per_f"], fs, n, 1.0, seed), "ghost")
    out["morph_parallel_050"] = (G.parallel(out["dissolve_000"][0], out["cloud_spectral"][0], 0.5),
                                 {"approach": "A", "D": 0.5}, "ghost")
    inband = cap.freq_mask >= 0.5
    for mode in ("harmonic", "transient"):
        cdf = G.position_cdf(cap.frames, R, H, mode, inband)
        out[f"cloud_guided_{mode}"] = (*G.dissolve(per_s, fs, n, 1.0, seed, pos_cdf=cdf), "ghost")
    # control for "beyond pre-filtering": same guided schedule, weights from the unmasked spectrum (metrics only)
    out["_guided_harmonic_broadband"] = (*G.dissolve(per_s, fs, n, 1.0, seed, pos_cdf=G.position_cdf(c["raw_frames"], R, H, "harmonic")), "metrics")
    traj = G.ramp(rcfg["progression_hold_s"], rcfg["progression_ramp_s"])
    out["progression_structural"] = (*G.dissolve(per_s, fs, npg, traj, seed), "progression")
    cld = G.dissolve(per_s, fs, npg, 1.0, seed)[0]
    d = np.array([traj(t) for t in np.arange(npg) / fs])
    out["progression_parallel"] = (G.parallel(tile(npg), cld, d), {"approach": "A", "D": "ramp"}, "progression")
    if with_variants:
        for name, prm in character_variants(fs).items():
            y, info = G.cloud(per_s, fs, n, prm, seed)
            out[name] = (y, dict(info, params=asdict(prm)), "ghost")
    return out


def sweep_metrics(c, fs, n, seed):
    """Native levels and identity proxies across DISSOLVE for approaches B and A."""
    per, R = c["per_s"], len(c["per_s"])
    trace = np.tile(per, (-(-n // R), 1))[:n]
    cld = G.dissolve(per, fs, n, 1.0, seed)[0]
    r0, p0 = max(Mx.rms(trace), Mx.EPS), max(Mx.peak(trace), Mx.EPS)
    rows = []
    for D in SWEEP:
        for name, y in (("structural", G.dissolve(per, fs, n, D, seed)[0]), ("parallel", G.parallel(trace, cld, D))):
            rows.append({"approach": name, "D": D, "rms_db_re_trace": round(Mx.db(Mx.rms(y) / r0), 2),
                         "peak_db_re_trace": round(Mx.db(Mx.peak(y) / p0), 2), "ripple_db": round(Mx.envelope_ripple_db(y, fs), 2),
                         "period_autocorr": round(period_autocorr(y, R), 3),
                         "envelope_period_corr": round(envelope_period_corr(y, fs, R), 3),
                         "timbre_distance_db_re_roi": round(Mx.log_spectral_distance_db(y, c["spec"], fs), 2),
                         "corr": round(Mx.interchannel_corr(y), 3), "mono_compat_db": round(Mx.mono_compat_db(y), 2)})
    return rows


def run(out_dir, cfg_path=ROOT / "experiments-p0b.json", inputs_dir=ROOT / "inputs", only=None, write_audio=True, log=print):
    cfg = json.loads(Path(cfg_path).read_text())
    base_cfg = json.loads((ROOT / "experiments.json").read_text())
    rcfg, seed, out_dir = cfg["render"], cfg["seed"], Path(out_dir)
    sources, skipped = X.load_sources(base_cfg, inputs_dir)
    renders, metrics, failures = [], {}, []

    def emit(rel, fs, audio):
        if write_audio:
            X.write_wav(out_dir / rel, fs, audio)

    for src in sources:
        if only and src["name"] not in only:
            continue
        user = src["kind"] == "user"
        fs = src["native_fs"] if user else cfg["fs"]
        N = X.RATE_TABLE[fs] if user else cfg["fft_size"]
        cases = [k for k in src["cases"] if user or f"{src['name']}/{k['name']}" in cfg["cases"]]
        if not cases:
            continue
        x = src["load"](fs)
        emit(f"{src['name']}/source.wav", fs, x)
        for case in cases:
            base = f"{src['name']}/{case['name']}"
            try:
                c = build_case(x, fs, N, case, rcfg)
            except (C.CaptureRejected, E.EngineError) as err:
                failures.append({"id": base, "error": str(err)})
                log(f"FAILED {base}: {err}")
                continue
            n = int(rcfg["ghost_seconds"] * fs)
            k = int(0.005 * fs)  # 5 ms fades on the emitted reference only: the buffer itself starts and ends mid-signal
            fade = np.ones(len(c["spec"]))
            fade[:k] = 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
            fade[-k:] = fade[:k][::-1]
            emit(f"{base}/roi_oneshot.wav", fs, c["spec"] * fade[:, None])
            metrics[f"{base}/capture"] = dict(c["info"], band_limited=c["band_limited"],
                                              seam={k: (round(v, 6) if isinstance(v, float) else v) for k, v in c["seam"].items()},
                                              spectral_vs_raw_buffer_db=round(Mx.error_db(c["spec"], c["raw"]), 2))
            metrics[f"{base}/roi_reference"] = {"rms_dbfs": round(Mx.db(Mx.rms(c["spec"])), 2), "crest_db": round(Mx.crest_db(c["spec"]), 2),
                                                "corr": round(Mx.interchannel_corr(c["spec"]), 3),
                                                "mono_compat_db": round(Mx.mono_compat_db(c["spec"]), 2)}
            outs = render_case(c, fs, N, rcfg, seed, user or base in cfg["character_cases"])
            trace = outs["dissolve_000"][0]
            for name, (raw, info, kind) in outs.items():
                rid = f"{base}/{name.lstrip('_')}"
                t60 = rcfg["progression_t60_seconds" if kind == "progression" else "t60_seconds"]
                matched, gain = E.match_level(raw, fs, rcfg["target_rms_dbfs"], rcfg["level_window_s"])
                final = matched * E.envelope(len(raw), fs, t60, rcfg["onset_fade_s"])
                m = X.ghost_metrics(raw, final, fs, c["cap"], info, c["spec"], gain)
                m["rms_db_re_trace"] = round(Mx.db(Mx.rms(raw[:n]) / max(Mx.rms(trace), Mx.EPS)), 2)
                m["peak_db_re_trace"] = round(Mx.db(Mx.peak(raw) / max(Mx.peak(trace), Mx.EPS)), 2)
                m["period_autocorr"] = round(period_autocorr(raw, len(c["per_s"])), 3)
                m["envelope_period_corr"] = round(envelope_period_corr(raw, fs, len(c["per_s"])), 3)
                metrics[rid] = m
                if kind == "metrics":
                    continue
                emit(f"{rid}.wav", fs, final)
                renders.append({"id": rid, "path": f"{rid}.wav", "source": src["name"], "source_kind": src["kind"],
                                "case": case["name"], "fs": fs, "fft_size": N, "engine": name, "seed": seed,
                                "t60_seconds": t60, "roi": {k: case[k] for k in ("t0", "t1", "low_hz", "high_hz")},
                                "sha256_float32": m["sha256_float32"]})
                if name in ("cloud_spectral", "progression_structural"):
                    start = int(case["t1"] * fs)  # BODY + GHOST: the ghost starts where the selection ends
                    mix = np.zeros((start + len(final), x.shape[1]))
                    mix[:len(x)] += x[:len(mix)]
                    mix[start:] += final
                    emit(f"{base}/mix_{name}.wav", fs, mix)
                    m["mix_peak_dbfs"] = round(Mx.db(Mx.peak(mix)), 2)
            metrics[f"{base}/dissolve_sweep"] = sweep_metrics(c, fs, n, seed)
            log(f"rendered {base}")

    manifest = {
        "schema": 1, "phase": "P0-B",
        "code_revision": X.code_revision(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "config": cfg,
        "dissolve_mapping": {str(D): asdict(G.dissolve_params(D, cfg["fs"])) for D in (0.0, 0.25, 0.5, 0.75, 1.0)},
        "character_variants": {k: asdict(v) for k, v in character_variants(cfg["fs"]).items()},
        "max_grains": G.MAX_GRAINS,
        "notes": "cloud_spectral is structural DISSOLVE at 1; dissolve_000 is the full-selection TRACE loop. "
                 "sha256 is over the float32 samples of each render. WAVs are not committed.",
        "skipped_inputs": skipped, "failures": failures, "renders": renders,
    }
    return manifest, metrics


def blind_pack(out_dir, seed=20261119, metrics_path=ROOT / "p0b-metrics.json"):
    """Shuffled copies under blind/<source>__<case>__<set>/{A,B,C}.wav. The key is
    written next to (not inside) the set folders."""
    out_dir = Path(out_dir)
    metrics = json.loads(Path(metrics_path).read_text())
    rng, key = random.Random(seed), {}
    for cap_id in sorted(k for k in metrics if k.endswith("/capture")):
        base = cap_id.rsplit("/", 1)[0]
        for set_name, (names, band_only) in BLIND_SETS.items():
            files = [out_dir / base / f"{n}.wav" for n in names]
            if (band_only and not metrics[cap_id]["band_limited"]) or not all(f.exists() for f in files):
                continue
            rng.shuffle(files)
            folder = f"{base.replace('/', '__')}__{set_name}"
            for label, f in zip("ABC", files):
                dst = out_dir / "blind" / folder / f"{label}.wav"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
                key[f"{folder}/{label}"] = f.stem
            shutil.copyfile(out_dir / base / "roi_oneshot.wav", out_dir / "blind" / folder / "reference_roi.wav")
    if key:
        X.dump(key, out_dir / "blind-KEY-do-not-open.json")
    return len({k.rsplit("/", 1)[0] for k in key})


def summarize(metrics):
    """Markdown tables for the report, straight from p0b-metrics.json."""
    out = []
    bases = sorted(k.rsplit("/", 1)[0] for k in metrics if k.endswith("/capture"))
    names = ["trace_loop_p0a", "freeze_delta", "dissolve_000", "dissolve_050", "morph_parallel_050", "cloud_spectral",
             "cloud_conventional", "cloud_prefiltered_iir", "cloud_guided_harmonic", "guided_harmonic_broadband", "cloud_guided_transient",
             "progression_structural", "progression_parallel"] + list(character_variants(48000))
    for b in bases:
        cp = metrics[f"{b}/capture"]
        out.append(f"\n**{b}** - period {cp['seam']['period_samples']} samples, buffer {cp['samples']} "
                   f"(P0-A interior {cp['p0a_interior_samples']}), spectral vs raw buffer {cp['spectral_vs_raw_buffer_db']} dB\n")
        out.append("| render | RMS re TRACE (dB) | peak re TRACE (dB) | final peak (dBFS) | ripple (dB) | period autocorr | envelope period corr | timbre dist re ROI (dB) "
                   "| in-band fraction | corr early / late | mono compat (dB) |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for nme in names:
            m = metrics.get(f"{b}/{nme}")
            if m:
                out.append(f"| {nme} | {m['rms_db_re_trace']:+.2f} | {m['peak_db_re_trace']:+.2f} | {m['peak_dbfs']:.2f} | {m['ripple_db']:.1f} "
                           f"| {m['period_autocorr']:.3f} | {m['envelope_period_corr']:.2f} | {m['timbre_distance_db_re_roi']:.1f} | {m['in_band_energy_fraction']:.4f} "
                           f"| {m['corr_early']:.2f} / {m['corr_late']:.2f} | {m['mono_compat_db']:.2f} |")
    out.append("\n**DISSOLVE sweep: waveform period autocorrelation / envelope period correlation / timbre distance re ROI (dB) / RMS re TRACE (dB)**\n")
    out.append("| case | approach | " + " | ".join(f"D={d}" for d in SWEEP[::2]) + " |")
    out.append("|---|---|" + "---|" * len(SWEEP[::2]))
    for b in bases:
        for ap in ("structural", "parallel"):
            rows = {r["D"]: r for r in metrics[f"{b}/dissolve_sweep"] if r["approach"] == ap}
            out.append(f"| {b} | {ap} | " + " | ".join(
                f"{rows[d]['period_autocorr']:.2f} / {rows[d]['envelope_period_corr']:.2f} / {rows[d]['timbre_distance_db_re_roi']:.1f} / {rows[d]['rms_db_re_trace']:+.1f}" for d in SWEEP[::2]) + " |")
    ghosts = {k: m for k, m in metrics.items() if isinstance(m, dict) and "finite" in m}
    out.append(f"\nRenders measured: {len(ghosts)}; non-finite: {sum(not m['finite'] for m in ghosts.values())}; "
               f"with float32 denormals: {sum(m['denormals_float32'] > 0 for m in ghosts.values())}; "
               f"max final peak {max(m['peak_dbfs'] for m in ghosts.values()):.2f} dBFS; "
               f"max BODY+GHOST mix peak {max(m.get('mix_peak_dbfs', -999) for m in ghosts.values()):.2f} dBFS.")
    return "\n".join(out)
