# SPDX-License-Identifier: AGPL-3.0-only
"""P0-C numerical verification of band decomposition and the SPLIT engine.

Threshold provenance: every limit below was committed in its own commit before
any SPLIT code existed (see the git history of this file). They were written
from the design and from two analytic predictions, not from measurements:
  * amplitude-complementary bands that decorrelate leave a hole of
    10*log10(1 - (1 - cos(delta_d*pi/2))/2) at the crossover centre (-3 dB at
    worst); the adopted design (power-complementary cloud bands) predicts
    -1.25 dB at worst, so CROSSOVER_HOLE_MAX_DB = 1.5 can fail;
  * the +13 dB coherent buildup measured in P0-B.
If a limit fails the algorithm is changed or the row is reported FAIL; the
constant is not edited. Rows marked "info" have no limit.
"""
MASK_SUM_TOL = 1e-12            # |sum of amplitude masks - 1| and |sum of squared cloud masks - 1|, every bin
BAND_RECON_DB = -120.0          # sum of spectral band buffers vs the source buffer
CONV_MAG_TOL_DB = 0.1           # magnitude of the summed conventional (LR4) crossover, 20 Hz - 20 kHz
ISOLATION_DB = -60.0            # spectral bands: tone one octave beyond a crossover, level in the wrong band
D0_ERR_DB = -120.0              # SPLIT at DISSOLVE 0 vs the TRACE loop of its source (spectral decomposition)
CROSSOVER_HOLE_MAX_DB = 1.5     # |1/6-octave long-term level re TRACE| at each crossover, any static SPLIT setting
DISSOLVE_STEP_MAX_DB = 1.0      # RMS change between DISSOLVE settings 0.05 apart, stationary material (as P0-B)
DISSOLVE_RANGE_MAX_DB = 3.0     # RMS range over DISSOLVE 0..1, stationary material (as P0-B)
TOTAL_GRAINS_MAX = 32           # simultaneous grains across ALL bands (the P0-B ceiling, not per band)
MONO_COMPAT_MIN_DB = -3.02      # dual-mono source through SPLIT (analytic floor of the balance law, as P0-B)
COHERENT_SAFE_DB = 0.5          # "assume coherent" gain policy: RMS re buffer at zero spray never above this
LOW_SIDEBAND_GAIN_MIN_DB = 6.0  # S1 vs unguided CLOUD: reduction of energy between partials below 400 Hz (guitar)
LOW_PITCH_TOL_CENTS = 1.0       # S1: median frequency of the lowest guitar partial re TRACE
