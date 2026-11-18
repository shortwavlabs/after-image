# AFTERIMAGE — P0-B Final Report: Spectral Granular Cloud Feasibility

Branch `research/p0b-spectral-granular-cloud`, stacked on
`research/p0a-spectral-feasibility` (PR #2, still an open draft, not merged).
Offline Python only. No plugin, GUI, presets or realtime code.

**The author of this report is an automated agent that cannot listen to audio.**
Every number below is measured; no statement here says how anything sounds.
Sections marked *hypothesis* are guesses for the owner to confirm or reject by
ear.

## Verdict (technical feasibility only)

| Success criterion (brief §16) | Result | Evidence |
|---|---|---|
| 1. Cloud engine deterministic and numerically stable | **PASS** | bit-identical reruns; 0 non-finite, 0 denormal in 86 measured renders |
| 2. Spectrally selected capture drives granular playback correctly | **PASS** | buffer = selection to −157 dB; mask rejection ≤ −66 dB |
| 3. TRACE/CLOUD transformation continuous and bounded | **PASS** | endpoints exact to −313 dB; loudness steps ≤ 0.89 dB |
| 4. A non-trivial DISSOLVE compared with a crossfade | **PASS** | structural (B) and guided (C) versus parallel (A) |
| 5. Reproducible blind listening pack | **PASS** | 16 blind sets, key kept outside the set folders |
| 6. No P0-A verification broken | **PASS** | P0-A `verification.json` and `metrics.json` regenerate byte-identical |
| **Overall technical verdict** | **PASS** | |
| Spectral selection adds something a pre-filter cannot | **NOT DEMONSTRATED** | §7: as built it is measurably equivalent to a band-pass filter in front of a granulator |
| Realtime feasibility | **NOT ASSESSED** | operation counts only (§9) |
| Musical value | **NOT ASSESSED** | needs the owner's ears (§11) |

Technical PASS means the engine does what it was specified to do. It does not
mean the result is beautiful, and one of the two central research questions
currently leans negative on the measurements (§7).

## 1. Implementation overview

Everything new lives beside the P0-A harness in `experiments/p0-spectral-ghost/`:

| File | Purpose |
|---|---|
| `p0/granular.py` | capture buffer with context frames, shared seam, grain scheduler and renderer, DISSOLVE mappings, spectral guide |
| `p0/verify_cloud.py` | 15 numerical checks, limits fixed in the first commit of the branch |
| `p0/cloud_experiment.py` | listening matrix, metrics, blind pack, summary tables |
| `run_p0b.py` | command line (`verify`, `render`, `all`, `summary`, `blind`) |
| `experiments-p0b.json` | cases, seed, render settings |
| `tests/test_granular.py`, `tests/test_cloud_pipeline.py` | 26 new tests |
| `p0b-verification.json`, `p0b-manifest.json`, `p0b-metrics.json`, `p0b-python-timing.json` | committed evidence |
| `listening-notes-p0b.md` | empty template for the owner |

The processing chain, buffer ownership, scheduler, windows, pitch, stereo and
the three DISSOLVE algorithms are described in
`docs/P0-B-SPECTRAL-GRANULAR-ARCHITECTURE.md`.

In one paragraph: a validated P0-A capture is reconstructed **once** into a
time-domain buffer covering exactly the selected region, made periodic with the
P0-A aligned seam, and then read either in order (TRACE) or by up to 32
windowed, interpolated grains (CLOUD). There is no per-grain FFT.

### Owner's P0-A blind picks, checked against the key

The four picks recorded on PR #2 were checked against the local
`renders/blind/KEY-do-not-open.json`:

| Case | Pick | Key says |
|---|---|---|
| guitar/full_spectrum | B | `loop_aligned80` |
| guitar/long_sustain | C | `loop_aligned80` |
| vocal/narrow_harmonic | B | `freeze_delta` |
| synth/full_spectrum | A | `loop_aligned80` |

The reconstructed mapping was correct: Loop 3, Freeze 1, Sustain 0. Only these
four entries were read out; the rest of the key is not reproduced here.

## 2. Architectural decisions and deviations

| # | Decision or deviation | Reason |
|---|---|---|
| D1 | `engines.loop()` was split into `loop()` + `loop_period()` | The granular engine needs the same seam on other buffers. Behaviour-preserving: all 361 P0-A render hashes are unchanged. This is the only edit to P0-A code; P0-A tests are untouched. |
| D2 | DISSOLVE's TRACE endpoint is a loop of the **full selection**, not `loop_aligned80` | The brief asks for context frames so short selections keep their material. `loop_aligned80` is still rendered as the named baseline. Measured difference: period 3.6–13 % longer (e.g. 27 963 → 31 458 samples), RMS within −0.17 to +0.59 dB. |
| D3 | A selection is defined as the M·H samples centred on its frames' window centres | Matches the duration P0-A already reports and makes "exactly the selection" testable. |
| D4 | Capture waits two hops for future context (42.7 ms at 48 kHz / N = 4096) | Needed for full overlap at the end of the selection. Without it the buffer is shortened by 1.5 hops instead (tested). |
| D5 | Grains read a **periodic** buffer modulo its length | No grain can read an unprepared edge, no clamping or grain shortening, and DISSOLVE = 0 can be exact. Cost: the first 80 ms of the buffer is a crossfade of start and end material. |
| D6 | One seam is computed on the spectral buffer and forced on the raw and IIR buffers | Otherwise the correlation search would pick different periods and the "same schedule" comparison would be confounded. |
| D7 | Overflow policy is drop-newest, not voice stealing | Click-free by construction and O(1); see architecture §3.3. |
| D8 | Gain law with a `coherence` term and a 0.75 floor | Plain power normalisation is wrong for the sequential stream at D = 0 and would boost sparse grains without bound. |
| D9 | Pitch is detune + octave jumps by default, uniform ±12 st as a variant | *Hypothesis:* octaves keep pitch class, uniform spread does not. Both are in the pack. |
| D10 | The capture's time feather is not used | The seam crossfade and the grain windows replace it. |
| D11 | The "conventional granular" baseline granulates a **frozen** capture | A commercial granular delay also has live input and feedback. That is not modelled; the baseline isolates spectral selection, not the whole product category. |
| D12 | Added a control not in the brief: `cloud_prefiltered_iir` | Spectral ON versus OFF is otherwise a filter-versus-no-filter test (§7). |
| D13 | Listening pack is 48 kHz / N = 4096 only, six P0-A cases | Brief §9 and §12: focused matrix first. Other rates and FFT sizes are covered by the numerical checks. |
| D14 | Fixtures are still synthetic | No owned recordings are in `inputs/`. The harness picks them up automatically when added. |

## 3. Reproduction

From `experiments/p0-spectral-ghost`:

```bash
uv sync --frozen
uv run pytest -q
uv run python run_p0b.py all
uv run python run_p0b.py blind
uv run python run_p0b.py summary
```

`run_p0b.py all` rewrites the four `p0b-*.json` files and `renders/p0b/`. Two
runs of the same commit on the same machine produce identical JSON and WAV
bytes (tested for the drum case in `test_cloud_pipeline.py`). Cross-machine
identity is untested, as in P0-A.

P0-A is reproduced with its own unchanged command, `uv run python run.py all`.
User-owned WAVs placed in `inputs/` are rendered automatically at their native
rate with all engines and variants; they stay git-ignored.

## 4. Numerical test results

**133 tests pass** (107 P0-A, unchanged, plus 26 new). **P0-B verification: 107
PASS, 0 FAIL, 146 informational rows.**

### Threshold provenance

All 14 limits were committed in their own commit (`5c6edd6`) before any engine
code existed. None has been edited since. One limit failed on the first run and
the **algorithm** was changed, not the limit (see §10, U1).

### Thresholded results

| Check | Worst measured | Limit |
|---|---|---|
| Capture buffer vs source, full band (5 rate/FFT combinations × 4 fixtures) | −157.6 dB | −90 dB |
| Buffer change when audio outside the context frames is replaced by noise | 0 exactly | 0 |
| Buffer vs source with noise right up to both selection edges, full band | −150.5 dB | −90 dB |
| No future context: tail trimmed 1.5 hops, remaining buffer vs source | −157.8 dB | −90 dB |
| Tone two octaves outside a 1–2 kHz band, level in buffer | −66.1 dB (N = 2048); ≤ −152 dB at N ≥ 4096 | −60 dB |
| Grain window first sample / last sample | 0 / 1.3e-5 | 0 / 1e-4 |
| Grain edge step ÷ steepest interior step (Hann, Tukey; 40 random grains each) | 0.005, 0.007 | ≤ 1.25 |
| Rectangular-window control | 338 | ≥ 2 |
| Pitch error, −12 … +12 semitones | 0.0014 cent | 1 cent |
| Reversed read vs flipped forward read | exact | −200 dB |
| Scheduled grain count vs density × time (15 settings) | within 1 grain in 2000 | ±2 % |
| Mean simultaneous grains vs density × duration | within 0.2 % | ±5 % |
| Max simultaneous grains at ceilings 8 / 16 / 32 | 8 / 16 / 31 | ≤ ceiling |
| Default cloud at ceiling 32: grains dropped | 0 | 0 |
| Silent buffer → cloud | exactly silent | exact |
| 0.2 s selection at N = 8192, 300 ms grains, ±12 st | finite, non-silent | — |
| 6-sample buffer | refused with an error | — |
| 24 clouds: non-finite renders / float32 denormals after envelope | 0 / 0 | 0 / 0 |
| Dual-mono source, spread 0 / 50 / 100 %: mono compatibility | 0.00 / −0.24 / −0.96 dB | ≥ −3.02 dB |
| Decorrelated cloud RMS vs buffer, overlap power ≥ 1 (6 settings) | −0.84 to −0.92 dB | ±1.5 dB |
| Dense cloud peak vs analytic hard bound | +0.69 dB vs +36.3 dB | ≤ bound |
| Structural D = 0 vs TRACE loop (5 materials) | −312.7 dB | −120 dB |
| Parallel D = 0 equals TRACE; D = 1 vs CLOUD | exact; −323 dB | exact; −120 dB |
| Loudness step between settings 0.05 apart, stationary material | 0.86 dB (noise), 0.09 dB (synth) | 1.0 dB |
| Loudness range over D = 0…1, stationary material | 0.95 dB (noise), 0.13 dB (synth) | 3.0 dB |
| Same seed → same schedule; other seed → different; rerender hash equal | true | true |

The −0.9 dB in the decorrelated-cloud row is not a gain-law error: it is the
interpolator's top-octave loss on white noise (§5).

## 5. Granular synthesis findings

All measured at 48 kHz.

1. **Context frames recover real material.** The buffer is 3 hops longer than
   P0-A's interior at every size (64 ms at N = 4096, 128 ms at N = 8192). For a
   0.25 s selection the loop period grows from 6912 → 8046 samples (N = 2048),
   5376 → 8045 (N = 4096) and 2304 → 7553 (N = 8192). P0-A's "short selections
   starve Loop at N = 8192" finding is largely removed.
2. **Grains at any setting are click-free and bounded.** Edge steps are 0.5 % of
   the steepest interior step.
3. **Granulation adds sidebands to low partials.** On `guitar/full_spectrum` the
   third-octave bands *between* the low string partials (63, 127 and 254 Hz)
   rise from below −33 dB in TRACE to −15…−21 dB once grains are scattered
   (D = 0.2), about 5 dB under the partials themselves. This is amplitude
   modulation by 120–200 ms windows and is inherent to time-domain grains.
   *Hypothesis:* audible as roughness or "flutter" on bass-heavy captures.
4. **A cloud fluctuates.** Envelope ripple (50 ms RMS) for steady sources rises
   from 2–5 dB (TRACE) to 7–13 dB at 4× overlap. 300 ms grains at 6/s give
   28–43 dB (audible gaps); 40 ms grains at 75/s give 5 dB on the voice.
5. **Pitch is exact but coupled to time**, and upward shifts are not
   anti-aliased. Fractional reads cost 0.9 dB RMS on white noise.
6. **Transposed grains leave the selected band.** In-band energy for the
   2–10 kHz synth selection: 1.000 with no pitch, 0.945 with the default
   detune + octaves, 0.729 with ±12 st. For the 500–620 Hz vocal selection the
   default cloud keeps 0.78 in band. The mask bounds what goes *into* the
   grains, not what comes out.
7. **The default cloud is cheap in voices.** DISSOLVE = 1 uses 5 simultaneous
   grains at most; the ceiling of 32 only matters for 300 ms grains near 100/s.

## 6. DISSOLVE comparison

Both approaches share exact endpoints. What differs is the path. Three proxies,
all computed on unprocessed output:

- **waveform**: correlation of the render with itself one loop period later
  (1 = exact loop);
- **envelope**: the same for the 20 ms RMS envelope (does the *sequence of
  events* still repeat? only meaningful when the capture has an envelope);
- **timbre**: third-octave long-term spectrum distance from the selected region.

| Case | Approach | D = 0 | 0.2 | 0.4 | 0.6 | 0.8 | 1.0 |
|---|---|---|---|---|---|---|---|
| guitar/long_sustain — waveform | structural | 1.00 | 0.02 | 0.00 | 0.00 | 0.01 | −0.03 |
| | parallel | 1.00 | 0.92 | 0.68 | 0.36 | 0.08 | −0.03 |
| guitar/long_sustain — envelope | structural | 1.00 | 0.88 | 0.83 | 0.59 | 0.21 | 0.25 |
| | parallel | 1.00 | 0.97 | 0.83 | 0.51 | 0.26 | 0.25 |
| guitar/long_sustain — timbre (dB) | structural | 3.1 | 4.5 | 3.1 | 7.7 | 9.4 | 9.7 |
| | parallel | 3.1 | 4.8 | 7.4 | 8.8 | 9.5 | 9.7 |
| drums/full_spectrum — envelope | structural | 1.00 | 0.84 | 0.64 | 0.41 | 0.01 | 0.09 |
| | parallel | 1.00 | 0.96 | 0.78 | 0.40 | 0.14 | 0.09 |
| vocal/mid_band_rfc — timbre (dB) | structural | 0.6 | 0.6 | 0.8 | 7.7 | 9.1 | 10.5 |
| | parallel | 0.6 | 5.2 | 8.1 | 9.5 | 10.3 | 10.5 |
| synth/upper_harmonics — timbre (dB) | structural | 0.1 | 0.2 | 0.2 | 11.2 | 12.3 | 15.0 |
| | parallel | 0.1 | 8.7 | 12.2 | 13.7 | 14.7 | 15.0 |

Measured conclusions:

- **The two approaches are objectively different paths.** The crossfade keeps
  the exact loop audible at reduced gain all the way (waveform 0.92 at D = 0.2)
  while the fully transposed cloud is already mixed in (timbre distance jumps at
  once). The structural version loses waveform repetition immediately, keeps the
  order of events longer, and keeps the average spectrum near the source until
  D ≈ 0.4–0.5, where octave jumps begin.
- **Most of the timbre distance at D = 1 is the pitch mapping, not the grains.**
  With pitch disabled the same cloud is 1.0 dB (voice) and 2.4 dB (guitar) from
  the selection, versus 9.4 and 8.3 dB with the default detune + octaves.
- **Loudness is continuous for both.** Largest change between settings 0.05
  apart: structural 0.09–0.89 dB across all five materials, parallel ≤ 0.07 dB.
  Range over the whole control: structural ≤ 1.36 dB (drums), parallel ≤ 0.89 dB.
  Through an 8 s moving ramp, 1 s RMS blocks change by at most 2.13 dB (drums,
  whose loop is itself uneven) and ≤ 1.01 dB elsewhere.
- **Peaks rise as structure dissolves.** At equal RMS the cloud peaks 1.2–5.8 dB
  above TRACE (§8).

*Hypothesis:* "spectrum stays, order goes" is the behaviour the brief describes
as temporal structure dissolving while harmonic identity remains. Whether it
sounds like that, or just like a granular smear arriving sooner, is the question
for the `__dissolve` blind sets.

**Approach C (spectral guide)** is compared in §7.

## 7. Spectral versus conventional granular

This is the section the brief asked to be told the truth about.

### 7.1 Spectral selection ON versus OFF

Same grains, same seed, same seam; only the buffer differs.

| Case (band) | In-band energy: spectral / IIR pre-filter / unfiltered | Timbre distance from selection (dB): spectral / IIR / unfiltered |
|---|---|---|
| guitar/long_sustain (350–5000 Hz) | 0.984 / 0.975 / 0.572 | 8.3 / 9.3 / 15.5 |
| vocal/mid_band_rfc (350–5000 Hz) | 0.986 / 0.986 / 0.979 | 9.4 / 9.6 / 10.4 |
| vocal/narrow_harmonic (500–620 Hz) | 0.779 / 0.769 / 0.113 | 24.3 / 24.6 / 25.3 |
| synth/upper_harmonics (2–10 kHz) | 0.934 / 0.842 / 0.028 | 10.4 / 13.2 / 23.7 |
| guitar/full_spectrum, drums/full_spectrum | buffers identical to −66 dB and −30 dB: **no difference by construction** | |

Measured conclusions:

- For a full-band selection the spectral path does nothing. The spectral cloud
  and the conventional cloud are the same audio.
- For a band-limited selection the spectral cloud differs from the unfiltered
  cloud exactly as a band-pass filter would make it differ, and a **4th-order
  Butterworth in front of the same granulator lands within 0.2–2.8 dB of timbre
  distance and 0–9 points of in-band energy**. The remaining difference is
  filter steepness.
- So, in this architecture, **spectral selection is a linear-phase band-pass
  filter with a time gate.** A conventional granular delay with a filter before
  it reproduces the result. The mask's only measurable advantages are steeper
  skirts (−152 dB two octaves out at N = 4096, against a 4th-order slope) and
  the fact that the band is chosen by drawing on a spectrogram.

That is a negative answer to "does the spectral representation contribute
something beyond pre-filtering" **for capture-then-granulate as built**. It does
not rule out couplings where the spectrum controls the grains (§12).

### 7.2 Spectrally guided positions (Approach C)

The guide was compared with an identical guide whose weights come from the
**unmasked** spectrum, i.e. what a broadband analysis could do without the
selection.

| Case | Weight in top 20 % of buffer (uniform = 0.20): harmonic / transient | Distance between in-band and broadband guide (0 = identical): harmonic / transient |
|---|---|---|
| guitar, full band | 0.27 / 0.41 | 0.000 / 0.003 |
| vocal, 350–5000 Hz | 0.21 / 0.32 | 0.001 / 0.000 |
| drums, full band | 0.53 / 0.84 | 0.000 / 0.001 |
| synth, 2–10 kHz | 0.21 / 0.34 | 0.017 / 0.42 |
| guitar, 2–10 kHz | 0.39 / 0.41 | 0.14 / 0.21 |
| drums, 5–16 kHz | 0.72 / 0.85 | 0.54 / 0.34 |

- On steady sources (voice, synth pad) the harmonic guide is almost uniform: it
  has nothing to choose between. Expected, and reported rather than dropped.
- On sources with events it does concentrate grains (drums: 53 % and 84 % of
  the weight in a fifth of the buffer). The rendered `cloud_guided_harmonic` on
  drums is 2.8 dB louder with 5 dB less ripple than the unguided cloud, i.e. it
  is mostly choosing the loud part of the hit.
- **The in-band guide and the broadband guide are the same guide** unless the
  band is narrow and high. On drums the two renders differ by 0.01 dB in level
  and nothing in ripple. Only for upper-band selections of percussive material
  (drums 5–16 kHz: 0.54) does the selection change where grains go.

Measured conclusion: Approach C works mechanically, but on this material it is
close to an energy-and-onset follower that a time-domain design could also
have. It has not shown a coupling that needs the spectrum.

## 8. Headroom and stereo

No limiter or compressor is used anywhere. Output is floating point and peaks
are reported as measured.

### Amplitude against density (stationary noise buffer, peak and RMS re buffer)

| Setting | Decorrelated cloud (what the gain law assumes) | Coherent worst case (zero spray and jitter) |
|---|---|---|
| 100 ms, 20 grains/s | RMS −0.9 dB, peak +2.7 dB | +1.25 dB |
| 100 ms, 100/s | RMS −0.9 dB, peak +0.6 dB | **+8.2 dB** |
| 300 ms, 20/s | RMS −0.9 dB, peak +0.8 dB | **+6.0 dB** |
| 300 ms, 100/s (31 voices) | RMS −0.9 dB, peak −0.4 dB | **+13.0 dB** |
| 20 ms, 2/s (sparse) | RMS −17.8 dB, peak −0.2 dB | — |

- Density does not build level in a decorrelated cloud: RMS is flat within
  0.1 dB from 10 to 100 grains/s once overlap power reaches 1.
- Sparse clouds get quieter instead of being boosted; single grains stay within
  +3.1 dB of the buffer peak.
- **The real headroom risk is coherence, not density.** If a user sets high
  density with no position spray, every grain reads the same instant and they
  add in amplitude: up to +13 dB at the ceiling. Telling the gain law the truth
  (`coherence = 1`) brings every row back to 0.00 dB, so the product needs the
  gain law to follow spray, or a deliberate headroom policy. This is an open
  decision, not something to hide behind a limiter.
- Analytic hard ceiling with 32 voices: +36.3 dB above the buffer peak. Never
  approached (+0.69 dB measured in the densest transposed cloud).

### Peaks in the listening pack

- At equal RMS, cloud peaks exceed TRACE peaks by +1.2 to +5.8 dB (crest factor
  rises from 6.7–17.7 dB to 11.0–19.2 dB). Largest on the voice.
- After level matching to −23 dBFS RMS, the highest render peak is −5.78 dBFS
  and the highest BODY + GHOST mix peak is −3.11 dBFS. No overs in this pack.

### Stereo

| Source | Inter-channel correlation: buffer → cloud | Mono compatibility: buffer → cloud |
|---|---|---|
| guitar | 0.87 → 0.67–0.68 | −0.30 → −0.87 dB |
| vocal (centred) | 1.00 → 0.72–0.80 | 0.00 → −0.61 dB |
| drums | 0.98 → 0.73–0.84 | −0.05 → −0.75 dB |
| synth (wide pad) | 0.02 → 0.04–0.08 | −2.93 → −2.89 dB |

- Spread widens narrow sources and leaves already-wide ones where they were.
- Mono compatibility never falls below the source's by more than 0.7 dB. P0-A's
  Sustain reached −9.1 dB on the same pad; the cloud stays at −2.9 dB.
- Correlation does not drift over time (first second versus last second within
  0.11), unlike P0-A's independent-stereo Sustain.
- An anti-phase source stays anti-phase (−0.74): the balance law cannot repair
  the input.

## 9. CPU and memory estimates

**Counts, not measurements. No realtime claim is made.** Python timings are in
`p0b-python-timing.json` and mean nothing for C++.

### Memory per voice (stereo float32, maximum 1.5 s selection)

| Rate / FFT | Capture buffer | Reconstruction scratch | Grain pool |
|---|---|---|---|
| 44.1 kHz / 4096 | 0.51 MiB | 0.56 MiB | 2 KiB |
| 48 kHz / 4096 | 0.56 MiB | 0.61 MiB | 2 KiB |
| 88.2 kHz / 8192 | 1.02 MiB | 1.13 MiB | 2 KiB |
| 96 kHz / 8192 | 1.11 MiB | 1.22 MiB | 2 KiB |

Small next to the P0-A history ring (12–27 MiB). Memory scales with sample rate
and maximum selection length, not with grain duration, density or polyphony.

### Work, by component

| Component | Cost | Scales with |
|---|---|---|
| STFT analysis | 1 forward FFT per channel per hop (unchanged from P0-A) | fs / H, N log N |
| Capture reconstruction | (M + 4) inverse FFTs per channel, once: 138–150 for a stereo maximum selection | selection length, N log N |
| Seam search | up to 1201 lags × 3840 samples at 48 kHz (2401 × 7680 at 96 kHz), once | fs² |
| Grain scheduling | per grain start: 8 random draws, 1 `pow2`, 1 `sin`/`cos`, 1 `sqrt` | density |
| Active grain rendering | per grain per sample: 8 taps, ~14 multiplies, 1 window lookup | active grains × fs |
| Stereo mix | 2 gains per grain per sample (included above) | active grains × fs |
| Modulation | D → 9 parameters, once per grain start | density |
| TRACE + CLOUD together | Approach A adds one buffer read per sample; Approach B has no separate TRACE | — |

At the ceiling: 32 grains × 4 taps × 2 channels = 12.3 M taps/s at 48 kHz and
24.6 M at 96 kHz. The default cloud uses 5 grains (1.9 M taps/s at 48 kHz).

Active grains ≈ density × grain duration, capped at 32. Cost is independent of
FFT size once the capture exists.

### Highest expected callback workload

96 kHz with N = 8192, a small host block, and all of these at once: analysis
FFTs, a capture reconstruction in progress (150 inverse 8192-point FFTs if not
spread over hops, plus the 2401-lag seam search), 32 grains transposed up an
octave (double stride through a 1.1 MiB buffer, so the worst cache behaviour),
and Approach A running TRACE alongside. The capture burst dominates; the PR #2
guidance to schedule it over several hops applies unchanged, and the seam search
now belongs in the same bounded job.

Measurements required from C++ before any realtime statement: worst-case
callback time for the 32-grain kernel at 96 kHz and 32-sample blocks; capture
job time per hop under a fixed IFFT budget; seam search time on a coarse lag
grid.

## 10. Known artifacts, limitations and unsuccessful experiments

### Artifacts and limitations

| # | Item | Measured |
|---|---|---|
| K1 | Low-partial sidebands from grain windows | bands between partials rise to −15…−21 dB (§5.3) |
| K2 | Band-limited selections contain neighbouring audio near their edges | −11 to −22 dB within 20 ms of an edge, ≤ −53 dB beyond 50 ms; low band edges ring longest. Measured by superposition with a hard time split, so the figure includes the in-band part of the split itself |
| K3 | Transposed grains leave the selected band | in-band 0.73–0.95 (§5.6) |
| K4 | Cloud level fluctuates | 7–13 dB ripple at 4× overlap on steady sources |
| K5 | Crest factor rises | cloud peaks +1.2 to +5.8 dB over TRACE at equal RMS |
| K6 | Coherent grains exceed the gain law | up to +13 dB (§8) |
| K7 | No anti-aliasing on upward transposition; interpolation dulls the top octave | 0.9 dB RMS on white noise |
| K8 | Capture waits two hops for context | 42.7–46.4 ms |
| K9 | The first 80 ms of every buffer is a crossfade of start and end material | by design (D5) |
| K10 | Loop periods are still short: every cloud draws on 0.2–1.5 s of audio | inherent to the selection limits |
| K11 | Guide weights are flat on steady sources | 0.21 of weight in the top fifth (§7.2) |
| K12 | Synthetic fixtures only; no distorted guitar, no real voice | D14 |
| K13 | The DISSOLVE mapping constants were chosen without listening | architecture §5.2 |

### Unsuccessful experiments

| # | What was tried | What happened |
|---|---|---|
| U1 | Gain law handing over from amplitude to power summation across D = 0…0.1 | **Failed its limit**: 1.52 dB loudness step on white noise (limit 1.0), because noise decorrelates on the first sample of spray. Hand-over shortened to D = 0…0.05; worst step is now 0.86–0.89 dB. Tonal sources still dip or bump by up to 0.6 dB at the first step, because how fast a sound decorrelates depends on the sound. |
| U2 | Plain power normalisation `1/√(overlap·E[w²])` | 1.25 dB low for the sequential stream and unbounded boost for sparse clouds. Replaced by D8. |
| U3 | Waveform period autocorrelation as the "temporal identity" proxy | Collapses to zero by D = 0.2 for every source, long before event order is lost. Kept in the tables, supplemented by the envelope proxy. |
| U4 | Tone-burst probe for neighbour leakage | Reported −13 dB "leak" for an out-of-band tone; it was measuring the click of the burst's own hard stop. Replaced by the superposition measurement (K2). |
| U5 | Spectral selection as a differentiator | Equivalent to a pre-filter (§7.1). |
| U6 | Spectral guide as a differentiator | Equivalent to a broadband guide except for high, narrow bands on percussive material (§7.2). |

Not attempted: voice stealing, per-grain FFT, grain-synchronous pitch (PSOLA),
feedback or live-input granulation, MOTION/WIDTH controls, any realtime
mechanics, other sample rates in the listening pack.

## 11. Listening instructions

Renders are local and git-ignored:
`experiments/p0-spectral-ghost/renders/p0b/` (160 WAVs, 383 MB, 48 kHz float32).

Setup: headphones or monitors at a fixed level; do not open
`renders/p0b/blind-KEY-do-not-open.json` until scores are written in
`listening-notes-p0b.md`. All files in a blind set have the same length and the
same −23 dBFS level window. `reference_roi.wav` in each set is the selected
capture played once.

Suggested order (about 30 minutes):

1. **`blind/*__dissolve/`** — A and B are 12 s journeys from TRACE to CLOUD
   (2 s loop, 6 s transformation, 4 s cloud; slow 12 s T60 so the change is
   audible). One is the crossfade, one is the structural dissolve. *Which one
   sounds like the sound coming apart, and which like two layers swapping?*
   Start with `guitar__long_sustain` and `drums__full_spectrum`.
2. **`blind/*__engine/`** — A/B/C among the P0-A spectral loop, the spectral
   cloud and the harmonically guided cloud. *Is any of these not "a glorified
   spectral delay"?*
3. **`blind/*__onoff/`** (band-limited cases only) — A/B/C among the spectral
   cloud, the same cloud from an ordinary band-pass filter, and the same cloud
   unfiltered. *Can the spectral one be told from the filtered one at all?*
4. Open, per case in `renders/p0b/<source>/<case>/`:
   `dissolve_000` → `dissolve_050` → `cloud_spectral` (fixed DISSOLVE settings),
   `morph_parallel_050` against `dissolve_050`, and
   `cloud_guided_harmonic` / `cloud_guided_transient` against `cloud_spectral`.
5. Character variants, `guitar/long_sustain` and `vocal/mid_band_rfc` only:
   `var_nopitch`, `var_wide_pitch`, `var_short_dense`, `var_long_sparse`,
   `var_tukey`. *Is the default pitch mapping (octave jumps) wanted at all?*
6. In context: `mix_cloud_spectral.wav` and `mix_progression_structural.wav`
   (BODY + GHOST, the ghost starts where the selection ends).

Things to listen for, from the measurements: bass roughness on
`guitar/full_spectrum` (K1); grain flutter on steady sources (K4); the repeating
0.66 s and 1.4 s periods in TRACE; whether the voice cloud reads as "choir" or
as "chopped"; whether the drum cloud is a usable texture or debris.

## 12. Recommended next phase

Decide by ear first. No new DSP until the listening notes exist.

**If the clouds are not compelling:** stop here. The measurements already say
the spectral part adds little to a granulator, so there is no hidden reserve to
optimise toward.

**If the clouds are compelling but indistinguishable from the filtered ones**
(the measurements predict this): the product is a good granular texture effect
with a spectrogram selector. That may be worth building, but the "spectral
memory" claim would rest on the interface, not the sound. Decide that knowingly.

**If something is promising, P0-C should test couplings where the spectrum
drives the grains**, one at a time, each against the P0-B cloud as control:

1. **Band-split dissolve**: DISSOLVE per frequency band, e.g. lows stay TRACE
   while highs disperse. This also removes K1. It cannot be done by a pre-filter.
2. **Pitch from the spectrum**: grain transposition chosen from intervals
   between detected partials instead of fixed octaves.
3. **Post-mask**: re-apply the selection after granulation so the ghost stays in
   its band under transposition (K3). Costs a second spectral pass.
4. **Grain length by band**: long grains for lows, short for highs.

Alongside, independent of the above: owned recordings in `inputs/` (the
real-recording gate from P0-A is still open), and a C++ micro-benchmark of the
32-grain kernel and a hop-scheduled capture job.

## 13. Verdict

**Technical: PASS.** All six success criteria are met, with every limit fixed
before the engine was written and no P0-A evidence changed.

**Central question 1** — can a sound keep its harmonic identity while its
temporal structure dissolves? Measurably, the structural DISSOLVE does that
ordering: waveform repetition goes first, event order second, average spectrum
last (and only because of the octave mapping). Whether that reads as identity
to a listener is **not assessed**.

**Central question 2** — is it something a conventional granular delay cannot
easily reproduce? **On the evidence so far, no.** A band-pass filter in front of
the same granulator measures within a few dB of it, and the spectral guide
behaves like a broadband one. The distinctive part, if there is one, is the
DISSOLVE control and the capture workflow, not the spectral processing.

P0-A's verdict is unchanged and is not revised here.

## Open technical decisions for the owner

1. Keep octave jumps in the default DISSOLVE mapping, or make the default
   pitch-free?
2. Should TRACE itself move to the full-selection loop (D2), given the extra
   42.7 ms capture wait?
3. Headroom policy for coherent dense clouds (+13 dB): tie the gain law to
   spray, cap density × duration when spray is low, or reserve headroom?
4. Polyphony ceiling 32 and drop-newest overflow: acceptable, or is voice
   stealing wanted?
5. Edge guard for band-limited selections (K2): shrink the usable region by the
   mask's ringing time, or accept?
6. Is the frozen-capture baseline (D11) a fair stand-in for "conventional
   granular delay", or should a live-input granulator with feedback be modelled
   before concluding §7?
