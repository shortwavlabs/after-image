# SPDX-License-Identifier: AGPL-3.0-only
"""P0-B: capture buffer, grain engine and DISSOLVE. The thresholded numerical
checks live in p0.verify_cloud (limits fixed there); here each one must have no
FAIL row, followed by direct unit tests of the pieces."""
from dataclasses import replace

import numpy as np
import pytest

from p0 import capture as C
from p0 import engines as E
from p0 import fixtures
from p0 import granular as G
from p0 import metrics as Mx
from p0 import stft as S
from p0 import verify_cloud as V

FS, N = 48000, 4096


@pytest.mark.parametrize("check", V.CHECKS, ids=lambda c: c.__name__)
def test_verification_check_has_no_failures(check):
    rows = check()
    assert rows
    assert [r for r in rows if r["result"] == "FAIL"] == []


def test_capture_buffer_is_exactly_the_selected_samples():
    x = fixtures.make("drums", FS)
    p = V.prepare(x, FS, N, 0.9, 1.65, 0.0, None, xfade_s=None)
    H, i = S.hop(N), p["info"]
    M = p["last"] - p["first"] + 1
    assert i["samples"] == i["selection_samples"] == M * H  # P0-A interior was (M - 3) * H
    assert i["start_sample"] == (p["first"] + 1) * H - N // 2 - H // 2  # half a hop before the first window centre
    assert i["context_missing"] == [] and i["context_latency_samples"] == 2 * H
    assert Mx.error_db(p["spectral"], x[i["start_sample"]:i["start_sample"] + M * H]) < -90


def test_capture_at_stream_start_uses_silent_context():
    x = fixtures.make("guitar", FS)
    h = C.SpectralHistory(FS, N, 2)
    h.push_signal(x[:FS])
    cap = C.capture(h, C.CaptureRequest(h.epoch, 0, 20, 0.0, FS / 2))
    buf, info = G.capture_buffer(h, cap)
    assert info["context_missing"] == [] and info["start_sample"] == -3 * S.hop(N) // 2
    pad = -info["start_sample"]  # the selection of frame 0 starts before the stream: that part is silence
    assert np.max(np.abs(buf[:pad])) < 1e-6
    assert Mx.error_db(buf[pad:], x[:len(buf) - pad]) < -90


def test_shared_seam_gives_both_buffers_one_period():
    p = V.prepare(fixtures.make("synth", FS), FS, N, 1.0, 1.75, 2000, 10000)
    assert len(p["per_s"]) == len(p["per_r"]) == p["seam"]["period_samples"]
    with pytest.raises(E.EngineError):
        E.loop_period(p["raw"], FS, 0.08, "aligned", period=10)


def test_schedule_draws_stay_inside_their_ranges():
    p = G.CloudParams(grain_s=0.1, density_hz=40, pitch_st=3.0, octave_prob=0.3, reverse_prob=0.25, spread=0.6, amp_var=0.5)
    g = G.schedule(20000, FS, 30 * FS, p, seed=3)
    st = 12 * np.log2(g["speed"])
    base = st - 12 * np.round(st / 12)  # remove octave jumps
    assert np.all(np.abs(base) <= 3.0 + 1e-9)
    octs = np.round(st / 12)
    assert set(np.unique(octs)) == {-1.0, 0.0, 1.0}
    assert abs(np.mean(octs != 0) - 0.3) < 0.05 and abs(np.mean(g["reverse"]) - 0.25) < 0.05
    assert np.all((g["amp"] >= 0.5) & (g["amp"] <= 1.0))
    pan = np.arctan2(g["gr"], g["gl"]) * 4 / np.pi - 1
    assert np.all(np.abs(pan) <= 0.6 + 1e-9) and np.allclose(g["gl"] ** 2 + g["gr"] ** 2, 2.0)
    assert np.all((g["pos"] >= 0) & (g["pos"] < 20000)) and np.all(np.diff(g["onset"]) >= 0)


def test_window_choice_and_seed_change_only_what_they_should():
    buf = V._noise(seconds=0.5)
    p = G.dissolve_params(1.0, FS)
    a, _ = G.cloud(buf, FS, FS, p, seed=1)
    b, _ = G.cloud(buf, FS, FS, replace(p, window="tukey"), seed=1)
    assert not np.array_equal(a, b)
    ga, gb = (G.schedule(len(buf), FS, FS, q, seed=1) for q in (p, replace(p, window="tukey")))
    for f in ("onset", "length", "pos", "speed", "reverse", "gl", "gr"):  # same grains, different envelope and gain
        assert np.array_equal(ga[f], gb[f])


def test_polyphony_overflow_drops_whole_grains_without_clicks():
    t = np.arange(FS) / FS
    buf = np.repeat((0.5 * np.sin(2 * np.pi * 110 * t))[:, None], 2, axis=1)
    p = G.CloudParams(grain_s=0.3, density_hz=100)
    y, info = G.cloud(buf, FS, 4 * FS, p, seed=2, max_grains=6)
    assert info["dropped"] > 0 and info["max_active"] <= 6
    full, _ = G.cloud(buf, FS, 4 * FS, p, seed=2, max_grains=1000)
    assert not np.array_equal(y, full)
    # a 110 Hz sine moves at most 2*pi*110/fs per sample per unit amplitude; no step may exceed the summed bound
    assert np.max(np.abs(np.diff(y, axis=0))) < 6 * 1.2 * np.sqrt(2) * 0.5 * (2 * np.pi * 110 / FS + 2 * np.pi / 14400) * 1.5


def test_time_varying_dissolve_starts_as_trace_and_ends_as_cloud():
    per = V.prepare(fixtures.make("guitar", FS), FS, N, *V.CASES["guitar"])["per_s"]
    n = 8 * FS
    y, info = G.dissolve(per, FS, n, G.ramp(2.0, 4.0), seed=5)
    trace = np.tile(per, (-(-n // len(per)), 1))[:n]
    hold = 2 * FS - 2 * 5760  # until the first non-zero-D grain can sound
    assert Mx.error_db(y[:hold], trace[:hold]) < -120
    assert Mx.error_db(y[-FS:], trace[-FS:]) > -6  # no longer the loop
    assert info["dropped"] == 0 and Mx.is_finite(y)


def test_parallel_morph_accepts_a_per_sample_trajectory():
    a, b = np.ones((100, 2)), np.full((100, 2), 3.0)
    d = np.linspace(0, 1, 100)
    y = G.parallel(a, b, d)
    assert np.array_equal(y[0], a[0]) and np.allclose(y[-1], b[-1])
    assert np.allclose(y[:, 0], np.cos(0.5 * np.pi * d) + 3 * np.sin(0.5 * np.pi * d))


def test_position_cdf_follows_the_spectrum():
    H, M, K = S.hop(N), 30, N // 2 + 1
    rng = np.random.default_rng(0)
    frames = np.full((M, 1, K), 1e-6, complex)
    frames[5] = 5 * rng.standard_normal(K)  # a broadband hit arriving at frame 5
    frames[18:26, 0, 100] = 50.0  # a steady tone later
    R = M * H
    for mode, target in (("transient", 5), ("harmonic", 22)):
        cdf = G.position_cdf(frames, R, H, mode)
        assert np.all(np.diff(cdf) >= 0) and abs(cdf[-1] - 1) < 1e-12
        median_frame = np.searchsorted(cdf, 0.5) / H - 0.5
        assert abs(median_frame - target) <= 3, (mode, median_frame)
    flat = G.position_cdf(np.zeros((M, 1, K), complex), R, H, "harmonic")
    assert np.allclose(np.diff(flat), 1 / R)  # silence falls back to uniform


def test_guided_positions_change_only_the_positions():
    per = V._noise(seconds=0.6)
    cdf = np.linspace(0, 1, len(per) + 1)[1:] ** 3  # weight piled towards the end of the buffer
    p = G.dissolve_params(1.0, FS)
    a, b = G.schedule(len(per), FS, 4 * FS, p, seed=7), G.schedule(len(per), FS, 4 * FS, p, seed=7, pos_cdf=cdf)
    for f in ("onset", "length", "speed", "reverse", "amp", "gain", "gl", "gr"):
        assert np.array_equal(a[f], b[f])
    centre = (b["pos"] + 0.5 * b["length"] * b["speed"]) % len(per)
    assert np.median(centre) > 0.6 * len(per)
