# SPDX-License-Identifier: AGPL-3.0-only
"""End-to-end determinism and safety of the experiment pipeline (small subset)."""
import json

import numpy as np

from p0 import experiment


def _run(tmp_path, name, **kw):
    return experiment.run(tmp_path / name, inputs_dir=tmp_path / "no-inputs", only=["drums"], fft_sizes=[2048],
                          log=lambda *_: None, **kw)


def test_two_runs_are_bit_identical(tmp_path):
    m1, x1 = _run(tmp_path, "a")
    m2, x2 = _run(tmp_path, "b")
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
    assert json.dumps(x1, sort_keys=True) == json.dumps(x2, sort_keys=True)
    assert len(m1["renders"]) == 12 and not m1["failures"]
    for r in m1["renders"]:
        a = (tmp_path / "a" / r["path"]).read_bytes()
        assert a == (tmp_path / "b" / r["path"]).read_bytes()


def test_renders_are_finite_bounded_and_level_matched(tmp_path):
    _, metrics = _run(tmp_path, "c", write_audio=False)
    ghosts = {k: v for k, v in metrics.items() if not k.endswith("roi_reference")}
    assert ghosts
    for k, m in ghosts.items():
        assert m["finite"] and m["denormals_float32"] == 0, k
        assert m["peak_dbfs"] < 0.0, k
        # -23 dBFS RMS target over 2 s; the shared T60 = 5 s decay (-12 dB/s) removes
        # 7.4 dB of RMS from a stationary signal over that window -> about -30.4 dBFS.
        # Non-stationary ghosts (drum loops) land within a few dB of that.
        assert -33.5 < m["rms_dbfs_first_2s"] < -27.5, k


def test_user_wav_is_picked_up(tmp_path):
    from scipy.io import wavfile
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fs = 44100
    t = np.arange(3 * fs) / fs
    wavfile.write(inputs / "take.wav", fs, (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16))
    wavfile.write(inputs / "odd_rate.wav", 22050, np.zeros(22050, np.int16))
    manifest, metrics = experiment.run(tmp_path / "out", inputs_dir=inputs, only=["user_take"], log=lambda *_: None)
    assert {r["source"] for r in manifest["renders"]} == {"user_take"}
    assert {r["fft_size"] for r in manifest["renders"]} == {4096}
    assert manifest["skipped_inputs"] == [{"file": "odd_rate.wav", "reason": "unsupported sample rate 22050"}]
    assert (tmp_path / "out" / "user_take" / "full_spectrum" / "fs44100_N4096" / "sustain_mean.wav").exists()
