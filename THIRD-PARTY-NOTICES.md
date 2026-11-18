# Third-party notices

AFTERIMAGE's own code is licensed under `AGPL-3.0-only` (see [LICENSE](LICENSE)). The P1-A build uses one third-party
framework, **JUCE 9.0.5** (commit `d60b7a78030661574a615b586d9325ba7a7fa7dd`), fetched at configure time and not stored
in this repository. JUCE's modules are dual-licensed; AFTERIMAGE uses them under the **AGPLv3** option, not the
commercial JUCE licence.

## How this list was derived

From JUCE's own SPDX bill of materials (`JUCE.spdx.json` at the pinned commit): every package vendored inside a JUCE
module that this build links. The linked modules are the transitive dependencies of `juce_audio_utils`, `juce_dsp` and
`juce_audio_plugin_client`: `juce_audio_basics`, `juce_audio_devices`, `juce_audio_formats`, `juce_audio_plugin_client`,
`juce_audio_processors`, `juce_audio_processors_headless`, `juce_audio_utils`, `juce_core`, `juce_data_structures`,
`juce_dsp`, `juce_events`, `juce_graphics`, `juce_gui_basics`, `juce_gui_extra`. Rebuild this list when the JUCE pin,
the linked modules or the build options change.

## Compiled into the macOS AU, VST3 and Standalone builds

| Component | Version | Licence | Vendored at (in JUCE) |
|---|---|---|---|
| JUCE modules listed above | 9.0.5 | AGPL-3.0-only (chosen) OR JUCE commercial | `modules/` |
| zlib | 1.3.2 | Zlib | `juce_core/zip/zlib` |
| HarfBuzz | 15.0.0 | MIT-Modern-Variant | `juce_graphics/fonts/harfbuzz` |
| SheenBidi | 2.9.0 | Apache-2.0 | `juce_graphics/unicode/sheenbidi` |
| LunaSVG | 3.5.0 | MIT | `juce_graphics/drawables/lunasvg` |
| PlutoVG | 1.3.2 | MIT | `juce_graphics/drawables/lunasvg/plutovg` |
| libpng | 1.6.58 | libpng-2.0 | `juce_graphics/image_formats/pnglib` |
| jpeglib (IJG) | 10.0 | IJG | `juce_graphics/image_formats/jpglib` |
| VST3 SDK | 3.8.0 | MIT | `juce_audio_processors_headless/format_types/VST3_SDK` |
| PreSonus plug-in extensions (headers) | — | public domain | `juce_audio_processors_headless/format_types/pslextensions` |
| AudioUnitSDK | 1.1.0 | Apache-2.0 | `juce_audio_plugin_client/AU/AudioUnitSDK` |

## Vendored in a linked module but not compiled in this configuration

| Component | Licence | Why it is not compiled |
|---|---|---|
| FLAC, libogg, libvorbis, Opus, opusfile, libopusenc | BSD-3-Clause | disabled: `JUCE_USE_FLAC=0`, `JUCE_USE_OGGVORBIS=0`, `JUCE_USE_OPUS=0` |
| libwebp | BSD-3-Clause | disabled: `JUCE_USE_WEBP=0` (its files compile to empty objects; no WebP symbol is linked) |
| Oboe | Apache-2.0 | Android only |
| ASIO SDK | Steinberg ASIO licence OR GPL-3.0-only | Windows only, and only with `JUCE_ASIO=1` |
| LV2, lilv, serd, sord, sratom | ISC | LV2 hosting off (`JUCE_PLUGINHOST_LV2=0`) and no LV2 format target |
| AAX SDK | Avid AAX licence OR GPL-3.0-only | no AAX target |
| `@juce-framework/webview` | AGPL-3.0-only OR JUCE commercial | `JUCE_WEB_BROWSER=0` |

Full licence texts are in the JUCE source tree at the pinned commit, next to each component. Before any binary is
distributed, the release checklist in [docs/LICENSING.md](docs/LICENSING.md) applies: ship these notices and licence
texts with the installer and publish the exact corresponding source.

No third-party audio, fonts, images or other assets are used. The 12 Freesound recordings used for research stay
local and are not part of any build (blocker B11 in [docs/RESEARCH-CONSOLIDATION.md](docs/RESEARCH-CONSOLIDATION.md)).
