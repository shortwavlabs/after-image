# AFTERIMAGE — P1-A Qualification

**Status:** limits fixed before measurement (§1). Results are added below them; §1 is not edited after the first run.
Architecture: [P1-A-REALTIME-ARCHITECTURE.md](P1-A-REALTIME-ARCHITECTURE.md).

## 1. Limits fixed before measurement

Committed before the engine code they judge. Machine-readable copy of the parity limits:
`experiments/p0-spectral-ghost/p1a-limits.json`.

### 1.1 Anchoring the new Python reference to P0

The P1-A reference (`p1a_reference.py`) is new code. Before C++ is compared with it, it must reproduce P0:

| # | Check | Limit |
|---|---|---|
| A1 | Reference scheduler fed NumPy PCG64 draws vs `granular.schedule` | identical grain table (every field, every row) |
| A2 | Reference FILTERED reconstruction vs `granular.capture_buffer` on a selection aligned to the P0 frame grid | error ≤ −200 dB re signal |
| A3 | Reference CLOUD render vs `granular.render` for the same grain table and buffer | error ≤ −200 dB |

### 1.2 C++ against the reference

Error = `20 log10(rms(cpp − ref) / rms(ref))`. The C++ engine runs in float32 (FFT, history, buffers); the reference in
float64. The margins below allow for float32 rounding (about −140 dB per operation, accumulated over an FFT of 8192
points and sums of up to 32 grains) and nothing else.

| # | Check | Limit |
|---|---|---|
| P1 | STFT frames (complex), all four rates | ≤ −100 dB |
| P2 | FULL capture loop buffer (period and seam) | period identical; ≤ −120 dB |
| P3 | FILTERED capture loop buffer | period identical; ≤ −90 dB |
| P4 | Grain table | onsets, lengths, reverse and dropped flags identical; positions within 1e-6 samples; gains and balances within 1e-6 relative |
| P5 | Ghost output, DISSOLVE 0 (TRACE) | ≤ −100 dB |
| P6 | Ghost output, DISSOLVE 1 (CLOUD) | ≤ −80 dB |
| P7 | Ghost output, DISSOLVE 0.5 | ≤ −80 dB |

### 1.3 C++ unit tests

| Area | Pass condition |
|---|---|
| Dry path | bit-identical to the input at BODY 1 with no sounding ghost, all rates, blocks 1/16/32/64/1024 and varying, mono and stereo, including denormals and −0; latency 0; an impulse stays at its index |
| Bypass | output bit-identical to input; GHOST restarts from 0 after bypass |
| Loop period | period = `s1 − s0` exactly, FULL and FILTERED, 0.20 / 0.75 / 1.50 s, all rates |
| Seam continuity | FULL: `loop[0] = audio[s1]` and `loop[R−1] = audio[s1 − 1]` exactly; FILTERED: the same within −90 dB of the selection RMS |
| Start of history | `s0 = 0`, `1` and `H − 1` capture and play finite audio; `s0 < 0` is rejected `BEFORE_STREAM` |
| Short / maximum | 0.20 s and 1.50 s accepted; one sample shorter / longer rejected |
| Rejections | stale epoch, future, invalid band, too few bins, expired and busy each give their code and leave the playing voice untouched |
| Determinism | sample-stamped commands and fixed parameters give bit-identical output for blocks 1/16/32/64/1024 and varying blocks |
| Grain ceiling | never more than 32 sounding grains in a voice, 64 in total during a REPLACE fade, under a stress density that requests more |
| CLEAR / REPLACE clicks | on a captured sine at DISSOLVE 0, the largest second difference of the ghost within ±5 ms of the event ≤ 1.5 × its largest value in the 200 ms before; at DISSOLVE 1 ≤ 2× |
| Rapid parameters | random jumps of every parameter every block for 10 s: output finite; with a DC input and no ghost the per-sample BODY step ≤ the 20 ms ramp slope |
| Non-finite input | NaN/Inf never reach history or a loop; output finite |
| Denormals | no float32 denormal in the output of a 60 s decay after capture |
| Gain contract | TRACE at DISSOLVE 0 has the loop's RMS within 0.1 dB (MEMORY decay accounted); CLOUD on a white-noise loop within ±1.5 dB of the loop RMS; DISSOLVE 0.5 within ±1 dB |
| State | restoring state never starts a capture or a voice |

### 1.4 Benchmark (worst-case callback time)

Release build, Apple M5 Max, macOS 26.6, one process, an ordinary thread (no realtime priority), so OS preemption is
included in the maxima rather than excluded. Each configuration runs the scenario below three times; the reported
value is the worst of the three.

Scenario, stereo, per rate: 7 s of white noise to fill the history, then for 20 s an IMPRINT of a maximum-length
(1.50 s) selection every 0.5 s alternating FULL and FILTERED (so a capture is always building or a REPLACE is fading),
DISSOLVE 0.5 (TRACE and CLOUD both rendered), plus the same with a stress grain density that keeps both voices at their
32-grain ceiling. Every callback is timed.

| Block | 44.1 / 48 / 88.2 / 96 kHz | Criterion |
|---|---|---|
| 32, 64, 1024 | **gated** | max callback ≤ 50 % of the block's duration, and 99.9th percentile ≤ 25 % |
| 16 | reported against the same numbers, **not gated** in P1-A | one 96 kHz stereo frame of FFTs (measured median 23 µs, worst 70 µs) already takes 14–42 % of 167 µs |
| 1 | **correctness only** | one FFT (5–35 µs) exceeds a 1-sample period (10–23 µs); hosts that call with 1-sample blocks inside a larger device buffer must be judged on the device buffer |

Averages are reported for information and are never a pass criterion. No result here is a host or realtime PASS for
the product: that needs host measurements (blocker B7).

---

## 2. Results summary (2026-11-18)

Everything below was measured by automated tests and tools on one machine. **Nobody has listened to the C++ engine.**

| Exit criterion (brief) | Result | Evidence |
|---|---|---|
| Research consolidated on `main` | **DONE**: PRs #2–#5 merged, `main` = `2db8e2e`, verified in a clean worktree | [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md) §6–7 |
| JUCE project builds reproducibly on the tested platform | **PASS** on macOS 26.6 arm64: fresh worktree, configure (JUCE fetched by commit) 28 s, build 46 s, tests pass | §3 |
| BODY passes zero-latency dry-path tests | **PASS**: bit-identical at all rates, blocks and layouts, latency 0 | §5 |
| Capture and CLOUD run without unbounded audio-thread work | **Bounded by design and measured**, but the **benchmark gate is not met**: 23 of 24 gated rows in each of two runs; each failure is one outlier callback | §6 |
| Loop timing and capture boundaries have explicit validated behaviour | **PASS**: period = selection exactly; `s0 = 0` captures; `s0 < 0` rejected | §5 |
| IMPRINT, CLEAR and REPLACE click-safe under tested conditions | **PASS** after one fix (raised-cosine release) | §5, §9 |
| Outputs finite and bounded under a documented gain policy | **PASS** for finiteness and the documented policy; the policy itself allows BODY + GHOST above 0 dBFS | §5, architecture §9 |
| C++ reference parity measured | **PASS**: 148 of 148 rows within the pre-set limits | §4 |
| Development UI can audition real audio | **PARTIAL**: builds, is tested offline against real engine state, AU passes `auval`; not yet used by a person in a host | §7 |
| Musical value | **NOT ASSESSED** | |

## 3. Build and toolchain

| Item | Value |
|---|---|
| Machine | Apple M5 Max (18 cores), 128 GB, macOS 26.6 (25G83), arm64 |
| Compiler / SDK | Xcode 27.2 (27B52), Apple clang 21.0.0 |
| CMake | 4.4.5, Unix Makefiles generator |
| JUCE | 9.0.5, commit `d60b7a78030661574a615b586d9325ba7a7fa7dd`, AGPLv3 option |
| Targets | AU (`aufx Aftr SwLb`), VST3, Standalone, `afterimage_tests`, `afterimage_render`, `afterimage_bench` |
| Not built or claimed | Windows, Linux, AAX, LV2, signed or notarised products, installers |

Clean-build check: `git worktree add` of `f3672aa`, `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` (28 s including the JUCE
fetch), `cmake --build build -j 14` (46 s), `ctest` passes. Build warnings in project code: none.

## 4. C++ against the Python reference (§1.2)

`run_p1a_parity.py`, all four rates, FULL and FILTERED, five source/duration/DISSOLVE cases per rate and source, a
stress-density case per rate, and mono cases (FULL and FILTERED) at 48 and 96 kHz. Evidence: `experiments/p0-spectral-ghost/p1a-parity.json`.

| # | Rows | Worst measured | Limit |
|---|---:|---:|---:|
| A1–A3 reference vs P0 | 3 pytest checks | identical schedule; reconstruction ≤ −200 dB; P0's own render | as set |
| P1 STFT frames | 4 | −137.7 dB | −100 dB |
| P2 FULL loop | 26 | −155.8 dB, period identical, ρ identical to 6 decimals | −120 dB |
| P3 FILTERED loop | 22 | −135.1 dB, period identical | −90 dB |
| P4 grain table | 48 | integers identical; position 9.1e-13 samples; gains 2.1e-12 relative; 528 of 880 grains dropped identically at the stress density | 1e-6 |
| P5 TRACE output | 8 | −136.0 dB | −100 dB |
| P6 CLOUD output | 32 | −133.6 dB | −80 dB |
| P7 DISSOLVE 0.5 | 8 | −133.5 dB | −80 dB |

Cross-language differences are float32 rounding only (C++ float32 FFT, history and buffers; reference float64). The
random sequence is shared (SplitMix64), so grain timing is identical, not merely statistically similar.

## 5. C++ unit tests (§1.3)

`afterimage_tests`: 25 groups, 4,304 checks, 0 failed. Python: 164 tests (159 research + 5 reference anchors).

| Area | Measured |
|---|---|
| Dry path | bit-identical at 44.1/48/88.2/96 kHz, blocks 1/16/32/64/1024 and varying, mono and stereo, with a denormal, −0 and an impulse; latency 0 |
| Bypass | identity; after bypass the GHOST restarts from 0 (first sample 0.00033 of a 0.31 steady level) |
| Loop period and seam | period = `s1 − s0` for 0.20/0.75/1.50 s at all rates, FULL and FILTERED; FULL `loop[0] = audio[s1]`, `loop[R−1] = audio[s1−1]` exactly; FILTERED ≤ −90 dB |
| Start of history | `s0 = 0, 1, H − 1` capture and play at all rates, both sources; `s0 = −1` → `BEFORE_STREAM` |
| Rejections | `STALE_EPOCH`, `TOO_SHORT`, `TOO_LONG`, `FUTURE`, `INVALID_BAND` (3 forms), `TOO_FEW_BINS`, `EXPIRED` (FULL and FILTERED), `BUSY`: each gives its code and the playing voice's output is bit-identical to a run without it |
| Determinism | bit-identical output for blocks 1/16/32/64/1024 and varying, at 44.1 and 96 kHz, with two captures and a CLEAR |
| Grain ceiling | stress density: 32 per voice reached, never exceeded; 33–64 in total only during REPLACE |
| CLEAR / REPLACE | second-difference ratio near the event: TRACE 0.956–0.961 (limit 1.5), CLOUD 0.450–0.641 (limit 2.0), all rates |
| Rapid parameters | 10 s of random jumps every 64 samples: BODY step never above the 20 ms ramp slope; with a ghost, finite and below 8 |
| Non-finite input | 500 NaN/Inf samples inside a selection: 500 counted, loops and output finite |
| Denormals | 60 s decay after a capture through the processor: no float32 denormal; voice retired |
| Gain contract | ghost RMS re loop RMS (decay removed): D 0 +0.001 dB (±0.1), D 0.5 −0.51 dB (±1), D 1 −1.07 dB (±1.5) |
| Post-roll seam | ρ = 1.000 for a continuing tone; ρ = 0.000 with silent post-roll, loop starts at 0, output finite |
| State | restoring state never starts a capture or voice |
| Silence and transients | a capture of digital silence plays exact zeros with ρ = 0; an impulse inside the selection recurs at exactly the same offset in each of four periods (48 and 96 kHz, FULL and FILTERED) |
| Mono | parity at 48 and 96 kHz, FULL and FILTERED (§4), and the dry-path tests |
| Allocations | macOS `malloc_logger` filtered to the audio thread, with a positive control: **0 allocations** in 3,000 blocks of 64 samples containing captures, REPLACE, CLEAR and host-style automation of every parameter on that thread, with the editor closed and open |
| Spectrogram mapping | after a display-FIFO overflow leaves a time gap, every column's centre maps to its own x and back (≤ 1 sample, < 0.01 px) |
| Editor | status text matches the engine's real state (idle, `TOO_SHORT`, a 750 ms FILTERED capture); an off-thread parameter change reaches the knob only on the next poll |

### Request-to-sound delay

Worst case: a maximum-length (1.50 s) selection ending at the newest sample, so the capture must wait for its post-roll.

| | 44.1 kHz | 48 kHz | 88.2 kHz | 96 kHz |
|---|---:|---:|---:|---:|
| FULL | 107.8 ms | 107.3 ms | 106.8 ms | 106.3 ms |
| FILTERED | 264.6 ms | 263.3 ms | 211.2 ms | 210.3 ms |

When the post-roll is already in the history (parity cases, selection ending ≥ 1.25 s before IMPRINT): 5.7–106 ms.

## 6. Worst-case callback benchmark (§1.4)

Evidence: `docs/evidence/p1a-bench.json` (run 1, engine at `bd449b6`), `docs/evidence/p1a-bench-final.json` (run 2, clean
build of `f3672aa`), `docs/evidence/p1a-bench-rt.json` (supplementary), `docs/evidence/p1a-bench-diagnostic.txt`.

**Gate result: NOT MET.** Each run passes 23 of the 24 gated rows (blocks 32, 64, 1024 × four rates × two densities)
and fails one, each on a single outlier callback:

| Run | Failing row | Max | 99.9th percentile |
|---|---|---:|---:|
| 1 | 88.2 kHz, block 32, stress | 5,811 µs (1,602 % of 363 µs) | 72 µs (19.9 %) |
| 2 | 96 kHz, block 32, stress | 339 µs (102 % of 333 µs) | 78 µs (23.5 %) |

Diagnosis (not a gate): 20 repeats of run 1's failing row on an ordinary thread gave 92–102 µs in 18 and 385/933 µs in
2; 20 repeats on the Mach time-constraint policy (what a host's audio thread uses) stayed at 85–94 µs. The supplementary
run with that policy for every row also passed 23 of 24, failing 96 kHz / block 32 / stress on the 99.9th percentile
(25.9 % against 25 %; max 28 %). The engine's own work per 32-sample callback at 96 kHz is about 90–100 µs worst case
(one stereo pair of 8192-point FFTs plus 64 grains); the gate failures are OS scheduling outliers on an ordinary thread,
and the stress setting at 96 kHz sits at the p99.9 bound. The gate was not relaxed.

Representative rows (run 2, final code):

| Density | Rate | Block | Deadline | Max | 99.9th pct | Median |
|---|---:|---:|---:|---:|---:|---:|
| CLOUD | 48 kHz | 32 | 667 µs | 51 µs (7.7 %) | 36 µs | 0.75 µs |
| CLOUD | 48 kHz | 1024 | 21.3 ms | 290 µs (1.4 %) | 290 µs | 54 µs |
| CLOUD | 96 kHz | 32 | 333 µs | 89 µs (26.7 %) | 68 µs | 0.75 µs |
| CLOUD | 96 kHz | 64 | 667 µs | 202 µs (30.3 %) | 95 µs | 1.5 µs |
| CLOUD | 96 kHz | 1024 | 10.7 ms | 603 µs (5.6 %) | 576 µs | 83 µs |
| stress | 96 kHz | 32 | 333 µs | **339 µs (101.7 %)** | 78 µs | 3.5 µs |
| stress | 96 kHz | 1024 | 10.7 ms | 672 µs (6.3 %) | 651 µs | 173 µs |

Block 16 (reported, not gated): up to 54–57 % of the deadline at 88.2/96 kHz, and one 1,107 µs outlier in run 2.
Block 1 (correctness only): 49–121 µs typical maxima against a 10–23 µs period, as expected; one 6.3 ms outlier.
FFT unit times: 4096-point 5.3 µs median, 8192-point 11.4 µs median (single channel).

Averages are in the JSON for information only. Nothing here is a host-level realtime PASS (blocker B7).

## 7. Host validation

| Check | Result |
|---|---|
| `auval -v aufx Aftr SwLb` | **AU VALIDATION SUCCEEDED** (`docs/evidence/p1a-auval.txt`); explicit channel capabilities `[1, 1]`, `[2, 2]`; latency and tail properties verified. The AU was copied to `~/Library/Audio/Plug-Ins/Components` for the run and removed afterwards |
| VST3 validator, pluginval | **not run**: not installed, and not downloaded without approval |
| DAW sessions, automation with the editor open, offline bounce, multiple instances | **not run** |
| Standalone | builds; it uses the audio input device, so it cannot audition files by itself |

## 8. What the development UI does and does not do

It shows the engine's own analysis (4 s, 160 log bands), lets you drag a time-frequency rectangle (the view holds
still while dragging), and sends a sample-exact IMPRINT with the current SOURCE; CLEAR fades the ghost. Status shows the
capture state, the last rejection code, the last capture's selected duration, loop period, seam, ρ and request-to-sound
delay, the output peak with an over-0 dBFS counter, and non-finite input. Snapshot: `docs/evidence/p1a-dev-ui.png`.

Not done: no optical-instrument styling, no Blender assets, no MOTION/WIDTH, no preset UI, no keyboard access, no
display of the ghost itself. It was exercised by an automated test, not by a person in a host.

## 9. Failed or replaced in P1-A

| What | What happened |
|---|---|
| Linear REPLACE/CLEAR fade-out | Its slope corner measured 1.499× the signal's own second difference at 88.2 kHz (limit 1.5); passed only by the sine's phase. Replaced by a raised cosine: ≤ 0.96 everywhere |
| Tools linking the plugin's shared-code target | Did not see JUCE headers. Replaced by one interface library compiled into each target |
| AU manufacturer code `Swlb` | Did not match the other Shortwav Labs plugins (`SwLb`); changed before any release |
| Benchmark gate | Not met in two runs (§6) |
| Spectrogram time mapping | Drawn by column index but mapped by linear time between the first and last column, so a gap in the columns (left by a FIFO overflow, or by dropping columns while a drag held the view) shifted selections off the audio they marked. Found in review; both directions now go through the column index, columns are left queued (not dropped) during a drag, and stale columns are discarded when the editor opens. Test added |
| Three first-run test failures | All test bugs (a request stamped before its selection ended, a step check including the first sample, a wrong decay expectation), fixed in the tests; the engine was not changed for them |

## 10. Blocker register after P1-A

From [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md) §5. Every item stays open until it is verified in a host and,
where it matters, by ear.

| # | Blocker | P1-A status |
|---|---|---|
| B1 | Loop shorter than the selection | **Resolved in the C++ engine** (period = selection, post-roll seam, tested). Open: whether post-roll sounds right; UI selections are drawn on a hop grid |
| B2 | Capture at sample 0 | **Resolved in the C++ engine** (tests at `s0 = 0, 1, H − 1`). The Python P0-C bug is documented, not fixed |
| B3 | BODY + GHOST headroom | Policy documented, peak/overs shown in the UI, no limiter. Not measured in a host mix |
| B4 | Coherent accumulation, crest factor | Overlap normalisation as P0-B; CLOUD on noise within −1.07 dB of the loop. Crest not re-measured in C++ |
| B5 | Transposition aliasing | Pitch off in P1-A; no anti-alias stage exists |
| B6 | Capture burst | **Bounded**: one frame of FFTs per 64 samples, never with an analysis hop; measured in §6 |
| B7 | Small-buffer realtime | Gate not met on an ordinary thread (§6); no host measurement |
| B8 | Sample-rate / FFT changes | Four rates tested; `prepareToPlay` rebuilds and bumps the epoch. Rate changes during a session not tested in a host |
| B9 | Stereo and mono compatibility | Stereo preserved by design (same position, positive balance); mono in/out tested (parity, dry path); mono fold-down of a stereo ghost not measured in C++ |
| B10 | Automation and state restore | Unit tests (restore, malformed state, bypass, polled UI links) and `auval`. No DAW session; decimal-comma locale not tested |
| B11 | Freesound licences | Unchanged: unknown |
| B12 | No realtime C++ measurement | Offline C++ benchmark exists (§6); host measurement still missing |

Realtime rules (no allocation, lock or blocking call in the callback): allocations **measured** at 0 (§5); locks and
blocking calls checked by inspection only.

Further known limitations: one capture builds at a time (`BUSY`); SOURCE applies at IMPRINT only; GHOST defaults to
−6 dB, which is a starting point, not a measured choice; FOCUS and GLITCH are not implemented.

## 11. Next milestone

**P1-B: host qualification and first listening of the C++ engine.**

1. Owner auditions the AU/VST3 in a DAW on the real recordings: does the C++ CLOUD with parallel DISSOLVE sound like the
   P0 renders the owner picked, and does the post-roll seam work on drums and sustained notes?
2. Host measurements: callback timing inside a host at 96 kHz / 32 and 64 samples with the editor open; pluginval
   (after approval to install it); automation with the editor open; offline bounce; several instances.
3. Decide the headroom default (B3) from a real BODY + GHOST mix, and whether the benchmark gate needs the host's thread
   policy to be meaningful.
4. Only then FOCUS (position CDF at capture time), and GLITCH behind an experimental flag.
