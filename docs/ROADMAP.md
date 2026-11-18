# AFTERIMAGE — Jam execution plan

**Start:** 2026-11-18. **Submission cutoff:** confirm the current official Jam page before release; initial working target is Jan 2027. This schedule is a planning proposal, not evidence of completed work.

> **Status update (2026-11-18):** offline research P0-A, P0-B, P0-C and real-audio qualification is complete and consolidated in [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md). The GHOST is now **granular** (CLOUD core engine, FOCUS later, GLITCH experimental) over a captured buffer, with a parallel TRACE → CLOUD DISSOLVE and FULL / FILTERED SOURCE. Where this document describes a spectral-only ghost, that text is kept for history and is superseded by the consolidation record and `P1-A-REALTIME-ARCHITECTURE.md` (added with P1-A on `feature/p1a-realtime-core`).

## Phase 0 — Sonic feasibility (highest priority)

**Done 2026-11-18** as P0-A, P0-B, P0-C and real-audio qualification (shortwavlabs/after-image#2–#5). The checklist below is the original plan, ticked where it was met; two items were not met as written and say so.

- [x] Commit controlled experiment harness. *Not met:* no recordings are committed; 12 local Freesound files have unknown licences (blocker B11).
- [x] Implement offline complex-STFT capture for region selections.
- [x] Compare WOLA loop/crossfade against phase-continuous spectral sustain on same input (P0-A); then granular (P0-B) and multiband (P0-C).
- [x] Export documented A/B WAVs for guitar, voice, drums, synth (synthetic and real; WAVs git-ignored).
- [x] Validate no NaN and chosen approach musically useful (owner listening, consolidation §2). *Not met:* bounded peak at the product output is open (B3, B4).
- [x] **Go/no-go:** the engine was changed — granular CLOUD was preferred over the spectral loop and freeze.

## Phase 1 — P1-A realtime foundation (current)

Scope and gates: `P1-A-REALTIME-ARCHITECTURE.md` (added with P1-A on `feature/p1a-realtime-core`), results: `P1-A-QUALIFICATION.md` (same branch). JUCE shell and zero-latency BODY, C++ STFT history and capture, CLOUD with parallel DISSOLVE, bounded capture scheduling, production gain contract, C++ tests and Python parity, a minimal development UI. FOCUS and GLITCH follow once CLOUD is realtime-qualified. The original Phase 1 checklist follows.

### Original Phase 1 checklist

- [x] Select and record project/framework licensing: `AGPL-3.0-only`, JUCE AGPL route. Verify the pinned JUCE version's notices as part of the implementation/release gate.
- [x] CMake JUCE project, minimal AU/VST3 targets (macOS). *Open:* Windows VST3 CI plan.
- [x] Param IDs and host state behaviour (P1-A development IDs). *Open:* preset contract.
- [x] Preallocated rolling complex-frame history.
- [x] Reliable command handoff / two-slot voice renderer with REPLACE and CLEAR fades.
- [x] Gain smoothing; 0-sample latency and bit-exact BODY verified; IMPRINT-to-GHOST delay measured.
- [x] Engine tests: null/impulse/silence/stereo/block boundaries, plus parity with the Python reference.

P1-A open items: host-level validation beyond `auval` (pluginval, DAW sessions, automation with the editor open), a realtime benchmark inside a host, Windows, listening to the C++ engine.

## Phase 2 — Signature interface

- [ ] Log-frequency spectrogram with selectable historic interval.
- [ ] Precise region-to-audio mapping and safe expiration behavior.
- [ ] Ghost overlay synced to real synthesis state.
- [ ] Minimal controls and keyboard/accessibility basics.
- [ ] Profile animation against heavy input and multiple host/plugin instances.

## Phase 3 — Musical polish

- [ ] Four showcase presets + two experimental presets.
- [ ] Listen against existing freeze/reverb/delay products.
- [ ] Assess ghost musicality at all tested sample rates.
- [ ] Clear automation and README/usage guide.
- [ ] Restore, bypass and session reload tests.
- [ ] Keep scope: defer multiple ghosts and AI extras unless all stability gates pass.

## Phase 4 — Submission

- [x] Commit original project open-source licence (`AGPL-3.0-only`).
- [ ] Complete third-party notices, exact shipped-source correspondence, and dependency/asset licence inventory.
- [ ] Build, sign and notarize macOS AU/VST3 installer; validate Windows VST3 installer on actual Windows host.
- [ ] auval/pluginval and host smoke tests; manual rendering/automation checks.
- [ ] Publish downloadable macOS and Windows installers, exact corresponding source, reproduction instructions, and SHA-256 checksums through GitHub Releases.
- [ ] ≤3-minute concept/demo video and 30-second social clip.
- [ ] Read official rules again; confirm submission, deadlines, asset permissions, AI/tool disclosure and release requirements.

## Risks / mitigations

| Risk | Mitigation |
|---|---|
| Spectral result mediocre | P0 must precede visual work |
| Complex resynthesis not realtime | Preallocation, short rolling history, per-frame profiling |
| Replayed ghost clicks | WOLA / crossfades, boundary tests |
| UI adds CPU spikes | Rate-limited decimated visualization, no work on audio thread |
| Framework licence conflict | AGPLv3 project/JUCE route decided; verify pinned dependency and distributed asset licence obligations |
| Cross-platform packaging stalls | Basic builds early; reserve final week |
| Feature creep | One ghost, one paint selection, five continuous controls |

## Explicit approvals required

- **RESOLVED:** Project licence = AGPL-3.0-only; JUCE AGPLv3 route. See [licensing policy](LICENSING.md).
- Target DAWs/platform order if time forces reductions.
- ~~Whether to prioritize musical sustain or faithful timbral playback after listening.~~ Resolved 2026-11-18: granular CLOUD; see consolidation §3.
- License provenance of the 12 local Freesound recordings (B11).
