# SPDX-License-Identifier: AGPL-3.0-only
"""Controlled A/B renders: same ROI, mask, onset fade, T60 and level window for
every engine. Writes WAVs plus manifest.json / metrics.json (no timestamps, so
two runs of the same code are byte-identical)."""
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import scipy
from scipy.io import wavfile

from . import capture as C
from . import engines as E
from . import fixtures
from . import metrics as Mx
from . import stft as S

ROOT = Path(__file__).resolve().parent.parent
RATE_TABLE = {44100: 4096, 48000: 4096, 88200: 8192, 96000: 8192}  # DSP-ARCHITECTURE 3.2

# name -> (callable(cap, n_samples), rendered at every FFT size?)
ENGINES = {
    "freeze_delta": (lambda c, n: E.freeze(c, n), True),
    "loop_ep80": (lambda c, n: E.loop(c, n, 0.08, "equal_power"), True),
    "loop_aligned80": (lambda c, n: E.loop(c, n, 0.08, "aligned"), True),
    "sustain_mean": (lambda c, n: E.sustain(c, n), True),
    "freeze_random": (lambda c, n: E.freeze(c, n, phase_mode="random", seed=0), False),
    "loop_ep30": (lambda c, n: E.loop(c, n, 0.03, "equal_power"), False),
    "loop_lin80": (lambda c, n: E.loop(c, n, 0.08, "linear"), False),
    "loop_aligned30": (lambda c, n: E.loop(c, n, 0.03, "aligned"), False),
    "sustain_scan": (lambda c, n: E.sustain(c, n, magnitude="scan"), False),
    "sustain_mean_lock": (lambda c, n: E.sustain(c, n, phase_lock=True), False),
    "sustain_mean_indep": (lambda c, n: E.sustain(c, n, stereo="independent"), False),
}
MIX_ENGINES = ("freeze_delta", "loop_aligned80", "sustain_mean")


def code_revision():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "p0", "experiments.json", "run.py"],
                                    cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
        return {"commit": sha, "harness_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "harness_dirty": None}


def read_wav(path):
    fs, d = wavfile.read(path)
    if d.dtype.kind == "f":
        x = d.astype(np.float64)
    elif d.dtype == np.uint8:
        x = (d.astype(np.float64) - 128) / 128
    else:
        x = d.astype(np.float64) / float(np.iinfo(d.dtype).max + 1)
    x = S.as_2d(x)
    return fs, x[:, :2]  # mono or stereo; extra channels are ignored


def write_wav(path, fs, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, fs, np.ascontiguousarray(x, dtype=np.float32))


def load_sources(cfg, inputs_dir):
    """Synthetic fixtures plus any user-owned WAVs in inputs/ (see inputs/README.md)."""
    sources, skipped = [], []
    for name in fixtures.NAMES:
        sources.append({"name": name, "kind": "synthetic", "cases": cfg["cases"][name],
                        "load": lambda fs, name=name: fixtures.make(name, fs), "native_fs": None})
    for wav in sorted(Path(inputs_dir).glob("*.wav")) if Path(inputs_dir).is_dir() else []:
        fs, x = read_wav(wav)
        if fs not in S.SAMPLE_RATES:
            skipped.append({"file": wav.name, "reason": f"unsupported sample rate {fs}"})
            continue
        sidecar = wav.with_suffix(".json")
        cases = json.loads(sidecar.read_text())["cases"] if sidecar.exists() else cfg["user_input_default_cases"]
        sources.append({"name": f"user_{wav.stem}", "kind": "user", "cases": cases,
                        "load": lambda _fs, x=x: x, "native_fs": fs})
    return sources, skipped


def run_case(x, fs, N, case, rcfg):
    """Capture one ROI exactly as the realtime path would see it: the history has
    only received audio up to shortly after the end of the selection."""
    high = fs / 2 if case["high_hz"] is None else min(case["high_hz"], fs / 2)
    h = C.SpectralHistory(fs, N, x.shape[1], np.complex64)
    h.push_signal(x[:int(case["t1"] * fs) + N])
    first, last = C.frames_for_interval(case["t0"], case["t1"], fs, N)
    req = C.CaptureRequest(h.epoch, first, last, float(case["low_hz"]), float(high),
                           rcfg["freq_feather_oct"], rcfg["time_feather_s"])
    return C.capture(h, req), req


def ghost_metrics(raw, final, fs, cap, info, roi_ref, gain):
    feather = 2 ** (1 / 6)
    m = {
        "finite": Mx.is_finite(final),
        "peak_dbfs": round(Mx.db(Mx.peak(final)), 2),
        "rms_dbfs_first_2s": round(Mx.db(Mx.rms(final[:2 * fs])), 2),
        "native_level_db_re_roi": round(Mx.db(Mx.rms(raw[:2 * fs]) / max(Mx.rms(roi_ref), Mx.EPS)), 2),
        "match_gain_db": round(Mx.db(gain), 2),
        "crest_db": round(Mx.crest_db(raw[:2 * fs]), 2),
        "ripple_db": round(Mx.envelope_ripple_db(raw, fs), 2),
        "corr_early": round(Mx.interchannel_corr(raw[:fs]), 3),
        "corr_late": round(Mx.interchannel_corr(raw[-fs:]), 3),
        "mono_compat_db": round(Mx.mono_compat_db(raw), 2),
        "in_band_energy_fraction": round(Mx.band_energy_fraction(raw, fs, cap.low_hz / feather, cap.high_hz * feather), 6),
        "timbre_distance_db_re_roi": round(Mx.log_spectral_distance_db(raw[:2 * fs], roi_ref, fs), 2),
        "denormals_float32": Mx.denormal_count(final),
        "sha256_float32": Mx.sha256(final),
    }
    if "seams" in info:
        m["seam_click_ratio"] = round(Mx.click_ratio(raw, info["seams"]), 3)
    m["engine_info"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in info.items() if k != "seams"}
    return m


def run(out_dir, cfg_path=ROOT / "experiments.json", inputs_dir=ROOT / "inputs", only=None, fft_sizes=None,
        write_audio=True, log=print):
    cfg = json.loads(Path(cfg_path).read_text())
    rcfg = cfg["render"]
    out_dir = Path(out_dir)
    sources, skipped = load_sources(cfg, inputs_dir)
    renders, metrics, failures = [], {}, []

    def emit(rel, fs, audio):
        if write_audio:
            write_wav(out_dir / rel, fs, audio)

    for src in sources:
        if only and src["name"] not in only:
            continue
        if src["kind"] == "user":
            configs = [(src["native_fs"], RATE_TABLE[src["native_fs"]])]
            if src["native_fs"] == cfg["primary_fs"]:
                configs = [(src["native_fs"], n) for n in cfg["fft_sizes"]]
        else:
            configs = [(cfg["primary_fs"], n) for n in cfg["fft_sizes"]]
        for fs in sorted({c[0] for c in configs} | ({r[0] for r in cfg["rate_sweep"]} if src["kind"] == "synthetic" else set())):
            emit(f"{src['name']}/source_fs{fs}.wav", fs, src["load"](fs))
        for case in src["cases"]:
            case_cfgs = list(configs)
            if f"{src['name']}/{case['name']}" in cfg["rate_sweep_cases"]:
                case_cfgs += [tuple(r) for r in cfg["rate_sweep"]]
            for fs, N in case_cfgs:
                if fft_sizes and N not in fft_sizes:
                    continue
                x = src["load"](fs)
                base = f"{src['name']}/{case['name']}/fs{fs}_N{N}"
                roi = {"t0_s": case["t0"], "t1_s": case["t1"], "low_hz": case["low_hz"], "high_hz": case["high_hz"]}
                try:
                    cap, req = run_case(x, fs, N, case, rcfg)
                except C.CaptureRejected as err:
                    failures.append({"id": base, "stage": "capture", "error": str(err)})
                    log(f"REJECTED {base}: {err}")
                    continue
                H, M = S.hop(N), cap.frames.shape[0]
                roi.update(first_frame=req.first_frame, last_frame=req.last_frame, frames=M,
                           duration_s=round(M * H / fs, 4))
                # reference: the frequency-masked source over the fully overlapped ROI interior
                roi_ref = S.istft_buffer(cap.frames.astype(np.complex128), N)[N - H:M * H]
                emit(f"{base}/roi_oneshot.wav", fs, E.oneshot(cap))
                n = int(rcfg["ghost_seconds"] * fs)
                env = E.envelope(n, fs, rcfg["t60_seconds"], rcfg["onset_fade_s"])
                metrics[f"{base}/roi_reference"] = {
                    "rms_dbfs": round(Mx.db(Mx.rms(roi_ref)), 2), "crest_db": round(Mx.crest_db(roi_ref), 2),
                    "ripple_db": round(Mx.envelope_ripple_db(roi_ref, fs, start_s=0), 2) if len(roi_ref) > 0.06 * fs else None,
                    "corr": round(Mx.interchannel_corr(roi_ref), 3), "mono_compat_db": round(Mx.mono_compat_db(roi_ref), 2)}
                for ename, (fn, all_sizes) in ENGINES.items():
                    if not all_sizes and N != cfg["variant_fft_size"]:
                        continue
                    rid = f"{base}/{ename}"
                    try:
                        raw, info = fn(cap, n)
                    except E.EngineError as err:
                        failures.append({"id": rid, "stage": "engine", "error": str(err)})
                        log(f"ENGINE FAILURE {rid}: {err}")
                        continue
                    matched, gain = E.match_level(raw, fs, rcfg["target_rms_dbfs"], rcfg["level_window_s"])
                    final = matched * env
                    metrics[rid] = ghost_metrics(raw, final, fs, cap, info, roi_ref, gain)
                    emit(f"{rid}.wav", fs, final)
                    entry = {"id": rid, "path": f"{rid}.wav", "source": src["name"], "source_kind": src["kind"],
                             "case": case["name"], "fs": fs, "fft_size": N, "hop": H, "engine": ename, "roi": roi,
                             "sha256_float32": metrics[rid]["sha256_float32"]}
                    renders.append(entry)
                    if ename in MIX_ENGINES and N == RATE_TABLE[fs] and fs == cfg["primary_fs"]:
                        # BODY + GHOST: the ghost starts where the selection ends
                        start = int(case["t1"] * fs)
                        mix = np.zeros((start + n, x.shape[1]))
                        mix[:len(x)] += x[:len(mix)]
                        mix[start:] += final
                        emit(f"{base}/mix_{ename}.wav", fs, mix)
                        metrics[rid]["mix_peak_dbfs"] = round(Mx.db(Mx.peak(mix)), 2)
                log(f"rendered {base}")

    manifest = {
        "schema": 1,
        "code_revision": code_revision(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "config": cfg,
        "engines": list(ENGINES),
        "mix_engines": list(MIX_ENGINES),
        "notes": "sha256 is over the float32 sample data of each ghost render. WAVs are not committed.",
        "skipped_inputs": skipped,
        "failures": failures,
        "renders": renders,
    }
    return manifest, metrics


def dump(obj, path):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=False) + "\n")


def summarize(metrics, verification=None):
    """Markdown tables for the report, computed from metrics.json (N per the
    rate table at 48 kHz unless stated). Medians/worst cases over all ROI cases."""
    import statistics as st
    rows = {}
    for rid, m in metrics.items():
        if rid.endswith("roi_reference"):
            continue
        base, engine = rid.rsplit("/", 1)
        cfg = base.rsplit("/", 1)[1]
        rows.setdefault((cfg, engine), []).append((m, metrics[f"{base}/roi_reference"]))
    out = []

    def table(cfg, engines, title):
        out.append(f"\n**{title}**\n")
        out.append("| engine | cases | level re ROI (dB) med | ripple - ROI ripple (dB) med / max | crest - ROI crest (dB) med "
                   "| timbre dist (dB) med / max | corr drift early->late max | mono-compat change (dB) worst | peak (dBFS) max |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for e in engines:
            r = rows.get((cfg, e))
            if not r:
                continue
            rip = [m["ripple_db"] - (ref["ripple_db"] or 0) for m, ref in r]
            crest = [m["crest_db"] - ref["crest_db"] for m, ref in r]
            td = [m["timbre_distance_db_re_roi"] for m, _ in r]
            drift = [abs(m["corr_late"] - m["corr_early"]) for m, _ in r]
            mono = [m["mono_compat_db"] - ref["mono_compat_db"] for m, ref in r]
            out.append(f"| {e} | {len(r)} | {st.median(m['native_level_db_re_roi'] for m, _ in r):+.2f} "
                       f"| {st.median(rip):+.1f} / {max(rip):+.1f} | {st.median(crest):+.1f} "
                       f"| {st.median(td):.1f} / {max(td):.1f} | {max(drift):.2f} | {min(mono):+.2f} "
                       f"| {max(m['peak_dbfs'] for m, _ in r):.1f} |")

    engines = list(ENGINES)
    table("fs48000_N4096", engines, "All engines and variants, 48 kHz, N=4096")
    for n in (2048, 8192):
        table(f"fs48000_N{n}", [e for e in engines if ENGINES[e][1]], f"Primary engines, 48 kHz, N={n}")
    out.append("\n**Loop seams (all renders)**\n")
    out.append("| engine | renders | click ratio max | short-xfade fallbacks | seam correlation med | period (s) min / max |")
    out.append("|---|---:|---:|---:|---:|---:|")
    loops = {}
    for rid, m in metrics.items():
        if "seam_click_ratio" in m:
            loops.setdefault(rid.rsplit("/", 1)[1], []).append(m)
    for e, ms in loops.items():
        info = [m["engine_info"] for m in ms]
        out.append(f"| {e} | {len(ms)} | {max(m['seam_click_ratio'] for m in ms):.3f} "
                   f"| {sum(i['fallback_short_xfade'] for i in info)} | {st.median(i['seam_correlation'] for i in info):.2f} "
                   f"| {min(i['period_s'] for i in info):.3f} / {max(i['period_s'] for i in info):.3f} |")
    ghosts = [m for k, m in metrics.items() if not k.endswith("roi_reference")]
    out.append(f"\nGhost renders: {len(ghosts)}; non-finite: {sum(not m['finite'] for m in ghosts)}; "
               f"with float32 denormals: {sum(m['denormals_float32'] > 0 for m in ghosts)}; "
               f"max ghost peak {max(m['peak_dbfs'] for m in ghosts):.2f} dBFS; "
               f"max BODY+GHOST mix peak {max(m.get('mix_peak_dbfs', -999) for m in ghosts):.2f} dBFS.")
    if verification:
        out.append(f"\nVerification rows: {verification['summary']}")
    return "\n".join(out)


def blind_pack(out_dir, seed=20261118):
    """Copy the three primary engines of every case (table FFT size, 48 kHz and
    user rates) to blind/<source>__<case>/{A,B,C}.wav in a seeded random order."""
    import random
    import shutil
    out_dir = Path(out_dir)
    rng, key = random.Random(seed), {}
    for cfg_dir in sorted(out_dir.glob("*/*/fs*_N*")):
        fs, N = (int(p[2:] if p.startswith("fs") else p[1:]) for p in cfg_dir.name.split("_"))
        files = [cfg_dir / f"{e}.wav" for e in MIX_ENGINES]
        if cfg_dir.parts[-3] == "blind" or RATE_TABLE.get(fs) != N or not all(f.exists() for f in files):
            continue
        if fs != 48000 and not cfg_dir.parts[-3].startswith("user_"):
            continue
        name = f"{cfg_dir.parts[-3]}__{cfg_dir.parts[-2]}"
        rng.shuffle(files)
        for label, f in zip("ABC", files):
            dst = out_dir / "blind" / name / f"{label}.wav"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
            key[f"{name}/{label}"] = f.stem
        shutil.copyfile(cfg_dir / "roi_oneshot.wav", out_dir / "blind" / name / "reference_roi.wav")
    if key:
        dump(key, out_dir / "blind" / "KEY-do-not-open.json")
    return len(key) // 3
