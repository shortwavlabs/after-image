# SPDX-License-Identifier: AGPL-3.0-only
"""Rolling complex history and ROI capture semantics (DSP-ARCHITECTURE 4, 5).

This models the *semantics* of the realtime ring (frame IDs, epochs, expiry,
validation, masks). It is not a lock-free or bounded-work implementation.
"""
import math
from dataclasses import dataclass

import numpy as np

from .stft import hop, window

HISTORY_SECONDS = 6.0
VISIBLE_SECONDS = 4.0
MIN_ROI_SECONDS = 0.20
MAX_ROI_SECONDS = 1.50
MIN_BINS = 3


class CaptureRejected(Exception):
    """A capture request that must be refused. `code` is machine-readable."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def history_capacity(fs, N, seconds=HISTORY_SECONDS):
    return math.ceil(seconds * fs / hop(N)) + 2


def frames_for_interval(t0_s, t1_s, fs, N):
    """Frame IDs whose window centre (end_sample - N/2) lies in [t0, t1] seconds."""
    H = hop(N)
    first = math.ceil((t0_s * fs + N / 2) / H) - 1
    last = math.floor((t1_s * fs + N / 2) / H) - 1
    return first, last


def frequency_mask(N, fs, low_hz, high_hz, feather_oct):
    """Per-bin gain: 1 inside [low, high], raised-cosine in log-frequency outside.

    The feather extends `feather_oct` octaves *outside* each edge. low_hz <= 0
    keeps everything down to and including DC; high_hz >= fs/2 keeps Nyquist.
    Otherwise DC is always 0.
    """
    f = np.arange(N // 2 + 1) * fs / N
    lf = np.log2(np.maximum(f, 1e-9))
    m = np.ones_like(f)
    if low_hz > 0:
        d = np.log2(low_hz) - lf  # octaves below the low edge
        m *= 1.0 if feather_oct <= 0 else 0.5 + 0.5 * np.cos(np.pi * np.clip(d / feather_oct, 0, 1))
        if feather_oct <= 0:
            m[f < low_hz] = 0
        m[0] = 0
    if high_hz < fs / 2:
        d = lf - np.log2(high_hz)
        if feather_oct <= 0:
            m[f > high_hz] = 0
        else:
            m *= 0.5 + 0.5 * np.cos(np.pi * np.clip(d / feather_oct, 0, 1))
    return m


def time_mask(n_frames, feather_frames):
    """Raised-cosine fade over `feather_frames` frames at each end, never zero."""
    m = np.ones(n_frames)
    n = min(int(feather_frames), n_frames // 2)
    if n > 0:
        ramp = 0.5 - 0.5 * np.cos(np.pi * (np.arange(n) + 1) / (n + 1))
        m[:n], m[-n:] = ramp, ramp[::-1]
    return m


@dataclass(frozen=True)
class CaptureRequest:
    epoch: int
    first_frame: int
    last_frame: int  # inclusive
    low_hz: float
    high_hz: float
    freq_feather_oct: float = 1 / 6
    time_feather_s: float = 0.05


@dataclass(frozen=True)
class Capture:
    """Frequency-masked complex frames plus the time mask (kept separate so each
    engine can decide how to use the temporal feather)."""
    fs: int
    N: int
    first_frame: int
    frames: np.ndarray  # (M, C, K) complex, frequency mask applied
    freq_mask: np.ndarray  # (K,)
    time_mask: np.ndarray  # (M,)
    low_hz: float
    high_hz: float

    @property
    def masked_frames(self):
        """Frames with the full M[m,k] = T[m] * F[k] mask."""
        return self.frames * self.time_mask[:, None, None]


class SpectralHistory:
    """Fixed-capacity ring of complex frames indexed by frame_id % capacity."""

    def __init__(self, fs, N, channels, dtype=np.complex64, epoch=0):
        self.fs, self.N, self.channels, self.epoch = fs, N, channels, epoch
        self.capacity = history_capacity(fs, N)
        self._frames = np.zeros((self.capacity, channels, N // 2 + 1), dtype)
        self._ids = np.full(self.capacity, -1, dtype=np.int64)
        self._win = window(N)
        self._reset_stream()

    def _reset_stream(self):
        self._ids[:] = -1
        self.next_id = 0
        self.samples_seen = 0
        self._tail = np.zeros((self.N, self.channels))  # last N input samples
        self._pending = 0  # samples since the last frame

    def reset(self):
        """prepare/reset/sample-rate change: new epoch, all old IDs become stale."""
        self.epoch += 1
        self._reset_stream()

    def push_signal(self, x):
        """Streaming analysis: emits frame m once sample (m+1)*H has arrived."""
        x = np.asarray(x, dtype=np.float64)
        x = x[:, None] if x.ndim == 1 else x
        H, i = hop(self.N), 0
        while i < len(x):
            n = min(H - self._pending, len(x) - i)
            self._tail = np.concatenate([self._tail[n:], x[i:i + n]])
            self._pending += n
            self.samples_seen += n
            i += n
            if self._pending == H:
                self._pending = 0
                slot = self.next_id % self.capacity
                self._frames[slot] = np.fft.rfft(self._tail.T * self._win, axis=-1)
                self._ids[slot] = self.next_id
                self.next_id += 1

    @property
    def latest_id(self):
        return self.next_id - 1

    @property
    def oldest_id(self):
        return max(0, self.next_id - self.capacity)

    def end_sample(self, frame_id):
        return (frame_id + 1) * hop(self.N)

    def visible_range(self):
        """(first, last) frame IDs inside the 4 s display window."""
        first = max(self.oldest_id, self.next_id - math.ceil(VISIBLE_SECONDS * self.fs / hop(self.N)))
        return first, self.latest_id

    def frame(self, frame_id, epoch):
        if epoch != self.epoch:
            raise CaptureRejected("STALE_EPOCH", f"request {epoch}, current {self.epoch}")
        if frame_id > self.latest_id:
            raise CaptureRejected("FUTURE", f"frame {frame_id} > latest {self.latest_id}")
        slot = frame_id % self.capacity
        if frame_id < 0 or self._ids[slot] != frame_id:
            raise CaptureRejected("EXPIRED", f"frame {frame_id} is no longer in the ring")
        return self._frames[slot]


def capture(history, req, min_s=MIN_ROI_SECONDS, max_s=MAX_ROI_SECONDS):
    """Validate a request and copy the ROI out of the ring, oldest frame first."""
    fs, N = history.fs, history.N
    if req.epoch != history.epoch:
        raise CaptureRejected("STALE_EPOCH", f"request {req.epoch}, current {history.epoch}")
    for v in (req.first_frame, req.last_frame):
        if not isinstance(v, (int, np.integer)):
            raise CaptureRejected("INVALID_FRAMES", "frame IDs must be integers")
    if req.first_frame > req.last_frame:
        raise CaptureRejected("INVALID_FRAMES", "first_frame > last_frame")
    vals = (req.low_hz, req.high_hz, req.freq_feather_oct, req.time_feather_s)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        raise CaptureRejected("INVALID_BAND", "non-finite frequency/feather value")
    if req.low_hz < 0 or req.high_hz > fs / 2 or req.low_hz >= req.high_hz:
        raise CaptureRejected("INVALID_BAND", f"[{req.low_hz}, {req.high_hz}] Hz at fs={fs}")
    if req.freq_feather_oct < 0 or req.time_feather_s < 0:
        raise CaptureRejected("INVALID_BAND", "negative feather")
    n = req.last_frame - req.first_frame + 1
    dur = n * hop(N) / fs
    if dur < min_s - 1e-9:
        raise CaptureRejected("TOO_SHORT", f"{dur:.3f} s < {min_s} s")
    if dur > max_s + 1e-9:
        raise CaptureRejected("TOO_LONG", f"{dur:.3f} s > {max_s} s")
    fmask = frequency_mask(N, fs, req.low_hz, req.high_hz, req.freq_feather_oct)
    if int(np.sum(fmask >= 0.5)) < MIN_BINS:
        raise CaptureRejected("TOO_FEW_BINS", f"band covers < {MIN_BINS} bins at N={N}")
    # Each header is re-checked by history.frame() immediately before its copy.
    frames = np.stack([history.frame(i, req.epoch) for i in range(req.first_frame, req.last_frame + 1)])
    tmask = time_mask(n, round(req.time_feather_s * fs / hop(N)))
    return Capture(fs, N, req.first_frame, frames * fmask.astype(frames.real.dtype), fmask, tmask,
                   req.low_hz, req.high_hz)
