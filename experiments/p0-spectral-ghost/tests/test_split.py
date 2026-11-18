# SPDX-License-Identifier: AGPL-3.0-only
"""P0-C: band decomposition and SPLIT. The thresholded checks live in
p0.verify_split (limits fixed there before the engine existed); each must have
no FAIL row. Direct unit tests of the pieces follow."""
import numpy as np
import pytest

from p0 import fixtures
from p0 import granular as G
from p0 import metrics as Mx
from p0 import split as SP
from p0 import verify_split as V

FS, N = 48000, 4096


@pytest.mark.parametrize("check", V.CHECKS, ids=lambda c: c.__name__)
def test_verification_check_has_no_failures(check):
    rows = check()
    assert rows
    assert [r for r in rows if r["result"] == "FAIL"] == []


def test_band_masks_are_complementary_and_ordered():
    B = SP.band_masks(N, FS, [250, 2000])
    f = np.arange(N // 2 + 1) * FS / N
    assert B.shape == (3, N // 2 + 1) and np.all(B >= 0) and np.all(B <= 1)
    assert np.abs(B.sum(axis=0) - 1).max() < 1e-12
    assert B[0, f < 170].min() == 1.0 and B[2, f > 2900].min() == 1.0  # flat outside the one-octave transitions
    k = np.argmin(np.abs(f - 250))
    assert abs(B[0, k] - 0.5) < 0.05 and abs(B[1, k] - 0.5) < 0.05  # equal at the crossover
    with pytest.raises(ValueError):
        SP.band_masks(N, FS, [2000, 250])


def test_relative_crossovers_sit_inside_the_selected_band():
    xo = SP.resolve_crossovers({"mode": "relative", "fractions": [1 / 3, 2 / 3]}, 350.0, 5000.0, FS)
    assert 350 < xo[0] < xo[1] < 5000
    assert abs(np.log2(xo[0] / 350) - np.log2(5000 / xo[1])) < 1e-9  # log-thirds
    assert SP.resolve_crossovers({"mode": "absolute", "hz": [250, 2000]}, 350.0, 5000.0, FS) == [250.0, 2000.0]


def test_strategy_amounts():
    s1 = [float(v) for v in SP.amounts("s1", 0.3, 3)]
    assert s1[0] == 0.0 and abs(s1[1] - 0.5 ** 1.5) < 1e-12 and s1[2] == 1.0
    keep, fade = (np.array(SP.amounts(s, np.array([0.0, 0.5, 1.0]), 3)) for s in ("s2_keep", "s2_fade"))
    assert np.array_equal(keep[:, 0], [0, 0, 0]) and np.array_equal(fade[:, 0], [0, 0, 0])  # DISSOLVE 0: all TRACE
    assert keep[2, 1] == 1.0 and keep[1, 1] == 0.5 and keep[0, 1] == 0.0  # at 0.5: high gone, mid half, low intact
    assert np.array_equal(keep[:, 2], [0, 1, 1]) and np.array_equal(fade[:, 2], [1, 1, 1])  # at 1: keep vs fade the lows
    assert all(float(v) == 0.7 for v in SP.amounts("s3", 0.7, 4))


def test_band_params_vary_with_frequency_only_in_s3_and_pitch_only_in_the_top_band():
    a = SP.band_params("s1", FS, 3, 32000, pitch="octaves")
    assert a[0].grain_s == a[1].grain_s == a[2].grain_s
    assert a[0].pitch_st == a[1].pitch_st == 0.0 and a[0].octave_prob == a[1].octave_prob == 0.0
    assert a[2].pitch_st == 0.15 and a[2].octave_prob == 0.2
    b = SP.band_params("s3", FS, 3, 32000)
    assert b[0].grain_s > b[1].grain_s > b[2].grain_s and abs(b[0].grain_s - 0.30) < 1e-3 and abs(b[2].grain_s - 0.08) < 1e-3
    assert b[0].spread < b[2].spread and b[0].reverse_prob == 0.0
    assert all(abs(q.density_hz * q.grain_s - 4) < 1e-9 for q in b)  # 4x overlap everywhere
    assert sum(SP.budgets(3)) == G.MAX_GRAINS


def test_iir_tree_band_count_and_allpass_sum():
    x = V.VC._noise(seconds=1.0, channels=1)
    bands = SP.iir_bands(x, FS, [250, 2000], "lr4")
    assert len(bands) == 3
    y = sum(bands)
    assert abs(Mx.db(Mx.rms(y) / Mx.rms(x))) < 0.05  # flat magnitude ...
    assert Mx.error_db(y, x) > -20  # ... but not the same waveform


def test_conventional_decomposition_matches_the_spectral_layout():
    dec, conv = V.decomp(fixtures.make("drums", FS), conventional=True)
    assert conv.kind == "iir" and dec.kind == "spectral" and conv.n_bands == dec.n_bands == 3
    assert all(a.shape == b.shape == dec.per_src.shape for a, b in zip(dec.trace + dec.cloud, conv.trace + conv.cloud))
    assert conv.seam is dec.seam


def test_moving_dissolve_starts_as_trace_and_uses_few_grains():
    dec = V.decomp(fixtures.make("guitar", FS))
    n = 6 * FS
    y, info = SP.render_split(dec, FS, n, "s2_keep", G.ramp(2.0, 3.0), seed=3)
    ref = V.tile(dec.per_src, n)
    assert Mx.error_db(y[:2 * FS], ref[:2 * FS]) < -120
    assert Mx.error_db(y[-FS:], ref[-FS:]) > -20
    assert info["bands"][0]["grains"] == 0 and info["bands"][0]["d_max"] == 0.0  # the low band never granulates
    assert info["max_active_total"] <= G.MAX_GRAINS and info["trace_readers"] == 3


def test_rejected_shared_schedule_design_is_a_different_render():
    dec = V.decomp(fixtures.make("synth", FS))
    a = SP.render_split(dec, FS, FS, "s2_keep", 1.0, seed=2)[0]
    b = SP.render_split(dec, FS, FS, "s2_keep", 1.0, seed=2, naive=True)[0]
    assert not np.array_equal(a, b)
