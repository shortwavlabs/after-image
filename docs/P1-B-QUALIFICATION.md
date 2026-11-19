# AFTERIMAGE — P1-B Qualification

**Status:** §0–§1 are fixed before any P1-B behaviour is implemented (Stage A) and are not edited afterwards. Results are
added below them. Design: [P1-B-CAPTURE-ARCHITECTURE.md](P1-B-CAPTURE-ARCHITECTURE.md), behaviour:
[P1-B-UX-CONTRACT.md](P1-B-UX-CONTRACT.md).

## 0. Starting point and what P1-B can claim

- Branch `feature/p1b-performance-capture` from P1-A head `b0c437f` (shortwavlabs/after-image#6, draft, not merged).
- **P1-A scope exception, recorded as the owner asked:** P1-A's precommitted callback-deadline gate was not met (two
  runs each failed 1 of 24 gated rows; the realtime-policy run failed 96 kHz / 32 / stress at the 99.9th percentile,
  25.9 % against 25 %). P1-A nevertheless continued into the development UI and documentation. That was a scope
  exception, not an approval of realtime safety; the P1-A gate remains open and is not re-judged here.
- **E1 baseline, run before any P1-B change:** the unchanged P1-A benchmark on `b0c437f` (same binary scenario,
  ordinary thread, worst of 3 × 20 s) passed 24 of 24 gated rows in this run
  (`docs/evidence/p1b-E1-baseline-p1a-b0c437f.json`). With the two earlier runs, identical code has now failed in
  2 of 3 runs. This is baseline evidence only; it does not change the P1-A verdict.
- **Best verdict available to P1-B is PARTIAL.** Neither Logic nor Live can be operated from this environment, and
  musical quality needs the owner's ears, so host-DAW qualification and listening can at most be prepared, not
  passed. P1-B is FAIL if a Stage B hard gate fails.

## 1. Limits fixed before implementation

### 1.1 Stages, hard gates and stop rule

| Stage | Gate type | Consequence of a failure |
|---|---|---|
| B — MANUAL + HOLD | **hard** (B1–B10) | stop; report; no Stage C |
| C — RANDOM | **hard** (C1–C7) | stop; report; no Stage D |
| D — AUTO | **experiment limits** (D1–D6) | AUTO stays labelled EXPERIMENTAL / UNRELIABLE in the UI and docs; Stage E continues |
| E — host and realtime | **hard** (E2–E4), run in this order: E2 → E3 → E4 | stop at the first failing step; no later gated step runs |
| E5 — diagnostics | evidence only, never a gate | allowed after a failure, to characterise it |

E1 (baseline above) is informational. Gated benchmark runs are uninstrumented and use the same scenario code and
thresholds as P1-A; instrumented runs (thread CPU time, overhead breakdown) are separate and labelled.

### 1.2 Stage B — MANUAL and HOLD (hard)

| # | Check | Limit |
|---|---|---|
| B1 | Existing suites | P1-A C++ tests (25 groups, 4,304 checks) pass with no change to their expectations; 164 Python tests pass; parity 148/148 with every value identical to the committed `p1a-parity.json` |
| B2 | Golden output | `afterimage_render` output for a fixed fixture and stamped commands is SHA-256-identical to the same render built from `b0c437f` (MANUAL default, no other trigger) |
| B3 | Selection exactness | for every LENGTH and all four rates: `s1` = trigger sample, `s0 = s1 − round(L·Fs)` exactly, for button, MIDI and automation origins; MIDI at offsets 0, 1, 17 and B−1 in blocks of 64 and 512 gives `s1 = block start + offset` |
| B4 | Automation edge | a rising edge captures once; holding "on" for 100 blocks captures once; "on" restored by state, by `prepareToPlay` or by un-bypassing captures 0 times; a pulse of ≥ 1 block always captures |
| B5 | HOLD | (a) HOLD before any ghost: 0 RANDOM/AUTO captures over 20 s of active input, suppressions counted, MANUAL still captures; (b) HOLD with a ghost: the ghost's capture is unchanged for 20 s; (c) explicit IMPRINT replaces under HOLD; (d) 100 toggles at random block boundaries over 10 s: output finite, no capture earlier than 0.75 × interval after a release; (e) the held ghost retires when MEMORY says so |
| B6 | Busy | triggers every 20 ms: at most one job at any time; triggers during a job are `BUSY`; nothing queued |
| B7 | Bypass | triggers of every origin during bypass: 0 captures, counted `IGNORED_BYPASS`; nothing captured after resume |
| B8 | Audio | REPLACE/CLEAR second-difference ratios within P1-A limits (TRACE ≤ 1.5, CLOUD ≤ 2.0) for MANUAL- and RANDOM-driven replacements; output finite; BODY bit-identical with no ghost; mode switched every 0.5 s for 20 s: finite, every voice retires on time |
| B9 | Allocations | 0 audio-thread allocations (malloc_logger, positive control) with MIDI and automation triggers and RANDOM/AUTO active |
| B10 | Editor and state | editor closed, reopened 20 times and destroyed while captures run: no crash, status consistent; state restore never captures |

### 1.3 Stage C — RANDOM (hard)

| # | Check | Limit |
|---|---|---|
| C1 | Determinism | identical capture list (`s0`, `s1`, band) and bit-identical output for blocks 1, 32, 1024 and varying, at 44.1 and 96 kHz |
| C2 | Attempt bound | ≤ 8 candidates per tick (instrumented maximum); decisions only on build-unit slots |
| C3 | Interval | consecutive successful RANDOM captures ≥ 0.75 × I apart; with continuously active input ≤ 1.25 × I + 0.5 s apart |
| C4 | Silence | silence and −80 dBFS noise at gate −48 dBFS: 0 RANDOM captures, `NO_CANDIDATE` counted |
| C5 | Validity | every RANDOM selection ends in `[now − 4 s, now − D]`, has mean hop level ≥ gate, and is never rejected `EXPIRED`, `FUTURE` or `BEFORE_STREAM` |
| C6 | No backlog | after a HOLD release or a busy tick at `t`, the next RANDOM request is ≥ `t + 0.75 × I` |
| C7 | Sparse activity | 1 s bursts every 4 s: every RANDOM capture's region reaches the gate |

### 1.4 Stage B/C audio limits are the P1-A limits; no new audio limit is introduced and none is relaxed.

### 1.5 Stage D — AUTO (experiment limits, synthetic fixtures generated in the tests)

`H` = hop (21.3 ms at 48 kHz). Defaults unless stated.

| # | Fixture | Limit |
|---|---|---|
| D1 | 10 plucked notes 3 s apart | ≥ 9 captures; each `s0` ≤ onset and onset − `s0` ≤ 3H + 10 ms |
| D2 | same | ≤ 1 capture per note |
| D3 | 20 s sustained chord with 5 Hz, 6 dB tremolo | ≤ 1 capture |
| D4 | 20 s silence; 20 s of −70 dBFS noise | 0 captures |
| D5 | drum hits every 0.5 s for 20 s, cooldown 2 s | 8–11 captures, each starting within 3H + 10 ms before a hit |
| D6 | determinism | as C1 |

Real recordings (local, licence unknown, blocker B11): AUTO is run on them and the counts are reported, but nothing is
tuned on them and no audio or render from them is committed.

### 1.6 Stage E — host and realtime (hard, in order)

| # | Check | Limit |
|---|---|---|
| E2.1 | `auval -v aufx Aftr SwLb` on the P1-B AU | PASS |
| E2.2 | AU and VST3 loaded by a JUCE hosting harness (not a DAW) | load, process; dry path bit-identical at BODY 1 through both wrappers |
| E2.3 | VST3 MIDI Note On and CC 64 at offsets 0, 17, B−1; automation trigger through both wrappers | the captured selection (recovered from a sample-index-encoded input) ends exactly at block start + offset (MIDI) or block start (automation) |
| E2.4 | AU and MIDI | behaviour observed and documented (the contract does not rely on it) |
| E2.5 | state restore through each wrapper, saved with IMPRINT "on" | 0 captures |
| E2.6 | bypass through each wrapper | output = input; triggers ignored |
| E2.7 | re-prepare 44.1 → 96 kHz, 512 → 32 samples | no crash, no capture, finite output |
| E3.0 | device-callback harness on BlackHole 2ch: one deliberately stalled callback | the xrun counter increases. If not, E3 is **NOT ASSESSED**, never PASS |
| E3.1 | 48 kHz / 64, 96 kHz / 64, 96 kHz / 32 (where the device offers them), VST3, RANDOM every 1 s alternating FULL/FILTERED plus MIDI triggers every 0.3 s, DISSOLVE 0.5, 60 s each, editor closed and open; and 4 instances at 48 kHz / 64 | 0 xruns; time inside the callback: max ≤ 50 % of the buffer period, 99.9th percentile ≤ 25 % |
| E4.1 | P1-A benchmark scenario, unchanged, on P1-B code | P1-A criterion unchanged: blocks 32, 64, 1024 at all four rates and both densities: max ≤ 50 %, p99.9 ≤ 25 % of the block period |
| E4.2 | P1-B stress: MANUAL triggers every 150 ms, RANDOM at 1 s, AUTO on a percussive input | same criterion, same blocks and rates |

Block 16 is reported and block 1 is correctness-only, as in P1-A. Logic and Live are **NOT ASSESSED** until the owner
runs the checklist in §8 (added with the results).

### 1.7 Musical assessment

Render cases from synthetic fixtures (riff, sustained chord, drum loop, sustained synth), reproducible with
`afterimage_render`, WAVs not committed. Whether RANDOM fragments are useful and whether AUTO catches musically relevant
events is the owner's judgement; no automated measure can pass it.

---

## 2. Results summary (2026-11-19)

**Verdict: PARTIAL.** Hands-free capture works and passes every functional gate (Stages B, C) and the AUTO experiment
limits (Stage D). The first realtime hard gate, **E3, FAILED** (96 kHz / 32 samples: 99.9th percentile 26.7 % of the
period against 25 % in the gated run, 27.0–27.5 % in six repeats with the editor closed and open), and its xrun component could not be assessed because JUCE's xrun counter failed its
positive control. Per §1.1 the gated benchmark E4 was **not run**. Logic, Live and listening are **NOT ASSESSED**.

| Stage | Result | Evidence |
|---|---|---|
| A — design and frozen limits | committed before implementation (`e198b88`) | this file §0–§1 |
| B — MANUAL + HOLD (hard) | **PASS** B1–B10 | §3 |
| C — RANDOM (hard) | **PASS** C1–C7 | §4 |
| D — AUTO (experiment) | **limits met**; stays labelled experimental (two first versions failed, §5) | §5 |
| E1 — baseline | P1-A benchmark on `b0c437f`: 24/24 gated rows this run | `docs/evidence/p1b-E1-baseline-p1a-b0c437f.json` |
| E2 — hosted AU/VST3 (hard) | **PASS**, 0 failures | §6 |
| E3 — device callback (hard) | **FAIL** (timing at 96k/32, editor closed); xrun component **NOT ASSESSED** | §7 |
| E4 — benchmark (hard) | **NOT RUN** (stopped by E3) | |
| E5 — diagnostics | CPU-time evidence and start-up gaps characterised | §8 |
| Logic Pro / Ableton Live | **NOT ASSESSED** (checklist §10 for the owner) | |
| Musical value of RANDOM / AUTO | **NOT ASSESSED** (render cases §9) | |

## 3. Stage B — MANUAL and HOLD

| # | Result |
|---|---|
| B1 | P1-A C++ suite unchanged: 4,304 checks pass; Python 164 pass; `p1a-parity.json` regenerated with every row and capture delay **identical** (148/148) |
| B2 | Golden render (guitar fixture, two captures and a CLEAR, varying blocks) SHA-256 `f5f202a2…829da` from both `b0c437f` and P1-B, re-checked after Stage D |
| B3 | 4 rates × 5 lengths: `s1` = trigger and `s0 = s1 − round(L·Fs)` exactly; 1 s at the stream start refused `BEFORE_STREAM`, never shortened. Processor: MIDI Note On and CC 64 at offsets 0, 1, 17, B−1 in blocks of 64 and 512 land on `block start + offset`; a second note in the same block is `DROPPED_RATE`; a held CC 64 does not retrigger; the automation edge lands on the block start |
| B4 | rising edge captures once over 100 blocks held on; a one-block pulse captures; "on" restored from state, across `prepareToPlay` (48 → 96 kHz) and set during bypass: 0 captures. **Defect found in review and fixed:** a restore on another thread while audio ran fired IMPRINT in 213–238 of 2,000 restores (the resync flag was set after `replaceState`). A restore sequence counter now makes the audio thread resync whenever a restore started, ran or finished since its last block: 0 in 2,000, three runs (test `b4race`). E2 was re-run on the fixed build: 0 failures |
| B5 | HOLD before a ghost: 0 RANDOM / AUTO captures over 20 s (RANDOM ≥ 15 and AUTO ≥ 5 suppressions), the button still captures; HOLD with a ghost keeps it 20 s; IMPRINT replaces under HOLD; 100 random toggles: no RANDOM capture within 0.75 × interval of a release, output finite; the held ghost retires with MEMORY |
| B6 | 16 triggers 20 ms apart during a FILTERED build: at most 2 accepted, at least 0.2 s apart; all others `BUSY`; nothing queued |
| B7 | button, MIDI and automation triggers while bypassed: one `IGNORED_BYPASS` each, 0 captures, none after resume |
| B8 | RANDOM-driven replacements on a sine: worst second-difference ratio 0.999 (TRACE, limit 1.5) and 1.186 (CLOUD, limit 2.0); BODY bit-identical in RANDOM mode with input under the gate; modes switched every 0.5 s for 20 s: finite, all voices retired |
| B9 | **0 audio-thread allocations** (malloc_logger with positive control) in 4,000 blocks with MIDI, the automation trigger, HOLD toggles and RANDOM, editor closed and open |
| B10 | editor created and destroyed 20 times during RANDOM captures, and destroyed with a capture in flight: no crash; completed outcomes = captures |

## 4. Stage C — RANDOM

| # | Result |
|---|---|
| C1 | at 44.1 and 96 kHz, FILTERED, bursts: identical request lists and bit-identical output for blocks 1, 32, 1024 and varying |
| C2 | at most 8 candidates per tick (8 observed, the limit); every RANDOM request on a stream sample ≡ 32 (mod 64) |
| C3 | interval 2 s, continuous input, all four rates: 13 captures, gaps 1.56–2.40 s (limits 1.5 and 3.0) |
| C4 | silence and −80 dBFS noise: 0 captures, `NO_CANDIDATE` on every tick |
| C5 | every selection ends in `[now − 4 s, now − D]`, is exactly LENGTH long and reaches the gate; no `EXPIRED`, `FUTURE` or `BEFORE_STREAM` |
| C6 | with manual FILTERED captures every 150 ms: 21 of 29 RANDOM ticks fell while busy, each dropped and rescheduled; none replayed |
| C7 | 1 s bursts every 4 s: 39 captures, all over the gate |

## 5. Stage D — AUTO (experimental)

Experiment limits, generated fixtures, defaults (gate −48 dBFS, sensitivity 0.5 = 7.5 dB, cooldown 2 s, length 750 ms):

| # | Result |
|---|---|
| D1/D2 | 10 plucked notes, 48 and 96 kHz: **10/10** captured, one each; every capture starts before its onset, at most 71.3 ms before (limit 74.0) |
| D3 | sustained chord with ±3 dB, 5 Hz tremolo: **1** capture (its fade-in) |
| D4 | silence and −70 dBFS noise: **0** |
| D5 | drum hits every 0.5 s for 20 s: **8** captures at 44.1 and 96 kHz, each starting ≤ 73.4 / 71.3 ms before a hit (limits 79.7 / 74.0) |
| D6 | identical requests and bit-identical output for blocks 1, 32, 1024 and varying |

Failed first versions, kept on record:

- **Fixed −90 dB band floor:** the tremolo chord triggered **4** times. Leakage bands crossing the floor counted as 30 dB
  rises. Fixed by measuring flux only within 60 dB of the frame's loudest band; the D3 limit was not changed.
- **Start before the stream:** onsets in the first 70 ms of a stream were rejected `BEFORE_STREAM`. AUTO's start is now
  clamped at sample 0 (only silence precedes it).

**Real recordings (local, licence unknown, untuned; `p1b-real-modes.json`):** AUTO captured on drum break 4 (21.7/min),
dense percussion 3, clean guitar 2, and 1 each on the distorted guitar, piano, bass, spoken voice, metallic hit, field
recording and pluck. It captured **nothing** on the sustained vocal (62 s) and the evolving pad (52 s): conservative by
design, but it means AUTO is mainly a percussive/attack mode. Whether its captures are musically relevant is the
owner's call. RANDOM (2 s interval) captured 25–33 times per minute on all material that passes the gate.

## 6. Stage E2 — real binaries through JUCE hosting (not a DAW)

`docs/evidence/p1b-E2-auval.txt`, `docs/evidence/p1b-E2-hosted.json`. **0 failures.**

| # | Result |
|---|---|
| E2.1 | `auval -v aufx Aftr SwLb`: **PASS**; explicit channel capabilities `[1, 1] [2, 2]` |
| E2.2 | AU and VST3 load; dry path bit-identical at blocks 64 and 512 |
| E2.3 | VST3 MIDI Note On and CC 64 at offsets 0, 17, B−1 (blocks 64, 512): the decoded selection ends at **exactly** block start + offset; the automation trigger ends at the block start in **both** AU and VST3 |
| E2.4 | the `aufx` AU reports no MIDI input and captured nothing from MIDI (expected, documented) |
| E2.5 | state saved with IMPRINT on and restored into a new instance: **0** captures (AU and VST3) |
| E2.6 | host bypass: output = input, MIDI and automation triggers ignored, nothing captured after resume |
| E2.7 | re-prepare 44.1 kHz / 512 → 96 kHz / 32: dry, finite, no capture |

Three harness bugs were found and fixed before the result above; the limits were not changed. (1) The decoder read
`s1 − 1` as the loop's last sample, but by the loop contract `loop[0] = audio[s1]`, so every trigger appeared one sample
late. (2) The bypass check counted the 20 ms post-bypass BODY ramp as a ghost. (3) The decoder then read that ramp as a
loop.

## 7. Stage E3 — real CoreAudio device callback

BlackHole 2ch (virtual CoreAudio device), the installed VST3 hosted by the harness on the device's IO thread, RANDOM
every 1 s alternating FULL / FILTERED, a MIDI IMPRINT every 0.3 s, DISSOLVE 0.5, output muted, 60 s per row.
Evidence: `docs/evidence/p1b-E3-*.json`.

**E3.0 positive control: FAILED.** A callback stalled for 3 periods, and in a diagnostic for 40 periods (53 ms, also on
the built-in speakers), never incremented JUCE's xrun counter (CoreAudio overload notifications) on this macOS 26.6
machine. The xrun component of E3 is therefore **NOT ASSESSED**: the "0 xruns" in every row proves nothing. The JSON
`result` fields say PASS/FAIL from the harness's own rule and must be read with this in mind.

Supplementary (not the gate): consecutive callbacks' CoreAudio host times. The same positive control produced exactly one
gap (4.06 and 41.06 periods for the 3× and 40× stalls), so this detector works.

| Rate / block | Editor | Instances | Max in callback | 99.9th pct | Timing limits (50 % / 25 %) | Host-time gaps |
|---|---|---:|---:|---:|---|---:|
| 48 kHz / 64 | closed | 1 | 113 µs (8.5 %) | 7.5 % | met | 0 |
| 48 kHz / 64 | open | 1 | 119 µs (8.9 %) | 6.9 % | met | 0 |
| 96 kHz / 64 | closed | 1 | 148 µs (22.1 %) | 17.0 % | met | 65, all in the first 0.13 s (device switching 48 → 96 kHz) |
| 96 kHz / 64 | open | 1 | 167 µs (25.0 %) | 16.3 % | met | 0 |
| **96 kHz / 32** | **closed** | 1 | 130 µs (39.1 %) | **26.7 %** | **p99.9 FAILED** | 0 |
| 96 kHz / 32 | open | 1 | 125 µs (37.4 %) | 22.3 % | met | 0 |
| 48 kHz / 64 | closed | 4 | 353 µs (26.5 %) | 18.1 % | met | 2 |

**E3 = FAIL.** Per §1.1, E4 was not run.

E5 repeats of the 96 kHz / 32 rows (three each, 60 s, on the build with the restore fix; `p1b-E5-repeat-*.json`): editor
closed 27.0 / 27.1 / 27.0 %, editor open 27.4 / 27.3 / 27.5 % at the 99.9th percentile; maxima 34–46 %. All six miss
the 25 % limit, so the single editor-open pass above (22.3 %) was run-to-run variation. BlackHole was returned to
48 kHz afterwards (it was at 48 kHz before E3); the MiniFuse was not used.

## 8. E5 — characterising the failure (evidence only)

`docs/evidence/p1b-E5-cpu-time.json` (ordinary thread, 1 × 20 s per row, thread CPU time read around every call; the
P1-A scenario path does not read CPU time and shows 0), `docs/evidence/p1b-E5-gaps-*.json`.

- **Execution cost, not preemption:** in every P1-B scenario row, the CPU time of the worst callback equals its wall time,
  except one 258 µs callback (random, stress, 96 kHz / 32) that used 12.5 µs of CPU: the single preemption observed in
  those rows.
- **The 96 kHz / 32 budget is tight:** the engine's worst callback there costs 76–98 µs of CPU (23–30 % of 333 µs) in
  the benchmark. The hypothesis, not yet broken down by component, is one stereo pair of 8192-point FFTs (analysis or a
  FILTERED build unit) plus grains: analysis callbacks are 1 in 64 (1.6 %), more than the top 0.1 %, so the 99.9th
  percentile sits on them.
- **No added cost shown for P1-B in the benchmark:** the unchanged P1-A scenario at 96 kHz / 32 / CLOUD has a p99.9 of
  68.0 µs on P1-A code (E1, `b0c437f`) and 67.3 µs on P1-B code (E5 `p1a` row). The P1-B scenarios give 66.1 (MANUAL),
  67.8 (RANDOM) and 68.4 µs (AUTO), medians 0.71–0.79 µs throughout. The scheduler's own cost was **not isolated**; it is
  inferred to be small from these equal medians.
- **Unexplained gap:** the device-callback p99.9 at 96 kHz / 32 (89 µs, editor closed) is about 21 µs above the
  ordinary-thread benchmark (66–68 µs), and that gap is what crosses the 83 µs limit. There is no P1-A baseline under E3,
  so the failure is **not shown to come from P1-B**, and not shown to be P1-A's either. Candidates, not causes: the VST3
  wrapper, MIDI triggers, and `computeMask`, which runs a `log2`/`cos` per bin at the sample of every accepted FILTERED
  capture, outside the build-unit schedule. Measured: 24.7 µs median / 61.5 µs max at 48 kHz (2,049 bins) and 34.7 µs /
  54.5 µs at 96 kHz (4,097 bins). Landing in a callback that also runs an analysis FFT pair, that alone would cross the
  limit.
- **The host-time gaps** at 96 kHz / 64 occur only during the first 0.13 s after the device switches rate; a repeat with
  the device already at 96 kHz had none.
- **Scope of E5:** it ran the whole E4 matrix (four scenarios, both densities, all rates and blocks) instrumented, once
  each, after E3 failed. That was declared in advance as evidence-only; **no E4 result is claimed from it.**
- Remedies to try in P1-C (not done here: P1-B excludes DSP changes and the stop rule applies): move `computeMask` into
  the first build unit or precompute its `log2` table; split each stereo FFT step into one channel per scheduled unit;
  measure a component breakdown; then re-run the unchanged gates.

## 9. Musical assessment — render cases (owner to listen)

`uv run python run_p1b_modes.py --render <afterimage_render>` writes `renders/p1b/` (git-ignored) from original synthetic
material, BODY 1, GHOST 0.7, DISSOLVE 0.5, MEMORY 6 s:

| Case | MANUAL (every 3 s) | RANDOM (2 s) | AUTO |
|---|---:|---:|---:|
| riff (32 plucked notes, 0.4 s apart) | 5 | 9 | 5 |
| sustained chord (3 chords, 6 s apart) | 5 | 10 | 3 |
| drum loop | 5 | 9 | 6 |
| sustained synth | 5 | 9 | 1 |

Listening questions: does RANDOM produce useful fragments or just churn; does AUTO pick musically meaningful moments or
just attacks; is 750 ms the right default length; is GHOST −6 dB sensible under a live guitar? None of this is
assessed here.

## 10. Owner checklist for Logic Pro and Ableton Live (NOT ASSESSED until run)

The P1-B build is installed for this user (`~/Library/Audio/Plug-Ins/Components/AFTERIMAGE.component`, `…/VST3/AFTERIMAGE.vst3`).

**Logic Pro (AU):**
1. Insert AFTERIMAGE on a guitar track (audio effect). Play, press IMPRINT in the plugin: a ghost appears ≈ 0.1 s later.
2. Footswitch: Logic → Control Surfaces → Learn Assignment, press the footswitch, then click **IMPRINT (trigger)** in the
   plugin's automation parameters (and likewise HOLD). Press while playing: one capture per press.
3. Save, close and reopen the project with IMPRINT (trigger) left on: no ghost should appear on load.
4. Bypass the plugin, press the footswitch, un-bypass: no ghost.
5. RANDOM and AUTO: play for a minute each; note whether captures feel useful.
6. Bounce offline and in real time once each.

**Ableton Live (VST3):**
1. Same as above on an audio track. Live may list the VST3 under Plug-Ins → VST3 → Shortwav Labs.
2. MIDI: create a MIDI track with your controller or footswitch; set its **MIDI To** to the guitar track, then
   AFTERIMAGE. A Note On or a sustain-pedal press should capture.
3. Map a footswitch to IMPRINT (trigger) with MIDI Map mode as the alternative.

Report anything that differs; until then host behaviour is known only through the E2 harness.

## 11. Deferred and open

- **Deferred:** FREEZE VIEW (design in the architecture §11), MIDI to the AU (`aumf`), in-plugin MIDI learn, the
  PERFORMANCE PAD, FOCUS/GLITCH engines, pitch, the production UI.
- **New blockers:** B13 — 96 kHz / 32-sample callback budget (E3 FAIL, same structure as P1-A's open gate); B14 — no
  working xrun counter on this macOS (host-time gaps are the only dropout evidence); B15 — Logic/Live behaviour of the
  trigger paths unverified.
- **Unchanged:** B1–B12 status as in P1-A-QUALIFICATION §10; B11 (Freesound licences) open.

## 12. Recommended next milestone

**P1-C: realtime budget and host qualification**, no new features:
1. Break the 96 kHz / 32 callback down by component, move `computeMask` into the build schedule, split stereo FFT work
   into one channel per scheduled unit (analysis and FILTERED build), keeping output bit-identical (parity, golden
   render), then re-run E3 and E4 unchanged.
2. Owner runs §10 in Logic and Live and listens to `renders/p1b/` and to live playing in all three modes.
3. Replace the xrun instrument with a validated one (host-time continuity, or a DAW's own overload counter) before any
   realtime PASS is claimed.
