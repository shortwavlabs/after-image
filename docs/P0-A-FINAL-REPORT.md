# AFTERIMAGE — P0-A Final Report: Spectral Ghost Feasibility

**Document ID:** P0A-REPORT-001  
**Date:** 2026-11-18  
**Branch:** `research/p0a-spectral-feasibility`  
**Harness:** [`experiments/p0-spectral-ghost/`](../experiments/p0-spectral-ghost/README.md)  
**Scope:** offline NumPy/SciPy research prototype only. No JUCE, no GUI, no realtime code.

> **Read this first.**
> 1. Every number below comes from committed, reproducible evidence (`verification.json`, `metrics.json`, `manifest.json`).
> 2. **Nobody has listened to the renders.** They were produced by an automated agent that cannot hear. Nothing here is a statement about sound quality, and no sonic winner is declared.
> 3. The source material is **synthetic** (deterministic stand-ins for guitar, voice, drums, synth). The roadmap's four real recordings were not available; the harness accepts user-owned WAVs for that step.
> 4. Python execution speed says nothing about realtime suitability. Section 7 gives operation counts and lists what must be measured in C++.

## Verdict (technical feasibility only)

| Area | Verdict | Basis |
|---|---|---|
| STFT/ISTFT, capture semantics, numerical safety | **PASS** | 178 of 178 thresholded checks pass, 0 fail; 107 pytest tests pass |
| Candidate A — Spectral Loop | **PASS** (numerical) | click-free seams by measurement, exact stereo, exact source copy; inherent periodicity is a musical question |
| Candidate B — Spectral Sustain | **PARTIAL** | exact on stationary tones; two measured defects on non-stationary or wide material (section 4) need a design decision |
| Distinct from conventional freeze | **PARTIAL** | measurably different behaviour, but Sustain on stationary input *is* a freeze; audible difference unverified |
| Realtime cost and memory | **NOT ASSESSED** | plausible by operation count; no C++ measurement exists |
| Musical value | **NOT ASSESSED** | requires human listening |
| **Overall** | **PARTIAL** | numerically sound and worth a listening gate; not yet evidence that the effect is compelling or realtime-safe |

---

## 1. Implementation summary and reproduction

### What was built

| Module | Purpose |
|---|---|
| `p0/stft.py` | Periodic sqrt-Hann STFT/ISTFT, H = N/4, frame `m` ↔ `end_sample = (m+1)·H`, signals `(samples, channels)`, spectra `(frames, channels, K)` |
| `p0/capture.py` | Model of the 6 s complex history ring (frame IDs, epoch, expiry), `CaptureRequest` validation with rejection codes, log-frequency and time feather masks |
| `p0/engines.py` | `freeze` (baseline), `loop` (candidate A), `sustain` (candidate B), shared MEMORY envelope and level matching |
| `p0/fixtures.py` | Four seeded synthetic stereo fixtures, 4 s each |
| `p0/metrics.py`, `p0/verify.py` | Metric definitions; numerical checks with fixed thresholds shared by pytest and `verification.json` |
| `p0/experiment.py`, `run.py` | A/B render pipeline, manifest, summary tables, blind pack, CLI |

Dependencies: Python 3.13, NumPy 2.3.4, SciPy 1.16.3, pytest 8.4.2 (dev), pinned in `pyproject.toml` and `uv.lock`. No other DSP code or audio was imported. All code is original and `AGPL-3.0-only`.

### Reproduce

```bash
cd experiments/p0-spectral-ghost
```

```bash
uv sync
```

```bash
uv run pytest -q
```

```bash
uv run python run.py all
```

```bash
uv run python run.py summary
```

```bash
uv run python run.py blind
```

`run.py all` regenerates `verification.json`, `manifest.json`, `metrics.json`, `python-timing.json` and about 0.9 GB of float32 WAVs under `renders/` (git-ignored).

**Determinism, as tested.** Two runs of the same commit on the same machine produce byte-identical manifests, metrics and WAVs (`tests/test_pipeline.py`). A clean checkout of the branch in a separate worktree (`uv sync --frozen`, `pytest`, `run.py all --no-wav`) reproduced `verification.json` and `metrics.json` exactly; only the commit SHA recorded in `manifest.json` and the wall-clock values in `python-timing.json` changed. Bit-identity across machines, operating systems or FFT/BLAS builds is **untested**.

**Threshold provenance.** The −90 dB reconstruction target comes from the brief. The other limits (0.05 Hz frequency error, 0.5 dB sine ripple, 0.1 dB level, seam-step ratio ≤ 1.25, hard-wrap control > 2) were written down after one exploratory probe of the engines had already shown approximate values. They were not derived from those values and have not been changed since, but they were not set blind. Margins are large except for the seam ratio, which is discussed in §3 A2.

### Experiment matrix actually run

- 17 ROI cases spread over 4 sources (full spectrum, narrow harmonic band, upper harmonics, short 0.25 s transient, long 1.5 s sustain, the RFC's 350 Hz–5 kHz selection).
- FFT 2048 / 4096 / 8192 at 48 kHz; plus 44.1 kHz/4096, 88.2 kHz/8192, 96 kHz/8192 on two cases.
- Engines at every FFT size: `freeze_delta`, `loop_ep80`, `loop_aligned80`, `sustain_mean`. At N = 4096 also `freeze_random`, `loop_ep30`, `loop_lin80`, `loop_aligned30`, `sustain_scan`, `sustain_mean_lock`, `sustain_mean_indep`.
- **361 ghost renders, 0 capture or engine failures, 0 non-finite.**
- Shared conditions per case: identical ROI and mask, 30 ms raised-cosine onset, T60 = 5 s, 6 s render, raw ghost RMS over its first 2 s matched to −23 dBFS before the envelope.

### Deviations from the architecture documents

| # | Deviation | Justification |
|---|---|---|
| D1 | Synthetic fixtures instead of four recorded stems | No redistributable recordings exist in the repo and none may be downloaded. `inputs/` accepts user-owned WAVs. The musical gate is therefore **not** met. |
| D2 | The 1.5 s maximum ROI is enforced as a **frame count** `ceil(1.5·Fs/H)`, not in seconds | With a seconds limit, an "exactly 1.5 s" selection was rejected or accepted depending on where its edges fell on the hop grid (6 of the 57 captures in the first full run were rejected `TOO_LONG` at 1.504–1.536 s). The frame rule matches the voice-slot sizing in DSP-ARCHITECTURE §4.2. |
| D3 | Loop ignores the capture's time feather and uses only the fully overlapped interior, `(M − 3)` hops | The ISTFT of `M` isolated frames is a faithful copy of the source only where four frames overlap. The seam crossfade replaces the time feather. |
| D4 | Third loop seam strategy `aligned` added to the two in §12 | The two fixed-end strategies produce a measurable level bump or dip that depends on seam correlation (section 3). |
| D5 | Sustain estimates frequency as the energy-weighted circular mean of the heterodyned cross-spectrum over all captured frame pairs | Same quantity as §7.1 for one pair; averaging avoids dividing by small magnitudes and gives a per-bin stability figure for free. |
| D6 | Sustain defaults to one shared frequency per bin for both channels | Centre stability; has a measured cost on wide sources (section 4). Per-channel variant kept for comparison. |
| D7 | Identity phase locking implemented as a variant | Justified by a measured artifact (section 4), per the brief. It is not the default. |
| D8 | `sustain_scan` variant added | "Interpolate magnitudes over the patch" (§7.1) read literally; cheap to compare. |
| D9 | T60 sweep (1/5/15 s) not rendered; one T60 = 5 s | The envelope is a shared post-multiply and is engine-independent. |
| D10 | MOTION and WIDTH not implemented | §12: "no MOTION first". Out of P0-A scope. |
| D11 | Level matching uses RMS, not a loudness model | No extra dependency; stated so the listener can re-trim. |
| D12 | Staged 8-frames-per-hop copy, command queues, lock-free ring not modelled | The brief asks for capture *semantics*; these are P1 items. |
| D13 | Reconstruction verified on all 12 Fs × N combinations, not only the §3.2 table | Superset. |

---

## 2. Reconstruction verification — PASS

**Metric.** `20·log10( RMS(reconstruction − reference) / RMS(reference) )` over **every** sample of the signal including the first and last (the reference zero-pads the head and emits three flush frames at the tail, so boundaries are in scope). For silence the value is the absolute error in dBFS. Target: better than −90 dB.

**Signals.** Impulses at samples 0, 1, H−1, H, N, L/2 and L−1; silence; DC; on-bin and off-bin sines; 20 Hz→0.45·Fs log chirp; white noise; decorrelated stereo; anti-phase stereo. Length `3N + 777` (not a hop multiple). All 4 sample rates × 3 FFT sizes.

| Spectrum storage | Worst case over all signals, rates, sizes | Best |
|---|---:|---:|
| complex128 | **−306.8 dB** (44.1 kHz, N = 8192, impulse at sample 1) | −313.8 dB |
| complex64 (the planned C++ format) | **−141.9 dB** (44.1 kHz, N = 8192, off-bin sine) | −144.0 dB |

Additional checks, all passing:

- Overlap-add of the window product equals 2 to within 1e-12 for all three sizes (`WOLA_GAIN = 2` is exact, not approximate).
- Lengths 0, 1, 2, 511, 1024, 2047, 8192, 8193 reconstruct at every FFT size.
- An impulse at sample `n` appears in exactly the four frames with `n < end_sample ≤ n + N`.
- On-bin sine peaks at bin `f·N/Fs` with magnitude `A·Σw/2`. The match is 2.5e-7 relative, not exact: the negative-frequency image leaks through the sqrt-Hann sidelobes. My first test assumed exactness (1e-9) and failed; the tolerance is now 1e-5 with that reason recorded in the test.
- Analysis frames equal `scipy.signal.ShortTimeFFT` (independent implementation) to 1e-9.
- Streaming analysis in odd-sized blocks equals the offline STFT.

Nothing in reconstruction required a fix to the algorithm.

**Capture model — PASS.** History capacity reproduces the §4.1/§4.2 figures (261 / 284 frames). A full-band unfeathered capture resynthesises its interior to better than −90 dB with complex64 storage. Each rejection path is tested: `STALE_EPOCH`, `EXPIRED`, `FUTURE`, `INVALID_FRAMES` (inverted, non-integer), `INVALID_BAND` (inverted, NaN, Inf, above Nyquist, negative), `TOO_SHORT`, `TOO_LONG`, `TOO_FEW_BINS`. A selection at the oldest *visible* frame is still captured correctly 1.9 s later and is rejected `EXPIRED` 2.2 s later; it never returns overwritten audio. Selection survives ring wrap.

---

## 3. Candidate A — Spectral Loop

### Method

1. WOLA-resynthesise the frequency-masked captured frames.
2. Keep the fully overlapped interior: `P = (M − 3)·H` samples.
3. Precompute one loop period of `R` samples in which the first `X` samples crossfade the material *following* the loop end into the loop start. The output is that buffer repeated, so the stream is exactly periodic and both channels share `R`, `X` and the gains.

Seam strategies: `equal_power` (sin/cos), `linear`, and `aligned` (search the loop end within 25 ms for the highest correlation ρ between the overlapped regions, then linear gains divided by `sqrt(a² + b² + 2ρab)` so expected power is constant for the measured ρ).

### Findings

**A1. Ordinary overlap-add does not give a seamless loop — confirmed, and the detector works.** A hard wrap (negative control) produces a seam step 26.8×, 7.6× and 5.3× the steepest step elsewhere in the material for a sine, two close partials and a 29-harmonic tone. The metric cannot see a hard wrap in white noise (0.53), which is expected and reported as `info`.

**A2. Crossfaded seams are no steeper than the material, by that metric.** The gated check is the 24 synthetic rows in `verification.json` (4 materials × 3 strategies × 2 crossfade lengths): worst ratio **0.995** against a limit of 1.25. The 171 loop renders of the experiment are measured but not gated: worst ratio **1.001** (`loop_ep30`). The 1.25 limit is a judgement, not a derived bound; under a strict ≤ 1.0 limit the gated rows would still pass and that one render would fail by 0.1 %.

**A3. Fixed-end crossfades change level at the seam, and the sign depends on the material.** Peak-to-peak short-time RMS, loop of a steady signal (source ripple in brackets):

| Material (source ripple) | equal-power 80 ms | linear 80 ms | aligned 80 ms |
|---|---:|---:|---:|
| sine (0.0 dB) | 2.9 dB bump (ρ = 1.00) | 0.0 dB | 0.0 dB |
| 29-harmonic tone (0.02 dB) | 2.8 dB (ρ = −0.50) | 5.5 dB dip | **0.02 dB** (ρ = 1.00) |
| white noise (0.61 dB) | 0.59 dB | 3.1 dB dip (ρ = 0.02) | 0.67 dB |
| two partials 26 Hz apart (2.5 dB) | 4.5 dB | 2.6 dB | 3.1 dB |

Equal-power is right only for uncorrelated material and linear only for correlated material. `aligned` is the only strategy within about 0.6 dB of the source on all four. On the fixtures its median seam correlation was 0.30–0.38 against −0.02–0.00 for fixed ends.

**A4. The loop is an exact copy of the source outside the crossfade.** With a unity mask, the loop between seams matches the original audio to better than −90 dB. Median level change against the ROI: +0.01 dB. This is the property the other two engines do not have.

**A5. Stereo is preserved exactly.** Centred input gives bit-identical channels; anti-phase stays at correlation −1; the wide synth pad keeps its mono compatibility within 0.3 dB at every FFT size. Early and late correlation differ by at most 0.16; because the output is exactly periodic, that is the measurement window landing on different parts of the loop, not drift.

**A6. Repetition is inherent and measurable.** The loop reproduces whatever envelope the capture had, once per period (0.06–1.4 s in these renders). Where the source decays or contains a hit, that becomes a periodic pattern:

| Case (N = 4096) | ROI ripple | Loop ripple | Period |
|---|---:|---:|---:|
| synth, full spectrum | 1.5 dB | 1.7 dB | 0.61 s |
| guitar, full spectrum (decaying) | 6.4 dB | 4.8 dB | 0.58 s |
| drums, full spectrum | 42.5 dB | 33.0 dB | 0.58 s |

On drums the Loop is a beat repeat, not a sustained voice. Whether a 5 dB sawtooth every 0.58 s on guitar reads as "texture" or "stutter" is a listening question.

**A7. Short selections lose most of their length.** The usable interior is `M − 3` hops, so a 0.25 s selection keeps 213 ms at N = 2048, 192 ms at N = 4096 and only 128 ms at N = 8192. At N = 8192 the 80 ms crossfade does not fit and falls back to 64 ms with a 64 ms period (15.6 Hz repetition). This fallback fired in 6 renders and is recorded per render (`fallback_short_xfade`). With 3 frames or fewer the engine refuses (`EngineError`), which is tested.

**A8. Transients survive.** Median crest-factor change against the ROI: −0.5 to 0.0 dB across FFT sizes.

**A9. Level matching does not bound peaks.** One Loop render reaches **+0.52 dBFS** (drums, upper harmonics, N = 8192: crest 23 dB at −23 dBFS RMS). Float WAVs hold it without clipping; a product needs an explicit headroom policy (DSP-ARCHITECTURE §1.1 already says not to promise unclipped output).

---

## 4. Candidate B — Spectral Sustain

### Method

Per bin, `ω = expected + angle( Σ_m T·X[m]·conj(X[m−1])·e^(−j·expected) )` with `expected = 2πkH/N`. Magnitude is the time-mask-weighted RMS over the capture. Phase starts from the loudest captured frame and advances by `ω` per synthesis hop (`H_s = H`). Stereo default: the sum also runs over channels, so both channels share one frequency per bin and each bin's interchannel phase is frozen.

### Findings

**B1. Frequency estimation is accurate — PASS.** 72 off-bin sines across all rates and FFT sizes. For partials at least 4 bin widths above DC (64 cases) the worst error is **7.3e-5 Hz** (limit 0.05 Hz). Below 4 bins the estimate is reported without a threshold: worst **0.037 Hz** at 1.2 bins (55 Hz, 96 kHz, N = 2048), where the negative-frequency image overlaps the main lobe.

**B2. A sustained stationary tone is reproduced essentially exactly — PASS.** Off-bin sine, 5 s sustain, five rate/size combinations: frequency error ≤ 2.1e-5 Hz, level error ≤ 0.0002 dB, envelope ripple ≤ 0.0003 dB. A 29-harmonic tone: 0.03 dB ripple, 0.0 dB level error. Plain per-bin accumulation is coherent on stationary harmonic material without phase locking.

**B3. Defect: beating on material whose pitch moves during the capture.** When a partial moves across bins (vibrato, glide), its averaged energy lands in several adjacent bins that each receive a slightly different frequency. Sustained together they beat. Ripple of the ghost against ripple of the captured audio:

| Vocal fixture (1 % vibrato + glide) | ROI ripple | `freeze_delta` | `sustain_mean` | `sustain_mean_lock` |
|---|---:|---:|---:|---:|
| narrow harmonic, N = 2048 | 5.1 dB | 4.4 dB | 8.3 dB | — |
| narrow harmonic, N = 4096 | 5.0 dB | 9.5 dB | **23.0 dB** | 0.01 dB |
| narrow harmonic, N = 8192 | 4.5 dB | 26.2 dB | **26.4 dB** | — |
| full spectrum, N = 4096 | 0.5 dB | 5.8 dB | 6.6 dB | 0.05 dB |

A 23 dB ripple on a single-harmonic selection is close to full amplitude nulls. It worsens with FFT size because the bins get narrower relative to the pitch movement. The baseline freeze has the same problem at N ≥ 4096. The per-bin stability figure predicts it: energy-weighted phase coherence is 0.88–0.90 on the vocal fixture against 0.97–0.9997 on guitar and synth.

**B4. Phase locking removes the beating and costs something else.** This is the "observable artifact" that justified trying it. Identity locking around magnitude peaks brings the vocal ripple to 0.01–0.06 dB. But across the 17 cases at N = 4096 it also lowers crest factor by a median 2.0 dB, raises the worst-case timbre distance from 9.1 to 15.3 dB, and loses level on dense material: −2.8 dB on two partials 26 Hz apart (it merges them into one), −3.9 dB on white noise, −4.1 dB on the drum fixture. Not adopted as default.

Scope of that result: it describes **this** implementation, a 5-point local-maximum peak picker with nearest-peak regions, tested on partials 2.2 bins apart at N = 4096. A finer peak picker or trough-bounded regions may separate those partials. The data do not show that phase locking in general collapses close partials.

**B5. Defect: shared-frequency stereo narrows and de-correlates wide sources.** On the hard-panned detuned synth pad (source correlation −0.07, mono compatibility −3.3 dB):

| Engine | Correlation (first s → last s) | Mono compatibility |
|---|---:|---:|
| source ROI | −0.07 | −3.3 dB |
| `loop_aligned80` | −0.01 → 0.02 | −3.2 dB |
| `sustain_mean` (shared), N = 4096 | −0.45 → −0.42 | **−5.2 dB** |
| `sustain_mean` (shared), N = 2048, narrow band | −0.75 → −0.76 | **−9.1 dB** |
| `sustain_mean_indep` (per channel), N = 4096 | 0.04 → −0.05 | −3.0 dB |

Forcing one frequency on two channels that really hold different frequencies freezes an arbitrary phase offset per bin. Per-channel estimation fixes that case but drifts on near-centred material: a centred tone with −40 dB independent noise per channel goes from correlation 0.9974 to 0.990 in 4 s (shared: 0.9998, stable), and on the guitar fixture from 0.79 to 0.46. Neither mode is right for both source types. Both keep an exactly centred source exactly centred and anti-phase at −1.

**B6. Level loss.** Median −1.4 dB against the ROI (range about −2.3 to −0.1 dB at N = 4096), because averaged magnitudes of moving partials do not sum coherently. Compensated by level matching in the renders; a product would need make-up gain.

**B7. Low-energy bins are numerically harmless.** No division by magnitude anywhere. Silent bins resolve to the bin-centre frequency with zero amplitude. A fully silent capture renders exact zeros; 1e-30-scale input and full-scale noise stay finite. More than 99.9 % of output energy stays inside the selected band in every render (minimum 0.9990).

**B8. Peaks are not bounded by the input.** A capture of full-scale uniform noise sustains at +7.5 dBFS peak before level matching. Phase relations between bins are not those of the source frame.

**B9. Transients become steady sound.** On the drum fixture `sustain_mean` turns a 42.5 dB ripple into 6.5 dB and drops crest by about 5 dB: a held noise/tone cluster. `sustain_scan` goes the other way (49 dB ripple, level −2 to −3.5 dB) and replays the hit forwards and backwards.

**B10. `sustain_scan` does not solve B3** (21 dB ripple on the vocal narrow band) and adds movement of its own (median +3.1 dB ripple over the ROI).

---

## 5. Comparison against conventional spectral freeze

Baseline `freeze_delta`: hold one frame's magnitudes; each bin keeps rotating by the phase step measured between that frame and its predecessor, per channel. This is what an ordinary spectral freeze does.

**Structural relationship (important for the novelty claim).** `sustain_mean` with a one-frame patch *is* `freeze_delta`. On a stationary sine, started from the same frame, the two outputs agree to better than −60 dB (tested). Sustain differs from freeze only through (a) averaging magnitude and frequency over the whole selection instead of one frame and (b) sharing frequency across channels. Loop is a different kind of object: it keeps time structure.


**All engines and variants, 48 kHz, N=4096**

| engine | cases | level re ROI (dB) med | ripple - ROI ripple (dB) med / max | crest - ROI crest (dB) med | timbre dist (dB) med / max | corr drift early->late max | mono-compat change (dB) worst | peak (dBFS) max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freeze_delta | 17 | -2.07 | -1.0 / +5.3 | +0.0 | 1.1 / 15.5 | 0.88 | -2.62 | -8.6 |
| loop_ep80 | 17 | +0.01 | -0.5 / +1.0 | -0.3 | 1.9 / 5.5 | 0.03 | -0.12 | -3.4 |
| loop_aligned80 | 17 | +0.01 | -0.9 / +1.6 | -0.4 | 1.0 / 5.4 | 0.16 | -0.02 | -3.4 |
| sustain_mean | 17 | -1.36 | +1.2 / +18.0 | -0.3 | 1.2 / 9.1 | 0.04 | -2.82 | -9.5 |
| freeze_random | 17 | -6.29 | +4.3 / +14.6 | +1.1 | 4.4 / 21.9 | 0.06 | -6.19 | -10.2 |
| loop_ep30 | 17 | +0.01 | -0.1 / +0.3 | -0.1 | 2.0 / 11.4 | 0.04 | -0.02 | -3.1 |
| loop_lin80 | 17 | -0.28 | -0.1 / +2.9 | -0.1 | 1.5 / 5.4 | 0.03 | -0.06 | -3.0 |
| loop_aligned30 | 17 | +0.01 | -0.4 / +0.2 | -0.1 | 2.0 / 7.4 | 0.06 | -0.06 | -3.3 |
| sustain_scan | 17 | -1.71 | +3.1 / +17.9 | +1.5 | 1.5 / 7.0 | 0.12 | -1.25 | -3.0 |
| sustain_mean_lock | 17 | -0.72 | -5.0 / -0.5 | -2.0 | 3.0 / 15.3 | 0.00 | -3.13 | -10.5 |
| sustain_mean_indep | 17 | -1.19 | -1.5 / +18.1 | -0.9 | 0.9 / 9.1 | 0.82 | -2.57 | -9.3 |

**Primary engines, 48 kHz, N=2048**

| engine | cases | level re ROI (dB) med | ripple - ROI ripple (dB) med / max | crest - ROI crest (dB) med | timbre dist (dB) med / max | corr drift early->late max | mono-compat change (dB) worst | peak (dBFS) max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freeze_delta | 17 | -2.49 | -0.7 / +18.8 | -1.3 | 1.6 / 15.1 | 0.97 | -2.54 | -9.7 |
| loop_ep80 | 17 | +0.02 | -0.4 / +1.4 | -0.5 | 1.0 / 5.1 | 0.10 | -0.02 | -3.6 |
| loop_aligned80 | 17 | +0.00 | -0.8 / +1.5 | -0.5 | 0.8 / 5.1 | 0.10 | -0.06 | -3.6 |
| sustain_mean | 17 | -1.58 | -0.2 / +4.2 | -1.3 | 1.1 / 7.5 | 0.03 | -5.84 | -10.5 |

**Primary engines, 48 kHz, N=8192**

| engine | cases | level re ROI (dB) med | ripple - ROI ripple (dB) med / max | crest - ROI crest (dB) med | timbre dist (dB) med / max | corr drift early->late max | mono-compat change (dB) worst | peak (dBFS) max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| freeze_delta | 17 | -1.54 | +0.3 / +21.7 | +0.2 | 0.9 / 9.8 | 1.05 | -2.63 | -3.3 |
| loop_ep80 | 17 | -0.11 | -0.3 / +2.7 | -0.1 | 1.0 / 8.9 | 0.04 | -0.28 | -2.3 |
| loop_aligned80 | 17 | -0.05 | -0.7 / +1.9 | -0.0 | 1.0 / 8.3 | 0.09 | -0.29 | 0.5 |
| sustain_mean | 17 | -1.35 | +1.3 / +21.9 | +1.3 | 1.3 / 15.9 | 0.07 | -1.78 | -6.7 |

**Loop seams (all renders)**

| engine | renders | click ratio max | short-xfade fallbacks | seam correlation med | period (s) min / max |
|---|---:|---:|---:|---:|---:|
| loop_ep80 | 57 | 0.933 | 3 | -0.02 | 0.064 / 1.392 |
| loop_aligned80 | 57 | 0.999 | 3 | 0.30 | 0.064 / 1.387 |
| loop_ep30 | 19 | 1.001 | 0 | 0.00 | 0.162 / 1.421 |
| loop_lin80 | 19 | 1.000 | 0 | -0.02 | 0.112 / 1.371 |
| loop_aligned30 | 19 | 0.849 | 0 | 0.38 | 0.137 / 1.410 |

Ghost renders: 361; non-finite: 0; with float32 denormals: 0; max ghost peak 0.52 dBFS; max BODY+GHOST mix peak -2.92 dBFS.

Verification rows: {'PASS': 178, 'FAIL': 0, 'info': 107}

Column meanings: *level re ROI* = raw ghost RMS against the masked source; *ripple − ROI ripple* = how much more (+) or less (−) the short-time level moves than the captured audio did; *timbre dist* = RMS difference of 1/3-octave long-term spectra (blind to time structure; with a very narrow band only one band qualifies and it reads 0); *corr drift* = change in L/R correlation between the first and last second; *mono-compat change* = against the source ROI.

What the numbers support:

| Property | `freeze_delta` | Loop (`aligned80`) | Sustain (`sustain_mean`) |
|---|---|---|---|
| Level against source (median) | −2.1 dB | 0.0 dB | −1.4 dB |
| Stereo correlation drift (worst) | **0.88–1.05**: image wanders | 0.09–0.16 | 0.03–0.07 |
| Mono compatibility change (worst) | −2.6 dB | −0.02 to −0.3 dB | −1.8 to **−5.8 dB** |
| Depends on which single frame was frozen | yes: ripple up to +18.8 dB (drum hit, N = 2048) and +21.7 dB (vocal, N = 8192) over the source | no | no (uses all frames) |
| Keeps time structure of the capture | no | yes, exactly, periodically | no |
| Beating on moving pitch | yes at N ≥ 4096 | no | yes, at least as bad |

So, numerically: Loop is clearly not a freeze. Sustain is a better-behaved freeze (stereo-stable, frame-independent, about 0.7 dB less level loss) that shares the freeze's main weakness on moving pitch and adds a stereo problem on wide sources. Whether either is *audibly* "more than spectral freeze" is the PRD's P0 gate and is unanswered.

`freeze_random` (new random phase per bin per frame) loses a median 6.3 dB and adds a median 4.3 dB of ripple; it is included for the listening comparison only.

---

## 6. Known artifacts and numerical failures

No thresholded check fails. The following are real and are not hidden by that statement.

| # | Item | Severity | Evidence |
|---|---|---|---|
| K1 | Sustain and freeze beat on vibrato/glide (up to 23–26 dB ripple on a narrow selection) | High for voice | §4 B3 |
| K2 | Shared-frequency Sustain narrows wide stereo (mono compatibility down to −9.1 dB) | High for wide pads | §4 B5 |
| K3 | Per-channel Sustain and the freeze baseline let the stereo image drift | Medium | §4 B5, §5 |
| K4 | Loop is periodic; decaying or percussive captures become a rhythmic pattern | Musical question | §3 A6 |
| K5 | Loop on a minimum-length ROI at N = 8192: 64 ms period, crossfade fallback | Medium | §3 A7 |
| K6 | Peaks exceed 0 dBFS in one render after RMS matching; Sustain peaks are not bounded by input peaks | Medium | §3 A9, §4 B8 |
| K7 | The phase-locking variant as implemented fixes K1 but removes 3–4 dB on dense material and merges partials 2.2 bins apart | Trade-off, implementation-specific | §4 B4 |
| K8 | Frequency estimate degrades below about 4 bins from DC (0.037 Hz at 1.2 bins) | Low | §4 B1 |
| K9 | A seconds-based maximum ROI rejects some exact-length selections | Fixed (D2) | §1 |

Failures encountered during development and how they were handled:

- STFT scale test expected exact equality and failed at 2.5e-7. Cause: sidelobe leakage of the negative-frequency image. The expectation was wrong; tolerance set to 1e-5 with the reason in the test.
- Two capture-rejection test cases hit a different (also correct) rejection first; the test inputs were corrected, not the validator.
- The freeze/sustain equivalence test compared outputs started from different frames; fixed to start both from the same frame.
- The first timbre-distance metric was dominated by near-empty bands (Loop scored 10 dB against the audio it copies). The metric was redefined (bands within 30 dB of total energy, 40 dB floor) before any conclusion was drawn from it.
- A level test assumed the T60 envelope removes 1–4 dB over 2 s; it removes 7.4 dB. The expectation was corrected.
- 6 of the 57 captures in the first full run were rejected `TOO_LONG` (K9). The rule was changed to a frame count (D2); a boundary test now accepts exactly `ceil(1.5·Fs/H)` frames and rejects one more at five rate/size combinations. Note that this rule change is what turned those six rejections into renders.

Limits of the evidence:

- Synthetic sources. Real distorted guitar, real voice (breath, consonants, formant noise) and real drums in a room will behave differently, most likely worse for Sustain.
- The click metric detects steps, not all audible seam artifacts (for example a timbre change across the seam).
- "Ripple" is a 50 ms RMS statistic. It cannot tell pleasant movement from an artifact.
- No metric here measures "metallic". Phase coherence is offered as a predictor, unvalidated against ears.

---

## 7. CPU and memory feasibility — estimates only

**No realtime claim is made.** The NumPy reference renders 4 s of stereo ghost in about 15 ms on an Apple M5 Max (`python-timing.json`). That figure is vectorised offline batch work and does not transfer to a per-hop callback.

### Operation counts per hop (stereo)

| Work | Transforms per hop | Other per-hop work |
|---|---:|---|
| Analysis (always on) | 2 forward real FFTs | window multiply, ring write of 2·K complex |
| Freeze or Sustain, steady state | 2 inverse | 2·K complex rotations + magnitude scale |
| Sustain during REPLACE (old + new voice) | 4 inverse | twice the above |
| Loop, steady state | **0** | buffer read, `X`-sample crossfade already baked in |
| Loop, preparation (once per IMPRINT) | 2·M inverse (up to 146 at 48 kHz / 4096, 1.5 s) | lag search ≈ lags × X × channels multiply-adds (about 9 M for 25 ms / 80 ms at 48 kHz) |
| Sustain, preparation | 0 | one pass of M·2·K complex multiply-accumulates (about 0.3 M) |

Hop period: 21.3 ms at 48 kHz/4096 and 96 kHz/8192; 10.7 ms at 48 kHz/2048; 42.7 ms at 48 kHz/8192. Analysis + Sustain is four N-point real transforms per hop in every configuration; in `N·log2 N` units per second that is 9.2 M at 48 kHz/4096 and 20.0 M at 96 kHz/8192.

Consequences for the architecture:

1. **Sustain's cost is flat; Loop's is front-loaded.** Loop needs `2·M` inverse transforms before it can sound. If done during the staged copy at 8 frames per hop, that is 16 inverse transforms in a hop that normally runs 2–4. If spread at 2 per hop, a 1.5 s selection takes about 71 hops (1.5 s) to prepare. This needs a budget decision before P1.
2. **Loop's steady state needs no FFT and no spectral voice slot**: one period of float32 stereo is at most 0.55 MiB (48 kHz) or 1.09 MiB (96 kHz) against 2.28 / 4.56 MiB for a spectral slot.
3. **Sustain can advance phase without trigonometry** by multiplying each bin by a fixed unit phasor per hop, with periodic renormalisation. Float32 drift of that recurrence is unmeasured.
4. **IMPRINT-to-ghost delay, lower bound from scheduling alone** (48 kHz / 4096): copy at 8 frames per hop takes 5 hops (107 ms) for 0.75 s and 9 hops (192 ms) for 1.5 s; then up to `N − H` samples (64 ms) until the first fully overlapped Sustain sample.

### Memory

The harness reproduces DSP-ARCHITECTURE §4.2 exactly (history + two voice slots, complex64 stereo): 12.35, 13.44, 24.69 and 26.88 MiB at 44.1, 48, 88.2 and 96 kHz. Sustain additionally needs per voice about `2·K` floats of frequency and `2·K` complex of phase state (about 50 KiB at N = 4096).

### Measurements required from the C++ implementation

- Per-hop wall time P50/P95/P99/max for: analysis; Sustain steady; Sustain during REPLACE; Loop preparation burst; staged copy of 8 frames.
- The same at host block sizes 16, 64, 128 and 1024, since all hop work lands in one callback.
- `juce::dsp::FFT` scaling and packed layout for the pinned JUCE version; reconstruction error with that backend against this reference (target −90 dB; this reference reaches −142 dB with complex64).
- Float32 phase accumulation drift over 30 s (maximum T60) against this float64 reference.
- Total RSS per instance; allocation and lock audit on the audio thread.
- Measured IMPRINT-to-first-ghost-sample latency.

---

## 8. Musical listening-test instructions

**I cannot listen to audio. All of this section is procedure; none of it is a result.**

### Setup

1. Run `uv run python run.py all`, then `uv run python run.py blind`.
2. To use real material (strongly recommended, and required to meet the roadmap gate), copy owned WAVs of distorted guitar, voice, drums and synth to `experiments/p0-spectral-ghost/inputs/` first. See `inputs/README.md` for format and for choosing selections.
3. Monitor at a fixed, moderate level on headphones and on speakers. Check mono once per case.

### What to play

| Step | Files | Question |
|---|---|---|
| 1. Orient | `renders/<source>/source_fs48000.wav`, then `…/<case>/fs48000_N4096/roi_oneshot.wav` | What was captured? |
| 2. Blind A/B/C | `renders/blind/<source>__<case>/{A,B,C}.wav` with `reference_roi.wav` | Score each before opening `KEY-do-not-open.json` |
| 3. In context | `…/fs48000_N4096/mix_freeze_delta.wav`, `mix_loop_aligned80.wav`, `mix_sustain_mean.wav` | Does the ghost sit behind the dry signal as a useful second voice? |
| 4. Seam | `loop_ep30.wav`, `loop_ep80.wav`, `loop_lin80.wav`, `loop_aligned30.wav`, `loop_aligned80.wav` | Any audible seam, bump or dip? |
| 5. Sustain variants | `sustain_mean.wav`, `sustain_mean_lock.wav`, `sustain_mean_indep.wav`, `sustain_scan.wav` | Is the beating on voice a defect? Does locking fix or flatten it? Is the synth image narrower? |
| 6. FFT size | same engine under `fs48000_N2048`, `N4096`, `N8192` | Preferred size per engine |

Cases to prioritise because the measurements flag them: `vocal/narrow_harmonic` and `vocal/full_spectrum` (K1); `synth/full_spectrum` and `synth/narrow_harmonic` (K2, check in mono); `guitar/full_spectrum` and `guitar/long_sustain` (K4); `drums/*` (K4, B9); every `short_*` case at N = 8192 (K5).

### Scoring

Record in `experiments/p0-spectral-ghost/listening-notes.md` (template provided): source recognisability, musical value as a sustained layer, seam or repetition audibility, metallic or synthetic character, transient smear, stereo stability. The criteria are those of DSP-ARCHITECTURE §7.3.

Levels: ghosts are RMS-matched before the envelope, not loudness-matched. Re-trim by ear if one engine is consistently louder.

### Decision rule (from DSP-ARCHITECTURE §12)

Choose the engine that gives an unmistakably useful ghost on guitar and at least one non-guitar source and that is distinguishable from `freeze_delta`. If both candidates sound generic or metallic, change the engine before any UI work.

---

## 9. Recommended next experiment

**P0-B: listening gate on real recordings, followed by one targeted fix chosen by its result.**

1. Supply four owned stems through `inputs/` and run the blind comparison in section 8. This is the only step that can close decision D-01 and the PRD's P0 gate. It needs no new code.
2. Then, depending on the outcome:
   - **If Loop is preferred:** test capturing three extra context frames on each side of the ROI from the history (they exist in the ring), so the usable interior equals the full selection (fixes K5); and test seam placement that avoids putting a transient inside the crossfade.
   - **If Sustain is preferred:** test a per-bin choice between shared and per-channel frequency driven by measured interchannel coherence (targets K2 and K3 together), and peak locking restricted to bins with low phase coherence (targets K1 without the level loss of K7).
   - **If neither beats freeze:** stop and revisit the sound design, as the roadmap says.
3. In parallel, a C++ micro-benchmark of the section 7 list on `juce::dsp::FFT`. It is independent of the engine choice because analysis cost is common.

The fixes in step 2 are deliberately not implemented here: stacking them before anyone has heard the baseline would be speculative.

---

## 10. Verdict

**Technical feasibility: PARTIAL.**

- **PASS** — The STFT/ISTFT reference, the capture model and all three engines are numerically sound: 178 thresholded checks pass and none fail (threshold provenance in §1); reconstruction is −142 dB with the planned float32 storage against a −90 dB target; all 361 renders are finite, denormal-free and deterministic.
- **PASS (numerical)** — Candidate A, Spectral Loop: click-free seams, exact stereo, exact copy of the source. Its open question is musical (periodicity), plus a preparation-cost decision.
- **PARTIAL** — Candidate B, Spectral Sustain: exact on stationary tones, with two measured defects (beating on moving pitch; stereo narrowing on wide sources) that have plausible but untested remedies.
- **NOT ASSESSED** — Realtime CPU, memory in a host, and IMPRINT latency. Operation counts are modest and consistent with the architecture; that is an estimate, not a measurement.
- **NOT ASSESSED** — Whether the effect is distinctive or musically compelling. No one has listened. No sonic winner is declared.

The evidence justifies proceeding to a human listening gate. It does not yet justify building the UI or declaring the concept viable as a product.

---

## Outstanding questions for the owner

1. Can four owned recordings (distorted guitar, voice, drums, synth) be supplied for P0-B?
2. Is a periodic ghost acceptable as the product's character, or must the ghost be non-repeating? This largely decides A against B before any listening.
3. Loop preparation cost: accept a burst of up to 16 inverse transforms per hop during capture, or accept longer IMPRINT latency?
4. Should the 0.20 s minimum ROI rise at N = 8192 (88.2/96 kHz), where it leaves Loop 128 ms of material?
5. Headroom policy for the ghost: document, or add a controlled safety stage?
