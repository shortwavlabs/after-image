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
