# AFTERIMAGE — P1-A Realtime Architecture

**Status:** design for P1-A, implemented on `feature/p1a-realtime-core`. Results and what was actually verified are in
[P1-A-QUALIFICATION.md](P1-A-QUALIFICATION.md). Product decisions come from
[RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md); where this document departs from the Python reference it says
so and why.

P1-A builds the realtime foundation: a JUCE plugin with a zero-latency BODY, the C++ STFT history and capture, the
CLOUD engine with the parallel TRACE → CLOUD DISSOLVE, bounded capture scheduling and an honest gain contract. It is
not the finished plugin: FOCUS, GLITCH, MOTION, WIDTH, presets and the production UI are out of scope.

## 1. Build and dependencies

| Item | Choice |
|---|---|
| Framework | JUCE **9.0.5**, commit `d60b7a78030661574a615b586d9325ba7a7fa7dd`, fetched by CMake `FetchContent` from the official GitHub archive with a pinned SHA-256 (`8237b297…d9f5`). Used under JUCE's AGPLv3 option. |
| Language / build | C++20, CMake ≥ 3.22 (tested with 4.4.5), Xcode 27.2 / Apple clang 21 on macOS 26.6 (arm64) |
| Formats | AU, VST3, Standalone (development). macOS only; no Windows claim until built and tested there. |
| Other targets | `afterimage_tests` (unit tests, CTest), `afterimage_render` (offline renderer for parity fixtures), `afterimage_bench` (worst-case callback benchmark). They link the plugin's shared-code target, so they test the same code the plugin runs. |
| Third-party code | JUCE only. No other library, no network access at runtime, no assets. Notices: [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md). |

The DSP lives in `plugin/Source/dsp/` and depends only on `juce_dsp` (FFT) and the standard library; the processor in
`plugin/Source/` owns parameters, state, bus layouts and the UI bridge.

## 2. Signal contract

```text
y_c[n] = body[n] * x_c[n]  +  ghost[n] * Σ_voices env_v[n] * ( cos(πD[n]/2) * trace_v,c[n] + sin(πD[n]/2) * cloud_v,c[n] )
```

- **BODY** is the input sample at the same index times a smoothed gain. At BODY = 1 and no sounding ghost it is the
  input bit for bit (a float multiply by exactly 1 and an add of exactly 0 are exact). Reported latency is **0 samples**.
- Analysis, capture and grains read the input; none of them writes to the BODY path.
- Mono → mono and stereo → stereo only; any other layout is refused by `isBusesLayoutSupported`.
- No limiter, compressor or saturation anywhere (§9).

## 3. Analysis and history (port of `p0/stft.py`, `p0/capture.py`)

| Fs | N | H = N/4 | history frames `ceil(6 Fs / H) + 2` |
|---:|---:|---:|---:|
| 44.1 / 48 kHz | 4096 | 1024 | 261 / 284 |
| 88.2 / 96 kHz | 8192 | 2048 | 261 / 284 |

- Periodic sqrt-Hann analysis and synthesis windows; WOLA gain 2 at H = N/4.
- Frame `m` analyses stream samples `[(m+1)H − N, (m+1)H)`, zero before sample 0, and is produced when sample
  `(m+1)H − 1` has been pushed. `end_sample = (m+1)H` is stored with the frame. This is the P0 contract unchanged.
- Spectra are `std::complex<float>` per channel, `K = N/2 + 1` bins, from `juce::dsp::FFT` (vDSP on macOS). The
  forward scaling equals NumPy's `rfft`; the inverse scale is calibrated once per FFT size at prepare time.
- A second ring keeps the last 6 s of **time-domain** input. FULL capture copies from it (exact, no IFFTs).
- An **epoch** counter changes on every `prepareToPlay`/reset. Requests and display columns carry it; a stale epoch is
  rejected.

## 4. Selection, capture and the loop-duration contract

### 4.1 Request

`IMPRINT(epoch, s0, s1, lowHz, highHz, source)` with `[s0, s1)` in **stream samples**, sample-exact.
SOURCE is sampled at IMPRINT time; changing it later does not alter a playing voice.

Validation (immediately, on the audio thread, constant time):

| Code | Condition |
|---|---|
| `STALE_EPOCH` | request epoch ≠ engine epoch |
| `BEFORE_STREAM` | `s0 < 0` |
| `TOO_SHORT` / `TOO_LONG` | `s1 − s0` outside [0.20 s, 1.50 s] (rounded to samples) |
| `FUTURE` | `s1` is later than the newest input sample |
| `INVALID_BAND` | non-finite, negative, `low ≥ high`, or `high > Fs/2` (FILTERED only) |
| `TOO_FEW_BINS` | the frequency mask keeps fewer than 3 bins at ≥ 0.5 (FILTERED only) |
| `EXPIRED` | audio or frames needed are no longer in the history (checked again before every copy) |
| `BUSY` | a capture is already being built (one at a time) |

### 4.2 The loop-duration contract (blocker B1)

The research loop was `selection − seam − alignment lag` long: the seam crossfade (80 ms) and a lag search (up to
25 ms) were taken **from inside** the selection, so a 1.38 s drum bar looped at 1.286 s.

P1-A contract: **the repeating period R equals the selected duration exactly, `R = s1 − s0` samples.** The seam
crossfade uses `X = round(0.08 Fs)` samples of **post-roll**, the audio that followed the selection:

```text
seg[n] = audio[s0 + n],  n ∈ [0, R + X)
loop[n] = seg[n]                                   for X ≤ n < R
loop[n] = a(n) seg[n] + b(n) seg[R + n]            for 0 ≤ n < X
a = t / g, b = (1 − t) / g, t = n / X, g = sqrt(a'² + b'² + 2 max(ρ, 0) a' b')   (P0 "aligned" gains)
ρ = correlation of seg[0, X) and seg[R, R + X), channels pooled
```

At the wrap, `loop[R − 1] = seg[R − 1]` and `loop[0] = seg[R]`: the loop continues exactly as the recording did, so
the seam is continuous without shortening the period. The P0 lag search is dropped because it changes the period.
`ρ` is reported. Reported per capture: selected samples, period samples (equal by construction), seam samples, `ρ`,
request-to-sound delay.

Consequence: a capture needs `X` samples after `s1` (FULL) or every frame overlapping `[s0, s1 + X)` (FILTERED,
i.e. up to `s1 + X + N`). If the selection ends close to "now", the capture **waits** for that audio; the wait is
at most `X + N + H` samples (≈ 190 ms at 48 kHz) and is part of the reported delay. The UI shows WAITING.

**Trade-off.** The first `X` samples of every period are a blend that ends in audio from *after* the selection. If
the selection is followed by silence or by an unrelated hit, each repeat starts with that material fading out (silence:
the loop fades in over 80 ms, ρ ≈ 0 so the gains are the equal-power-like `1/sqrt(a'² + b'²)`). The alternative,
**pre-roll** (blend the end of the period with audio from *before* `s0`), has the mirror problem at the end of each
period and fails at `s0 = 0`, where there is no pre-roll. Post-roll was chosen because a selection usually ends on
material that continues (a sustained note, the next beat). Both cases are tested (ρ ≈ 0 with silent post-roll, ρ ≈ 1
with a continuing tone); whether post-roll is the right default is a listening question.

Not covered by this contract: hop quantisation of what the user drew on a spectrogram. The request is sample-exact;
the development UI converts its drawn rectangle to samples and displays the resulting duration.

### 4.3 Capture at the start of the stream (blocker B2)

Samples before stream sample 0 are silence by definition (P0 contract). Frames overlapping `[s0, s1 + X)` all have
`m ≥ floor(s0 / H) ≥ 0`, so a selection at `s0 = 0` reads only existing frames: there is no negative index to
mishandle. A request with `s0 < 0` is rejected with `BEFORE_STREAM`. Regression tests cover `s0 = 0`, `s0 = 1` and
`s0 = H − 1`.

### 4.4 Reconstruction

- **FULL:** copy `R + X` samples per channel from the time-domain ring.
- **FILTERED:** for each frame `m` in `[floor(s0/H), floor((s1 + X − 1 + N)/H) − 1]`: multiply by the frequency mask
  (`capture.frequency_mask`, 1/6-octave raised-cosine feather), inverse FFT per channel, synthesis window / 2,
  overlap-add into the slot at offset `(m+1)H − N − s0`, clipped to `[0, R + X)`. Every sample of the slot is then
  covered by four frames. The P0 time mask is not used (P0-B did not use it for granular capture either).
- The slot belongs to an idle voice; the playing voice is never touched (§6).

## 5. Bounded capture scheduling (Stage D)

All DSP state is owned by the audio callback; there is **no worker thread** in P1-A. Capture work is split into
**units** executed at fixed **stream-sample times**, so the work per callback is bounded and the result is identical
for every block size.

| Work | Unit | When |
|---|---|---|
| Analysis | `C` forward FFTs (one frame) | at each hop boundary, stream sample ≡ 0 (mod H) |
| FILTERED build | one frame: `C` inverse FFTs + overlap-add | every `S` samples at stream sample ≡ S/2 (mod S) |
| FULL build | copy 4096 samples per channel | same slots |
| Seam | correlation + blend over `X` samples | one slot after the last build unit |
| Voice start | the new voice plays from the sample after the seam unit | |

`S = 64` samples at every rate.

Block-size independence: because work happens at stream-sample times, output is bit-identical for any block size
**when commands carry a sample stamp and parameters are fixed** (the offline renderer and the tests do this). In the
plugin a command from the UI is applied at the start of the block it arrives in, so its timing depends on the host's
block size by up to one block, as any UI event does. Because `S` divides `H` and build slots sit at `S/2` offsets, a build unit **never**
falls on the same sample as an analysis frame. The worst work at any single stream sample is therefore one frame of
FFTs (analysis or build), plus grain rendering. A callback of `B` samples contains at most
`ceil(B / H)` analysis frames and `ceil(B / S)` build units.

Build length (worst case, 1.5 s FILTERED selection): 80 frames at 44.1/48 kHz and 96 kHz alike (frames scale with
H), so `80 × 64 = 5120` samples: 107 ms at 48 kHz, 53 ms at 96 kHz. Worst request-to-sound delay ≈ post-roll wait +
build ≈ 300 ms at 48 kHz. Measured values are in the qualification report.

**Ownership and handoff:** the UI sends IMPRINT / CLEAR through a single-producer single-consumer FIFO
(`juce::AbstractFifo`, fixed capacity, no allocation). The audio thread pops commands at the start of each block,
validates, builds into the idle slot, and swaps voice states itself. The UI reads status through atomics and display
columns through a second SPSC FIFO; it never touches DSP buffers.

## 6. Voices, IMPRINT, CLEAR and REPLACE

- Two preallocated voice slots; each holds a loop buffer of up to `1.5 s + X` per channel and its grain state.
- **IMPRINT** with no voice: the new voice starts with the MEMORY onset fade (30 ms raised cosine).
- **REPLACE** (IMPRINT while a voice plays): the new voice fades in as above while the old one fades out linearly over
  50 ms, then is retired. Old and new overlap only during that fade.
- **CLEAR**: the playing voice fades out over 50 ms.
- A voice retires when its MEMORY envelope passes −100 dB (exact zeros afterwards, as in P0).
- A capture request while two voices are still sounding (inside a 50 ms REPLACE fade) waits for the old voice to
  retire before its slot is reused.

## 7. CLOUD engine (port of `p0/granular.py`)

| Item | P1-A value | Source |
|---|---|---|
| Grain parameters | P0-B `dissolve_params(1.0)` with pitch off: 200 ms Hann grains, 20 grains/s (4× overlap), spray 1, jitter 1, reverse 0.5, spread 0.8, coherence 0 | the configuration the owner picked as CLOUD (`p0b_cloud`) |
| Per-grain gain | `nominal_gain` (overlap-power normalisation, S_REF = 0.75) | P0-B |
| Polyphony | 32 grains per voice; a grain that would be the 33rd is dropped whole (never truncated). During a 50 ms REPLACE fade two voices sound, so the hard ceiling is 64 grains; the benchmark includes it | P0-B |
| Random numbers | SplitMix64, 8 uniform draws per grain whatever the parameters; ties in rounding resolved half-to-even (`std::nearbyint`) like Python's `round`; positions kept in double with a floor-mod | **departure**: NumPy's PCG64 is replaced by a generator that is trivial to reproduce in both languages. The reference scheduler takes its draws from an injectable source and is checked against `granular.schedule` with PCG64 draws |
| Interpolation | 4-point Catmull-Rom, exact at integer positions | P0-B |
| Stereo | both channels read the same position; positive-gain balance | P0-B |
| Pitch / octave | off (speed 1) | blocker B5 |
| TRACE | the periodic loop from index 0 at voice start | P0-C `trace` |
| DISSOLVE | equal-power parallel crossfade of TRACE and CLOUD | consolidation §3 |
| MEMORY | `env[n] = 10^(−3n / (T60 Fs))`, 30 ms onset fade, retire at −100 dB; T60 0.25–30 s | P0 `envelope` |

The scheduler streams the P0 `schedule()` semantics: grains are generated in nominal-time order one interval ahead,
start one grain length before voice time 0 so the overlap is in steady state at the first sample, are admitted at their
onset in onset order, and are dropped whole when the voice already has 32 sounding.

**Extension point for FOCUS and GLITCH.** The scheduler takes its grain parameters as a plain struct and its grain
positions from a position policy (uniform spray for CLOUD). FOCUS adds a position CDF computed at capture time from
the capture's frames; GLITCH adds per-band parameter sets over band-split loop buffers. Neither changes the voice,
capture, scheduling or gain structure.

## 8. Parameters, state, bypass and tail

| ID (version 1) | Range | Default | Notes |
|---|---|---|---|
| `body` | 0–1 linear | 1.0 | BODY gain |
| `ghost` | 0–1 linear | 0.5 | GHOST gain (−6 dB default, see §9) |
| `memory_t60` | 0.25–30 s, log | 5 s | MEMORY decay |
| `dissolve` | 0–1 | 1.0 | TRACE → CLOUD |
| `source` | FULL / FILTERED | FULL | sampled at IMPRINT |

These are development IDs for P1-A; they follow DSP-ARCHITECTURE §11 where it had names. IMPRINT and CLEAR are **not**
parameters, so restoring a session or a preset can never trigger a capture. State stores the parameters only; captured
audio is not saved. Gains and DISSOLVE are smoothed per sample (20 ms and 50 ms linear ramps).

Host bypass (`processBlockBypassed`): output equals input exactly; the analysis keeps running so the history stays
continuous, and the ghost is muted. On resume the BODY gain ramps from 1 to its parameter value and the GHOST from 0
up, so neither edge clicks.

Tail: `getTailLengthSeconds()` returns 50.1 s, the time for the longest MEMORY (30 s) to fall 100 dB plus the fades.

## 9. Gain contract (Stage E)

The research renders were RMS-matched to −23 dBFS for fair comparison. **The plugin does not normalise captures.**

| Stage | Rule |
|---|---|
| Direct BODY | `body` × input; unity at 1 |
| Captured source | the loop is the captured audio at its recorded level (FILTERED: after the mask) |
| Grain overlap | `nominal_gain` makes a dense incoherent cloud match the loop's RMS; sparser clouds are not boosted; coherent material can be louder (P0-B: up to +13 dB for a sequential stream; not the CLOUD setting) |
| DISSOLVE | equal-power: TRACE and CLOUD of equal RMS keep the same RMS across D |
| MEMORY | decay from unity after the onset fade |
| GHOST | `ghost` × the voice sum |

Consequences, stated rather than hidden: BODY + GHOST can exceed 0 dBFS (the host's float path carries it; a fixed-point
output stage will clip); the cloud's crest factor is higher than the loop's; the receding character the owner liked is
kept because nothing compensates level. The plugin measures the output peak per block and shows it, with an over-0 dBFS
indicator, in the development UI. The GHOST default of 0.5 (−6 dB) leaves some headroom for a captured loop of a full-
scale source; it is a default, not a guarantee.

## 10. Realtime rules

- No allocation, lock, blocking call, file I/O, logging or UI call in `processBlock`. All buffers, FFT plans and FIFOs
  are created in `prepareToPlay`; the processor's state functions run on host threads, not the audio callback.
- `juce::ScopedNoDenormals` in the callback. NaN/Inf input samples are replaced by 0 **before** BODY, analysis and
  capture, and counted; so the output stays finite and no non-finite value enters history or a loop. This is the only
  case where the dry path differs from the input, and the count is shown in the development UI.
- Parameter values are read from APVTS atomics once per block.
- The development editor uses polled parameter attachments (an atomic flag per control, a 30 Hz timer), not the stock
  APVTS attachments, so host automation with the editor open does no message-thread work on the audio thread.

## 11. Python reference for parity

`experiments/p0-spectral-ghost/p1a_reference.py` implements this document's contract with the P0 modules: the same
STFT, frequency mask and WOLA, the post-roll loop of §4.2, the scheduler of §7 with SplitMix64, and P0-B's `render`.
`run_p1a_parity.py` writes deterministic synthetic fixtures, runs `afterimage_render` on them, and compares against the
reference with limits fixed before the comparison ran. The P0 modules are not modified.
