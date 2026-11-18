# AFTERIMAGE

**A spectral memory instrument by Shortwav Labs**  
Concept-stage submission for [The Audio Programmer Plugin Jam 2026–27](https://www.theaudioprogrammer.com/events/plugin-jam).

> Paint a ghost from a moment of sound. Keep what was there, or let it disappear into something new.

## Concept

AFTERIMAGE is a real-time audio effect that continuously remembers a short rolling window of incoming audio. The user selects a **time–frequency region** in a scrolling spectrogram and turns that selection into a persistent, transformable sound layer (the **GHOST**), while the live signal remains the **BODY**.

The signature interaction is **painting a musical memory**, not simply pressing a spectral-freeze button.

## Status

**Exploration / architecture only.** No plugin implementation, audio engine, build, or sound-quality claims yet.

Design and acceptance criteria are proposed in the development docs on the concept branch.

## Proposed MVP

- JUCE 9 / C++20, CMake; macOS AU/VST3 and Windows VST3 (subject to build validation).
- Stereo real-time STFT capture; ~3–4 second rolling complex-spectral buffer.
- Visual selection of a recent time–frequency fragment; one capturable GHOST layer.
- Seamless loop / sustained ghost with decay, filtering, stereo spread, and safe clear/replace behavior.
- BODY/GHOST blend, host automation and preset persistence.
- Audio-first technical tests; no audio-thread allocation or locks.

## Licensing and attribution

**AFTERIMAGE is free and open-source software licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).** See [LICENSE](LICENSE) for the complete license text and [licensing guidance](docs/LICENSING.md) for framework, contribution, attribution, and asset requirements (the guidance document is part of the design PR until merged).

JUCE 9 will be used under its **AGPLv3** option, not a commercial JUCE license. No purchase is required for that choice, but the application's distribution must respect AGPL obligations. Third-party code, fonts, and artwork require separate licence verification. The Shortwav Labs name and logos are trademarks/branding; the software licence does not itself grant trademark rights.

See [JUCE licensing](https://github.com/juce-framework/JUCE/blob/master/LICENSE.md) and the [Jam's official overview](https://www.theaudioprogrammer.com/events/plugin-jam).

## Project principles

1. Make the musical result worth using before polishing the visualization.
2. One standout interaction beats a long list of mediocre features.
3. Test actual phase/latency/reconstruction properties; never assume perfect reconstruction.
4. Keep real-time audio execution deterministic, bounded, allocation-free, and lock-free.
5. Keep experiments distinct from validated behavior, and document decisions.

Copyright © 2026 Shortwav Labs contributors. Original project code is licensed under AGPL-3.0-only unless otherwise noted.
