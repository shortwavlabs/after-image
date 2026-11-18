# SPDX-License-Identifier: AGPL-3.0-only
"""P0-C listening matrix: one capture per case; P0-B references, SPLIT S1/S2/S3,
the conventional multiband baseline, FULL vs FILTERED and pitch variants, all
from the same seed, level window and MEMORY envelope. Writes renders/p0c/ plus
p0c-manifest.json / p0c-metrics.json (no timestamps: reruns are byte-identical)."""
import json
import platform
import random
import shutil
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import scipy
from scipy.signal import resample_poly

from . import capture as C
from . import engines as E
from . import experiment as X
from . import fixtures
from . import granular as G
from . import metrics as Mx
from . import split as SP
from . import stft as S
from . import verify_split as V

ROOT = X.ROOT
BLIND_SETS = {  # set -> (render names, band-limited selections only?)
    "cloud_vs_split": (("p0b_cloud", "p0b_focus", "split_s1"), False),
    "strategies": (("split_s1", "split_s2_keep_100", "split_s3_100"), False),
    "implementation": (("split_s3_100", "conv_s3_100"), False),
    "source": (("split_s1", "filtered_split_s1"), True),
    "pitch": (("split_s1", "split_s1_detune", "split_s1_octaves"), False),
    "progression": (("progression_parallel", "progression_s2_keep", "progression_s2_fade", "progression_s3"), False),
}


@lru_cache(maxsize=None)
def guitar_dist(fs):
    """Synthetic "distorted chord": the guitar fixture through a tanh waveshaper
    (gain 100) at 4x oversampling, peak-normalised like the other fixtures.
    Original code, no samples. It exists because the clean fixture has 0.4 % of
    its energy above 2 kHz; this one has about 3.5 %. It is a stand-in, not an
    amplifier model."""
    y = resample_poly(np.tanh(100.0 * resample_poly(fixtures.make("guitar", fs), 4, 1, axis=0)), 1, 4, axis=0)
    return y * (fixtures.PEAK / np.max(np.abs(y)))


def load_sources(base_cfg, inputs_dir):
    sources, skipped = X.load_sources(base_cfg, inputs_dir)
    sources.append({"name": "guitar_dist", "kind": "synthetic", "cases": base_cfg["cases"]["guitar"],
                    "load": guitar_dist, "native_fs": None})
    return sources, skipped


def build_case(x, fs, N, case, cfg):
    rcfg = cfg["render"]
    high = fs / 2 if case["high_hz"] is None else min(case["high_hz"], fs / 2)
    h = C.SpectralHistory(fs, N, x.shape[1], np.complex64)
    feed = int(case["t1"] * fs) + N  # as in P0-A/B: only audio up to just after the selection
    h.push_signal(x[:feed])
    first, last = C.frames_for_interval(case["t0"], case["t1"], fs, N)
    cap = C.capture(h, C.CaptureRequest(h.epoch, first, last, float(case["low_hz"]), float(high),
                                        rcfg["freq_feather_oct"], rcfg["time_feather_s"]))
    info = G.capture_buffer(h, cap)[1]
    w = cfg["crossover_width_oct"]
    xo_full = SP.resolve_crossovers(cfg["crossovers_full"], 20.0, fs / 2, fs)
    full = SP.decompose_spectral(h, cap, fs, xo_full, "full", w, rcfg["xfade_s"])
    conv = SP.decompose_iir(x[:feed], info["start_sample"], info["samples"], fs, xo_full, full.seam)
    band_limited = case["low_hz"] > 20 or case["high_hz"] is not None
    filt = None
    if band_limited:
        xo_f = SP.resolve_crossovers(cfg["crossovers_filtered"], float(case["low_hz"]), float(high), fs)
        filt = SP.decompose_spectral(h, cap, fs, xo_f, "filtered", w, rcfg["xfade_s"])
    raw_frames = np.stack([h.frame(i, h.epoch) for i in range(first, last + 1)])
    return {"cap": cap, "full": full, "conv": conv, "filt": filt, "raw_frames": raw_frames, "info": info, "band_limited": band_limited}


def render_case(c, fs, N, rcfg, seed):
    """name -> (raw audio, info, kind, reference decomposition)."""
    n, npg = int(rcfg["ghost_seconds"] * fs), int(rcfg["progression_seconds"] * fs)
    full, conv, filt = c["full"], c["conv"], c["filt"]
    R = len(full.per_src)
    nop = replace(G.dissolve_params(1.0, fs), pitch_st=0.0, octave_prob=0.0)  # P0-B cloud endpoint, no pitch
    out = {}
    out["trace"] = (V.tile(full.per_src, n), {"engine": "TRACE, FULL source"}, "ghost", full)
    out["p0b_cloud"] = (*G.cloud(full.per_src, fs, n, nop, seed), "ghost", full)
    cdf = G.position_cdf(c["raw_frames"], R, S.hop(N), "harmonic")
    out["p0b_focus"] = (*G.cloud(full.per_src, fs, n, nop, seed, pos_cdf=cdf), "ghost", full)
    out["split_s1"] = (*SP.render_split(full, fs, n, "s1", 1.0, seed), "ghost", full)
    out["split_s2_keep_100"] = (*SP.render_split(full, fs, n, "s2_keep", 1.0, seed), "ghost", full)
    out["split_s3_100"] = (*SP.render_split(full, fs, n, "s3", 1.0, seed), "ghost", full)
    out["conv_s1"] = (*SP.render_split(conv, fs, n, "s1", 1.0, seed), "ghost", full)
    out["conv_s3_100"] = (*SP.render_split(conv, fs, n, "s3", 1.0, seed), "ghost", full)
    out["split_s1_detune"] = (*SP.render_split(full, fs, n, "s1", 1.0, seed, pitch="detune"), "ghost", full)
    out["split_s1_octaves"] = (*SP.render_split(full, fs, n, "s1", 1.0, seed, pitch="octaves"), "ghost", full)
    if filt is not None:
        out["filtered_cloud"] = (*G.cloud(filt.per_src, fs, n, nop, seed), "ghost", filt)
        out["filtered_split_s1"] = (*SP.render_split(filt, fs, n, "s1", 1.0, seed), "ghost", filt)
    # metrics only: the remaining static settings of the brief
    for strat, D in (("s2_keep", 0.25), ("s2_keep", 0.5), ("s2_keep", 0.75), ("s2_fade", 0.25), ("s2_fade", 0.5),
                     ("s2_fade", 0.75), ("s2_fade", 1.0), ("s3", 0.25), ("s3", 0.5), ("s3", 0.75)):
        out[f"_split_{strat}_{int(D * 100):03d}"] = (*SP.render_split(full, fs, n, strat, D, seed), "metrics", full)
    traj = G.ramp(rcfg["progression_hold_s"], rcfg["progression_ramp_s"])
    d = np.array([traj(t) for t in np.arange(npg) / fs])
    out["progression_parallel"] = (G.parallel(V.tile(full.per_src, npg), G.cloud(full.per_src, fs, npg, nop, seed)[0], d),
                                   {"engine": "P0-B parallel morph, no pitch"}, "progression", full)
    for strat in ("s2_keep", "s2_fade", "s3"):
        out[f"progression_{strat}"] = (*SP.render_split(full, fs, npg, strat, traj, seed), "progression", full)
    return out


def split_metrics(raw, fs, dec, n):
    """How each band of a render relates to its own TRACE reference."""
    R = len(dec.per_src)
    ref = V.band_split(V.tile(dec.per_src, len(raw)), fs, dec.crossovers)
    bands = V.band_split(raw, fs, dec.crossovers)
    tr = V.tile(dec.per_src, n)
    return {"rms_db_re_trace": round(Mx.db(Mx.rms(raw[:n]) / max(Mx.rms(tr), Mx.EPS)), 2),
            "changed_db_re_trace": round(Mx.error_db(raw[:n], tr), 1),  # how much of the ghost is no longer the loop
            "peak_db_re_trace": round(Mx.db(Mx.peak(raw) / max(Mx.peak(dec.per_src), Mx.EPS)), 2),
            "band_period_autocorr": [round(V.period_autocorr(b, R), 3) for b in bands],
            "band_level_db_re_trace": [round(Mx.db(Mx.rms(b) / max(Mx.rms(r), Mx.EPS)), 2) for b, r in zip(bands, ref)],
            "crossovers_hz": [round(v, 1) for v in dec.crossovers]}


def run(out_dir, cfg_path=ROOT / "experiments-p0c.json", inputs_dir=ROOT / "inputs", only=None, write_audio=True, log=print):
    cfg = json.loads(Path(cfg_path).read_text())
    base_cfg = json.loads((ROOT / "experiments.json").read_text())
    rcfg, seed, out_dir = cfg["render"], cfg["seed"], Path(out_dir)
    sources, skipped = load_sources(base_cfg, inputs_dir)
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
                c = build_case(x, fs, N, case, cfg)
            except (C.CaptureRejected, E.EngineError, ValueError) as err:
                failures.append({"id": base, "error": str(err)})
                log(f"FAILED {base}: {err}")
                continue
            n = int(rcfg["ghost_seconds"] * fs)
            full = c["full"]
            k = int(0.005 * fs)
            fade = np.ones(len(full.src))
            fade[:k] = 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
            fade[-k:] = fade[:k][::-1]
            emit(f"{base}/roi_oneshot.wav", fs, full.src * fade[:, None])
            share = lambda d: [round(float(v), 4) for v in np.array([np.sum(b ** 2) for b in d.cloud]) / max(sum(np.sum(b ** 2) for b in d.cloud), Mx.EPS)]
            metrics[f"{base}/capture"] = {
                "band_limited": c["band_limited"], "period_samples": full.seam["period_samples"], "buffer_samples": c["info"]["samples"],
                "full": {"crossovers_hz": [round(v, 1) for v in full.crossovers], "band_energy_share": share(full)},
                "filtered": None if c["filt"] is None else {"crossovers_hz": [round(v, 1) for v in c["filt"].crossovers],
                                                              "band_energy_share": share(c["filt"]),
                                                              "level_db_re_full": round(Mx.db(Mx.rms(c["filt"].src) / max(Mx.rms(full.src), Mx.EPS)), 2)}}
            outs = render_case(c, fs, N, rcfg, seed)
            raws = {}
            for name, (raw, info, kind, dec) in outs.items():
                rid = f"{base}/{name.lstrip('_')}"
                t60 = rcfg["progression_t60_seconds" if kind == "progression" else "t60_seconds"]
                matched, gain = E.match_level(raw, fs, rcfg["target_rms_dbfs"], rcfg["level_window_s"])
                final = matched * E.envelope(len(raw), fs, t60, rcfg["onset_fade_s"])
                m = X.ghost_metrics(raw, final, fs, c["cap"], info, dec.src, gain)
                m.update(split_metrics(raw, fs, dec, n))
                if src["name"] == "guitar":
                    m["low_sideband_db"] = round(V.sideband_ratio_db(raw[:n], fs, V.guitar_partials(400.0), 400.0), 1)
                metrics[rid] = m
                raws[name] = raw
                if kind == "metrics":
                    continue
                emit(f"{rid}.wav", fs, final)
                renders.append({"id": rid, "path": f"{rid}.wav", "source": src["name"], "source_kind": src["kind"],
                                "case": case["name"], "fs": fs, "fft_size": N, "engine": name, "seed": seed, "t60_seconds": t60,
                                "match_gain_db": m["match_gain_db"], "capture_source": dec.source, "decomposition": dec.kind,
                                "crossovers_hz": [round(v, 1) for v in dec.crossovers],
                                "roi": {k2: case[k2] for k2 in ("t0", "t1", "low_hz", "high_hz")}, "sha256_float32": m["sha256_float32"]})
                if name in ("split_s1", "progression_s2_keep"):
                    start = int(case["t1"] * fs)  # BODY + GHOST: the ghost starts where the selection ends
                    mix = np.zeros((start + len(final), x.shape[1]))
                    mix[:len(x)] += x[:len(mix)]
                    mix[start:] += final
                    emit(f"{base}/mix_{name}.wav", fs, mix)
                    m["mix_peak_dbfs"] = round(Mx.db(Mx.peak(mix)), 2)
            metrics[f"{base}/spectral_vs_conventional"] = {
                s: {"third_octave_distance_db": round(Mx.log_spectral_distance_db(raws[a], raws[b], fs), 2),
                    "rms_difference_db": round(Mx.db(Mx.rms(raws[a]) / max(Mx.rms(raws[b]), Mx.EPS)), 2),
                    "sample_difference_db": round(Mx.error_db(raws[b], raws[a]), 1)}
                for s, a, b in (("s1", "split_s1", "conv_s1"), ("s3", "split_s3_100", "conv_s3_100"))}
            log(f"rendered {base}")

    manifest = {
        "schema": 1, "phase": "P0-C", "code_revision": X.code_revision(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "config": cfg,
        "strategies": {s: {str(D): [round(float(v), 4) for v in SP.amounts(s, D, 3)] for D in (0.0, 0.25, 0.5, 0.75, 1.0)} for s in SP.STRATEGIES},
        "band_params_s1_s2": [q.__dict__ for q in SP.band_params("s1", cfg["fs"], 3, 32000)],
        "band_params_s3": [q.__dict__ for q in SP.band_params("s3", cfg["fs"], 3, 32000)],
        "grain_budgets": list(SP.BUDGET_3), "max_grains_total": G.MAX_GRAINS,
        "notes": "Every render is RMS-matched to target_rms_dbfs over level_window_s BEFORE the MEMORY envelope; match_gain_db is "
                 "recorded per render. FULL renders use crossovers_full; FILTERED renders use crossovers_filtered resolved inside "
                 "the selected band, so FULL vs FILTERED differ in source AND crossover placement. WAVs are not committed.",
        "skipped_inputs": skipped, "failures": failures, "renders": renders,
    }
    return manifest, metrics


def blind_pack(out_dir, seed=20261121, metrics_path=ROOT / "p0c-metrics.json"):
    """Shuffled copies under blind/<source>__<case>__<set>/{A,B,...}.wav; the key
    is written next to (not inside) the set folders."""
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
            for label, f in zip("ABCD", files):
                dst = out_dir / "blind" / folder / f"{label}.wav"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
                key[f"{folder}/{label}"] = f.stem
            shutil.copyfile(out_dir / base / "roi_oneshot.wav", out_dir / "blind" / folder / "reference_roi.wav")
    if key:
        X.dump(key, out_dir / "blind-KEY-do-not-open.json")
    return len({k.rsplit("/", 1)[0] for k in key})


def summarize(metrics):
    out = []
    bases = sorted(k.rsplit("/", 1)[0] for k in metrics if k.endswith("/capture"))
    names = ["trace", "p0b_cloud", "p0b_focus", "split_s1", "conv_s1", "split_s2_keep_050", "split_s2_keep_100", "split_s2_fade_050",
             "split_s2_fade_100", "split_s3_050", "split_s3_100", "conv_s3_100", "split_s1_detune", "split_s1_octaves",
             "filtered_cloud", "filtered_split_s1", "progression_parallel", "progression_s2_keep", "progression_s2_fade", "progression_s3"]
    for b in bases:
        cp = metrics[f"{b}/capture"]
        out.append(f"\n**{b}** - FULL crossovers {cp['full']['crossovers_hz']} Hz, band energy share {cp['full']['band_energy_share']}"
                   + (f"; FILTERED crossovers {cp['filtered']['crossovers_hz']} Hz, share {cp['filtered']['band_energy_share']}, "
                      f"level {cp['filtered']['level_db_re_full']} dB re FULL" if cp["filtered"] else "") + "\n")
        out.append("| render | RMS re TRACE (dB) | changed re TRACE (dB) | peak re TRACE (dB) | final peak (dBFS) | match gain (dB) | ripple (dB) | band repetition low / mid / high "
                   "| band level re TRACE (dB) | low sidebands (dB) | corr early / late | mono compat (dB) |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|")
        for nme in names:
            m = metrics.get(f"{b}/{nme}")
            if m:
                out.append(f"| {nme} | {m['rms_db_re_trace']:+.2f} | {m['changed_db_re_trace']:.1f} | {m['peak_db_re_trace']:+.2f} | {m['peak_dbfs']:.2f} | {m['match_gain_db']:+.1f} | {m['ripple_db']:.1f} "
                           f"| {' / '.join(f'{v:.2f}' for v in m['band_period_autocorr'])} | {' / '.join(f'{v:+.1f}' for v in m['band_level_db_re_trace'])} "
                           f"| {m.get('low_sideband_db', '')} | {m['corr_early']:.2f} / {m['corr_late']:.2f} | {m['mono_compat_db']:.2f} |")
        sv = metrics[f"{b}/spectral_vs_conventional"]
        out.append(f"\nSpectral vs conventional: S1 third-octave distance {sv['s1']['third_octave_distance_db']} dB, level difference {sv['s1']['rms_difference_db']} dB; "
                   f"S3 {sv['s3']['third_octave_distance_db']} dB, {sv['s3']['rms_difference_db']} dB.")
    ghosts = {k: m for k, m in metrics.items() if isinstance(m, dict) and "finite" in m}
    out.append(f"\nRenders measured: {len(ghosts)}; non-finite: {sum(not m['finite'] for m in ghosts.values())}; "
               f"with float32 denormals: {sum(m['denormals_float32'] > 0 for m in ghosts.values())}; "
               f"max final peak {max(m['peak_dbfs'] for m in ghosts.values()):.2f} dBFS; "
               f"max BODY+GHOST mix peak {max(m.get('mix_peak_dbfs', -999) for m in ghosts.values()):.2f} dBFS.")
    return "\n".join(out)
