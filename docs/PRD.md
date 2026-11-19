# AFTERIMAGE — Product Requirements (Draft v0.1)

**Status:** Proposed; research complete, realtime implementation starting (P1-A). **Product:** Shortwav Labs AFTERIMAGE. **Use:** The Audio Programmer Plugin Jam 2026–27.

> **Status update (2026-11-18):** offline research P0-A, P0-B, P0-C and real-audio qualification is complete and consolidated in [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md). The GHOST is now **granular** (CLOUD core engine, FOCUS later, GLITCH experimental) over a captured buffer, with a parallel TRACE → CLOUD DISSOLVE and FULL / FILTERED SOURCE. Where this document describes a spectral-only ghost, that text is kept for history and is superseded by the consolidation record and `P1-A-REALTIME-ARCHITECTURE.md` (added with P1-A on `feature/p1a-realtime-core`).

## Positioning

AFTERIMAGE is a spectral-memory audio effect: **paint a time-frequency moment from the recent past, then play its afterimage as a controllable, slowly disappearing second voice.**

Audience: ambient producers, guitarists, electronic composers, sound designers. Priority: a distinctive audible result within 30 seconds of first use.

## Job to be done

“I just played a sound I love. I want to pull out a piece of its spectral history and leave it ringing behind the next thing I play.”

## Signature workflow

1. Insert AFTERIMAGE on guitar, synth, drums, or vocal track; BODY remains a direct, zero-latency dry through-path while GHOST is independently synthesized from past audio.
2. The live spectrogram scrolls, showing about four seconds from a proposed six-second internal complex-spectral history with a capture safety margin.
3. Drag to select a region spanning time and frequency. Selected region is previewed visually; audio is not destructively altered.
4. Press **IMPRINT** in the UI to create one GHOST voice from the selected history. MIDI and host-automatable capture triggers are deferred until their event/restore semantics are designed and tested.
5. Adjust MEMORY, MOTION, WIDTH, and GHOST level. **REPLACE** gently crossfades old to new; **CLEAR** removes the ghost with a short fade.
6. Mix BODY and GHOST and save/recall continuous parameters. On re-open, these parameters restore; recorded spectral audio memory, selections, and captures do **not** survive host reload in MVP, and that behavior is disclosed.

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
| DISSOLVE | TRACE (captured loop) → CLOUD (granular) | Added 2026-11-18 from P0-B/P0-C; parallel crossfade by default |
| SOURCE | FULL / FILTERED | Added 2026-11-18: whole time slice vs. the painted time-frequency region |
| ENGINE | CLOUD (FOCUS later) | Added 2026-11-18; GLITCH experimental, not MVP. MOTION and WIDTH above are unresearched |

One voice in MVP; multiple accumulating ghosts are **stretch**, not baseline. No user accounts, AI API, cloud, convolution libraries, or neural inference.

## Sound quality goals

- Guitar: articulate dry picking with a stable halo of captured harmonics.
- Voice: sustained harmonic tail that avoids obviously metallic stuttering.
- Drums: captures non-harmonic shimmer without uncontrolled clicks.
- Synth: smooth, evolving sustaining layer and musical decay.
- BODY is sample-aligned with the input and timbrally transparent at unity gain (host latency 0 for this additive architecture), verified by impulse/null tests rather than assumed.
- Ghost must remain bounded and stable across silence, abrupt input, preset changes, and all sample rates.

## Target hosts and formats

macOS AU and VST3, Windows VST3; 44.1/48/88.2/96 kHz, mono/stereo, common block sizes including variable sizes. Implement with JUCE 9 + C++20/CMake under the decided AGPLv3 route. Free macOS and Windows installers will be published via GitHub Releases only after host qualification, macOS signing/notarization, and release-artifact checks.

## Acceptance gates

- **P0 sonic spike**: offline Python/C++ prototype that produces four before/after demos. Listening vote confirms this is more than spectral freeze.
- **P1 realtime**: safe stereo rolling STFT memory, region selection, capture, ghost resynthesis, clickless clear/replace.
- **P2 UI**: spectrogram selection feels immediate; controls clearly communicate the audio behavior.
- **P3 host**: pluginval/auval where applicable, sample-rate and block-size qualification, state restore and automation.
- **P4 submission**: clean reproducible builds, open-source licence and dependency attribution, instructions, demo video, permitted use of third-party assets verified against the then-current rules.

## Non-goals

Polyphonic pitch tracking; arbitrary high-quality offline time stretching; multi-layer painting; spectrogram editing of past source audio; accurate source separation; standalone DAW; infinite memory.

## Main risks

- Superseded risk list for the granular direction: see the blocker register in [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md) §5.
- Phase-vocoder smearing and metallic artifacts from short, isolated spectral regions.
- Buffer size/time-frequency resolution tradeoff.
- CPU cost of real-time FFT + spectrogram rendering.
- Undo/history semantics when old audio scrolls out.
- Third-party framework and asset licences for a public Jam entry.

## Decision log (open)

1. **RESOLVED:** Original project code `AGPL-3.0-only`; JUCE 9 via AGPLv3 path. See [licensing and release policy](LICENSING.md).
2. **RESOLVED (provisional, 2026-11-18):** both, as SOURCE = FULL | FILTERED. See [consolidation](RESEARCH-CONSOLIDATION.md) §3.
3. **RESOLVED (provisional, 2026-11-18):** neither as the main ghost; granular CLOUD over a captured buffer, with the frame loop kept as the TRACE end of DISSOLVE. Sustain was not preferred in any listening set.
4. **DEFERRED:** IMPRINT MIDI/host automation beyond GUI trigger, pending event and state-restore contract.
5. Whether transient routing receives a dedicated parameter.
6. **DECIDED for P1-A (2026-11-18), revisit by ear:** the loop period equals the selected duration; the seam crossfade uses 80 ms of audio *after* the selection (post-roll). See [P1-A architecture](P1-A-REALTIME-ARCHITECTURE.md) §4.2.
7. **DECIDED for P1-A:** captures are not normalised; GHOST defaults to −6 dB; no limiter; output peak and overs are shown. §9 of the P1-A architecture.
8. **DECIDED for P1-A:** development parameter IDs `body`, `ghost`, `memory_t60`, `dissolve`, `source` (version 1). IMPRINT and CLEAR are not host parameters. Not yet a preset contract.
9. **DECIDED for P1-B (2026-11-19), after the owner's first guitar audition:** hands-free capture is the primary workflow; the spectrogram selection stays as an advanced option. Capture modes MANUAL (one-action IMPRINT of the last 250–1500 ms), RANDOM and AUTO (experimental), plus a latched HOLD. See [P1-B UX contract](P1-B-UX-CONTRACT.md).
10. **DECIDED for P1-B, revisits decision 8:** IMPRINT is now also an automatable trigger parameter (`imprint`, rising edge, never fired by state restore), and HOLD is a parameter, so footswitches work through host controller assignment. VST3 accepts MIDI Note On / CC 64 as IMPRINT; the AU stays a plain effect (`aufx`) without MIDI.

**Project management:** Preserve validated tests as gates, write up every stop/decision, avoid speculative performance claims.
