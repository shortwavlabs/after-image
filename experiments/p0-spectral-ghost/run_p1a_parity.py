# SPDX-License-Identifier: AGPL-3.0-only
"""P1-A parity: the C++ engine (afterimage_render) against p1a_reference, limits in p1a-limits.json.

  uv run python run_p1a_parity.py --render /path/to/afterimage_render     -> p1a-parity.json

Fixtures are the synthetic P0 sources, written as float32 WAVs to a temporary folder and deleted afterwards.
The reference reads the same float32 WAV, so both sides start from identical samples.
"""
import argparse
from dataclasses import replace
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

import p1a_reference as P
from p0 import experiment as X, fixtures, stft as S

ROOT = Path(__file__).resolve().parent
LIM = json.loads((ROOT / "p1a-limits.json").read_text())
RATES = (44100, 48000, 88200, 96000)


def err_db(test, ref):
    d, r = np.asarray(test) - np.asarray(ref), np.asarray(ref)
    num, den = np.sqrt(np.mean(np.abs(d) ** 2)), np.sqrt(np.mean(np.abs(r) ** 2))
    return float(-400.0 if num == 0 else 20 * np.log10(num / den))


def read(path):
    fs, d = wavfile.read(path)
    d = d.astype(np.float64)
    return fs, (d[:, None] if d.ndim == 1 else d)


class Renderer:
    def __init__(self, exe, tmp):
        self.exe, self.tmp = exe, Path(tmp)

    def __call__(self, name, x, fs, *args):
        inp = self.tmp / f"{name}.in.wav"
        wavfile.write(inp, fs, x.astype(np.float32))
        pre = self.tmp / name
        subprocess.run([self.exe, f"in={inp}", f"out={pre}", *args], check=True, capture_output=True)
        return pre, json.loads(Path(f"{pre}.json").read_text()), read(inp)[1]


def row(check, case, value, limit, ok, unit="dB"):
    return {"check": check, "case": case, "value": value, "limit": limit, "unit": unit, "result": "PASS" if ok else "FAIL"}


def frames_parity(r, rows):
    for fs in RATES:
        x = fixtures.make("guitar", fs)
        N = 4096 if fs <= 48000 else 8192
        pre, info, xf = r(f"frames_{fs}", x, fs, "frames=0,40")
        K = N // 2 + 1
        got = np.fromfile(f"{pre}.frames.f32", dtype=np.complex64).reshape(41, xf.shape[1], K)
        ref = S.stft(xf, N)[:41]
        v = err_db(got, ref)
        rows.append(row("P1 STFT frames", f"guitar fs={fs} N={N} frames 0-40", round(v, 1), LIM["P1_stft_frames_db"], v <= LIM["P1_stft_frames_db"]))


def capture_parity(r, rows, fs, src, source, dur, D, low=350.0, high=5000.0, seed=11, t60=5.0, density=0.0, mono=False):
    x = fixtures.make(src, fs)[:, :1] if mono else fixtures.make(src, fs)
    N = 4096 if fs <= 48000 else 8192
    s0 = int(1.0 * fs)
    s1 = s0 + int(round(dur * fs))
    at = int(3.0 * fs)
    case = f"{src} fs={fs} {source} {dur:.2f}s D={D}" + (f" density={density:g}/s" if density else "") + (" mono" if mono else "")
    name = f"cap_{src}_{fs}_{source}_{int(dur * 100)}_{int(D * 100)}_{int(density)}_{int(mono)}"
    pre, info, xf = r(name, x, fs, f"imprint={at},{s0},{s1},{source},{low},{high}", f"dissolve={D}", f"t60={t60}",
                      f"seed={seed}", "pad=3.5", "grainlog=1", f"density={density}")
    cap = info["captures"][0]
    _, loop = read(f"{pre}.loop.wav")
    ref_loop, ref_info = P.capture_loop(xf, fs, N, s0, s1, source, low if source == "filtered" else 0.0,
                                        high if source == "filtered" else None)
    lim = LIM["P2_full_loop_db" if source == "full" else "P3_filtered_loop_db"]
    v = err_db(loop, ref_loop)
    rows.append(row("P2 FULL loop" if source == "full" else "P3 FILTERED loop", case,
                    {"period_cpp": cap["period"], "period_ref": ref_info["period_samples"], "error_db": round(v, 1),
                     "rho_cpp": round(cap["rho"], 6), "rho_ref": round(ref_info["seam_correlation"], 6)},
                    lim, cap["period"] == ref_info["period_samples"] == s1 - s0 and v <= lim))

    # output: ghost only (BODY 0, GHOST 1), from the voice's first sample, 2 s; reference scheduled 1 s further
    _, y = read(f"{pre}.out.wav")
    start, n = cap["started_at"], int(2.0 * fs)
    params = replace(P.cloud_params(fs), density_hz=density) if density else None
    ref, grains = P.ghost(ref_loop, fs, n + fs, D, t60, cap["seed"], params)
    v = err_db(y[start:start + n], ref[:n])
    key = "P5_trace_db" if D == 0 else ("P6_cloud_db" if D == 1 else "P7_parallel_half_db")
    rows.append(row({"P5_trace_db": "P5 TRACE", "P6_cloud_db": "P6 CLOUD", "P7_parallel_half_db": "P7 D=0.5"}[key], case,
                    round(v, 1), LIM[key], v <= LIM[key]))

    # grain table
    g = np.genfromtxt(f"{pre}.grains.csv", delimiter=",", names=True)
    g = g[np.argsort(g["onset"], kind="stable")]
    g, ref_g = g[g["onset"] < n], grains[grains["onset"] < n]
    same_int = (len(g) == len(ref_g) and np.array_equal(g["onset"], ref_g["onset"]) and np.array_equal(g["length"], ref_g["length"])
                and np.array_equal(g["reverse"].astype(bool), ref_g["reverse"]) and np.array_equal(g["dropped"].astype(bool), ref_g["dropped"]))
    if same_int:
        dpos = float(np.max(np.abs(g["pos"] - ref_g["pos"])))
        dgain = float(max(np.max(np.abs(g[f] / ref_g[f] - 1)) for f in ("gain", "gl", "gr")))
    else:
        dpos = dgain = float("inf")
    rows.append(row("P4 grain table", case, {"grains": int(len(ref_g)), "dropped": int(ref_g["dropped"].sum()), "identical_integers": bool(same_int),
                                             "max_pos_diff_samples": dpos, "max_gain_rel_diff": dgain},
                    {"pos": LIM["P4_grain_position_abs"], "gain_rel": LIM["P4_grain_gain_rel"]},
                    same_int and dpos <= LIM["P4_grain_position_abs"] and dgain <= LIM["P4_grain_gain_rel"], unit=""))
    return {"case": case, "accepted_at": cap["accepted_at"], "started_at": cap["started_at"],
            "delay_samples": cap["started_at"] - cap["accepted_at"], "delay_ms": round(1000 * (cap["started_at"] - cap["accepted_at"]) / fs, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    a = ap.parse_args()
    rows, delays = [], []
    with tempfile.TemporaryDirectory() as tmp:
        r = Renderer(a.render, tmp)
        frames_parity(r, rows)
        for fs in RATES:
            for source in ("full", "filtered"):
                for src, dur, D in (("guitar", 0.75, 0.0), ("guitar", 0.75, 1.0), ("drums", 0.75, 0.5), ("vocal", 0.20, 1.0), ("synth", 1.50, 1.0)):
                    delays.append(capture_parity(r, rows, fs, src, source, dur, D))
            # stress density: the 32-grain ceiling drops grains, exercising the admission rule
            capture_parity(r, rows, fs, "guitar", "full", 0.75, 1.0, density=400.0)
            if fs in (48000, 96000):  # mono: one channel in, one out, no stereo balance
                for source in ("full", "filtered"):
                    capture_parity(r, rows, fs, "guitar", source, 0.75, 1.0, mono=True)
    summary = {k: sum(r_["result"] == k for r_ in rows) for k in ("PASS", "FAIL")}
    X.dump({"note": "C++ afterimage_render against p1a_reference.py; limits fixed beforehand in p1a-limits.json.",
            "code_revision": X.code_revision(), "summary": summary, "rows": rows, "capture_delay": delays},
           ROOT / "p1a-parity.json")
    print("parity:", summary)
    for r_ in rows:
        if r_["result"] == "FAIL":
            print("  FAIL", r_["check"], r_["case"], r_["value"])
    return 1 if summary["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
