# AFTERIMAGE — Licensing and Release Policy

**Decision date:** 2026-11-18  
**Original project code:** GNU Affero General Public License version 3.0 only (`AGPL-3.0-only`)  
**Framework:** JUCE 9 under its AGPLv3 path, subject to verification against the pinned release  
**Official distribution:** GitHub Releases for macOS and Windows  
**Status:** Policy adopted; installers and DSP have not been built.

## Why this license

AFTERIMAGE is intended to remain free and open source. AGPLv3 is a straightforward reciprocal match for JUCE's open-source AGPL option. The full unmodified license text is in [LICENSE](../LICENSE). Use the SPDX expression `AGPL-3.0-only` for original source.

Users can run, inspect, modify and redistribute the code under AGPLv3 terms. The license does **not** restrict redistribution merely because Shortwav Labs has no plans to sell the plugin. Contributors must have the rights to submit the work under the project's terms.

JUCE code, third-party components, fonts, Blender source files, texture assets and sample audio need their own provenance checks and attribution where applicable. No copyright or trademark licence for the Shortwav Labs name or logos is implied by the software licence.

## GitHub Releases: product distribution contract

The [GitHub Releases page](https://github.com/shortwavlabs/after-image/releases) is the canonical user-facing download location. Target assets:

- `AFTERIMAGE-vX.Y.Z-macOS-universal.pkg` — installer containing AU and VST3; universal arm64/x86_64 **only if** both architectures pass validation.
- `AFTERIMAGE-vX.Y.Z-Windows-x64-Setup.exe` — installer containing VST3; build/installation tested on Windows x64.
- `SHA256SUMS.txt` — SHA-256 digests of the uploaded binaries.
- `THIRD_PARTY_NOTICES.txt` — required third-party notices/attribution (or a documented equivalent included inside installer).
- Version-tagged corresponding source via GitHub release archive/tag, plus build/reproduction instructions; if corresponding source requires additional materials not present in that tag, attach or link a complete source bundle.

**Packaging forms are proposed**, not yet selected or verified. If macOS universal is not qualified, release an explicitly labeled arm64-only installer rather than claiming universal support. If an installer builder brings non-redistributable bundled dependencies, resolve before publication.

### Installer installation targets (to qualify)

- macOS AU: `/Library/Audio/Plug-Ins/Components/`; VST3: `/Library/Audio/Plug-Ins/VST3/` (system-wide installation with authorization) or documented per-user equivalents.
- Windows VST3: `C:\Program Files\Common Files\VST3\` (standard system-wide location).

Installer and uninstall behavior must be verified against clean test machines or clean virtual machines. Never describe a build as signed/notarized, universal, or host-compatible without direct evidence.

### macOS

- Sign plugin binaries, their bundles and installer appropriately with Developer ID identities.
- Notarize the shipped installer and staple where applicable.
- Verify Gatekeeper acceptance and AU/VST3 discovery on a clean target macOS installation.
- Test AU in Logic, VST3 in a representative host, and run `auval`/`pluginval` where applicable.

### Windows

- Build VST3 x64 and installer on Windows; verify installation, DAW scan/loading, preset handling, bypass and uninstall.
- Code-sign the installer **if signing credentials are available** and document SmartScreen limitations if unsigned; do not misrepresent an unsigned installer as a trusted download.
- Run appropriate plugin validation and actual DAW smoke tests.

## AGPL release checklist

1. Include full `LICENSE` and required notices with the repository and release distribution.
2. Provide complete corresponding source for the exact shipped binary, with matching release tag, build instructions, build scripts and any applicable source for linked/distributed components as required by the licence.
3. Maintain dependency/asset licence inventory: component, version, source, licence, copyright and notice obligations.
4. State the licence prominently in README, releases and About UI; retain copyright and attribution.
5. Don't bundle third-party sample recordings or fonts without distribution permission.
6. Check the official Jam rules immediately before release for delivery, rights, disclosure and deadline requirements.

## Proposed versioning and CI workflow

- Development: feature branches → reviewed pull requests → `main`, with reproducible CMake/JUCE dependency version.
- Candidate: `v0.1.0-rcN` prereleases, built and tested on each OS; retain logs and checksums.
- Release: annotated immutable `v1.0.0` tag after test gates; GitHub Release with downloadable installers, checksums, source pointers, notes and known limitations.
- CI may automate building/package construction; signing secrets must never enter the source repository.
- Manual signing/notarization and host validation are acceptable if fully reproducible/documented. Don't publish generated installers as validated until executed on target systems.

## Release acceptance gates

- [ ] macOS and Windows builds from same release tag.
- [ ] Installer installs to correct plugin directories and optionally uninstalls cleanly.
- [ ] Plugin scan, real audio playback, capture, clear, automation, state restore and bypass validated on both platforms.
- [ ] auval/pluginval applicable tests pass or documented exceptions reviewed.
- [ ] macOS Developer ID signing, notarization and Gatekeeper verification pass.
- [ ] Windows signing choice and SmartScreen behavior disclosed.
- [ ] License, corresponding source, notices, version tags and SHA-256 checksums published.
- [ ] Clean-machine install guide and release notes included.
- [ ] Official contest submission points at the validated GitHub Release artifacts.

## Open decisions

- Choose installer builders and Windows signing arrangement.
- Confirm macOS x86_64 coverage; otherwise ship arm64 first.
- Decide whether Blender project/source art will be included in full repository or published as separate distributable assets with explicit licenses.

**This policy replaces earlier “not planning to distribute” wording. AFTERIMAGE will be available as a free GitHub Release for macOS and Windows, subject to successful qualification.**
