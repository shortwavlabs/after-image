# AFTERIMAGE — Jam execution plan

**Start:** 2026-11-18. **Submission cutoff:** confirm the current official Jam page before release; initial working target is Jan 2027. This schedule is a planning proposal, not evidence of completed work.

## Phase 0 — Sonic feasibility (highest priority)

- [ ] Commit controlled experiment harness and four properly attributed dry example recordings.
- [ ] Implement offline complex-STFT capture for region selections.
- [ ] Compare WOLA loop/crossfade against phase-continuous spectral sustain on same input.
- [ ] Export documented A/B WAVs for guitar, voice, drums, synth.
- [ ] Validate no NaN, bounded peak, no obvious capture/clear clicks, chosen approach musically useful.
- [ ] **Go/no-go:** if ghost only sounds like a poor spectral freeze, change the sound engine before making a UI.

## Phase 1 — Host skeleton and realtime safety

- [x] Select and record project/framework licensing: `AGPL-3.0-only`, JUCE AGPL route. Verify the pinned JUCE version's notices as part of the implementation/release gate.
- [ ] CMake JUCE project, minimal AU/VST3 targets (macOS), VST3 Windows CI plan.
- [ ] Define param IDs, host state behavior and preset contract before implementation.
- [ ] Preallocated rolling complex-frame history.
- [ ] Reliable command handoff / single voice ghost renderer.
- [ ] Gain smoothing and verify 0-sample host latency for the direct BODY through-path; measure IMPRINT-to-GHOST response separately.
- [ ] Engine tests: null/impulse/phase/silence/stereo/block boundaries.

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
- Whether to prioritize **musical sustain** (phase-continuous spectral hold) or **faithful timbral playback** (frame WOLA loop) after listening.
