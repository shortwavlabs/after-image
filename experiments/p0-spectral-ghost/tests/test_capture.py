# SPDX-License-Identifier: AGPL-3.0-only
import math

import numpy as np
import pytest

from p0 import capture as C
from p0 import stft as S
from p0.metrics import error_db

FS, N = 48000, 4096
H = S.hop(N)


def noise(seconds, channels=2, seed=0):
    return np.random.default_rng(seed).standard_normal((int(seconds * FS), channels)) * 0.1


def make_history(x, dtype=np.complex64):
    h = C.SpectralHistory(FS, N, x.shape[1], dtype)
    for i in range(0, len(x), 333):  # odd block size: streaming must not care
        h.push_signal(x[i:i + 333])
    return h


def req(h, first, last, low=20.0, high=FS / 2, **kw):
    return C.CaptureRequest(h.epoch, first, last, low, high, **kw)


def test_capacity_matches_architecture_table():
    assert C.history_capacity(44100, 4096) == 261
    assert C.history_capacity(48000, 4096) == 284
    assert C.history_capacity(88200, 8192) == 261
    assert C.history_capacity(96000, 8192) == 284


def test_streaming_history_equals_offline_stft():
    x = noise(2.0)
    h = make_history(x, np.complex128)
    ref = S.stft(x, N)
    assert h.latest_id == len(x) // H - 1
    for m in (0, 3, 40, h.latest_id):
        assert np.allclose(h.frame(m, h.epoch), ref[m], atol=1e-10)
        assert h.end_sample(m) == S.frame_end(m, N)


def test_capture_selects_exact_frames_and_band():
    x = noise(3.0)
    h = make_history(x, np.complex128)
    first, last = C.frames_for_interval(1.0, 1.75, FS, N)
    cap = C.capture(h, req(h, first, last, 350.0, 5000.0))
    ref = S.stft(x, N)
    assert cap.frames.shape == (last - first + 1, 2, N // 2 + 1)
    assert np.allclose(cap.frames, ref[first:last + 1] * cap.freq_mask)
    f = np.arange(N // 2 + 1) * FS / N
    inside = (f >= 350) & (f <= 5000)
    assert np.all(cap.freq_mask[inside] == 1.0)
    assert cap.freq_mask[0] == 0 and np.all(cap.freq_mask[f > 5000 * 2 ** (1 / 6) + 1] == 0)
    assert np.all(cap.freq_mask[f < 350 * 2 ** (-1 / 6) - 1] == 0)
    assert np.all(np.diff(cap.freq_mask[f <= 350]) >= 0)  # monotone feather
    # window centres of the selected frames lie inside the requested interval
    centres = (np.arange(first, last + 1) + 1) * H - N / 2
    assert centres[0] >= 1.0 * FS and centres[-1] <= 1.75 * FS
    assert centres[0] - H < 1.0 * FS and centres[-1] + H > 1.75 * FS


def test_time_mask_is_smooth_and_symmetric():
    m = C.time_mask(20, 3)
    assert np.all(m > 0) and np.all(m[3:-3] == 1) and np.allclose(m, m[::-1])
    assert np.all(np.diff(m[:4]) > 0)


def test_unity_capture_is_identity():
    """Full-band, unfeathered capture resynthesises the original interior < -90 dB."""
    x = noise(3.0)
    for dtype in (np.complex128, np.complex64):
        h = make_history(x, dtype)
        first, last = 40, 100
        cap = C.capture(h, req(h, first, last, 0.0, FS / 2, freq_feather_oct=0.0, time_feather_s=0.0))
        assert np.all(cap.freq_mask == 1) and np.all(cap.time_mask == 1)
        buf = S.istft_buffer(cap.frames, N)
        M = last - first + 1
        start = S.frame_end(first, N) - H  # input sample at buffer index N - H
        interior = buf[N - H:M * H]
        assert error_db(interior, x[start:start + len(interior)]) < -90


def test_complex_data_preserved():
    x = noise(2.0)
    h = make_history(x, np.complex128)
    cap = C.capture(h, req(h, 20, 40, 0.0, FS / 2, freq_feather_oct=0.0))
    assert np.iscomplexobj(cap.frames) and np.array_equal(cap.frames, S.stft(x, N)[20:41])


@pytest.mark.parametrize("kw,code", [
    (dict(first=50, last=40), "INVALID_FRAMES"),
    (dict(first=40.5, last=60), "INVALID_FRAMES"),
    (dict(first=40, last=45), "TOO_SHORT"),
    (dict(first=10, last=90), "TOO_LONG"),
    (dict(first=130, last=150), "FUTURE"),  # 3 s of audio = frames 0..139
    (dict(first=-5, last=20), "EXPIRED"),
    (dict(first=40, last=60, low=5000.0, high=350.0), "INVALID_BAND"),
    (dict(first=40, last=60, low=float("nan")), "INVALID_BAND"),
    (dict(first=40, last=60, high=float("inf")), "INVALID_BAND"),
    (dict(first=40, last=60, high=FS), "INVALID_BAND"),
    (dict(first=40, last=60, low=-1.0), "INVALID_BAND"),
    (dict(first=40, last=60, low=1000.0, high=1010.0, freq_feather_oct=0.0), "TOO_FEW_BINS"),
])
def test_rejections(kw, code):
    h = make_history(noise(3.0))
    with pytest.raises(C.CaptureRejected) as e:
        C.capture(h, req(h, **kw))
    assert e.value.code == code


def test_stale_epoch_rejected_after_reset():
    h = make_history(noise(3.0))
    r = req(h, 40, 60)
    C.capture(h, r)
    h.reset()
    h.push_signal(noise(3.0, seed=1))
    with pytest.raises(C.CaptureRejected) as e:
        C.capture(h, r)
    assert e.value.code == "STALE_EPOCH"


def test_expiry_and_guard_margin():
    """A selection at the oldest *visible* frame survives the ~2 s guard, then
    expires cleanly - it must never return different (overwritten) audio."""
    x = noise(13.0, channels=1)
    h = C.SpectralHistory(FS, N, 1)
    h.push_signal(x[:int(5.0 * FS)])
    first, _ = h.visible_range()
    r = req(h, first, first + 20)
    ref = C.capture(h, r).frames.copy()
    assert math.isclose((h.latest_id - first + 1) * H / FS, C.VISIBLE_SECONDS, abs_tol=2 * H / FS)

    h.push_signal(x[int(5.0 * FS):int(6.9 * FS)])  # 1.9 s later: still inside the guard
    assert np.array_equal(C.capture(h, r).frames, ref)

    h.push_signal(x[int(6.9 * FS):int(7.2 * FS)])  # 2.2 s later: oldest frame overwritten
    with pytest.raises(C.CaptureRejected) as e:
        C.capture(h, r)
    assert e.value.code == "EXPIRED"

    # ring wrap: IDs keep increasing and a fresh selection reads the right audio
    h.push_signal(x[int(7.2 * FS):])
    assert h.latest_id > h.capacity
    f2 = h.latest_id - 30
    cap = C.capture(h, req(h, f2, f2 + 20, 0.0, FS / 2, freq_feather_oct=0.0))
    assert np.allclose(cap.frames, S.stft(x, N)[f2:f2 + 21], atol=1e-4)  # complex64 storage


@pytest.mark.parametrize("fs,n", [(48000, 2048), (48000, 4096), (48000, 8192), (44100, 4096), (96000, 8192)])
def test_max_roi_boundary_is_a_frame_count(fs, n):
    """Exactly ceil(1.5 * fs / H) frames is accepted; one more is TOO_LONG."""
    h = C.SpectralHistory(fs, n, 1)
    h.push_signal(np.random.default_rng(0).standard_normal(3 * fs) * 0.1)
    limit = math.ceil(C.MAX_ROI_SECONDS * fs / S.hop(n))
    cap = C.capture(h, C.CaptureRequest(h.epoch, 10, 10 + limit - 1, 20.0, fs / 2))
    assert cap.frames.shape[0] == limit
    with pytest.raises(C.CaptureRejected) as e:
        C.capture(h, C.CaptureRequest(h.epoch, 10, 10 + limit, 20.0, fs / 2))
    assert e.value.code == "TOO_LONG"
