# AFTERIMAGE — P0-C Frequency-Dependent Architecture (SPLIT)

Status: **research prototype, offline Python.** This describes
`experiments/p0-spectral-ghost/p0/split.py`. It adds to, and does not replace,
`DSP-ARCHITECTURE.md` and `P0-B-SPECTRAL-GRANULAR-ARCHITECTURE.md`.

The author is an automated agent that cannot listen. Every constant below is a
research setting, not a product parameter, and every statement about sound is a
hypothesis until `listening-notes-p0c.md` is filled in.

## 1. Processing graph

```text
input ─► STFT ─► history ring ─► validated capture (P0-A)            frames first-2 … last+2 (P0-B context)
                                        │
                              SOURCE mask S[k]      FULL: S = 1      FILTERED: S = the selection's mask
                                        │
                    ┌───────────────────┼─────────────────────────────┐
              S·B_i[k]  (i = 1…n)   S[k]                      S·sqrt(B_i[k])  (i = 1…n)
              WOLA, trim             WOLA, trim                 WOLA, trim
                    │                   │                             │
               TRACE band i        source buffer                CLOUD band i
                    │                   │ aligned seam search (P0-A)  │
                    └──────── the SAME linear seam applied to all 2n+1 buffers ────────┘
                                        │
     per band i:   cos(d_i·π/2) · [TRACE band i read in order]
                 + sin(d_i·π/2) · [grains over CLOUD band i, own schedule, own budget]
                                        │
                              sum over bands ─► MEMORY envelope ─► GHOST ─► + BODY
```

`d_i ∈ [0, 1]` is the dissolve amount of band `i`. MODE decides how `d_i` and the
grain settings depend on the band; DISSOLVE moves `d_i`; SOURCE only chooses `S`.

## 2. Band masks

For crossovers `f_1 < … < f_(n-1)` and transition width `w` octaves (default 1):

```text
T_j(f) = 0                                   f ≤ f_j · 2^(−w/2)
       = ½ − ½·cos(π·(log2(f / f_j)/w + ½))  in between
       = 1                                   f ≥ f_j · 2^(+w/2)

B_1 = 1 − T_1        B_i = T_1 ⋯ T_(i−1) · (1 − T_i)        B_n = T_1 ⋯ T_(n−1)
```

The sum telescopes: `Σ B_i = 1` at every bin, for any number of bands and
however the transitions overlap (measured deviation: 0).

Two mask sets are used:

| Branch | Mask | Property | Why |
|---|---|---|---|
| TRACE | `B_i` | amplitudes sum to 1 | unmodified bands are coherent and must add back to the source exactly |
| CLOUD | `sqrt(B_i)` | powers sum to 1 | band clouds are decorrelated (independent schedules) and add in power |

### Why two sets

If both branches used `B_i` and adjacent bands were at different amounts, the
level at a crossover centre would be `10·log10(½·(1 + cos(Δd·π/2)))`: −3 dB when
one band is TRACE and its neighbour CLOUD. This was built first and measured
(−2.66 to −2.91 dB); it is kept behind `naive=True` for the record. With the
adopted masks the worst case is predicted at −1.25 dB and measured at −1.27 dB.

### Crossover placement

| SOURCE | Crossovers |
|---|---|
| FULL | absolute, default 250 Hz and 2 kHz |
| FILTERED | relative: log-thirds of the selected band (e.g. 849 Hz and 2061 Hz for 350–5000 Hz) |

Absolute crossovers on a FILTERED source can leave bands empty (a 2–10 kHz
selection puts 76 % of its energy in the top band and none in the bottom one),
which turns SPLIT back into CLOUD. Relative placement keeps three populated
bands. This means FULL and FILTERED differ in two ways at once: the material
and where it is split. Both crossover sets are recorded in the manifest.

Nothing about 250 Hz / 2 kHz / three bands is assumed elsewhere: band count
follows the crossover list, and 2- and 5-band decompositions pass the same tests.

## 3. Decomposition candidates

### A. Spectral (STFT-derived)

Each band buffer is one P0-B context-frame reconstruction of the selected
frames with mask `S·B_i` or `S·sqrt(B_i)`. Because WOLA is linear, the TRACE
bands sum to the source buffer to −314 dB. Bands are zero-phase: no group delay,
no latency to align, but each band rings symmetrically around a transient.

### B. Conventional (time-domain)

A causal crossover tree run over the input stream:

- TRACE bands: Linkwitz-Riley 4th order, earlier bands all-pass compensated, so
  the bands sum to an all-pass (flat magnitude to 0.0000 dB, phase shifted).
- CLOUD bands: 3rd-order Butterworth, which is power-complementary.

This is the baseline the brief asks for, given the same two-branch treatment so
that it is not handicapped by a crossover hole the spectral version avoids.

### Measured differences

| | Spectral | Conventional |
|---|---|---|
| Sum of unmodified bands vs source | −314 dB (identical waveform) | flat magnitude; waveform error −1.6 dB (all-pass) |
| Group delay of the sum | 0 | up to 2.4 ms |
| Isolation one octave past a crossover | ≤ −95 dB | −24.6 dB (LR4), −18.1 dB (Butterworth-3) |
| Click: band ringing (99 % energy), low / mid / high | 6.4 / 2.7 / 0.3 ms, half of it **before** the click | 3.6 / 2.8 / 0.3 ms, none before |
| Click: sum of unmodified bands | 0 ms (exact) | 2.1 ms |
| Capture-time work, stereo, max selection | 828–900 inverse FFTs (6 band buffers) | 40 biquad sections × 66–145 k samples |
| Rendered SPLIT, third-octave distance between the two | 0.17–0.45 dB | |

## 4. One seam for every buffer

The P0-A aligned seam is searched once on the source buffer (period `R`,
crossfade `X`, correlation `ρ`). `apply_seam()` then applies that crossfade,
with gains fixed by `ρ`, to all `2n + 1` buffers:

```text
a(t) = t/X,  b(t) = 1 − t/X,  g = sqrt(a² + b² + 2·max(ρ, 0)·a·b)
per[0:X] = seg[0:X]·a/g + seg[R:R+X]·b/g          per[X:R] = seg[X:R]
```

Because this is now a single linear operation, the periodic TRACE bands still
sum to the periodic source (the loop), and every band shares one period, so
grains in different bands address the same source instants.

Side effect, measured: the 80 ms seam crossfade sits exactly where P0-B's edge
leakage (K2) lives. For a FULL source, neighbouring audio in a band buffer is
−19 to −25 dB within 20 ms of an edge before the seam and −61 to −64 dB in the
first 20 ms after it. For FILTERED selections, whose 1/6-octave feather rings
longer, the seam helps less: −12.5 to −23.7 dB before, −33.7 to −48.2 dB after.

## 5. Grain routing and scheduling

- One grain pool per band. Budgets `(6, 10, 16)` for three bands; they total the
  P0-B ceiling of 32. It is **not** 32 per band.
- Each band has its own schedule (seed + band index), its own grain settings and
  its own drop-newest overflow against its budget.
- A band whose `d_i` is 0 schedules nothing and costs one buffer read.
- Measured use at the default settings: 0–5 grains per band, 10–15 in total.

The cost unit is buffer taps, not grains. A design with one shared schedule
whose grains read all three band buffers would spend three grains' worth of taps
per grain; it was also the design with the crossover hole (§2).

## 6. MODE, SOURCE and DISSOLVE

**SOURCE selects material. MODE determines behaviour. DISSOLVE determines transformation.**

### SOURCE

`FULL`: `S[k] = 1`, the whole spectrum of the selected time span.
`FILTERED`: `S[k]` is the capture's feathered frequency mask. SOURCE acts before
the band decomposition and never changes band behaviour.

### Per-band transform

Inside a band, the owner-preferred **parallel** morph is used:
`cos(d·π/2)·TRACE + sin(d·π/2)·CLOUD`. Grain settings do not move with DISSOLVE;
only the crossfade does. (P0-B's structural morph is unchanged and still
available as an engine; it is not used inside SPLIT.)

### Strategies

With band position `p = 0` (lowest) … `1` (highest):

| Strategy | `d_i` | Grain settings |
|---|---|---|
| S1 static | `p^1.5` → 0, 0.35, 1 | same in every band |
| S2 keep-low | `smoothstep((D − 0.6·(1 − p)) / 0.4)`; lowest band fixed at 0 | same in every band |
| S2 fade-low | as above, lowest band dissolves over D = 0.6…1 | same in every band |
| S3 | `D` in every band | vary with `p` (below) |

S2 at D = 0 / 0.25 / 0.5 / 0.75 / 1 gives (low, mid, high) =
(0, 0, 0), (0, 0, 0.68), (0, 0.5, 1), (0 or 0.32, 1, 1), (0 or 1, 1, 1).
All mappings are continuous and non-decreasing in D.

S1/S2 grain settings: the P0-B cloud endpoint without pitch (200 ms Hann grains,
20 grains/s, full spray, 50 % reversed, 80 % spread).

S3 grain settings:

| | low | mid | high |
|---|---|---|---|
| grain length | 300 ms | 155 ms | 80 ms |
| density (4× overlap) | 13 /s | 26 /s | 50 /s |
| position spray | 50 % | 75 % | 100 % |
| stereo spread | 20 % | 60 % | 100 % |
| reversed | 0 % | 25 % | 50 % |

### What S1 and S2 are

`Σ_i [cos(d_i)·TRACE_i + sin(d_i)·CLOUD_i]` is a TRACE/CLOUD crossfade whose
position depends on frequency. Structurally, S1 and S2 are **the P0-B parallel
morph with a crossover in front of it**. Only S3 changes what the grains do per
band. This matters for the product decision in the report (§14).

### Pitch

Off by default. Variants apply to the **top band only**: restrained detune
(±0.15 semitone) or detune plus P0-B's 20 % octave jumps. The lower bands are
never transposed.

## 7. Headroom strategy candidates

P0-B: dense grains with no position spray add coherently, up to +13 dB.

| Candidate | Rule | Worst over-level | Worst under-level |
|---|---|---|---|
| None | gain law told "decorrelated" | +13.0 dB RMS, +13.2 dB peak | — |
| Coherence from spray, 5 ms knee | coherent until spray > 5 ms | +10.6 dB (82 Hz tone), +4.7 dB (guitar) | −10.7 dB (noise) |
| Coherence from spray, 50 ms knee | coherent until spray > 50 ms | +0.6 dB | −13.3 dB (noise), −8.3 dB (guitar) |
| Assume coherent | amplitude normalisation always | +0.04 dB | −13.9 dB |
| Fixed reservation | no law change | needs 13.2 dB of headroom | — |

No single spray rule is right, because how quickly grains decorrelate depends on
the material: noise after one sample, a low tone only after about half its
period. A short knee is unsafe for bass; a long knee is safe but makes noisy
material up to 13 dB quiet at small spray.

SPLIT's default settings sit outside the problem: every cloud branch uses at
least 50 % spray, where all four laws agree, and measured SPLIT RMS stays within
−0.25 to +0.20 dB of TRACE. The hazard returns only if spray becomes a user
control. A second coherent case exists too: at small spray a band's CLOUD
correlates with its own TRACE, and the equal-power pair sums to +3.0 dB at
`d = 0.5` (+1.0 dB at 5 ms spray, 0 dB at full spray).

There is no limiter. Peaks at equal RMS do rise (crest factor): +0.7 to +6.1 dB
on the clean guitar, and +7.6 to +12 dB on the distorted chord, whose TRACE has
a crest factor near 1 dB.

## 8. Phase and latency alignment

- Spectral bands are zero-phase. All buffers share one seam, so there is nothing
  to align: at DISSOLVE 0 the output is the TRACE loop to −314 dB.
- Conventional bands carry the crossover's phase. They are consistent among
  themselves, but their sum is not the waveform of the spectral TRACE (+3.7 dB
  sample error, 0.01 dB third-octave distance). A product could not crossfade
  between a full-band TRACE and conventionally split bands without comb
  filtering; it would have to use the split bands for TRACE as well.
- Capture latency is unchanged from P0-B (two hops of future context).

## 9. Proposed realtime buffer ownership

| Buffer | Count | Size each (stereo float32, max selection) | Written | Read |
|---|---|---|---|---|
| History ring | 1 | P0-A table | every hop | capture job |
| Reconstruction scratch | 1 | 0.56–1.22 MiB | capture job, reused per band | capture job |
| TRACE band | n | 0.51–1.11 MiB | once per capture | TRACE readers |
| CLOUD band | n | 0.51–1.11 MiB | once per capture | that band's grains |
| Grain pool | n | budget × 64 B | grain start/stop | render loop |

Three bands need 3.05–6.66 MiB per voice against 0.51–1.11 MiB for P0-B. The
source buffer itself need not be kept (the TRACE bands sum to it).

## 10. CPU and memory estimates

Counts, not measurements. No realtime claim.

| Item | P0-B CLOUD | SPLIT, 3 bands, spectral | SPLIT, 3 bands, conventional |
|---|---|---|---|
| Capture: inverse FFTs (stereo, max selection) | 138–150 | 828–900 | 0 for the bands (138–150 only if a FILTERED source is still masked spectrally) |
| Capture: filter work | — | — | 40 biquad sections × selection length |
| Seam search | 1 | 1 (shared) | 1 (shared) |
| Per-voice buffers | 0.51–1.11 MiB | 3.05–6.66 MiB | 3.05–6.66 MiB |
| Steady state at the ceiling, 48 kHz | 12.3 M taps/s | 12.6 M taps/s (32 grains + 3 TRACE readers) | same |
| Steady state at defaults | 5 grains | 10–15 grains + 3 readers | same |

The steady-state cost is essentially P0-B's, because the grain budget is shared.
What SPLIT adds is **capture-time work (6×) and memory (6×)**. The capture burst
was already the dominant realtime risk in P0-B; the spectral SPLIT makes it six
times larger unless bands are reconstructed over more hops (longer wait before
the ghost can sound) or the cloud branches reuse the TRACE bands (which brings
back the crossover dip).

Worst callback: 96 kHz, N = 8192, small host block, capture reconstruction of
six band buffers in progress, all 32 grains active in the top band's settings.

## 11. Unresolved architectural choices

1. Spectral or conventional decomposition. They measure the same in the render;
   they differ in capture cost, phase and transient behaviour (§3).
2. Whether SPLIT is a third MODE or a property of DISSOLVE (report §14).
3. Crossover frequencies, transition width and band count. Untested by ear.
4. Two buffers per band (flat, 6× memory) versus one (3× memory, up to −3 dB
   dips), or more, narrower bands.
5. Gain policy if spray is ever exposed (§7).
6. Whether the top band should be transposed at all, and anti-aliasing if so:
   an octave up folds everything above 12 kHz back at full level.
7. Rounding grain positions to whole samples at unity speed would remove the
   interpolator's top-octave loss for untransposed grains (not done: it would
   change the P0-B engine).
