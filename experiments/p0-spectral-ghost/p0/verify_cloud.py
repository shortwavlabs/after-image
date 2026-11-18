# SPDX-License-Identifier: AGPL-3.0-only
"""P0-B numerical verification of the capture buffer, CLOUD engine and DISSOLVE.

Threshold provenance: every limit below was committed in its own commit before
the granular engine existed (see git history of this file), so none of them was
chosen after seeing a measurement. If a limit fails, the algorithm is changed or
the row is reported as FAIL; the constant is not edited. Rows marked "info"
have no limit. Nothing here says how a render sounds.
"""
CAPTURE_RECON_DB = -90.0       # full-band capture buffer vs the source samples of the selected region
MASK_REJECT_DB = -60.0         # tone two octaves outside the selected band, level in buffer re its source level
WINDOW_END_MAX = 1e-4          # last sample of a grain window (first sample must be exactly 0)
GRAIN_CLICK_RATIO_MAX = 1.25   # same judgement as P0-A CLICK_RATIO_MAX
GRAIN_CLICK_CONTROL_MIN = 2.0  # the rectangular-window control must be detected
PITCH_TOL_CENTS = 1.0
REVERSE_ERR_DB = -200.0        # reversed read vs time-flipped forward read of the same span
DENSITY_COUNT_TOL = 0.02       # relative error of scheduled grain count vs density * duration
OVERLAP_TOL = 0.05             # relative error of mean simultaneous grains vs density * grain duration
MONO_COMPAT_MIN_DB = -3.02     # mono source at 100 % stereo spread (analytic floor of the balance law is -3.01 dB)
DENSITY_RMS_TOL_DB = 1.5       # decorrelated cloud RMS re buffer RMS, wherever nominal overlap power >= 1
D0_ERR_DB = -120.0             # structural DISSOLVE at 0 vs the TRACE loop it is built on
DISSOLVE_STEP_MAX_DB = 1.0     # RMS change between adjacent DISSOLVE settings 0.05 apart, stationary material
DISSOLVE_RANGE_MAX_DB = 3.0    # RMS range over DISSOLVE 0..1, stationary material
