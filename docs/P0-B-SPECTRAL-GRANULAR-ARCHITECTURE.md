# AFTERIMAGE — P0-B Spectral Granular Architecture

Status: **research prototype, offline Python**. This describes what
`experiments/p0-spectral-ghost/p0/granular.py` does and how it would translate
to a realtime C++ engine. It does not replace `DSP-ARCHITECTURE.md`; where the
two differ, the difference is listed in `P0-B-FINAL-REPORT.md` §2.

Nothing here has been listened to by its author (an automated agent). Every
statement about sound is a hypothesis until the owner fills in
`experiments/p0-spectral-ghost/listening-notes-p0b.md`.

## 1. Processing chain

```text
input ──► STFT (P0-A, sqrt-Hann, H = N/4) ──► history ring (P0-A)
                                                   │
                           validated capture request (P0-A rules, unchanged)
                                                   │
             frames first-2 … last+2  ×  frequency mask F[k]      ◄── capture_buffer()
                                                   │  one WOLA reconstruction
                              trim to the selection: M·H samples
                                                   │
                     aligned seam (P0-A loop_period) ──► periodic buffer, R samples
                                                   │
                 ┌─────────────────────────────────┴───────────────────────────┐
        TRACE: read the buffer in order                       CLOUD: ≤ 32 windowed grains,
        (the P0-A spectral loop)                              interpolated reads, no FFT
                 └───────────────┬─────────────────────────────────────────────┘
                              DISSOLVE (A: crossfade, B: one grain stream, C: guided positions)
                                 │
                       MEMORY envelope (P0-A T60) ──► GHOST ──► + BODY
```

There is exactly one spectral operation per capture. After it, everything is
time-domain reads of a fixed buffer.

## 2. Capture buffer

### 2.1 Selection geometry

P0-A frame `m` has `end_sample = (m+1)·H` and a window centre at
`(m+1)·H − N/2`. A selection of frames `first..last` (M frames) is defined in
P0-B as the M·H samples centred on those window centres:

```text
[ (first − 1.5)·H ,  (last − 0.5)·H )          length = M·H = the duration P0-A already reports
```

### 2.2 Context frames

The M selected frames alone only overlap fully over `(M − 3)·H` samples; P0-A's
loop used that interior and discarded the rest. P0-B reads **two extra frames on
each side** from the history ring, applies the same frequency mask, runs one
WOLA pass over `M + 4` frames and **trims the result back to exactly the
selection**. The context frames only complete the overlap inside the selection;
none of their own audio is kept.

| | P0-A loop | P0-B capture buffer |
|---|---|---|
| usable samples | (M − 3)·H | M·H |
| 0.25 s selection, N = 8192, 48 kHz: loop period | 3072 samples (64 ms) | 7553 samples (157 ms) |
| extra wait before capture can complete | none | 2 hops (42.7 ms at 48 kHz / N = 4096) |

Rules:

- Context frames before the stream start are zeros (that audio is silence).
- A context frame that is not in the ring (selection touches the newest frame,
  or the oldest frame has expired) **shortens the buffer on that side** by H/2
  or 3H/2 instead of exposing partially overlapped audio.
- Audio outside the M + 4 frames cannot reach the buffer at all (measured: the
  buffer is bit-identical when that audio is replaced by noise).

### 2.3 What the mask does and does not isolate

With a full-band mask the buffer equals the source samples of the selection
(−157 dB). With a band-limited mask the capture is a linear filter, so audio
just outside the selection **in time** rings into it near the edges
(−11 to −22 dB relative to the selected audio within 20 ms of an edge, measured
by superposition; below −53 dB deeper than 50 ms). The ringing length follows
the mask's feather width in Hz, so low band edges ring longer. This is the one
place where "do not expose neighbouring audio" is not exactly met; see the
report §10 K2.

### 2.4 Periodic buffer and the shared seam

The buffer is made periodic with P0-A's "aligned" seam (`engines.loop_period`,
extracted from `loop()` without changing its arithmetic): a loop end is searched
within 25 ms for maximum correlation, then crossfaded over 80 ms with gains
normalised for that correlation. Grains then address the buffer **modulo its
period R**, so no grain can read across an unprepared edge.

For controlled comparisons the seam is computed once, on the spectral buffer,
and the same period and crossfade length are forced on the comparison buffers
(raw time-domain, IIR pre-filtered). One grain schedule therefore addresses the
same source instants in all of them.

### 2.5 Ownership (realtime)

| Buffer | Size (stereo float32, maximum 1.5 s selection) | Owner | Written | Read |
|---|---|---|---|---|
| History ring | P0-A table (12–27 MiB) | analysis | every hop | capture job |
| Reconstruction scratch | 0.56–1.22 MiB | capture job | during capture only | capture job |
| Voice capture buffer (periodic) | 0.51–1.11 MiB | voice | once, then immutable | TRACE reader and all grains |
| Grain pool | 32 × 64 B | voice | grain start/stop | render loop |

A voice's buffer is written once and never modified while grains read it. A new
capture fills a second buffer and the voice switches with a short fade; nothing
is reallocated on the audio thread.

## 3. Grain engine

### 3.1 A grain

| Field | Meaning |
|---|---|
| `onset`, `length` | output sample range |
| `pos` | fractional start position in the periodic buffer |
| `speed` | source samples per output sample (pitch ratio) |
| `reverse` | plays the same source span backwards |
| `amp`, `gain` | per-grain amplitude and the normalisation gain (§3.4) |
| `gl`, `gr` | stereo balance gains |

All fields are fixed for the life of the grain. Parameter changes take effect on
the next grain start, which keeps the inner loop branch-free and makes every
change click-free by construction.

### 3.2 Scheduler

- Parameters are a `CloudParams` value or a function of time (for a moving
  DISSOLVE); they are evaluated once per grain at its nominal onset.
- Inter-onset interval = `fs / density`. Onset jitter moves a grain by up to
  ±half an interval. At jitter 0 the stream is a regular grid.
- Scheduling starts one grain length before sample 0, so the overlap is in
  steady state at the first output sample.
- **Every grain consumes exactly eight uniform random draws**, used or not. The
  random stream is therefore identical for every parameter setting and every
  buffer: changing DISSOLVE, or swapping the spectral buffer for the raw one,
  changes how the draws are mapped, not which draws a grain gets.
- Position: `pos = onset·scan + spray·R·(u − ½)`, i.e. a sequential playhead
  plus a random offset. With a spectral guide (§5.3), the position is instead
  drawn from a weight over the buffer.

### 3.3 Polyphony ceiling

`MAX_GRAINS = 32`. 300 ms grains at 100 grains/s need 30–31. Grains are admitted
in onset order; a grain that would be the 33rd is **dropped whole** and counted.
Dropping never shortens a sounding grain, so it cannot click, and it needs no
search in the realtime version. The alternative (steal the oldest with a short
fade) keeps density more even but adds a fade path; it was not built.

### 3.4 Windows and gain

- **Hann** (periodic): `w[0] = 0` exactly, and two copies half a grain apart sum
  to exactly 1. **Tukey** (flat middle half): `w[0] = w[L−1] = 0`. A rectangular
  window exists only as the click-detection control in the tests.
- Gain law, per grain, from the expected overlap power:

```text
overlap  = density · grain_length
P        = c · (overlap · E[w] · E[amp])²  +  (1 − c) · overlap · E[w²] · E[amp²]
g        = 1 / sqrt( max(P, 0.75) )
```

`c` ("coherence") is the expected share of amplitude summation: 1 for a
sequential stream whose grains read consecutive material, 0 for a cloud. 0.75 is
the overlap power of Hann at 50 % overlap; clouds sparser than that are **not**
boosted further, so sparse grains never exceed +1.25 dB and the cloud simply
gets quieter. There is no limiter, compressor or saturator anywhere in the path.

The law assumes what it is told. A dense cloud with zero spray is coherent
whatever `c` says and sums up to +13 dB above the buffer (report §8).

### 3.5 Pitch and reverse

Reads use 4-point Catmull-Rom interpolation at `pos + speed·k`. At integer
positions and unity speed it returns the stored samples exactly, which is what
makes DISSOLVE = 0 sample-exact. Transposition is plain resampling: duration and
pitch are coupled inside a grain, there is no anti-alias filter for upward
shifts, and fractional reads lose some top-octave level (0.9 dB of RMS on white
noise at 48 kHz). Pitch is drawn as a uniform ± range plus optional octave
jumps (60 % up, 40 % down).

### 3.6 Stereo

Both channels of a grain read the **same** source position, so the source's own
stereo image is carried into every grain. Spread is a constant-power *balance*
with positive gains, `(√2·cos a, √2·sin a)`, equal to (1, 1) at centre. Because
the gains are never negative and there is no inter-channel delay, the engine
cannot create anti-phase content: a mono source at 100 % spread has an analytic
mono-compatibility floor of −3.01 dB (measured −0.96 dB). It also cannot repair
a source that is already anti-phase.

## 4. TRACE

TRACE is the periodic buffer read in order: the P0-A spectral loop, built on the
full selection instead of the 3-hop-shorter interior. P0-A's own
`loop_aligned80` is still rendered separately as the named baseline.

## 5. DISSOLVE

At a fixed setting all three approaches share both endpoints: D = 0 is TRACE
and D = 1 is the same cloud with the same schedule. (A DISSOLVE that moves over
time reaches the same settings but a different random realisation.)

### 5.1 Approach A — parallel morph (control)

`cos(D·π/2)·TRACE + sin(D·π/2)·CLOUD`. An ordinary equal-power crossfade.

### 5.2 Approach B — structural dissolution

One grain stream. Its parameters are continuous functions of D:

| Parameter | D = 0 | → | D = 1 | Law |
|---|---|---|---|---|
| grain length | 120 ms | | 200 ms | linear |
| overlap | 2 | | 4 | held at 2 until D = 0.1, smoothstep to 0.7 |
| position spray | 0 | | 100 % of buffer | D² |
| onset jitter | 0 | | 100 % of interval | D |
| reverse probability | 0 | | 50 % | smoothstep from D = 0.25 |
| detune | 0 | | ±0.15 semitone | linear |
| octave jumps | 0 | | 20 % of grains | smoothstep from D = 0.4 |
| stereo spread | 0 | | 80 % | linear |
| gain-law coherence | 1 | | 0 | smoothstep over D = 0…0.05 |

At D = 0 this is Hann grains at exactly 50 % overlap, sequential, forward,
unity speed and centred: the windows sum to 1 and the grains read consecutive
samples, so the output **is** the TRACE loop (measured −313 dB). Nothing is
switched; raising D first breaks waveform continuity, then event order, then
introduces reversed and octave-shifted grains.

The constants in this table are first guesses chosen by an agent that cannot
hear them. They are the first thing listening should revise.

### 5.3 Approach C — spectrally guided positions

Three per-frame features are computed from the captured frames (in-band bins
only): energy, positive spectral flux (onset-ness) and tonalness
(1 − spectral flatness). Two weights are built from them:

- `harmonic`: √energy · tonal² · (1 − flux)² — loud, peaky, steady frames
- `transient`: √energy · flux — frames where energy arrives

The weight is interpolated over buffer positions and used as the distribution
of grain *centres*, using the same random draw the unguided cloud uses for
spray. Everything else in the schedule is unchanged, so guided versus unguided
differ only in where grains read. This is deliberately a three-feature
heuristic, not a framework.

## 6. Realtime translation

| Offline model | Realtime equivalent |
|---|---|
| one WOLA pass over M + 4 frames | capture job spread over several hops with a fixed number of inverse FFTs per hop (owner guidance on PR #2: no 16-IFFT bursts without a benchmark); the voice starts after a measured, reported delay |
| seam search over 25 ms of lags | bounded job after reconstruction, or a coarser lag grid; not on the per-sample path |
| grain list built ahead of time | sample-accurate countdown to the next onset; parameters and 8 PRNG draws evaluated at each grain start |
| NumPy generator | small per-voice PRNG with a stored seed (the *contract* is eight draws per grain, not the generator) |
| window computed per length | one high-resolution window table, read with a per-grain phase increment |
| drop-newest overflow | "pool full → skip start", O(1) |
| float64 | float32 buffers; phase/position in double or fixed-point |

Per active grain per output sample (stereo): 8 buffer taps, about 14
multiplies, one window lookup, two balance gains. Per grain start: 8 draws, one
`pow2`, one `sin`/`cos` pair, one `sqrt`. All memory is preallocated and all
loops are bounded by `MAX_GRAINS` and the block size.

Worst callback load is expected where these coincide: 96 kHz with N = 8192, a
capture reconstruction in progress, 32 active grains transposed up an octave
(each strides through its buffer at twice the rate), TRACE and CLOUD both
running (Approach A; Approach B replaces TRACE with grains), and a small host
block. None of this has been measured in C++; see the report §9.
