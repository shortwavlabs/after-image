# AFTERIMAGE

**A spectral memory instrument by Shortwav Labs**  
Concept-stage submission for [The Audio Programmer Plugin Jam 2026–27](https://www.theaudioprogrammer.com/events/plugin-jam).

> Paint a ghost from a moment of sound. Keep what was there, or let it disappear into something new.

## Concept

AFTERIMAGE is a real-time audio effect that continuously remembers a short rolling window of incoming audio. The user selects a **time–frequency region** in a scrolling spectrogram and turns that selection into a persistent, transformable sound layer (the **GHOST**), while the live signal remains the **BODY**.

The signature interaction is **painting a musical memory**, not simply pressing a spectral-freeze button.

## Status

**Offline research complete; realtime implementation starting.** Python research (P0-A, P0-B, P0-C, real-audio qualification) is consolidated in [docs/RESEARCH-CONSOLIDATION.md](docs/RESEARCH-CONSOLIDATION.md): the GHOST is a granular cloud over a captured slice of recent audio. No released plugin, installer or realtime qualification exists yet.

**P1-A (in progress, `feature/p1a-realtime-core`):** a JUCE 9 plugin (AU, VST3, Standalone; macOS only so far) with a zero-latency BODY, C++ STFT history and capture, the CLOUD engine with a parallel TRACE → CLOUD DISSOLVE, and a minimal development interface. See [docs/P1-A-REALTIME-ARCHITECTURE.md](docs/P1-A-REALTIME-ARCHITECTURE.md) and [docs/P1-A-QUALIFICATION.md](docs/P1-A-QUALIFICATION.md).

## Build (macOS, development)

Requires CMake ≥ 3.22, Xcode command-line tools and network access on first configure (JUCE 9.0.5 is fetched by commit).

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
```
```bash
cmake --build build -j 8
```
```bash
ctest --test-dir build --output-on-failure
```

Products are in `build/AFTERIMAGE_artefacts/Release/{AU,VST3,Standalone}`; nothing is installed automatically. To audition in a host, copy the AU to `~/Library/Audio/Plug-Ins/Components` or the VST3 to `~/Library/Audio/Plug-Ins/VST3`. Parity against the Python reference: `uv run python run_p1a_parity.py --render build/afterimage_render_artefacts/Release/afterimage_render` in `experiments/p0-spectral-ghost`.

## Proposed MVP

- JUCE 9 / C++20, CMake; macOS AU/VST3 and Windows VST3 (subject to build validation).
- Stereo real-time STFT capture; proposed ~6-second internal complex-spectral history with ~4 seconds visible for selection.
- Visual selection of a recent time–frequency fragment; one capturable GHOST layer.
- Seamless loop / sustained ghost with decay, filtering, stereo spread, and safe clear/replace behavior.
- Zero-latency BODY through-path, additive GHOST blend, automatable continuous controls, and parameter preset persistence (captured audio is ephemeral).
- Audio-first technical tests; no audio-thread allocation or locks.

## Downloads and releases

AFTERIMAGE will be distributed **free of charge** through [GitHub Releases](https://github.com/shortwavlabs/after-image/releases), with downloadable **macOS (AU/VST3)** and **Windows (VST3)** installers once built and qualified. There are **no installers available yet**. The release will also include corresponding source, build instructions, license notices and checksums. See [release and licensing policy](docs/LICENSING.md).

## Licensing and attribution

**AFTERIMAGE is free and open-source software licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).** See [LICENSE](LICENSE) for the complete license text and [licensing guidance](docs/LICENSING.md) for framework, contribution, attribution, and asset requirements (included in the project's design documentation).

JUCE 9 will be used under its **AGPLv3** option, not a commercial JUCE license. No purchase is required for that choice, but the application's distribution must respect AGPL obligations. Third-party code, fonts, and artwork require separate licence verification. The Shortwav Labs name and logos are trademarks/branding; the software licence does not itself grant trademark rights.

See [JUCE licensing](https://github.com/juce-framework/JUCE/blob/master/LICENSE.md) and the [Jam's official overview](https://www.theaudioprogrammer.com/events/plugin-jam).

## Project principles

1. Make the musical result worth using before polishing the visualization.
2. One standout interaction beats a long list of mediocre features.
3. Test actual phase/latency/reconstruction properties; never assume perfect reconstruction.
4. Keep real-time audio execution deterministic, bounded, allocation-free, and lock-free.
5. Keep experiments distinct from validated behavior, and document decisions.

Copyright © 2026 Shortwav Labs contributors. Original project code is licensed under AGPL-3.0-only unless otherwise noted.
