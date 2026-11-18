# AFTERIMAGE — Product Requirements (Draft v0.1)

**Status:** Proposed; not implemented. **Product:** Shortwav Labs AFTERIMAGE. **Use:** The Audio Programmer Plugin Jam 2026–27.

## Positioning

AFTERIMAGE is a spectral-memory audio effect: **paint a time-frequency moment from the recent past, then play its afterimage as a controllable, slowly disappearing second voice.**

Audience: ambient producers, guitarists, electronic composers, sound designers. Priority: a distinctive audible result within 30 seconds of first use.

## Job to be done

“I just played a sound I love. I want to pull out a piece of its spectral history and leave it ringing behind the next thing I play.”

## Signature workflow

1. Insert AFTERIMAGE on guitar, synth, drums, or vocal track; audio flows through the BODY path with latency matching.
2. The live spectrogram scrolls, maintaining about four seconds of recent history.
3. Drag to select a region spanning time and frequency. Selected region is previewed visually; audio is not destructively altered.
4. Press **IMPRINT** (or trigger its MIDI/automatable command) to create one GHOST voice from the selected history.
5. Adjust MEMORY, MOTION, WIDTH, and GHOST level. **REPLACE** gently crossfades old to new; **CLEAR** removes the ghost with a short fade.
6. Mix BODY and GHOST and save/recall the state. On re-open, preset parameters and mode restore; recorded spectral audio memory does **not** survive host reload in MVP, and that behavior is disclosed.

## MVP controls

| Control | Purpose | Notes |
|---|---|---|
| IMPRINT | Capture selected fragment | Momentary action with click-free ghost replacement |
| CLEAR | Fade out captured memory | No abrupt cut |
| BODY | Monitor level | 0–100% |
| GHOST | Wet layer level | 0–100% |
| MEMORY | Ghost decay or hold time | Musical scale; freeze/hold only if stable |
| MOTION | Slow evolution of captured texture | Minimal, bounded drift |
| WIDTH | Ghost stereo diffusion | Mono-compatible operation |
| SELECTION | Spectrogram time-frequency rectangle | Mouse/touch; spectral feathering |

One voice in MVP; multiple accumulating ghosts are **stretch**, not baseline. No user accounts, AI API, cloud, convolution libraries, or neural inference.

## Sound quality goals

- Guitar: articulate dry picking with a stable halo of captured harmonics.
- Voice: sustained harmonic tail that avoids obviously metallic stuttering.
- Drums: captures non-harmonic shimmer without uncontrolled clicks.
- Synth: smooth, evolving sustaining layer and musical decay.
- Dry path is timbrally transparent after latency compensation, verified numerically rather than assumed.
- Ghost must remain bounded and stable across silence, abrupt input, preset changes, and all sample rates.

## Target hosts and formats

macOS AU and VST3, Windows VST3; 44.1/48/88.2/96 kHz, mono/stereo, common block sizes including variable sizes. Implement with JUCE 9 + C++20/CMake after licence decision. Host compatibility and notarization are release gates, not assumed.

## Acceptance gates

- **P0 sonic spike**: offline Python/C++ prototype that produces four before/after demos. Listening vote confirms this is more than spectral freeze.
- **P1 realtime**: safe stereo rolling STFT memory, region selection, capture, ghost resynthesis, clickless clear/replace.
- **P2 UI**: spectrogram selection feels immediate; controls clearly communicate the audio behavior.
- **P3 host**: pluginval/auval where applicable, sample-rate and block-size qualification, state restore and automation.
- **P4 submission**: clean reproducible builds, open-source licence and dependency attribution, instructions, demo video, permitted use of third-party assets verified against the then-current rules.

## Non-goals

Polyphonic pitch tracking; arbitrary high-quality offline time stretching; multi-layer painting; spectrogram editing of past source audio; accurate source separation; standalone DAW; infinite memory.

## Main risks

- Phase-vocoder smearing and metallic artifacts from short, isolated spectral regions.
- Buffer size/time-frequency resolution tradeoff.
- CPU cost of real-time FFT + spectrogram rendering.
- Undo/history semantics when old audio scrolls out.
- Third-party framework and asset licences for a public Jam entry.

## Decision log (open)

1. Exact licence: GPLv3/AGPLv3-compatible vs commercial JUCE route; owner approval required.
2. Default selection: whole-band recent slice versus time-frequency rectangular paint.
3. Ghost algorithm: complex frame-loop overlap-add versus phase-accumulator spectral sustain.
4. Whether IMPRINT supports MIDI note triggering in MVP.
5. Whether transient routing receives a dedicated parameter.

**Project management:** Preserve validated tests as gates, write up every stop/decision, avoid speculative performance claims.
