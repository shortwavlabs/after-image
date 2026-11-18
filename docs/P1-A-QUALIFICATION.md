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
