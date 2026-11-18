# SPDX-License-Identifier: AGPL-3.0-only
"""Numerical gates for the engines. Thresholds live in p0/verify.py so the
tests and the published verification.json can never disagree."""
import numpy as np
import pytest

from p0 import capture as C
from p0 import engines as E
from p0 import metrics as Mx
from p0 import verify as V


@pytest.mark.parametrize("check", V.CHECKS, ids=lambda c: c.__name__)
def test_no_numerical_failures(check):
    failed = [r for r in check() if r["result"] == "FAIL"]
    assert not failed, failed


def test_loop_rejects_capture_without_interior():
    fs, N = 48000, 8192
    x = np.random.default_rng(0).standard_normal(3 * fs) * 0.1
    h = C.SpectralHistory(fs, N, 1)
    h.push_signal(x)
    cap = C.capture(h, C.CaptureRequest(0, 20, 22, 20.0, fs / 2), min_s=0.0)  # 3 frames
    with pytest.raises(E.EngineError):
        E.loop(cap, fs)


def test_loop_is_exactly_periodic_and_copies_source():
    fs, N = 48000, 4096
    x = np.random.default_rng(1).standard_normal((3 * fs, 2)) * 0.1
    cap = V.make_capture(x, fs, N, freq_feather_oct=0.0)
    y, info = E.loop(cap, 4 * fs, 0.08, "aligned")
    R, X = info["period_samples"], info["xfade_samples"]
    assert np.array_equal(y[:R], y[R:2 * R])
    # outside the crossfade the loop is the original audio (unity mask): < -90 dB
    start = (cap.first_frame + 1) * (N // 4) - N // 4
    assert Mx.error_db(y[X:R], x[start + X:start + R]) < -90


def test_freeze_is_single_frame_sustain():
    """Documents how close the baseline is to candidate B: on a stationary sine
    they are the same signal; they differ only when the capture is not stationary."""
    fs, N = 48000, 4096
    x = 0.5 * np.sin(2 * np.pi * 441.37 * np.arange(3 * fs) / fs)
    cap = V.make_capture(x, fs, N)
    y, info = E.sustain(cap, fs)
    # same starting frame -> same starting phase (otherwise they differ by a time shift)
    assert Mx.error_db(E.freeze(cap, fs, frame=info["reference_frame"])[0], y) < -60


def test_envelope_t60_and_level_match():
    fs = 48000
    env = E.envelope(4 * fs, fs, 2.0)
    assert abs(Mx.db(env[2 * fs, 0]) + 60) < 0.01 and env[0, 0] == 0.0
    y, g = E.match_level(np.random.default_rng(2).standard_normal((3 * fs, 2)), fs, -20.0)
    assert abs(Mx.db(Mx.rms(y[:2 * fs])) + 20) < 1e-6 and g > 0
    assert E.match_level(np.zeros((fs, 2)), fs)[1] == 1.0
