# AFTERIMAGE — Research Consolidation (P0-A, P0-B, P0-C, real-audio qualification)

**Date:** 2026-11-18. **Status:** consolidation record and **provisional** product decisions. Nothing here is a
release, a musical sign-off, or a realtime qualification.

This document is the single place that says what the offline research established, what the owner heard, what was
decided from that, and what is still blocking a product. The four phase reports are **immutable evidence**: they are
not edited, and where their wording is now out of date (for example "nobody has listened"), this document carries the
correction.

| Phase | Report | PR | Head verified before merge |
|---|---|---|---|
| P0-A spectral ghost feasibility | [P0-A-FINAL-REPORT.md](P0-A-FINAL-REPORT.md) | shortwavlabs/after-image#2 | `0d755ba` |
| P0-B spectral granular cloud | [P0-B-FINAL-REPORT.md](P0-B-FINAL-REPORT.md), [architecture](P0-B-SPECTRAL-GRANULAR-ARCHITECTURE.md) | shortwavlabs/after-image#3 | `62a3d26` |
| P0-C frequency-dependent dissolution | [P0-C-FINAL-REPORT.md](P0-C-FINAL-REPORT.md), [architecture](P0-C-FREQUENCY-DEPENDENT-ARCHITECTURE.md) | shortwavlabs/after-image#4 | `f80845d` |
| Real-audio qualification | [REAL-AUDIO-QUALIFICATION.md](REAL-AUDIO-QUALIFICATION.md) | shortwavlabs/after-image#5 | `dd39766`, plus the consolidation commits on that branch |

## 1. What each phase established — three separate verdicts

Each report keeps **technical**, **musical** and **realtime** verdicts apart. The musical column below is updated from
the owner's blind listening (section 2); the technical and realtime columns are the reports' own.

| Phase | Technical (numerical) | Musical (human listening) | Realtime (C++ measurement) |
|---|---|---|---|
| P0-A | PARTIAL overall: reconstruction, capture, Loop and Sustain PASS their limits; known artifacts K1–K9 | Owner preferred the spectral Loop in 3 of 4 synthetic cases, freeze in 1, Sustain in none | **NOT ASSESSED** |
| P0-B | PASS on the seven feasibility criteria; spectral selection ≈ pre-filter, spectral guide ≈ broadband guide | Granular cloud preferred over the P0-A Loop in both engine sets; parallel DISSOLVE preferred over structural in both; unfiltered capture preferred in both on/off sets, with the receding level described as desirable | **NOT ASSESSED** |
| P0-C | PASS on the seven criteria; "spectral SPLIT distinguishable from conventional multiband" NOT SUPPORTED | Static SPLIT S1 lost to CLOUD/FOCUS in both synthetic guitar sets; on synthetic drums the S3 and S2 keep-low journeys were preferred over parallel; no guitar journey preferred | **NOT ASSESSED** |
| Real audio | 12/12 captures render, no non-finite output; defects listed in §6 of that report | Owner picks across 6 sets: S3 ×2, CLOUD ×3 (one with FOCUS also liked), FOCUS ×1; progressions: parallel ×1, S2 keep-low ×1 | **NOT ASSESSED** |

**Supersession of report wording.** P0-B, P0-C and the real-audio report each state that nobody had listened when they
were written. That was true at the time and the reports keep it. Listening happened afterwards and is recorded only in
the PR discussions and in section 2 below; the four `listening-notes*.md` templates in
`experiments/p0-spectral-ghost/` are still the unfilled templates (verified unchanged in git).

**Unsuccessful approaches are preserved** in the reports and are not repeated here: P0-A §6 (K1–K9) and §5
(freeze_random), P0-B §10 (U1–U7), P0-C §12 (F1–F6), real-audio §3 (two amended selection rules) and §6.1 (capture
failure). Every original verdict table is unchanged.

## 2. Owner listening record

The owner's picks were posted to the PR discussions on 2026-11-18 together with a mapping reconstructed from the
committed shuffle code. **Each mapping below was checked against the local, git-ignored answer key on 2026-11-18;
all 23 agree.** The keys are `renders/blind/KEY-do-not-open.json` (P0-A), `renders/p0b/…`, `renders/p0c/…` and
`renders/real-audio/blind-KEY-do-not-open.json`.

| Phase | Blind set | Pick | Render (from the local key) | Posted (UTC) |
|---|---|---|---|---|
| P0-A | guitar/full_spectrum | B | `loop_aligned80` | 17:02 |
| P0-A | guitar/long_sustain | C | `loop_aligned80` | 17:02 |
| P0-A | vocal/narrow_harmonic | B | `freeze_delta` | 17:02 |
| P0-A | synth/full_spectrum | A | `loop_aligned80` | 17:02 |
| P0-B | guitar long_sustain dissolve | B | `progression_parallel` | 18:36 |
| P0-B | drums full_spectrum dissolve | B | `progression_parallel` | 18:36 |
| P0-B | guitar long_sustain engine | A | `cloud_guided_harmonic` (FOCUS) | 18:40 |
| P0-B | drums full_spectrum engine | C | `cloud_spectral` (CLOUD) | 18:40 |
| P0-B | guitar long_sustain on/off | B | `cloud_conventional` (unfiltered) | 18:45 |
| P0-B | synth upper_harmonics on/off | C | `cloud_conventional` (unfiltered) | 18:45 |
| P0-C | guitar_dist cloud_vs_split | C | `p0b_cloud` | 20:41 |
| P0-C | guitar long_sustain cloud_vs_split | C | `p0b_focus` | 20:41 |
| P0-C | guitar_dist progression | none | (no journey preferred) | 20:43 |
| P0-C | drums progression | B | `progression_s3` | 20:43 |
| P0-C | drums progression | D | `progression_s2_keep` (also liked, unranked) | 20:43 |
| Real | 01 distorted guitar, engines | C | `split_s3_100` | 21:37 |
| Real | 03 drum break, engines | B | `p0b_focus` | 21:37 |
| Real | 05 vocal, engines | A | `p0b_cloud` | 21:37 |
| Real | 07 synth pad, engines | D | `split_s3_100` | 21:37 |
| Real | 04 drum break, progression | C | `progression_parallel` | 21:41 |
| Real | 06 vocal, progression | B | `progression_s2_keep` | 21:41 |
| Real | 13 metallic percussion, engines | C | `p0b_cloud` | 21:44 |
| Real | 15 dense percussion, engines | D | `p0b_cloud` (C = `p0b_focus` also liked) | 21:44 |

Owner remarks recorded in those comments, kept because they shaped the decisions:

- P0-B: the parallel morph "starts as a delay and goes into a granular sound in the tail end".
- P0-B: the level drop of the unfiltered cloud was liked, not a defect ("i picked those because it has that effect").
- P0-C: the S3 drum journey had "more complex grain patterns" and "sounded more glitchy", which the owner likes.
- Real audio: the effects "sound more interesting on short sounds (drums, vocals) than on sustained notes".

Limits of this record: 23 picks by one listener, mostly first impressions, no scores, no repeated trials. Ten sets of
the real-audio pack and most P0-C sets were not auditioned. P0-A and P0-B use synthetic sources only.

## 3. Provisional product decisions

These are **provisional** and can be reversed by later listening. They are the brief the P1 implementation works to.

| Area | Decision | Evidence | Status |
|---|---|---|---|
| **CLOUD** | Core engine: unguided granular synthesis over the captured buffer. Leading all-round candidate. | Preferred in 5 of the 10 auditioned engine sets (P0-B 1, P0-C 1, real audio 3); FOCUS 3, S3 2 | Core, P1-A |
| **FOCUS** | Core engine: guided grain selection (harmonic position CDF). Alternative grain character. | Preferred on synthetic guitar sustain (P0-B, P0-C) and real drum break; also liked on dense percussion | Core, deferred to after CLOUD is realtime-qualified |
| **GLITCH** | Experimental engine based on P0-C S3 (band-dependent grain length, spray, spread, reverse). Implementation preserved in `p0/split.py`. **Not committed as a third MVP mode.** | Won 2 real-audio sets (distorted guitar, synth pad) and the synthetic drum journey; lost on metallic and dense percussion, where its glitch metric was highest | Experimental, not in MVP |
| **DISSOLVE** | Default transformation is the simple parallel TRACE → CLOUD crossfade. S2 and S3 progressions are not the default. | Parallel preferred in both P0-B dissolve sets and the real drum progression; S2 keep-low won the vocal progression (5 % of that selection is below 250 Hz); no guitar journey preferred | Default, P1-A |
| **SOURCE** | FULL and FILTERED capture stay as separate user-facing choices, independent of the engine. | Unfiltered preferred in both P0-B on/off sets; owner asked to keep both | Both in P1-A |
| **SPLIT** | Research reference only. The spectral multiband implementation is not a production requirement. If multiband behaviour ships later, conventional crossovers are the default candidate. | Spectral and conventional within seed-to-seed distance on 11 of 12 synthetic comparisons and most real sources; 6× capture cost for spectral bands; one real exception (acoustic pluck, 2.74 dB around the 250 Hz slope) | Not in MVP |

Orthogonality is kept as the P0-B review proposed: engine (CLOUD / FOCUS / later GLITCH), SOURCE (FULL / FILTERED) and
DISSOLVE are independent controls, so adding an engine later does not add modes to SOURCE or DISSOLVE.

Not decided and not to be inferred from the above: crossover frequencies, grain parameter values for the product,
pitch/octave behaviour (P0-B default had octave jumps; all P0-C/real comparisons used no transposition), MOTION and
WIDTH (never researched), the headroom policy (§5, B3–B4).

## 4. Documentation conflicts resolved

The documents merged in shortwavlabs/after-image#1 describe a **spectral-only** ghost: a spectral frame loop (candidate A)
or a phase-continuous spectral sustain (candidate B), resynthesised by IFFT. The research moved the GHOST to
**granular synthesis over a captured time-domain buffer**, with the STFT history used for analysis, selection and
FILTERED capture.

| Topic | Original concept (PR #1 docs) | Current direction |
|---|---|---|
| GHOST synthesis | Spectral Loop (A) or spectral Sustain (B), no winner | Granular CLOUD; the spectral Loop survives as the TRACE end of DISSOLVE |
| Role of the STFT history | Source of resynthesised frames | Analysis, time-frequency selection, FILTERED mask, capture reconstruction |
| Ghost modes | Engine A/B development switch | CLOUD (core), FOCUS (core, later), GLITCH (experimental) |
| Transformation | MOTION (bounded drift) | DISSOLVE (TRACE → CLOUD); MOTION and WIDTH remain unresearched |
| Filtering | Always the painted ROI | SOURCE = FULL or FILTERED |
| "More than spectral freeze" gate | P0 go/no-go | Passed in the owner's ears for granular over Loop and freeze; not tested against third-party granular or freeze products |

What changed in the living documents (dated supersession notes, original text kept for history):

- [PRD.md](PRD.md): status note, decision log items 2 and 3 resolved or narrowed, DISSOLVE / SOURCE / engine added to MVP controls.
- [ROADMAP.md](ROADMAP.md): Phase 0 marked complete with pointers; Phase 1 rewritten as P1-A.
- [DSP-ARCHITECTURE.md](DSP-ARCHITECTURE.md): status note; §6–§7 (spectral Loop / Sustain) marked superseded for the GHOST; the BODY, analysis, history, capture-safety and host contracts remain normative.
- [RFC-001-spectral-engine.md](RFC-001-spectral-engine.md), [UI-CONCEPT.md](UI-CONCEPT.md), [README.md](../README.md): status notes.

## 5. Blocker register

All items are **OPEN**. None is closed by the Python experiments passing; each needs a measured result in the C++
implementation or an owner decision.

| # | Blocker | Evidence | Needed to close |
|---|---|---|---|
| B1 | The loop period is about 80 ms (the seam crossfade) shorter than the drawn selection; one real drum bar is still 14 ms short after the selection was lengthened | Real-audio §3 (amendment 2); P0-B architecture (`periodic_pair`) | A loop-duration contract where the repeating period equals the selected duration, with continuity, and a test that measures both |
| B2 | Capture fails with an unhandled shape error when the selection starts at sample 0 | Real-audio §6.1 | Selections at the start of history either capture (zero context) or are rejected with a defined error; regression test |
| B3 | BODY + GHOST headroom: four real-audio mixes exceed 0 dBFS (up to +1.02 dBFS); research renders are RMS-matched, so no natural wet/dry balance has been measured | Real-audio §6.2–6.3 | A documented production gain contract and measured peaks at the plugin output; no hidden limiter |
| B4 | Coherent granular accumulation (+13 dB on a tone at full overlap) and crest factor rising up to +12 dB at equal RMS | P0-B §8, P0-C §10, real-audio §6.3 | Overlap normalisation chosen and measured on tones, noise and real sources |
| B5 | Upward grain transposition aliases at full level above fs/4 | P0-C §10 (aliasing), P0-B K7 | Pitch kept off by default, or an anti-alias stage measured |
| B6 | Capture-time computational burst: capture reconstruction is many IFFTs (P0-B ~140, spectral SPLIT ~830–900) | P0-B §9, P0-C §11 | Bounded, scheduled capture with measured worst-case callback time |
| B7 | Small-buffer realtime execution (1–64 samples, 96 kHz) never measured | All reports: realtime NOT ASSESSED | Worst-case (not average) callback benchmark in a release build |
| B8 | Sample-rate and FFT configuration changes | DSP-ARCHITECTURE §1.2, §3.2 | Reconfiguration on prepare, epoch invalidation, tests at 44.1/48/88.2/96 kHz |
| B9 | Stereo preservation and mono compatibility (wide sources lose 2.5–2.9 dB in mono; engines add up to 0.8 dB) | P0-A K2–K3, real-audio §6.4 | Stereo tests in C++; mono fold-down measured on the plugin output |
| B10 | Host automation and state restoration (no IMPRINT on restore, parameter persistence, bypass) | DSP-ARCHITECTURE §11 | Host-level tests and validation in at least one host and `auval` |
| B11 | Licences of the 12 Freesound recordings unknown; no Freesound IDs in the files | Real-audio §7 | Owner fills the provenance table; until then no redistribution of the audio or renders |
| B12 | No realtime C++ performance measurement exists | All reports | C++ benchmarks (P1-A onwards) |

## 6. Integration gates run before merging

Run on 2026-11-18 against the PR heads listed above, before any merge. "Clean worktree" means a fresh
`git worktree` of `dd39766` with an empty `inputs/` folder and `uv sync --frozen`.

| # | Gate | Result |
|---|---|---|
| 1 | All existing tests | **PASS**: 158 passed in the clean worktree (206 s). With the guard below: 159 passed in the main checkout, with the 12 recordings present |
| 2 | Reproduce committed numerical evidence without overwriting it | **PASS**. In the clean worktree, `run.py`, `run_p0b.py` and `run_p0c.py all --no-wav` regenerated every verification and metrics file **byte-identical** (361, 80 and 93 renders, 0 failures). Only the three manifests (one line: the recorded commit) and the three NumPy timing files changed. Real audio: with the 12 WAVs (no sidecars) copied into the worktree, `run_real.py inventory`, `regions` and `render` reproduced `real-audio-inventory.json` and `real-audio-regions.json` byte-identical and `real-audio-metrics.json` / `real-audio-manifest.json` **value-identical** (all 324 metric entries and 168 render entries equal). Their key order differs because the committed files were last written by the single-source re-run of §9 of that report, which appends the re-run source at the end. |
| 3 | Local recordings cannot contaminate committed evidence | **FIXED and verified**. Before: every loader globbed `inputs/`, so a default run would have added 12 user sources and rewritten the committed P0-A/B/C files. Now `experiment.evidence_inputs()` lets user WAVs into a run only when `--only` names a `user_…` source; default runs see the synthetic fixtures alone. Regression test `test_default_runs_never_read_local_recordings`. Proved in the main checkout with all 12 recordings present: `run_p0b.py render --no-wav` used no user source and left `p0b-metrics.json` unchanged (manifest restored afterwards). `run_real.py` and `--only user_<name>` are unaffected. No `blind` command was run, so no answer key was touched. |
| 4 | No third-party audio or unlicensed assets tracked | **PASS**. No audio file was ever added in any ref (`git log --all --diff-filter=A`). The only non-text files ever committed are `LICENSE` and an `experiments/.DS_Store` (Finder metadata) that was added in `d5bdec6` and removed in `0d755ba` on the P0-A branch; it remains in history and holds no audio. Largest tracked blob: `real-audio-metrics.json`, 390 kB. The real-audio JSON names the recordings and two embedded author tags; that is metadata, not audio. |
| 5 | Reports preserve failures and original verdicts | **PASS**. P0-A §6 K1–K9, P0-B §10 U1–U7, P0-C §12 F1–F6, real-audio §3/§6.1 are intact; no report file is modified by the consolidation. |
| 6 | Owner feedback in PR discussions matches the listening notes | **PARTIAL, recorded as is**. All 23 PR-reported picks match the local answer keys (§2). The four `listening-notes*.md` files were never filled in, so they do not contradict the PR record but do not contain it either; §2 is now the record. |
| 7 | Spectral-only concept vs granular direction | **RESOLVED** in the living documents with dated notes (§4); historical text kept. |
| 8 | Every report separates technical PASS, musical approval and realtime | **PASS with one note**. P0-A, P0-B and P0-C have explicit three-way verdict tables. The real-audio report states "everything below is measurement" and "nobody has listened" and lists realtime cost as not measured, without a verdict table; §1 above supplies it. |

Root cause of blocker B2, found during the gates: `p0/split.py` `decompose_iir()` cuts the conventional-band
selection with `x[start:start + samples]`. For a selection starting at 0 s, `start` is −512 (half a hop before 0,
because the capture is centred on frame windows), and a negative Python slice start counts from the end of the array,
giving an empty `(0, 2)` slice. The spectral path pads correctly. The research code is left unchanged; the C++
implementation must treat samples before the stream start as silence.

## 7. Merge record

Filled in after the merges.
