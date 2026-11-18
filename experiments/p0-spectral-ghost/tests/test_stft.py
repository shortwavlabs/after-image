# SPDX-License-Identifier: AGPL-3.0-only
"""STFT/ISTFT gate. Everything else depends on this passing.

Metric: RMS(recon - ref) / RMS(ref) in dB over ALL samples of the signal,
including the first and last samples (boundaries are in scope because the
reference zero-pads and emits flush frames). Silence uses absolute dBFS.
Target: better than -90 dB, both for float64 spectra and for complex64 spectra
(the eventual C++ storage format).
"""
import numpy as np
import pytest
from scipy.signal import ShortTimeFFT

from p0 import stft as S
from p0.metrics import error_db, is_finite
from p0.verify import test_signals

TARGET_DB = -90.0
GRID = [(fs, N) for fs in S.SAMPLE_RATES for N in S.FFT_SIZES]


signals = test_signals


def test_wola_gain_is_exact():
    for N in S.FFT_SIZES:
        w2 = S.window(N) ** 2
        ola = sum(np.roll(w2, i * S.hop(N)) for i in range(4))
        assert np.max(np.abs(ola - S.WOLA_GAIN)) < 1e-12


@pytest.mark.parametrize("fs,N", GRID)
@pytest.mark.parametrize("dtype", [np.complex128, np.complex64])
def test_reconstruction(fs, N, dtype):
    for name, x in signals(fs, N).items():
        X = S.stft(x, N, dtype)
        assert X.dtype == dtype and is_finite(X)
        y = S.istft(X, N, len(x))
        assert y.shape == S.as_2d(x).shape
        err = error_db(y, S.as_2d(x))
        assert err < TARGET_DB, f"{name} fs={fs} N={N} {dtype.__name__}: {err:.1f} dB"


@pytest.mark.parametrize("N", S.FFT_SIZES)
@pytest.mark.parametrize("L", [0, 1, 2, 511, 1024, 2047, 8192, 8193])
def test_boundary_lengths(N, L):
    x = np.random.default_rng(L).standard_normal(L)
    X = S.stft(x, N)
    assert X.shape == (S.num_frames(L, N), 1, N // 2 + 1)
    y = S.istft(X, N, L)
    assert y.shape == (L, 1)
    if L:
        assert error_db(y, x[:, None]) < TARGET_DB


@pytest.mark.parametrize("N", S.FFT_SIZES)
def test_frame_indexing(N):
    """An impulse at sample n appears only in frames with n < end_sample <= n + N."""
    H, n = S.hop(N), 5 * S.hop(N) + 17
    x = np.zeros(4 * N)
    x[n] = 1.0
    energy = np.sum(np.abs(S.stft(x, N)) ** 2, axis=(1, 2))
    ends = np.array([S.frame_end(m, N) for m in range(len(energy))])
    expected = (ends > n) & (ends <= n + N)
    assert expected.sum() == 4
    assert np.all(energy[expected] > 1e-6) and np.all(energy[~expected] < 1e-20)


@pytest.mark.parametrize("fs,N", GRID)
def test_bin_frequency_and_scale(fs, N):
    """On-bin sine: peak at bin k = f*N/fs with magnitude A * sum(window) / 2."""
    k = N // 16
    x = 0.5 * np.sin(2 * np.pi * (k * fs / N) * np.arange(4 * N) / fs)
    mag = np.abs(S.stft(x, N)[6, 0])  # a steady-state frame
    assert int(np.argmax(mag)) == k
    # Not exact: the negative-frequency image, 2k bins away, leaks ~2.5e-7 through
    # the sqrt-Hann sidelobes (measured). 1e-5 bounds that leakage with margin.
    assert abs(mag[k] / (0.5 * S.window(N).sum() / 2) - 1) < 1e-5


def test_matches_scipy_reference():
    """Independent cross-check of the analysis against scipy.signal.ShortTimeFFT."""
    N, H = 2048, 512
    x = np.random.default_rng(7).standard_normal(5 * N)
    ours = S.stft(x, N)[:, 0]
    sft = ShortTimeFFT(S.window(N), H, fs=1.0, fft_mode="onesided", phase_shift=None)
    ref = sft.stft(x)  # columns are slices p, centred at sample p*H
    # our frame m is centred at (m+1)*H - N/2  ->  p = m + 1 - N/(2H) = m - 1
    for m in (4, 9, 15):
        assert np.allclose(ours[m], ref[:, m - 1 - sft.p_min], atol=1e-9)
