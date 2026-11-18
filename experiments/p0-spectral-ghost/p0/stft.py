# SPDX-License-Identifier: AGPL-3.0-only
"""Reference STFT/ISTFT following DSP-ARCHITECTURE.md section 3.1.

Indexing contract (H = N/4, K = N/2 + 1):
  * frame m has end_sample = (m + 1) * H (exclusive right endpoint)
  * frame m analyses input samples [end_sample - N, end_sample), zero-padded
    before sample 0 and after the last sample
  * a signal of L > 0 samples yields M = ceil(L / H) + 3 frames, so every input
    sample is covered by exactly four frames (three of the last frames are
    "flush" frames whose end_sample lies beyond L)
  * arrays: signals are (samples, channels); spectra are (frames, channels, K)

Windows: periodic sqrt-Hann for analysis and synthesis. Their product is a
periodic Hann window whose overlap-add at H = N/4 is exactly WOLA_GAIN = 2.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

FFT_SIZES = (2048, 4096, 8192)
SAMPLE_RATES = (44100, 48000, 88200, 96000)
WOLA_GAIN = 2.0


def hop(N):
    return N // 4


def window(N):
    """Periodic sqrt-Hann."""
    return np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N))


def as_2d(x):
    x = np.asarray(x, dtype=np.float64)
    return x[:, None] if x.ndim == 1 else x


def num_frames(length, N):
    return 0 if length <= 0 else -(-length // hop(N)) + 3


def frame_end(m, N):
    """Exclusive end sample of frame m."""
    return (m + 1) * hop(N)


def stft(x, N, dtype=np.complex128):
    """(samples, channels) -> (frames, channels, K) complex spectra."""
    x = as_2d(x)
    L, C = x.shape
    H, M = hop(N), num_frames(L, N)
    if M == 0:
        return np.zeros((0, C, N // 2 + 1), dtype)
    padded = np.zeros(((M + 3) * H, C))
    padded[N - H:N - H + L] = x  # frame m reads padded[m*H : m*H + N]
    frames = sliding_window_view(padded, N, axis=0)[::H]  # (M, C, N)
    return np.fft.rfft(frames * window(N), axis=-1).astype(dtype)


def istft_buffer(X, N):
    """Weighted overlap-add of spectra. Frame m lands at buffer[m*H : m*H + N].

    Returns ((M + 3) * H, channels). Buffer index b corresponds to input sample
    b - (N - H) relative to frame 0's end_sample - H. Only buffer[N-H : M*H] is
    covered by four frames (fully overlapped); the rest is partial overlap.
    DC and Nyquist imaginary parts are discarded by the real inverse FFT.
    """
    M, C, _ = X.shape
    H = hop(N)
    td = np.fft.irfft(X, n=N, axis=-1).astype(np.float64) * (window(N) / WOLA_GAIN)
    out = np.zeros(((M + 3) * H, C))
    for m in range(M):
        out[m * H:m * H + N] += td[m].T
    return out


def istft(X, N, length):
    """Inverse of stft() for a signal of `length` samples."""
    if X.shape[0] == 0:
        return np.zeros((length, X.shape[1]))
    return istft_buffer(X, N)[N - hop(N):N - hop(N) + length]
