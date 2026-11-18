# RFC-001 — Rolling spectral history and ghost resynthesis

**Status:** Design proposal / requires P0 sonic experiments. Do not implement as validated until numerical and listening tests pass.

## Proposed architecture

```
Input
  ├─ delay-compensated BODY ───────────────────────────────┐
  └─ stereo analysis STFT → rolling complex frames        │
                   │                                     │
                   ├─ decimated visualization data       │
                   │      (audio→UI lock-free snapshots) │
                   └─ selected time-frequency ROI        │
                             ↓                           │
                        IMPRINT snapshot                 │
                             ↓                           │
                      one GHOST synthesizer              │
                       ↳ decay / motion / width          │
                             ↓                           │
                  click-free gain and mix ←───────────────┘
                             ↓
                           output
```

### Analysis

Prototype FFT 2048, 4096 and 8192 points with Hann/WOLA, hop N/4, measuring artifact/CPU tradeoffs at 44.1/48/96 kHz. 4096 at 48 kHz gives ~85 ms window and ~11.7 Hz/bin; 1024-sample hop gives ~21 ms new frame cadence. These are prototype parameters, **not a commitment**. Note: buffered STFT introduces latency; explicitly report and compensate *actual* processing latency to host.

Keep 3–4 s of **complex** stereo STFT frames. For 48 kHz, N=4096, hop=1024: ~188 frames × 2049 positive bins × 2 channels × 8 bytes/complex float ≈ 6.2 MB, excluding metadata/masks and overhead. At 96 kHz, ≈ 12.3 MB for the same window duration with unchanged hop. Allocate fixed buffers off audio thread and avoid per-block dynamic growth.

Retain exact frame indices and timestamps. The spectrogram is a decimated *view* of immutable/recent analysis records. UI selections are absolute time/index plus frequency limits; clamp when regions expire and visually mark invalid selections. Never pretend that editing a view retroactively changes audio that has already passed.

### Imprint semantics

Selection is a closed interval of historical frame indices and a feathered frequency mask, potentially made with a rectangular brush. **IMPRINT** snapshots eligible frames into a preallocated voice buffer or fixed-size audio-owned storage. UI commands go to audio thread through bounded, lock-free messages; audio thread owns live memory.

At capture, expose an audible ghost synthesized from captured complex frames; avoid direct looping with discontinuities. Evaluate two candidate engines:

**A. Frame-loop WOLA:** loop or interpolate the saved complex frame sequence and overlap-add with appropriate phase continuity/crossfade. This can preserve transient nuance when capture interval is long enough; short loops risk rhythmic repetition and phase discontinuities.

**B. Phase-continuous spectral hold:** derive magnitudes from the selected frames and advance per-bin phase using estimated instantaneous frequencies (phase vocoder) or stable carrier approaches. This may sustain better but smear transients and become synthetic.

Use listening tests to choose, not aesthetics or theoretical elegance.

### Spectral mask

Feather selection boundaries in time and log-frequency (not just hard binary bins), so selection does not cause broadband ringing. A rectangular UI brush implies a two-dimensional mask over historical material, **not** a source-separation system.

Avoid “perfect reconstruction” language for the processed effect. If BODY is a delayed dry pass-through and GHOST is additive, the BODY-only output can null against a matching delayed reference. If later adding complementary live spectral masks, they require independent reconstruction tests under matching complex STFT processing/phase and latency.

### Memory and motion

- MEMORY: release time constant / exponential decay envelope after capture or after optional HOLD release.
- MOTION: bounded low-frequency modulation of spectral magnitude/phase or diffusion; evaluate for artifacts, deterministic PRNG seed per voice.
- WIDTH: mid/side or decorrelation processing applied *after* resynthesis with mono sum compatibility checks.
- CLEAR / REPLACE: 10–50 ms fades with no clicks; tune by ear, test impulses.

### Real-time and UI boundaries

- No lock, file/network IO, dynamic allocations, or UI calls in processBlock.
- Preallocate analysis/synthesis rings, plans, FFT workspaces, ghost voice, parameter smoothing.
- Support variable block sizes and channels. Handle transport, sample-rate, buffer, and state changes without stale frame indices.
- Pass downsampled visualization via sequence-numbered snapshots or triple-buffering. UI must never directly lock the audio processor.
- Rate-limit spectrogram updates (target 20–30 fps at most). Interactive drawing should not affect audio thread scheduling.

### Tests to implement

1. Known sinusoids: frequency/bin correctness across FFT sizes and rates.
2. Silence, DC, impulse, chirp, noise, fast transients: bounded, finite, no pops/denormals.
3. Stereo phase/correlation and mono downmix; stable output for centered mono inputs.
4. BODY null test against calibrated delayed reference at all supported rates/block sizes.
5. Rapid capture/clear/replace; selection wrapping; sample-rate changes; no out-of-bounds.
6. Measured P95 and worst-case per-block CPU versus realistic audio deadlines, under sanitizer where possible.
7. Audible A/B demos: guitar, voice, drums, synth; blinded preference against ordinary spectral freeze.
8. Preset automation and restore; explicit note that spectral content is ephemeral in MVP.

### P0 experiment

Build the offline two-engine comparison before full JUCE scaffolding. Generate WAVs with one shared selection: 1.0–1.8 s, 350 Hz–5 kHz; resynthesize a 5–10 second evolving ghost, and compare metallicity, click behavior, and musicality by listening. Include a no-mask and a very narrow-mask test. Only promote a candidate after measurement + ears.
