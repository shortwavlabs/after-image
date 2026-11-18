# AFTERIMAGE — UI / interaction study (v0.1)

**Visual direction:** midnight graphite, ice-cyan BODY, violet/magenta GHOST, delicate blurred afterimage trails. Avoid skeuomorphic knobs everywhere; emphasize a single luminous live time-frequency canvas.

## Primary view

```
┌─────────────────────────────────────────────────────────────┐
│  SHORTWAV LABS                          AFTERIMAGE   [⋯]   │
│                                                             │
│  FREQ  ┌─────────────────────────────────────────────────┐  │
│   ↑    │   cyan live spectral energy                    │  │
│        │          ╔══════════╗ purple selected halo     │  │
│        │          ║ IMPRINT  ║  ghost trails            │  │
│        │          ╚══════════╝                           │  │
│        └─────────────────────────────────────────────────┘  │
│             ← past                                   now →  │
│                                                             │
│     [IMPRINT]          [CLEAR]              REPLACE / HOLD  │
│                                                             │
│      BODY ━━━━━━━   GHOST ━━━━━━━    MEMORY  ○   MOTION ○  │
│                                             WIDTH ○         │
└─────────────────────────────────────────────────────────────┘
```

## Interaction rules

- Default view must be useful without tutorials: show animated spectrogram and a translucent default selection over recent frames.
- Drag: select frequency/time rectangle; clamp bounds, display frequency/time span in a small tooltip.
- IMPRINT: capture exact region currently visible/valid; button pulses as the new ghost blooms.
- The ghost is rendered as a second translucent layer of magenta/violet lines drifting from the selected region, distinguishable from raw input history.
- CLEAR must remain accessible. Crossfade makes REPLACE musically safe.
- Live status is always legible: EMPTY / ARMED / CAPTURED / DECAYING / HOLD.
- Keyboard shortcuts should not hijack host key commands. Accessibility: labels, non-color-only state, scalable text/contrast.
- Avoid dozens of knobs; limit primary controls to BODY, GHOST, MEMORY, MOTION, WIDTH.
- An optional tiny freeze icon can be added only if the ghost engine supports genuinely sustained material.

## Render architecture

Prototype an independent 2D visual system (JUCE Component / Graphics, GPU optional only if profiling justifies). No dependency on WebView, internet, or a 3D realtime engine. Maintain audio/UI isolation.

Decimate spectral data off the audio callback where possible; render ~20–30 fps; aggressively limit pixels/bins/historical columns. Use a perceptual/log-frequency y-axis, a time-linear x-axis, and a legend for BODY versus GHOST. Changes to UI frame rate must not affect DSP.

## User story for a 30-second demo

1. Play a distorted guitar phrase: spectrum appears (0–6 seconds).
2. Paint high harmonics over the final chord and press IMPRINT (6–12 seconds).
3. Mute input: shimmering ghost remains (12–18 seconds).
4. Turn MOTION and WIDTH, replay a dry riff over the ghost (18–27 seconds).
5. CLEAR; abrupt-to-silent-free transition, logo (27–30 seconds).

## Asset direction

Original procedural animation/gradients only for initial prototype. Any third-party fonts, sample packs, audio demos, or icons must have an explicit compatible redistribution licence.

## User-experience success criteria

- The first imprint should take no more than two obvious actions: select region → IMPRINT (or default selected region → IMPRINT).
- Readable at a laptop window width near 800–1000 px, and on standard/Retina scaling.
- A visually clear explanation of *what* was selected and *what* the ghost is doing, even when input stops.
- The visualization should tell the truth about DSP state; never draw fictional spectral detail.
