# SPDX-License-Identifier: AGPL-3.0-only
"""Anchors the P1-A reference to P0 (docs/P1-A-QUALIFICATION.md 1.1) before C++ is compared with it."""
import json
from pathlib import Path

import numpy as np

import p1a_reference as P
from p0 import capture as C, fixtures, granular as G, metrics as Mx, stft as S

LIM = json.loads((Path(__file__).resolve().parents[1] / "p1a-limits.json").read_text())


def test_A1_schedule_equals_p0_with_pcg64():
    for fs in (44100, 96000):
        p = P.cloud_params(fs)
        for params in (p, G.dissolve_params(0.6, fs)):  # CLOUD, and a setting with pitch, octaves and partial spray
            a = G.schedule(30000, fs, 3 * fs, params, seed=5)
            b = P.schedule(30000, fs, 3 * fs, params, np.random.default_rng(5))
            assert a.dtype == b.dtype and len(a) == len(b)
            for f in a.dtype.names:
                assert np.array_equal(a[f], b[f]), f


def test_A2_reconstruction_equals_p0_capture_buffer():
    fs, N = 48000, 4096
    x = fixtures.make("guitar", fs)
    h = C.SpectralHistory(fs, N, x.shape[1])
    h.push_signal(x[:3 * fs])
    first, last = C.frames_for_interval(1.0, 1.75, fs, N)
    cap = C.capture(h, C.CaptureRequest(h.epoch, first, last, 350.0, 5000.0))
    ref, info = G.capture_buffer(h, cap)
    frames = np.stack([h.frame(i, h.epoch) for i in range(h.oldest_id, h.latest_id + 1)])
    frames = np.concatenate([np.zeros((h.oldest_id,) + frames.shape[1:], frames.dtype), frames])
    got = P.reconstruct(frames, cap.freq_mask, N, info["start_sample"], info["samples"])
    assert Mx.error_db(got, ref) <= LIM["A2_filtered_vs_p0_capture_buffer_db"]


def test_A3_render_is_p0_render():
    assert P.G.render is G.render  # the reference renders with P0's code, not a copy


def test_loop_period_and_post_roll_seam():
    fs, N = 48000, 4096
    x = fixtures.make("guitar", fs)
    s0, s1 = 0, int(0.75 * fs)
    loop, info = P.capture_loop(x, fs, N, s0, s1, "full")
    X = P.seam_samples(fs)
    assert len(loop) == s1 - s0 == info["period_samples"]
    assert np.array_equal(loop[0], x[s1]) and np.array_equal(loop[-1], x[s1 - 1])  # wrap continues the recording
    assert np.array_equal(loop[X:], x[s0 + X:s1])
    floop, _ = P.capture_loop(x, fs, N, s0, s1, "filtered", 0.0, None)  # unmasked FILTERED == FULL
    assert Mx.error_db(floop, loop) < -200


def test_splitmix64_known_values():
    # first outputs for seed 1234567 from the published SplitMix64 reference (Vigna)
    r = P.SplitMix64(1234567)
    vals = [r._next() for _ in range(3)]
    assert vals == [6457827717110365317, 3203168211198807973, 9817491932198370423]
