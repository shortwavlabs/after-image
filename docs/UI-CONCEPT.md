# AFTERIMAGE — UI and Blender Production Concept (v0.2)

**Status:** Proposed visual and interaction contract; no Blender scene, artwork, JUCE UI, or DSP implementation is claimed complete.  
**Product:** Shortwav Labs AFTERIMAGE — spectral memory instrument.  
**Companion docs:** [PRD](PRD.md), [spectral engine RFC](RFC-001-spectral-engine.md), [roadmap](ROADMAP.md).

## 1. Art direction: an instrument you can peer inside

**Design thesis:** *Prismatica looks like an instrument you can touch. AFTERIMAGE should look like an instrument you can touch and peer inside.*

A premium, slightly mysterious **experimental optical instrument**: imagine a high-end late-1970s recording-studio processor reimagined with futuristic spectral display technology. Not a stompbox, conventional spectrum analyzer, cyberpunk dashboard, or generic synth plugin.

The physical chassis is restrained so the living spectral-memory chamber feels extraordinary.

- **Enclosure:** dark brushed / satin anodized aluminum, near-black graphite or black titanium impression, subtle bevels and chamfers, machined recesses, fine fasteners, engraved legends, disciplined highlights.
- **Display assembly:** a large recessed smoked-glass chamber with real-looking edge depth, shadowed bezel, optical reflections, and an optional *subtle* iridescent violet finish on the metal near the chamber.
- **Hardware:** five luxurious machined-metal rotary knobs with knurled or fine-grooved surfaces, two physically satisfying mechanical action buttons, understated status indicators. No giant footswitch.
- **Color roles:** BODY/live energy = ice cyan / pale turquoise; selection and GHOST = violet / magenta; metal and type = cool neutral graphite/silver; alerts = restrained amber only if truly needed.
- **Typography:** modern precision-lab / boutique-studio typography; small, readable uppercase engraved labels, with AFTERIMAGE as the most prominent brand. No ornamental fonts that compromise legibility.
- **Emotional arc:** dormant precision device → cyan living audio → a purple imprint lifts away from the original → ghost slowly dissolves into silence.

This is a *concept*, not a finalized palette or product render. Material and color tests belong in Blender.

## 2. Landscape panel layout

**Design coordinate system:** 1200 × 720 logical pixels (16:9-ish), authored in normalized anchors, not hard-coded as the only runtime size. First high-density renders at 2× (2400 × 1440). Keep useful scaling around 800–1000 px wide, including host/HiDPI behavior.

The central display should occupy roughly **half the faceplate**. The bottom controls should be physically substantial but visually subordinate to the display.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ SHORTWAV LABS                                       AFTERIMAGE    [PRESET]│
│                                                    SPECTRAL MEMORY       │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │                     RECESSED SMOKED-GLASS CHAMBER                    │ │
│ │  FREQ ↑   cyan: live spectrogram/time history                        │ │
│ │           ╔══════════════════╗ violet: selected ROI                  │ │
│ │           ║  selected audio  ║  → magenta ghost trails               │ │
│ │           ╚══════════════════╝                                        │ │
│ │                ← PAST                                       NOW →     │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│  [     IMPRINT     ]      GHOST: CAPTURED / DECAYING      [    CLEAR   ] │
│                                                                          │
│       ◉               ◉               ◉            ◉           ◉        │
│      BODY            GHOST           MEMORY        MOTION       WIDTH    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Top:** quiet Shortwav Labs nameplate; AFTERIMAGE identity; compact preset menu in the upper right (never cover the chamber by default).

**Middle:** recessed spectrogram; log-frequency vertical axis, time-linear horizontal axis, newest material at right. Only include small legends/readouts that teach the interaction.

**Lower action strip:** prominently lit IMPRINT to capture selected recent spectral history, CLEAR to smoothly remove it, and readable state text such as EMPTY / ARMED / CAPTURED / DECAYING / HOLD. REPLACE is the natural default when an existing ghost is present; HOLD is shown or enabled only if sustained material is genuinely supported by the chosen engine.

**Bottom:** exactly five primary knobs: BODY, GHOST, MEMORY, MOTION, WIDTH. Avoid a sprawling matrix of secondary controls, false hardware elements, and decorative displays.

## 3. Signature interaction: a spectral memory chamber

The visual must be a faithful explanation of the *actual* audio engine, not an independent looping animation.

**State sequence:**

1. **LIVE:** cyan spectrogram scrolls with roughly the last four seconds of *real* analyzed input; a translucent default selection provides a one-click starting point.
2. **SELECT:** drag to draw a time-frequency rectangle across recent audio. The selected harmonics are outlined in violet, with subtle edge feathering; optional tooltip shows frequency and time span.
3. **IMPRINT:** when valid, the region becomes a captured GHOST. Brief physical button illumination and a restrained violet bloom communicate success; avoid an expensive full-screen particle effect.
4. **AFTERIMAGE:** magenta spectral trails remain spatially separate from the advancing cyan history. They represent captured/synthesized energy and change with MEMORY/MOTION, not fabricated historical samples.
5. **DISSOLVE:** a decaying ghost visually thins and fades; changing WIDTH may modify dispersion in the visualization while its meters/readouts remain truthful. CLEAR and REPLACE invoke click-free fades (implemented by the DSP, not the GUI).

**Selection validity:** selection must not silently target overwritten history. As the ring scrolls, selection indices refer to genuine captured frames. On expiration, clear/disable or explicitly show an expired/invalid region. Display must not promise source separation or arbitrary offline spectral editing.

**Interaction priorities:**

- A user can make a useful first ghost via **IMPRINT** with a default selection; explicit selection → IMPRINT is a two-step discovery path.
- Immediate visual feedback for selection and capture, without blocking audio.
- High-contrast, non-color-only state labels; host-safe keyboard behavior; pointer hit targets large enough for laptop use.
- Do not make visual frames dictate capture timing: a command captures audio-owned frame indices, not textures.
- Preset recall restores parameters; unless a future feature explicitly serializes captured samples, spectral audio history **does not persist across host/session reload** in the MVP.

## 4. Blender × JUCE production architecture

Use the proven Shortwav Labs hybrid workflow: **Blender renders static high-fidelity hardware and independent control assets; JUCE manages interaction and draws an actual data-driven spectral chamber.** This is intentionally *not* runtime 3D.

### Layer and Z-order contract

From rear to front:

| Z | Asset/layer | Authoring | Runtime owner | Notes |
|---|---|---|---|---|
| 0 | Faceplate / enclosure and labels | Blender, final camera | JUCE image | Static; includes bevels, screws, empty recessed aperture; *no* painted spectrum |
| 1 | Chamber shadow / inner rim (if not baked into 0) | Blender | JUCE image | Defines perceived depth and mask boundary |
| 2 | Live time-frequency canvas | N/A | JUCE custom 2D component | Real analyzed BODY spectral magnitude; clipped to aperture |
| 3 | Selection / ghost trails / feedback | N/A | JUCE custom 2D component | Accurate capture selection and state; separate cyan/violet encodings |
| 4 | Smoked-glass reflection / edge-glow overlay | Blender transparent RGBA | JUCE image | Transparent center; subdued reflection; must *not* obliterate the live spectrum or pointer hit-testing |
| 5 | Physical knob / button sprites and status indicators | Blender, separate assets | JUCE controls | Each sprite aligned with matching camera/light; indicators reflect host state |
| 6 | Dynamic readouts / menus / tooltips / focus feedback | N/A | JUCE UI | Above relevant artwork, accessible and sharp at scale |

The glass overlay can be split into **bezel-under-display** and **reflection-over-display** passes to obtain correct depth. The visible camera and display corners, cutout, perspective, highlights, and aspect ratio must match exactly across all passes.

### Blender scene organization

Proposed collections:

- `01_CHASSIS_STATIC`: panel, hardware cutouts, bezel, screws, engraved legends.
- `02_CONTROLS`: knob geometry, pointers, button caps, mechanical sockets.
- `03_GLASS`: translucent glass, reflections and optional subtle blooming edges.
- `04_LIGHTING_CAMERA`: orthographic or long-focal-length front camera; consistent softboxes, world, color transform.
- `05_EXPORT_HELPERS`: object IDs/masks, safe-area guides, sprite export anchors.

Use a repeatable fixed camera, lighting setup, exposure, and color management for every pass. Match shadows on separate controls to faceplate contact shadows and avoid double shadows when compositing. The perspective should read as a premium front panel rather than extreme dramatic 3D.

### Asset outputs (proposed)

```text
assets/
  blender/
    afterimage-panel.blend
    render-presets.md
  ui/
    panel/
      enclosure@2x.png
      chamber-glass-overlay@2x.png
    controls/
      knob-body-strip@2x.png
      knob-ghost-strip@2x.png
      knob-memory-strip@2x.png
      knob-motion-strip@2x.png
      knob-width-strip@2x.png
      imprint-up@2x.png
      imprint-down@2x.png
      clear-up@2x.png
      clear-down@2x.png
    masks/
      chamber-aperture@2x.png
    ui-layout.json
```

These paths are **target conventions**, not existing files. A shared knob strip/atlas may replace individual duplicated strips after art validation. Knob frames should be generated deterministically from real model rotation (e.g. 64–128 frames only if needed for smoothness), with a visible pointer whose position precisely matches the JUCE parameter value. Provide fixed frame bounds and pivot coordinates. For smaller UI packages, compare a single transparent knob sprite rotated by JUCE against frame strips; choose by visual quality, memory and scaling measurements.

**Export discipline:**

- Render enclosure and control assets in consistent camera space; use clean, antialiased alpha and transparent backgrounds where required.
- Convert final color assets to consistent sRGB before bundling; verify alpha-edge appearance with JUCE's image pipeline (straight vs premultiplied compositing).
- Keep text/labels in Blender only where the static etched appearance matters. Dynamic values, preset names, state messages, focus outlines and tooltips are JUCE text for readability/accessibility.
- Ensure asset licences allow repository publication and plugin redistribution. Do **not** commit third-party fonts/textures without explicit compatible terms.
- Bundle offline assets locally; no remote image loads or runtime Blender dependency.
- Establish per-element bounding rectangles and pixel-to-logical mappings in the layout manifest; unit-test hit areas against art anchors.

## 5. Spectral visualization renderer

Implement as a dedicated JUCE 2D component; GPU acceleration is *optional* and should only be added when profiling warrants it. Do not require WebView, JavaScript, Vulkan, Metal, OpenGL, or real-time 3D for the MVP.

- Source: low-rate, downsampled analysis snapshots delivered through a safe, bounded audio/UI handoff; never read mutable DSP buffers directly from the UI.
- Horizontal coordinate: monotonic historical time, newest at the right edge. Vertical coordinate: perceptual/log frequency with appropriately labeled ticks.
- Colors: BODY cyan, selected ROI violet outline, captured GHOST magenta translucent trails. Ghost trails derive from synthesis state/spectrum where feasible, and cannot imply nonexistent content.
- Framerate: initial target **20–30 fps** (UI-only scheduling), adaptive throttling when hidden or inactive. Lower rates must not change audio behavior.
- Rendering: cache/back-buffer static overlays, clip to the transparent glass aperture, simplify bins and columns to the display's real pixel resolution; avoid per-frame giant allocation.
- Cross-platform: verify on standard/Retina macOS and Windows fractional scaling, with plugin window resizing within sane limits.
- Performance: audio path must remain allocation-free and lock-free, even during resize, hover, scrub, capture, or a display rebuild.

**Important:** spectral history and selection are audio-domain data; the visual is a view. Visual smoothing, blooming and synthetic trails may stylize *measured* energy but must not suggest that a silent or empty ghost is making sound.

## 6. Hardware interaction and parameter correspondence

| Control | Physical presentation | Action |
|---|---|---|
| IMPRINT | Illuminated tactile mechanical pushbutton | Trigger capture on valid ROI; short success pulse |
| CLEAR | Recessed mechanical button | Trigger click-free ghost fade/clear |
| BODY | Aluminum rotary knob, cyan accent | Dry/body level |
| GHOST | Aluminum rotary knob, violet accent | Spectral memory layer level |
| MEMORY | Rotary knob | Memory decay/sustain duration as supported by DSP |
| MOTION | Rotary knob | Bounded spectral drift/evolution |
| WIDTH | Rotary knob | Stereo spread/diffusion |
| Preset menu | Compact top-right text/menu | Preset and state operations |

Labels and active indicator orientations must always agree with actual values. No fake switches, unlabeled white lines, or ornaments that resemble actionable controls. Buttons expose disabled/active/working states and a11y names. Host automation updates the displayed hardware position.

## 7. 30-second judging/demo storyboard

| Seconds | Action | What the audience learns |
|---|---|---|
| 0–6 | Play a dry distorted guitar line and final chord | Cyan live history is real audio |
| 6–12 | Paint a harmonic slice; press IMPRINT | The signature two-dimensional capture gesture |
| 12–18 | Mute incoming guitar; captured ghost keeps singing | Audible differentiation from dry signal |
| 18–27 | Turn MOTION, WIDTH, MEMORY, play a riff over the ghost | Expressive and usable processing, not a one-shot novelty |
| 27–30 | Press CLEAR; smooth fade to quiet, logo/branding | Control and polish |

Record audio at high quality, with matched playback levels and no unrelated backing FX that hide the plugin's character. Longer submission video can expand on synth, drums, and voice, depending on the official rules.

## 8. Design validation / acceptance gates

**Visual integration:**
- [ ] Blender scene matches the chosen 1200 × 720 logical layout; clean 2× exports align to fixed anchors.
- [ ] Faceplate is visually strong even with the spectral display blank.
- [ ] Glass/reflection overlay does not make colored spectral data unreadable or block pointer interactions.
- [ ] Hardware sprites register without visible jumps, changing shadows, clipped rims, or misaligned pointer axes.
- [ ] At least one 800–1000 px wide and one high-DPI size remain readable.
- [ ] Color alone never conveys selected/expired/empty/active states.

**Interaction and fidelity:**
- [ ] Real source audio creates a readable, correctly oriented spectrogram; silence correctly decays to no displayed input.
- [ ] Selection maps to sample/frame/frequency indices used by the DSP, even after ring wrap.
- [ ] IMPRINT with default selection works immediately; selecting a region works within two clear actions.
- [ ] GHOST visualization responds to genuine capture/decay/clear, not an uncorrelated decorative animation.
- [ ] Host automation, resize, bypass, variable sample rates, and preset restoration do not desync audio and controls.

**Performance and release:**
- [ ] Profiling demonstrates that GUI refreshes/resize do not cause audio deadline overruns.
- [ ] All art and fonts have documented redistribution permissions compatible with the public repo's chosen licence.
- [ ] Physical UI and sonic effect remain compelling with motion embellishments disabled (fallback/reduced-motion path).

## 9. Next art experiments (after P0 sonic viability)

1. Blender **graybox chassis**: wide, low-profile hardware proportions and 50%-of-panel chamber with no materials.
2. **Materials lighting test**: graphite satin aluminum, brushed metal controls, smoked glass reflection transparency, cyan/violet edge treatment. Check at normal plugin size.
3. **Control test sheet**: rotating knurled knob with clear pointer, IMPRINT/CLEAR button states, glass compositing over a temporary diagnostic checkerboard.
4. **JUCE chamber proof of concept**: fake test data explicitly labeled *debug visualization* at first, then swap to real decimated audio analysis as soon as available.
5. **Integrated screenshot and capture test**: verify the Blender exports and live renderer before adding animation flourishes.

**Design rule:** invest in the Blender enclosure only after a P0 audio test demonstrates a musical, distinctive ghost. The product must still sound good with the window closed.
