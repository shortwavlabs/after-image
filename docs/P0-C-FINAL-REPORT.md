# AFTERIMAGE — P0-C Final Report: Frequency-Dependent Granular Dissolution (SPLIT)

Branch `research/p0c-frequency-dependent-cloud`, stacked on
`research/p0b-spectral-granular-cloud` (PR #3), which is stacked on
`research/p0a-spectral-feasibility` (PR #2). Both earlier PRs were still open
drafts when this branch was cut from `62a3d26`. Offline Python only.

**The author of this report is an automated agent that cannot listen to audio.**
Every number is measured; nothing here says how anything sounds. Sections marked
*hypothesis* or *provisional* are for the owner to confirm or reject by ear.

## Verdict (technical feasibility only)

| Success criterion (brief §16) | Result | Evidence |
|---|---|---|
| 1. Complementary band decomposition validated | **PASS** | masks sum to 1 exactly; bands recombine to −314 dB at five rate/FFT settings |
| 2. Lows stay coherent while highs transform | **PASS** | S1: low band still the loop (0.95–1.00 repetition), top band fully dispersed (0.00–0.04); energy between low partials 10.8 dB below CLOUD |
| 3. DISSOLVE moves bands independently without discontinuities | **PASS** | monotonic mappings; loudness steps ≤ 0.26 dB; worst crossover dip 1.27 dB (limit 1.5) |
| 4. Deterministic and bounded | **PASS** | bit-identical reruns; 0 non-finite; at most 15 of 32 grains at defaults, budgets hold under 8× overload |
| 5. P0-A and P0-B verification intact | **PASS** | their `verification.json` and `metrics.json` files regenerate byte-identical; no P0-A/P0-B source file was edited |
| 6. Reproducible blind pack against granular and multiband baselines | **PASS** | 39 blind sets, key outside the set folders |
| 7. Headroom, stereo, CPU/memory measured or bounded | **PASS** | §10, §11 |
| **Overall technical verdict** | **PASS** | |
| SPLIT is distinguishable from a conventional multiband granulator | **NOT SUPPORTED** | §8: the two renders are 0.17–0.45 dB apart in long-term third-octave spectrum and ≤ 0.26 dB in level. That is all this rests on: their transient and phase differences are measured (§5) but not judged by ear |
| Realtime feasibility | **NOT ASSESSED** | counts only; capture work is 6× P0-B's |
| Musical value | **NOT ASSESSED** | needs the owner's ears (§13) |

The engine does what was specified. The measurements also say that **nothing
about the result depends on the spectral implementation**: an ordinary crossover
feeding the same grains produces the same output to within half a decibel.

## 1. Technical implementation summary

New files only, beside the P0-A/P0-B harness in `experiments/p0-spectral-ghost/`:

| File | Purpose |
|---|---|
| `p0/split.py` | band masks, spectral and conventional decomposition, shared seam, strategies S1/S2/S3, per-band rendering |
| `p0/verify_split.py` | 15 numerical checks; 13 limits committed first |
| `p0/split_experiment.py` | listening matrix, metrics, blind pack, tables, the synthetic distorted-chord source |
| `run_p0c.py`, `experiments-p0c.json` | command line and configuration |
| `tests/test_split.py`, `tests/test_split_pipeline.py` | 25 new tests |
| `p0c-verification.json`, `p0c-manifest.json`, `p0c-metrics.json`, `p0c-python-timing.json` | committed evidence |
| `listening-notes-p0c.md` | empty template |

In one paragraph: the captured frames are split by complementary log-frequency
masks into bands. Each band gets two buffers (an amplitude-complementary one for
TRACE, a power-complementary one for CLOUD), all made periodic with one shared
seam. Each band then runs the owner-preferred equal-power TRACE/CLOUD crossfade
at its own amount, with its own grain pool, and the bands are summed. Details
and equations: `docs/P0-C-FREQUENCY-DEPENDENT-ARCHITECTURE.md`.

### Owner's P0-B blind picks, checked against the key

The PR #3 comments reconstructed the mappings without opening the key. Checked
against `renders/p0b/blind-KEY-do-not-open.json` (these six entries only):

| Set | Pick | Key says |
|---|---|---|
| guitar__long_sustain__dissolve | B | `progression_parallel` |
| drums__full_spectrum__dissolve | B | `progression_parallel` |
| guitar__long_sustain__engine | A | `cloud_guided_harmonic` |
| drums__full_spectrum__engine | C | `cloud_spectral` |
| guitar__long_sustain__onoff | B | `cloud_conventional` (unfiltered) |
| synth__upper_harmonics__onoff | C | `cloud_conventional` (unfiltered) |

All six reconstructions were correct.

## 2. Deviations from the existing architecture

| # | Decision or deviation | Reason |
|---|---|---|
| D1 | Two buffers per band (amplitude masks for TRACE, square-root masks for CLOUD) | One buffer per band leaves a hole of up to 3 dB at a crossover once neighbouring bands decorrelate. Built, measured and rejected (§12 F1). |
| D2 | Independent grain schedule per band | Needed for D1 to be power-flat. Consequence: S2 fade-low at DISSOLVE 1 is statistically, not sample-for-sample, the P0-B cloud. |
| D3 | Inside a band the transform is the **parallel** crossfade, not P0-B's structural morph | The owner preferred the parallel morph in both blind progressions. The structural morph is untouched and still available. |
| D4 | Grain budget 6 / 10 / 16 per band, 32 in total | Brief §8F: the P0-B ceiling is a total. |
| D5 | FILTERED sources use crossovers placed inside the selected band (log-thirds) | Absolute crossovers leave empty bands on narrow selections (§9). |
| D6 | Conventional baseline uses Linkwitz-Riley 4 for TRACE and Butterworth 3 for CLOUD | The same two-branch treatment as D1, so the baseline is not handicapped. Rendered for FULL sources only. |
| D7 | P0-B reference clouds are rendered without pitch, and FOCUS uses broadband weights | Brief §8D asks for no transposition as the controlled reference; a FULL source has no selection mask to guide from. |
| D8 | Added a synthetic source, `guitar_dist` | The clean guitar fixture has 0.4 % of its energy above 2 kHz, so it cannot exercise the top band. This one (tanh waveshaper, original code, no samples) has 3.5 %. It is a stand-in, not an amplifier model. |
| D9 | No new sample rates or FFT sizes in the listening pack | Brief §11. Other settings are covered numerically. |
| D10 | No P0-A or P0-B source, test, evidence or report file was modified | Only the README gained a section. |

## 3. Reproduction commands

From `experiments/p0-spectral-ghost`:

```bash
uv sync --frozen
uv run pytest -q
uv run python run_p0c.py all
uv run python run_p0c.py blind
uv run python run_p0c.py summary
```

`run.py` and `run_p0b.py` are unchanged and reproduce the earlier phases.
User-owned WAVs in `inputs/` are picked up automatically and get every SPLIT
render at their native rate (tested with a 44.1 kHz file); they stay git-ignored.
Two runs of the same commit on the same machine are byte-identical (tested).
Cross-machine identity is untested.

## 4. Test results and threshold provenance

**158 tests pass** (133 from P0-A/P0-B, unchanged, plus 25 new). **P0-C
verification: 69 PASS, 0 FAIL, 173 informational rows.**

### Provenance

The 13 limits were committed alone in `659020a`, before any SPLIT code existed,
and have not been edited. They were written from the design and two analytic
predictions (the crossover-hole formula and P0-B's +13 dB). **Every limit passed
on the first formal run**, so no algorithm was adjusted against them afterwards.
One design decision did precede that run: the two-mask scheme (D1) was adopted
because the analysis predicted the one-mask scheme would fail the 1.5 dB limit.
That prediction was then confirmed by measuring the rejected scheme.

Three PASS rows were added after review ("DISSOLVE 1 is bounded"). They compare
the measured peak with an analytic ceiling, not with a new tuned constant.

Two limits could not have failed and are reported as such: the low-partial pitch
row and the low-band part of the sideband row, because S1's lowest band is TRACE
by construction. The sideband limit was therefore placed across the whole region
below 400 Hz, including the crossover transition where grains are present.

### Thresholded results

| Check | Worst measured | Limit |
|---|---|---|
| Amplitude masks: deviation of the sum from 1 (57 configurations) | 0 | 1e-12 |
| Cloud masks: deviation of the power sum from 1 | 2.2e-16 | 1e-12 |
| Sum of TRACE bands vs source TRACE (5 rate/FFT settings, 4 fixtures; 2, 3, 5 bands; FILTERED) | −314.2 dB | −120 dB |
| Shared seam vs `engines.loop_period` | identical | −120 dB |
| Conventional crossover sum: deviation from flat magnitude | 0.0000 dB | 0.1 dB |
| Spectral bands: tone one octave past a crossover, in the wrong band (8 rows) | −94.8 dB | −60 dB |
| S2/S3 at DISSOLVE 0 vs TRACE (4 fixtures, 3 rate/FFT settings) | −314.6 dB | −120 dB |
| Level at each crossover re TRACE, 8 static settings | −1.27 dB | ±1.5 dB |
| Band amounts non-decreasing in DISSOLVE (2, 3, 4 bands) | true | true |
| Loudness step between settings 0.05 apart / range, stationary material | 0.26 / 0.96 dB | 1.0 / 3.0 dB |
| Simultaneous grains, all bands | 15 | 32 |
| Per-band budget under 8× density (6 / 10 / 16) | 6 / 10 / 16 | budget |
| S2 / S3 at DISSOLVE 1: peak re source peak | +6.1 dB | analytic ceiling +29.2 dB |
| Same seed → same hash, other seed → different | true | true |
| "Assume coherent" policy at zero spray | +0.04 dB | +0.5 dB |
| Dual-mono source through S1 / S2 / S3: mono compatibility | −0.82 dB | ≥ −3.02 dB |
| S1 vs CLOUD: reduction of energy between partials below 400 Hz | 10.8 dB | ≥ 6 dB |
| S1: lowest partial, median frequency re TRACE | 0.0001 cent | 1 cent |
| Silent capture → silent output; 0.2 s capture at N = 8192 finite | true | true |
| Invalid crossover lists refused | 7 of 7 | 7 |
| Crossover at 12 Hz, at 23.5 kHz, 2 bands, 5 bands: exact at 0, finite at 1 | true | true |

## 5. Complementary band reconstruction

| | Spectral bands | Conventional bands |
|---|---|---|
| Sum of unmodified bands vs source | −314 dB | flat to 0.0000 dB in magnitude; −1.6 dB as a waveform (all-pass) |
| Largest group delay of the sum | 0 | 2.4 ms |
| Tone one octave past a crossover, wrong band | −95 to −198 dB | −24.6 dB (LR4), −18.1 dB (Butterworth-3) |
| Click, 99 % energy duration, low / mid / high band | 6.4 / 2.7 / 0.3 ms | 3.6 / 2.8 / 0.3 ms |
| Click, share of band energy arriving **before** it | 49 / 46 / 4 % | 0 / 0 / 0 % |
| Click, sum of unmodified bands | 0 ms (exact) | 2.1 ms |

- No frequency-response holes or bumps when bands are unmodified, in either
  version. The spectral one is also phase-exact.
- **Once bands are treated differently, crossovers dip.** Adopted design: at
  most −1.27 dB (S2 keep-low at DISSOLVE 1, at 250 Hz) and −0.81 dB (S1, at
  2 kHz). The conventional baseline, given the same two-branch treatment, dips
  the same amount (−1.18 and −0.83 dB).
- **Transient smearing differs in kind.** Spectral bands ring on both sides of a
  click, so when the low band stays TRACE and the others disperse, about 3 ms of
  low-band energy precedes the click. Conventional bands never ring early but
  their sum is smeared over 2.1 ms even when nothing is processed.
- Stereo: bands are derived identically for both channels; see §10.

## 6. Low-frequency fidelity

Guitar chord, FULL source, 12 s renders. "Sidebands" is the energy below 400 Hz
that is not within 4 Hz of a known partial, relative to the partials. The
lowest string (E2, 82.4 Hz) is tracked on its own.

| Render | Sidebands (dB) | E2 frequency spread (IQR) | E2 level swing | Low / mid / high band still the loop |
|---|---:|---:|---:|---|
| TRACE | −21.6 | 0.96 cent | 5.2 dB | 1.00 / 1.00 / 1.00 |
| CLOUD (P0-B, no pitch) | −6.9 | 73 cents | 24.8 dB | −0.01 / 0.03 / −0.01 |
| SPLIT S1 | −17.6 | 0.95 cent | 5.2 dB | 0.96 / 0.72 / −0.02 |
| SPLIT S2 keep-low, D = 1 | −12.5 | 0.95 cent | 5.2 dB | 0.83 / 0.00 / −0.03 |
| SPLIT S2 fade-low, D = 1 | −7.0 | 73 cents | 24.8 dB | 0.00 / 0.02 / −0.03 |
| SPLIT S3, D = 1 | −8.8 | 48 cents | 22.5 dB | 0.02 / −0.01 / 0.02 |
| Conventional S1 | −17.1 | 1.6 cents | 5.6 dB | — |
| Conventional S3, D = 1 | −8.5 | 49 cents | 21.5 dB | — |

Measured conclusions:

- **Protecting the lows works.** S1 removes 10.8 dB of the between-partial
  energy that CLOUD adds, and leaves the lowest partial's pitch and level
  exactly as TRACE has them. The 4 dB that remains over TRACE comes from the
  crossover transition (177–354 Hz), where the mid band's grains reach.
- **Longer grains do not protect the lows.** S3 gives its low band 300 ms grains
  and less spray, and gains only 1.9 dB over CLOUD; the lowest partial still
  wanders by 48 cents and swings 22 dB. P0-B's roughness is a property of
  granulating bass at all, not of the grain length tried here.
- **The benefit is the crossover, not the spectrum.** The conventional S1 is
  within 0.5 dB of the spectral one.
- The 0.83 (not 1.00) for S2 keep-low's low band is the measurement, not the
  band: the analysis band is a brick wall at 250 Hz, which includes half of the
  crossover transition, where the fully dissolved mid band's grains are.
- No pitch drift anywhere: median frequency of the lowest partial stays within
  4 cents of TRACE in every render (the *spread* is what grows).

## 7. S1 / S2 / S3 comparison

All at 48 kHz, FULL source, no pitch. "Changed" is the level of the difference
from TRACE: how much of the ghost is no longer the loop.

| Case (energy share low / mid / high) | Render | Changed re TRACE (dB) | Low / mid / high still the loop | Ripple (dB) | Peak re TRACE (dB) |
|---|---|---:|---|---:|---:|
| guitar_dist/full_spectrum (44 / 53 / 3.5 %) | CLOUD | +3.0 | 0.00 / 0.00 / 0.00 | 6.9 | +7.6 |
| | S1 | −6.5 | 0.96 / 0.69 / 0.03 | 2.8 | +8.0 |
| | S2 keep-low, D = 1 | +0.3 | 0.86 / −0.06 / 0.00 | 4.8 | +10.6 |
| | S3, D = 1 | +3.1 | 0.01 / 0.00 / 0.00 | 6.3 | +11.5 |
| guitar/long_sustain (45 / 54 / 0.4 %) | CLOUD | +2.8 | 0.07 / 0.05 / 0.05 | 14.2 | +1.0 |
| | S1 | −7.6 | 0.98 / 0.73 / 0.04 | 12.6 | +0.8 |
| | S2 keep-low, D = 1 | +0.4 | 0.93 / 0.03 / 0.02 | 13.7 | −0.6 |
| | S3, D = 1 | +2.7 | −0.03 / 0.00 / −0.03 | 13.6 | −0.4 |
| drums/full_spectrum (83 / 2 / 15 %) | CLOUD | +3.0 | 0.02 / 0.01 / 0.00 | 36.2 | +1.2 |
| | S1 | −5.4 | 1.00 / 0.60 / 0.00 | 33.4 | −1.0 |
| | S2 keep-low, D = 1 | −4.9 | 1.00 / 0.02 / 0.00 | 35.5 | −0.9 |
| | S3, D = 1 | +2.8 | −0.01 / −0.02 / 0.00 | 29.8 | +0.8 |
| vocal/mid_band_rfc (1 / 81 / 18 %) | CLOUD | +3.0 | −0.14 / 0.02 / −0.01 | 6.5 | +5.9 |
| | S1 | −2.3 | 0.99 / 0.73 / −0.01 | 5.9 | +3.6 |
| | S2 keep-low, D = 1 | +3.0 | 0.98 / 0.05 / −0.02 | 7.8 | +4.3 |
| | S3, D = 1 | +2.9 | 0.03 / 0.02 / 0.02 | 7.3 | +2.9 |
| synth/upper_harmonics (60 / 39 / 1.4 %) | S1 | −8.6 | 0.97 / 0.73 / 0.02 | 2.8 | +1.6 |

Measured conclusions:

- **SPLIT does what the diagram says.** In S1 and S2 keep-low the low band is
  still the loop and the top band is fully dispersed, on every source.
- **S1 changes much less than CLOUD.** Only 2–9 dB below the loop level is
  altered, against +3 dB for a full cloud. On these sources most energy sits in
  the bands S1 leaves alone or half-dissolves, so S1 is closer to TRACE than to
  CLOUD by every level-based measure. Energy share understates audibility of
  the top band (hearing is most sensitive at 2–5 kHz), so this does not say S1
  is inaudible; it says the bulk of the signal is untouched.
- **What S2 keep-low retains depends entirely on where the source's energy is.**
  Drums keep 83 % of their energy as the loop (the kick); the voice keeps 1 %,
  so S2 keep-low at D = 1 is as changed as CLOUD there.
- **S3 at D = 1 measures like a cloud.** All bands lose the loop, ripple and
  peaks are cloud-like. Its per-band grain settings change stereo (§10) and
  little else that these metrics see.
- **S2's progression is band-ordered as designed**: at D = 0.5 the top band is
  gone, the mid band is half, the low band is intact (0.92 / 0.48 / 0.03 on the
  guitar).
- Loudness through DISSOLVE is flat for all three in RMS (≤ 0.26 dB per 0.05
  step, ≤ 0.96 dB over the range): the per-band crossfade is equal-power.

### S2 and S3 across DISSOLVE (guitar_dist/full_spectrum)

Low / mid / high band still the loop, and how much of the ghost has changed:

| DISSOLVE | S2 keep-low | S2 fade-low | S3 |
|---|---|---|---|
| 0.25 | 1.00 / 0.99 / 0.31, −14.7 dB | same | 0.85 / 0.85 / 0.85, −8.1 dB |
| 0.50 | 0.94 / 0.46 / 0.02, −4.3 dB | same | 0.49 / 0.47 / 0.50, −2.2 dB |
| 0.75 | 0.86 / −0.06 / 0.00, +0.3 dB | 0.66 / −0.05 / 0.00, +0.7 dB | 0.14 / 0.12 / 0.14, +1.0 dB |
| 1.00 | 0.86 / −0.06 / 0.00, +0.3 dB | 0.01 / −0.04 / 0.00, +3.0 dB | 0.01 / 0.00 / 0.00, +3.1 dB |

S2 disperses the bands in order (top first), S3 all together. **S2 keep-low has
nothing left to do above DISSOLVE 0.7**: its top and mid bands are fully
dissolved by then and its low band never moves, so the last 30 % of the control
is dead (K11).

*Hypothesis:* S1 and S2 keep-low are the candidates for "weight stays, top
shimmers". Whether the dispersed top band is audible enough over an intact low
band to matter is the first thing to listen for.

## 8. Spectral versus conventional multiband

Same crossovers, same seeds, same seam, same strategies.

| Case | S1: third-octave distance / level difference | S3: third-octave distance / level difference |
|---|---|---|
| guitar/full_spectrum | 0.45 dB / −0.08 dB | 0.40 dB / −0.07 dB |
| guitar/long_sustain | 0.38 dB / −0.03 dB | 0.42 dB / −0.05 dB |
| guitar_dist/full_spectrum | 0.23 dB / +0.03 dB | 0.30 dB / −0.06 dB |
| drums/full_spectrum | 0.17 dB / +0.03 dB | 0.21 dB / +0.02 dB |
| synth/upper_harmonics | 0.35 dB / +0.09 dB | 0.37 dB / −0.04 dB |
| vocal/mid_band_rfc | 0.35 dB / +0.26 dB | 0.24 dB / −0.03 dB |

Low-frequency fidelity (§6), crossover dips (§5), band coherence, ripple, stereo
and peaks also agree between the two to within measurement scatter.

**Measured conclusion: they are practically indistinguishable.** The yardstick
is the same engine rendered with a different random seed, which differs from
itself by 0.24–1.62 dB in the same measure. In 11 of the 12 comparisons above,
changing the implementation moves the result less than changing the seed does
(the exception is S1 on the synth pad: 0.35 dB against 0.24 dB). The real
differences are not in the steady sound:

| | Spectral | Conventional |
|---|---|---|
| DISSOLVE 0 equals the full-band TRACE | exactly | in spectrum only (phase differs) |
| Band isolation | ≤ −95 dB | −18 to −25 dB per octave |
| Transients | symmetric ringing, a few ms of pre-echo in low bands | no pre-echo, 2 ms all-pass smear |
| Capture-time work | 6× P0-B's inverse FFTs | a few dozen biquads over the selection |
| Reuses the existing capture frames | yes | needs the time-domain selection |

S1 and S2 are, structurally, the P0-B parallel morph with a crossover in front
(architecture §6). Nothing in them uses the spectrum beyond filtering. This is
the same finding as P0-B §7, one level up: **the frequency-dependent behaviour
is real and measurable, but it is a multiband effect, not a spectral one.**

The `__implementation` blind sets let the owner test this by ear on S3, the only
strategy where the grains themselves differ by band.

## 9. FULL versus FILTERED

| Case | SOURCE, crossovers | Energy share low / mid / high | Level re FULL |
|---|---|---|---:|
| guitar/long_sustain | FULL, 250 / 2000 Hz | 0.45 / 0.54 / 0.004 | 0 dB |
| | FILTERED 350–5000 Hz, 250 / 2000 Hz | 0.003 / 0.985 / 0.013 | |
| | FILTERED, 849 / 2061 Hz (relative) | 0.82 / 0.17 / 0.012 | −4.6 dB |
| vocal/mid_band_rfc | FULL, 250 / 2000 Hz | 0.008 / 0.81 / 0.18 | 0 dB |
| | FILTERED, 849 / 2061 Hz | 0.40 / 0.43 / 0.17 | 0.0 dB |
| synth/upper_harmonics | FULL, 250 / 2000 Hz | 0.60 / 0.39 / 0.014 | 0 dB |
| | FILTERED 2–10 kHz, 250 / 2000 Hz | 0.000 / 0.24 / 0.76 | |
| | FILTERED, 3420 / 5848 Hz | 0.92 / 0.08 / 0.002 | −18.1 dB |

- Both SOURCE options work with every strategy, recombine exactly, and stay
  bounded. SOURCE filtering and SPLIT's band processing are separate stages.
- **Fixed crossovers degenerate on filtered sources**: the guitar selection
  becomes 98.5 % one band, the synth selection loses its bottom band entirely.
  SPLIT then behaves like a single-band morph. Crossovers placed inside the
  selected band avoid that.
- Consequently the FULL-versus-FILTERED blind sets compare two things at once
  (material and crossover placement). That is unavoidable if both are to have
  three populated bands; it is recorded per render in the manifest.
- FILTERED ghosts are natively quieter (−4.6 and −18.1 dB on the guitar and
  synth selections). **The blind sets compensate for that**: every file is
  level-matched, with +5.3 and +11.5 dB applied to the FILTERED renders against
  +1.0 and −6.4 dB for FULL (gains are in the manifest). The engine itself
  compensates nothing. To hear the uncompensated relationship, each band-limited
  case also has `filtered_split_s1_native.wav`, which is the FILTERED render
  with FULL's gain: it sits 4.2 dB (guitar) and 17.9 dB (synth) below
  `split_s1.wav`, as it would in a product without make-up gain.

### A possible account of the "receding" unfiltered cloud

The owner preferred the unfiltered cloud in P0-B's ON/OFF sets and described its
level as dropping. All three files in those sets shared one envelope and one RMS
match, so neither explains the difference. An A-weighted level (a rough loudness
proxy that discounts bass) does separate them. At matched RMS, in this pack:

| Case | FULL cloud, A-weighted | FILTERED cloud, A-weighted | Difference |
|---|---:|---:|---:|
| guitar/long_sustain | −35.7 dBFS | −32.3 dBFS | FULL 3.4 dB lower |
| synth/upper_harmonics | −36.8 dBFS | −29.5 dBFS | FULL 7.4 dB lower |
| vocal/mid_band_rfc | −30.7 dBFS | −30.7 dBFS | none |

A full-band ghost carries bass that counts fully toward RMS and little toward
loudness, so RMS matching leaves it quieter to the ear than a band-limited one.
*Hypothesis:* that offset is what was heard as the unfiltered cloud sitting
further back. It is a property of comparing at equal RMS, not of the engine, and
nothing here changes it.

## 10. Headroom, stereo and aliasing

No limiter or compressor anywhere. Floating-point output, peaks as measured.

### Headroom: four policies against P0-B's coherent buildup

Three buffers (noise, guitar, 82 Hz tone) × three dense settings × five spray
values. RMS relative to the source buffer.

| Policy | Loudest case | Quietest case | Verdict |
|---|---|---|---|
| None (law told "decorrelated") | +13.0 dB RMS, +13.2 dB peak | −0.9 dB | unsafe |
| Coherence from spray, 5 ms knee | **+10.6 dB** (82 Hz tone), +4.7 dB (guitar) | −10.7 dB (noise) | unsafe for bass |
| Coherence from spray, 50 ms knee | +0.6 dB | −13.3 dB (noise), −8.3 dB (guitar) | safe, costs level |
| Assume coherent | +0.04 dB | −13.9 dB | safe, costs most level |
| Fixed reservation | needs 13.2 dB of headroom | — | safe, costs nothing in level but 13 dB of range |

- A spray-based rule cannot be right for every sound: noise decorrelates after
  one sample of spray, an 82 Hz tone only after several milliseconds.
- SPLIT's defaults avoid the problem (every cloud uses ≥ 50 % spray): measured
  SPLIT RMS is within −0.25 to +0.20 dB of TRACE at every setting.
- A second coherent case: at small spray a band's cloud correlates with its own
  TRACE, and the equal-power pair sums to +3.0 dB at half dissolve (+1.0 dB at
  5 ms spray, 0 dB at full spray).
- **Crest factor is the practical headroom cost.** At equal RMS, SPLIT peaks
  +0.7 to +6.1 dB above TRACE on the clean guitar and **+8 to +12 dB on the
  distorted chord**, whose loop is nearly a square wave (crest about 1 dB): any
  scrambling of phase raises its peaks. After level matching the highest render
  peak in the pack is −5.78 dBFS and the highest BODY + GHOST mix is −3.31 dBFS.

### Stereo

| | Mono compatibility | Correlation |
|---|---|---|
| Dual-mono source: S1 / S2 keep / S2 fade / S3 | −0.53 / −0.58 / −0.58 / −0.82 dB | 0.77 / 0.75 / 0.75 / 0.66 |
| Guitar, S1: source → render | −0.35 → −0.41 dB | 0.85 → 0.80–0.83 |
| Guitar, S1: low band only | | 0.894 → 0.886 |
| Guitar, S3: low band only | | 0.894 → 0.852 |
| Guitar, P0-B CLOUD (listening-pack selection) | −0.30 → −0.86 dB | 0.87 → 0.58–0.68 |
| Wide synth pad, S1 and S3 | −3.32 → −3.33 dB | unchanged |

SPLIT keeps the low end's stereo image where the source had it (S1 exactly, S3
within 0.04), and widens less than CLOUD overall because less of the signal is
granulated. No drift between the first and last second beyond 0.10.

### Aliasing (P0-B K7, now tested)

| Test | Result |
|---|---|
| +12 st: 5 kHz tone → 10 kHz | −0.0 dB (correct) |
| +12 st: 15 kHz tone → should be 30 kHz | **appears at 18 kHz at −0.0 dB**: full-level alias |
| +7 st and +0.15 st: 15 kHz tone | not aliased; −1.2 dB from the interpolator |
| Share of the top band above 12 kHz (aliases at +12 st) | drums 29 %; guitar, voice, synth, 0 % |
| Top band with octave jumps: energy landing below the 2 kHz crossover | 0.8–5.5 % |

The P0-B interpolator provides **no** anti-aliasing: content above a quarter of
the sample rate folds back at full level when transposed up an octave. On the
synthetic guitar, voice and pad that content does not exist, so the octave
variant in the pack is clean; on the drums (hats and noise) 29 % of the top band
would fold. Downward octave jumps put up to 5.5 % of the top band's energy into
the mid band's range. Restricting pitch to the top band keeps the low end
stable by construction (its grains, where it has any, are never transposed).

Measured band levels barely move between no pitch, detune and octaves (within
0.4 dB), so these metrics cannot say whether pitch adds value. That is a
listening question (`__pitch` sets).

## 11. CPU and memory estimates

**Counts, not measurements. No realtime claim.** Python timings are in
`p0c-python-timing.json` and mean nothing for C++.

| | P0-B CLOUD | SPLIT, 3 bands, spectral | SPLIT, 3 bands, conventional |
|---|---|---|---|
| Capture inverse FFTs (stereo, max selection) | 138–150 | 828–900 | 0 for the bands |
| Capture filter work | — | — | 40 biquad sections × 66 k–145 k samples |
| Per-voice buffers | 0.51–1.11 MiB | 3.05–6.66 MiB | 3.05–6.66 MiB |
| Band buffers | 1 | 6 (3 TRACE + 3 CLOUD) | 6 |
| Grain pools | 1 × 32 | 3, budgets 6 / 10 / 16 = 32 | same |
| Max concurrent grains | 32 | 32 total; 10–15 at defaults | same |
| Steady state at the ceiling, 48 kHz | 12.3 M taps/s | 12.6 M taps/s (adds 3 TRACE readers) | same |
| Added latency | 2 hops | 2 hops | 2 hops |

- **Steady-state cost is P0-B's**, because the grain budget is shared, not
  multiplied. Multiplying it by three would triple the 12.3 M taps/s ceiling
  for no measured benefit: the defaults use 15 grains.
- **SPLIT's cost is at capture**: six times the inverse FFTs and six times the
  buffer memory. P0-B already identified the capture burst as the main realtime
  risk, and PR #2's guidance was to spread it over hops. Six times the work
  means either six times the wait before the ghost can sound, or a conventional
  crossover for the bands.
- Preparation: one seam search, shared by all buffers (unchanged from P0-B).
- Crossfade cost: two gains per band per sample.
- Small-host-buffer worst case: 96 kHz, N = 8192, capture of six band buffers
  in progress (900 inverse 8192-point FFTs if unscheduled), 32 grains active.

## 12. Failed approaches and known defects

### Failed or rejected

| # | What was tried | What happened |
|---|---|---|
| F1 | One buffer per band, one shared grain schedule | Crossover hole when neighbouring bands differ: −2.66 dB at 250 Hz (S2 keep-low, D = 1), −2.91 and −2.89 dB at both crossovers (S3, D = 1). Predicted before building, then measured. Replaced by D1/D2. Kept as `naive=True`. |
| F2 | Gain policy "coherent until 5 ms of spray" | +10.6 dB on an 82 Hz tone and +4.7 dB on the guitar at 5 ms spray. A 50 ms knee is safe but drops noise by 13 dB. No spray rule fits all material. |
| F3 | Long grains to protect the lows (S3) | 1.9 dB better than CLOUD between partials; the lowest partial still spreads 48 cents. |
| F4 | Fixed crossovers on FILTERED sources | Empty bands; SPLIT degenerates (§9). |
| F5 | Clean guitar fixture as the "power chord" | 0.4 % of energy above 2 kHz. A first distorted version (waveshaper gain 12) changed that to 0.46 %, because the decaying signal sits below the knee; gain 100 gives 3.5 %. |
| F6 | SPLIT as a spectral differentiator | Not supported: a conventional crossover gives the same render (§8). |

### Known defects and limitations

| # | Item | Measured |
|---|---|---|
| K1 | Crossover dips when neighbouring bands are at different amounts | up to −1.27 dB |
| K2 | Sideband energy remains in the crossover transition | S1: 4 dB above TRACE below 400 Hz |
| K3 | Spectral bands pre-ring on transients | low band 6.4 ms, half before the click |
| K4 | Crest factor rises, most on compressed or distorted sources | up to +12 dB at equal RMS |
| K5 | No anti-aliasing on upward transposition | full-level alias above fs/4 |
| K6 | Six band buffers and six reconstructions per capture | §11 |
| K7 | Top band holds little energy on most fixtures | 0.4–18 % |
| K8 | Edge leakage (P0-B K2) | FULL-source bands: −19 to −25 dB before the seam, −61 to −64 dB after. FILTERED selections: −12.5 to −23.7 dB before, −33.7 to −48.2 dB after |
| K9 | Crossovers, width, band count, S1 amounts and S3 settings were chosen without listening | architecture §6 |
| K10 | Synthetic sources only | D8; the real-recording gate is still open |
| K11 | S2 keep-low stops changing at DISSOLVE 0.7 | §7 |

K8 in full. SPLIT does not make P0-B's edge leakage worse, and the seam
crossfade (which sits exactly where the leak is) reduces it, by an amount that
depends on how long the mask rings:

| Buffer | Leak within 20 ms of an edge, before the seam | First 20 ms after the seam | 20–80 ms after |
|---|---:|---:|---:|
| FULL source, SPLIT bands (1-octave transitions) | −19 to −25 dB | −61 to −64 dB | — |
| FILTERED 350–5000 Hz (1/6-octave feather) | −23.7 dB | −43.2 dB | −57.1 dB |
| FILTERED 1000–2000 Hz | −22.0 dB | −48.2 dB | −72.3 dB |
| FILTERED 100–200 Hz | −12.5 dB | −33.7 dB | −44.7 dB |

So the seam is an effective bounded edge guard for SPLIT's own bands and a
partial one for FILTERED selections: a narrow, low selection still carries
neighbouring audio at −34 dB at the start of its loop. P0-B's K2 is reduced, not
closed. The selection is not shortened by any of this. When bands are unmodified
their leaks cancel in the sum (−174 dB).

Not attempted: per-bin dissolve amounts (flat at crossovers with two buffers but
unusable under a moving DISSOLVE), more than five bands, structural morph inside
bands, anti-aliased transposition, live-input or feedback granulation, any
realtime mechanics.

## 13. Blind listening instructions

Renders are local and git-ignored:
`experiments/p0-spectral-ghost/renders/p0c/` (263 WAVs, 618 MB, 48 kHz float32).
The P0-B pack in `renders/p0b/` was not touched.

Score in `listening-notes-p0c.md` before opening
`renders/p0c/blind-KEY-do-not-open.json`. Files in a set have equal length and
are matched to −23 dBFS RMS over their first 2 s before the MEMORY envelope; the
gain applied to each is in `p0c-manifest.json`. `reference_roi.wav` is the
selected audio played once.

There are 39 sets. A suggested first pass of ten, about 30 minutes:

1. **`guitar_dist__full_spectrum__cloud_vs_split`** and
   **`guitar__long_sustain__cloud_vs_split`**: CLOUD, FOCUS and SPLIT S1. *Does
   one of them keep the weight of the chord while something happens on top?*
2. **`guitar_dist__full_spectrum__progression`** and
   **`drums__full_spectrum__progression`**: four 12 s journeys (the P0-B
   parallel morph you preferred, S2 keeping the lows, S2 letting them go, S3).
   *Is any of them better than the plain crossfade?*
3. **`guitar_dist__full_spectrum__strategies`**: S1, S2 keep-low and S3 at
   full dissolve.
4. **`drums__full_spectrum__implementation_s1`**,
   **`guitar_dist__full_spectrum__implementation_s1`** and
   **`guitar_dist__full_spectrum__implementation_s3`**: spectral versus
   conventional multiband. The S1 pairs are the ones that carry TRACE bands,
   where the two differ in phase and transient ringing; drums are the hardest
   case. *Can you tell them apart at all?* The long-term spectrum says no.
5. **`guitar__long_sustain__source`**: FULL versus FILTERED, same mode, level
   matched. Then compare `split_s1.wav` with `filtered_split_s1_native.wav` in
   the case folder for the uncompensated level.
6. **`guitar_dist__full_spectrum__pitch`**: none, detune, octave jumps in the
   top band only.

Then, in context: `mix_split_s1.wav` and `mix_progression_s2_keep.wav` in each
case folder (BODY + GHOST).

Things the measurements suggest listening for: whether S1's dispersed top is
audible over its intact lows; bass roughness in CLOUD versus its absence in S1;
a slight thinning around 250 Hz in S2 keep-low at full dissolve; pre-echo on
drum hits in the spectral S1; harsher peaks on the distorted chord.

## 14. Recommended product mode architecture — PROVISIONAL

**Provisional until the owner has listened. Nothing here is validated by ear.**

1. **Keep SOURCE, MODE and DISSOLVE independent**, as proposed. The measurements
   support it: SOURCE acts before the bands and never changes their behaviour.
2. **Treat SPLIT as a shape of DISSOLVE, not as a third grain engine.** S1 and
   S2 are the parallel morph applied per band. One continuous amount, "how far
   the low end lags behind the top", turns the existing parallel DISSOLVE (lag
   0) into S2 keep-low (full lag) with no new grain behaviour. It would combine
   with CLOUD or FOCUS rather than replace them. S3 would only earn a place if
   the `__strategies` sets prefer it.
3. **Choose the band implementation on cost, since it does not change the
   sound.** A conventional crossover is far cheaper at capture; the spectral one
   is phase-exact against TRACE and reuses the capture frames. This needs the
   C++ capture benchmark, not more Python.
4. **FILTERED needs crossovers that follow the selection**, or SPLIT silently
   becomes CLOUD on narrow selections. The interface should show when that
   happens.
5. **Pitch off by default; if offered, top band only, and not upward by an
   octave without an anti-alias filter.**
6. **Headroom:** keep spray away from zero in every mode, or adopt the
   50 ms-knee law and accept that noisy material gets quieter at small spray;
   reserve at least 12 dB for crest factor on compressed sources. No limiter.
7. **Do not add more modes.** If neither S1 nor S2 keep-low is preferred to the
   plain parallel morph in the blind sets, SPLIT should be dropped, and the
   product is CLOUD/FOCUS with a parallel DISSOLVE and a FULL/FILTERED source.

## 15. Verdict

**Technical: PASS** on all seven success criteria, with every limit fixed before
the engine existed and passed on the first formal run, and no earlier evidence
changed.

**Central question 1** — can the upper harmonics become a cloud while the
fundamental identity stays intact? **Measurably yes**: in S1 the low band is
still the loop, the lowest partial's pitch and level are unchanged, the
between-partial energy that CLOUD adds is reduced by 10.8 dB, and the top band
is fully dispersed. Whether that is audible and attractive is **not assessed**.

**Central question 2** — is it compelling enough to justify its complexity over
ordinary multiband granular processing? **The spectral implementation is not
justified by the sound**: a conventional multiband version measures the same.
If the behaviour is worth having, it is worth having as multiband processing;
the complexity to justify is two buffers and one grain pool per band, not the
STFT.

P0-A's and P0-B's verdicts are unchanged and not revised here.

## Unresolved decisions for the owner

1. Is SPLIT (S1 or S2 keep-low) preferred to the plain parallel morph at all?
2. If so: a third MODE, or a "low-end lag" on DISSOLVE (§14.2)?
3. Spectral or conventional bands (same sound, different cost and phase)?
4. Crossover frequencies, transition width, number of bands.
5. Pitch in the top band: none, detune, or octaves with an anti-alias filter?
6. Headroom policy: spray floor, 50 ms-knee law, or fixed reservation.
7. Is the 1.3 dB crossover dip acceptable, or should narrower bands be tried?
