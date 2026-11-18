# SPDX-License-Identifier: AGPL-3.0-only
"""End-to-end determinism of the P0-B pipeline and blind pack (drums only)."""
import json

from scipy.io import wavfile

from p0 import cloud_experiment as CE
from p0 import experiment


def _run(tmp_path, name, **kw):
    return CE.run(tmp_path / name, inputs_dir=tmp_path / "no-inputs", only=["drums"], log=lambda *_: None, **kw)


def test_two_runs_are_bit_identical_and_blind_pack_is_clean(tmp_path):
    m1, x1 = _run(tmp_path, "a")
    m2, x2 = _run(tmp_path, "b")
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
    assert json.dumps(x1, sort_keys=True) == json.dumps(x2, sort_keys=True)
    assert len(m1["renders"]) == 11 and not m1["failures"]
    for r in m1["renders"]:
        assert (tmp_path / "a" / r["path"]).read_bytes() == (tmp_path / "b" / r["path"]).read_bytes()
    ghosts = [m for m in x1.values() if isinstance(m, dict) and "finite" in m]
    assert ghosts and all(m["finite"] and m["denormals_float32"] == 0 for m in ghosts)
    # the two cloud endpoints are the same thing by construction
    assert x1["drums/full_spectrum/dissolve_000"]["period_autocorr"] == 1.0

    experiment.dump(x1, tmp_path / "metrics.json")
    sets = CE.blind_pack(tmp_path / "a", metrics_path=tmp_path / "metrics.json")
    key = json.loads((tmp_path / "a" / "blind-KEY-do-not-open.json").read_text())
    assert sets == 2  # engine + dissolve; the full-band drum case has no ON/OFF set
    assert not list((tmp_path / "a" / "blind").rglob("*.json"))  # the key is outside the set folders
    for folder in {k.rsplit("/", 1)[0] for k in key}:
        lengths = {len(wavfile.read(f)[1]) for f in (tmp_path / "a" / "blind" / folder).glob("[ABC].wav")}
        assert len(lengths) == 1
