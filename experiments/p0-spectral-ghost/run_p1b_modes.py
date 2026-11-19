# SPDX-License-Identifier: AGPL-3.0-only
"""P1-B capture modes on audio (docs/P1-B-QUALIFICATION.md 1.5, 1.7).

  uv run python run_p1b_modes.py --render /path/to/afterimage_render

1. Musical render cases from original synthetic material (riff, sustained chord, drum loop, sustained synth), each in
   MANUAL (triggers), RANDOM and AUTO, BODY + GHOST, written to renders/p1b/ (git-ignored). Request summaries go to
   p1b-render-cases.json.
2. AUTO and RANDOM, untuned, on the local recordings in inputs/ (licence unknown, blocker B11): counts only, in
   p1b-real-modes.json. No audio from them is written outside renders/ and nothing is tuned on them.
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from p0 import experiment as X, fixtures

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "renders" / "p1b"
FS = 48000


def pluck(fs, onsets, f0s, decay_db_s=10.0, seconds=None):
    n = int((seconds or onsets[-1] + 3.0) * fs)
    x = np.zeros(n)
    for t0, f0 in zip(onsets, f0s):
        t = np.arange(n - int(t0 * fs)) / fs
        env = np.minimum(1, t / 0.003) * 10 ** (-decay_db_s * t / 20)
        x[int(t0 * fs):] += env * sum(np.sin(2 * np.pi * f0 * h * t) / h for h in range(1, 7))
    return x


def cases(fs):
    riff_on = [1.0 + 0.4 * k for k in range(32)]
    riff = pluck(fs, riff_on, [[196, 247, 294, 392, 330, 294, 247, 220][k % 8] for k in range(32)], 18.0, 16.0)
    chord = pluck(fs, [1.0, 7.0, 13.0], [98.0, 110.0, 82.4], 3.0, 18.0) + pluck(fs, [1.0, 7.0, 13.0], [147.0, 165.0, 123.5], 3.0, 18.0)
    drum = np.tile(fixtures.make("drums", fs)[:, 0], 4)
    synth = np.tile(fixtures.make("synth", fs)[:, 0], 4)
    out = {}
    for name, x in (("riff", riff), ("sustained_chord", chord), ("drum_loop", drum), ("sustained_synth", synth)):
        x = x / np.max(np.abs(x)) * 0.5
        out[name] = np.stack([x, x * 0.95], axis=1)
    return out


def run(exe, inp, prefix, args):
    subprocess.run([exe, f"in={inp}", f"out={prefix}", *args], check=True, capture_output=True)
    with open(f"{prefix}.requests.csv") as f:
        return list(csv.DictReader(f))


def summary(rows, fs):
    caps = [r for r in rows if r["outcome"] in ("ACCEPTED", "COMPLETED")]
    by = {}
    for r in rows:
        by[f"{r['origin']}:{r['outcome']}"] = by.get(f"{r['origin']}:{r['outcome']}", 0) + 1
    return {"captures": len(caps), "outcomes": by,
            "capture_starts_s": [round(int(r["s0"]) / fs, 3) for r in caps], "capture_lengths_ms": sorted({round(1000 * (int(r["s1"]) - int(r["s0"])) / fs) for r in caps})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    exe = ap.parse_args().render
    OUT.mkdir(parents=True, exist_ok=True)
    common = ["body=1", "ghost=0.7", "dissolve=0.5", "t60=6", "pad=3"]
    modes = {"manual": lambda n: ["mode=manual"] + [f"trigger={int(t * FS)}" for t in np.arange(2.0, n / FS - 1, 3.0)],
             "random": lambda n: ["mode=random", "interval=2"],
             "auto": lambda n: ["mode=auto"]}
    rendered = {}
    for name, x in cases(FS).items():
        d = OUT / name
        d.mkdir(exist_ok=True)
        wavfile.write(d / "input.wav", FS, x.astype(np.float32))
        rendered[name] = {m: summary(run(exe, d / "input.wav", d / m, common + f(len(x))), FS) for m, f in modes.items()}
        print(name, {m: v["captures"] for m, v in rendered[name].items()})
    X.dump({"note": "Original synthetic material only. WAVs in renders/p1b/ (git-ignored). BODY 1, GHOST 0.7, DISSOLVE 0.5, MEMORY 6 s; "
                    "MANUAL triggers every 3 s; RANDOM interval 2 s; AUTO defaults. Listening is the owner's.",
            "code_revision": X.code_revision(), "cases": rendered}, ROOT / "p1b-render-cases.json")

    real = {}
    for wav in sorted((ROOT / "inputs").glob("*.wav")):
        fs, d = wavfile.read(wav)
        n = d.shape[0]
        dd = OUT / "real" / wav.stem
        dd.mkdir(parents=True, exist_ok=True)
        real[wav.stem] = {"seconds": round(n / fs, 2)}
        for m, args in (("auto", ["mode=auto"]), ("random", ["mode=random", "interval=2"])):
            s = summary(run(exe, wav, dd / m, ["body=0", "ghost=1", "pad=1", *args]), fs)
            s["per_minute"] = round(60 * s["captures"] / (n / fs), 1)
            real[wav.stem][m] = s
        print(wav.stem, real[wav.stem]["auto"]["captures"], "AUTO,", real[wav.stem]["random"]["captures"], "RANDOM")
    X.dump({"note": "Local recordings of unknown licence (B11): counts and times only, untuned, AUTO defaults, RANDOM interval 2 s.",
            "code_revision": X.code_revision(), "recordings": real}, ROOT / "p1b-real-modes.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
