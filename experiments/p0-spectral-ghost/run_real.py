# SPDX-License-Identifier: AGPL-3.0-only
"""AFTERIMAGE real-audio qualification: the unchanged P0-C experiment on the WAVs in inputs/.

  uv run python run_real.py inventory   measure every file in inputs/ -> real-audio-inventory.json
  uv run python run_real.py regions     test the default selection, write inputs/<name>.json where it fails
  uv run python run_real.py render      P0-C renders of user sources only -> renders/real-audio/, real-audio-{manifest,metrics}.json
  uv run python run_real.py blind       shuffled sets -> renders/real-audio/blind/
  uv run python run_real.py summary     markdown tables from real-audio-metrics.json

No DSP lives here: rendering is p0.split_experiment.run restricted to user sources.
Nothing is written to the P0-A/B/C evidence files or to renders/p0b, renders/p0c.

Region criteria (fixed before any render; `regions` only applies them):
  sustained  the default 1.00-1.75 s stands if its RMS is within DEFAULT_WITHIN_DB of the
             loudest 0.75 s window of the file and no 50 ms block is below SILENCE_DBFS.
             Otherwise: the 0.75 s window (50 ms steps) maximising mean - std of the 50 ms
             block levels in dB, i.e. the loudest steady stretch.
  rhythmic   always explicit: start 10 ms before the strongest onset, length = beat period
             (autocorrelation of the onset strength, 0.25-1.5 s) times the largest power of
             two that fits in 1.5 s.
  event      always explicit: from 10 ms before the first 10 ms block within EVENT_RANGE_DB
             of the loudest block to the end of the last one (0.2-1.5 s).
Amendment after the first run: 07_bass_sustained was picked at 0.00 s and failed (the capture needs
audio before the selection; the harness raised a ValueError). Sustained picks now start at >= 0.05 s.
Second amendment: the first rhythmic selections were exactly one period long, but the loop is the
selection minus the 80 ms seam (03 looped at 1.286 s for a 1.38 s bar). Rhythmic selections are now
period + seam long and start seam + 10 ms before the onset, so the seam blends the same bar position.
Classes are assigned by hand from the file names. Nobody listened: this is measurement only.
"""
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from p0 import experiment as X, metrics as Mx, split_experiment as SX

ROOT = Path(__file__).resolve().parent
INPUTS, OUT = ROOT / "inputs", ROOT / "renders" / "real-audio"
DEFAULT, DEFAULT_WITHIN_DB, SILENCE_DBFS, EVENT_RANGE_DB, WIN_S = (1.00, 1.75), 6.0, -50.0, 30.0, 0.75
CLASSES = {"03_acoustic_drum_break": "rhythmic", "11_dense_rhythmic_percussion": "rhythmic",
           "08_spoken_voice": "event", "09_metallic_percussion": "event"}  # everything else: sustained
PRIORITY = ["01_distorted_guitar_chord", "03_acoustic_drum_break", "04_sustained_vocal", "05_evolving_synth_pad"]
SETS = {"engines": ["p0b_cloud", "p0b_focus", "split_s3_100", "split_s2_keep_100"],
        "progression": ["progression_parallel", "progression_s2_keep", "progression_s3"]}  # progression: priority sources only
CASE = "full_spectrum"
SEAM_S = 0.08  # xfade_s of experiments-p0c.json: the loop is about this much shorter than the selection


def blocks_db(x, fs, win_s):
    k = int(win_s * fs)
    return np.array([Mx.db(Mx.rms(x[i:i + k])) for i in range(0, len(x) - k + 1, k)])


def rms_db(x, fs, t0, t1):
    return Mx.db(Mx.rms(x[int(t0 * fs):int(t1 * fs)]))


def tags(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream=codec_name,bits_per_raw_sample",
                          "-of", "json", str(path)], capture_output=True, text=True)
    d = json.loads(out.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    return {"codec": s.get("codec_name"), "bits_raw": s.get("bits_per_raw_sample"), "tags": d.get("format", {}).get("tags", {})}


def inventory():
    rows = []
    for f in sorted(p for p in INPUTS.iterdir() if p.suffix.lower() in (".wav", ".aiff", ".aif", ".flac")):
        row = {"file": f.name, "bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), **tags(f)}
        if f.suffix.lower() != ".wav":
            row["converted_to"] = f.with_suffix(".wav").name if f.with_suffix(".wav").exists() else None
            rows.append(row)
            continue
        if any(f.with_suffix(e).exists() for e in (".aiff", ".aif", ".flac")):
            row["converted_from"] = next(f.with_suffix(e).name for e in (".aiff", ".aif", ".flac") if f.with_suffix(e).exists())
        fs, d = wavfile.read(f)
        _, x = X.read_wav(f)
        b = blocks_db(x, fs, 0.05)
        loud = np.flatnonzero(b > SILENCE_DBFS)
        e = np.abs(np.fft.rfft(x.mean(axis=1))) ** 2
        fr = np.fft.rfftfreq(len(x), 1 / fs)
        full = np.abs(x) >= 1.0 - 2.0 ** -15
        runs = np.diff(np.flatnonzero(np.diff(np.concatenate([[0], full.any(axis=1).astype(int), [0]])))[:2 * 10 ** 6])[::2]
        row.update({
            "sample_rate": fs, "channels": d.shape[1] if d.ndim > 1 else 1, "dtype": str(d.dtype),
            "duration_s": round(len(x) / fs, 3), "supported_rate": fs in X.RATE_TABLE,
            "peak_dbfs": round(Mx.db(Mx.peak(x)), 2), "rms_dbfs": round(Mx.db(Mx.rms(x)), 2), "crest_db": round(Mx.crest_db(x), 2),
            "full_scale_samples": int(full.sum()), "longest_full_scale_run": int(runs.max()) if len(runs) else 0,
            "dc_offset": [round(float(v), 6) for v in x.mean(axis=0)],
            "silent_fraction_below_-60dbfs": round(float(np.mean(b < -60)), 3),
            "leading_silence_s": round(float(loud[0] * 0.05), 2) if len(loud) else None,
            "trailing_silence_s": round(float(len(x) / fs - (loud[-1] + 1) * 0.05), 2) if len(loud) else None,
            "interchannel_corr": round(Mx.interchannel_corr(x), 3) if x.shape[1] > 1 else None,
            "energy_share_below_250_250_2000_above_2000": [round(float(e[(fr >= a) & (fr < c)].sum() / e.sum()), 4)
                                                             for a, c in ((0, 250), (250, 2000), (2000, fs))],
            "class": CLASSES.get(f.stem, "sustained"),
        })
        rows.append(row)
    return rows


def pick(x, fs, cls):
    """-> (t0, t1, default_ok, reason). The criteria are in the module docstring."""
    dur = len(x) / fs
    if cls == "sustained":
        b = blocks_db(x, fs, 0.05)
        n = int(WIN_S / 0.05)
        best = max(rms_db(x, fs, i * 0.05, i * 0.05 + WIN_S) for i in range(len(b) - n + 1))
        d0 = rms_db(x, fs, *DEFAULT)
        dmin = b[int(DEFAULT[0] / 0.05):int(DEFAULT[1] / 0.05)].min() if dur >= DEFAULT[1] else -np.inf
        if d0 >= best - DEFAULT_WITHIN_DB and dmin >= SILENCE_DBFS:
            return (*DEFAULT, True, f"default kept: {d0:.1f} dBFS, loudest 0.75 s window {best:.1f} dBFS")
        i = int(np.argmax([b[j:j + n].mean() - b[j:j + n].std() for j in range(len(b) - n + 1)]))
        t0 = max(round(i * 0.05, 2), 0.05)  # see docstring: 0.00 cannot be captured
        return (t0, t0 + WIN_S, False, f"default is {d0:.1f} dBFS (quietest 50 ms block {dmin:.1f}) against a loudest 0.75 s window of "
                                       f"{best:.1f} dBFS; replaced by the loudest steady 0.75 s ({rms_db(x, fs, t0, t0 + WIN_S):.1f} dBFS)")
    e = blocks_db(x, fs, 0.01)
    if cls == "event":
        on = np.flatnonzero(e >= e.max() - EVENT_RANGE_DB)
        t0 = max(0.0, on[0] * 0.01 - 0.01)
        t1 = min((on[-1] + 1) * 0.01, t0 + 1.5)
        t1 = max(t1, t0 + 0.2)
        return (round(t0, 2), round(t1, 2), False, f"short event: blocks within {EVENT_RANGE_DB:.0f} dB of the loudest 10 ms")
    o = np.clip(np.diff(e), 0, None)
    lags = np.arange(25, 151)
    ac = [np.dot(o[:-k], o[k:]) / np.sqrt(np.dot(o[:-k], o[:-k]) * np.dot(o[k:], o[k:])) for k in lags]
    period = lags[int(np.argmax(ac))] * 0.01
    length = period * 2 ** int(np.floor(np.log2(1.5 / period)))
    ok = (np.arange(len(o)) * 0.01 + length + SEAM_S + 0.2 < dur) & (np.arange(len(o)) * 0.01 >= SEAM_S + 0.02)
    t0 = int(np.argmax(np.where(ok, o, 0))) * 0.01 - SEAM_S  # block i of o starts 10 ms before the onset
    return (round(t0, 2), round(t0 + length + SEAM_S, 2), False,
            f"rhythmic: beat period {period:.2f} s (onset autocorrelation {max(ac):.2f}), {length / period:.0f} period(s) plus the "
            f"{SEAM_S * 1000:.0f} ms seam, starting {SEAM_S * 1000 + 10:.0f} ms before the strongest onset")


def regions():
    rows = []
    for wav in sorted(INPUTS.glob("*.wav")):
        fs, x = X.read_wav(wav)
        cls = CLASSES.get(wav.stem, "sustained")
        t0, t1, ok, reason = pick(x, fs, cls)
        side = wav.with_suffix(".json")
        if ok:
            side.unlink(missing_ok=True)
            # the harness default would also add a 350 Hz-5 kHz case; keep this pack to one full-band case per file
        X.dump({"cases": [{"name": CASE, "t0": t0, "t1": t1, "low_hz": 20, "high_hz": None}], "class": cls,
                "default_selection_ok": ok, "reason": reason, "chosen_by": "run_real.py regions (measurement, not listening)"}, side)
        rows.append({"file": wav.name, "class": cls, "t0": t0, "t1": t1, "default_ok": ok,
                     "region_rms_dbfs": round(rms_db(x, fs, t0, t1), 2), "region_peak_dbfs": round(Mx.db(Mx.peak(x[int(t0 * fs):int(t1 * fs)])), 2),
                     "reason": reason})
    return rows


def jumpiness(path):
    """Fine-window envelope figures from a rendered file: mean |level change| between
    adjacent 10 ms blocks (dB) and upward jumps > 6 dB per second, over 0.5-4 s. The MEMORY
    decay contributes a constant 0.12 dB per block (T60 5 s) and is left in for every render alike."""
    fs, x = X.read_wav(path)
    d = np.diff(blocks_db(x[int(0.5 * fs):4 * fs], fs, 0.01))
    return round(float(np.mean(np.abs(d))), 2), round(float(np.sum(d > 6.0) / 3.5), 2)


def render(only=None):
    names = [f"user_{w.stem}" for w in sorted(INPUTS.glob("*.wav"))]
    manifest, metrics = SX.run(OUT, only=[n for n in names if not only or n in only])
    for r in manifest["renders"]:
        if r["engine"].startswith("progression"):
            continue
        j = jumpiness(OUT / r["path"])
        metrics[r["id"]]["mean_abs_level_step_db_10ms"], metrics[r["id"]]["jumps_over_6db_per_s"] = j
    if only:  # merge a re-run of some sources into the full-run files
        old_man = json.loads((ROOT / "real-audio-manifest.json").read_text())
        old_met = json.loads((ROOT / "real-audio-metrics.json").read_text())
        keep = lambda k: not any(k.startswith(f"{n}/") for n in only)
        manifest["renders"] = [r for r in old_man["renders"] if r["source"] not in only] + manifest["renders"]
        manifest["failures"] += [f for f in old_man["failures"] if keep(f["id"])]
        metrics = {**{k: v for k, v in old_met.items() if keep(k)}, **metrics}
    X.dump(manifest, ROOT / "real-audio-manifest.json")
    X.dump(metrics, ROOT / "real-audio-metrics.json")
    bad = [k for k, m in metrics.items() if isinstance(m, dict) and m.get("finite") is False]
    print(f"renders: {len(manifest['renders'])}  failures: {manifest['failures']}  skipped: {manifest['skipped_inputs']}  non-finite: {len(bad)}")
    return 1 if bad or manifest["failures"] else 0


def blind(seed=20261122):
    rng, key, order = random.Random(seed), {}, []
    stems = PRIORITY + sorted(w.stem for w in INPUTS.glob("*.wav") if w.stem not in PRIORITY)
    shutil.rmtree(OUT / "blind", ignore_errors=True)
    for stem in stems:
        base = OUT / f"user_{stem}" / CASE
        for set_name, names in SETS.items():
            files = [base / f"{n}.wav" for n in names]
            if (set_name == "progression" and stem not in PRIORITY) or not all(f.exists() for f in files):
                continue
            rng.shuffle(files)
            folder = f"{len(order) + 1:02d}__{stem}__{set_name}"
            order.append(folder)
            for label, f in zip("ABCD", files):
                dst = OUT / "blind" / folder / f"{label}.wav"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
                key[f"{folder}/{label}"] = f.stem
            shutil.copyfile(base / "roi_oneshot.wav", OUT / "blind" / folder / "reference_roi.wav")
    X.dump(key, OUT / "blind-KEY-do-not-open.json")
    print(f"blind sets: {len(order)}")
    return 0 if order else 1


def summary():
    m = json.loads((ROOT / "real-audio-metrics.json").read_text())
    names = ["trace", "p0b_cloud", "p0b_focus", "split_s1", "split_s2_keep_100", "split_s3_100", "conv_s3_100"]
    out = []
    for cap in sorted(k for k in m if k.endswith("/capture")):
        b = cap.rsplit("/", 1)[0]
        out.append(f"\n**{b}** - period {m[cap]['period_samples']} samples, energy share low/mid/high {m[cap]['full']['band_energy_share']}\n")
        out.append("| render | match gain (dB) | final peak (dBFS) | crest (dB) | ripple (dB) | 10 ms level step (dB) | jumps > 6 dB /s | band repetition low/mid/high | band level re TRACE (dB) | mono compat (dB) |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---|---|---:|")
        for n in names:
            r = m.get(f"{b}/{n}")
            if r:
                out.append(f"| {n} | {r['match_gain_db']:+.1f} | {r['peak_dbfs']:.2f} | {r['crest_db']:.1f} | {r['ripple_db']:.1f} | {r['mean_abs_level_step_db_10ms']:.2f} "
                           f"| {r['jumps_over_6db_per_s']:.2f} | {' / '.join(f'{v:.2f}' for v in r['band_period_autocorr'])} "
                           f"| {' / '.join(f'{v:+.1f}' for v in r['band_level_db_re_trace'])} | {r['mono_compat_db']:.2f} |")
        out.append("\nBODY+GHOST mix peaks (dBFS): " + ", ".join(f"{n} {m[f'{b}/{n}']['mix_peak_dbfs']:+.2f}" for n in ("split_s1", "progression_s2_keep")))
    print("\n".join(out))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["inventory", "regions", "render", "blind", "summary"])
    ap.add_argument("--only", nargs="*", help="source names, e.g. user_03_acoustic_drum_break")
    a = ap.parse_args()
    if a.command == "inventory":
        X.dump(inventory(), ROOT / "real-audio-inventory.json")
    elif a.command == "regions":
        rows = regions()
        X.dump(rows, ROOT / "real-audio-regions.json")
        for r in rows:
            print(f"{r['file']:40s} {r['class']:9s} {r['t0']:6.2f}-{r['t1']:6.2f}  {r['region_rms_dbfs']:6.1f} dBFS  {r['reason']}")
    else:
        return {"render": lambda: render(a.only), "blind": blind, "summary": summary}[a.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
