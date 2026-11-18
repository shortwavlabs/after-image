# SPDX-License-Identifier: AGPL-3.0-only
"""End-to-end determinism of the P0-C pipeline, blind pack and user-WAV path."""
import json

import numpy as np
from scipy.io import wavfile

from p0 import experiment
from p0 import split_experiment as SE


def test_two_runs_are_bit_identical_and_blind_pack_is_clean(tmp_path):
    run = lambda name: SE.run(tmp_path / name, inputs_dir=tmp_path / "no-inputs", only=["drums"], log=lambda *_: None)
    (m1, x1), (m2, x2) = run("a"), run("b")
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
    assert json.dumps(x1, sort_keys=True) == json.dumps(x2, sort_keys=True)
    assert len(m1["renders"]) == 14 and not m1["failures"]
    for r in m1["renders"]:
        assert (tmp_path / "a" / r["path"]).read_bytes() == (tmp_path / "b" / r["path"]).read_bytes()
        assert r["capture_source"] == "full" and r["crossovers_hz"] == [250.0, 2000.0] and "match_gain_db" in r
    ghosts = [m for m in x1.values() if isinstance(m, dict) and "finite" in m]
    assert ghosts and all(m["finite"] and m["denormals_float32"] == 0 for m in ghosts)
    assert x1["drums/full_spectrum/split_s1"]["band_period_autocorr"][0] > 0.95  # lows still the loop

    experiment.dump(x1, tmp_path / "metrics.json")
    sets = SE.blind_pack(tmp_path / "a", metrics_path=tmp_path / "metrics.json")
    key = json.loads((tmp_path / "a" / "blind-KEY-do-not-open.json").read_text())
    assert sets == 6  # the full-band drum case has no FULL-vs-FILTERED set
    assert not list((tmp_path / "a" / "blind").rglob("*.json"))
    for folder in {k.rsplit("/", 1)[0] for k in key}:
        lengths = {len(wavfile.read(f)[1]) for f in (tmp_path / "a" / "blind" / folder).glob("[ABCD].wav")}
        assert len(lengths) == 1


def test_user_wav_gets_every_split_render(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fs = 44100
    t = np.arange(3 * fs) / fs
    sig = 0.2 * sum(np.sin(2 * np.pi * f * t) for f in (110, 440, 3520))
    wavfile.write(inputs / "take.wav", fs, (sig * 32767).astype(np.int16))
    manifest, metrics = SE.run(tmp_path / "out", inputs_dir=inputs, only=["user_take"], log=lambda *_: None)
    assert not manifest["failures"] and {r["source"] for r in manifest["renders"]} == {"user_take"}
    assert {r["fs"] for r in manifest["renders"]} == {44100}
    names = {r["engine"] for r in manifest["renders"] if r["case"] == "mid_band"}
    assert {"split_s1", "split_s3_100", "conv_s3_100", "filtered_split_s1", "filtered_split_s1_native", "progression_s2_keep"} <= names
    m = metrics["user_take/mid_band/filtered_split_s1_native"]
    assert m["match_gain_db"] == metrics["user_take/mid_band/split_s1"]["match_gain_db"]  # FULL's gain, not its own
    assert (tmp_path / "out" / "user_take" / "mid_band" / "filtered_split_s1.wav").exists()
