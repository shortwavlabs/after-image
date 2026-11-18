# AFTERIMAGE — Real-Audio Qualification (P0-C engines, unchanged)

Date: 2026-11-18. Code: P0-C head `f80845d` plus one new runner, `experiments/p0-spectral-ghost/run_real.py`
(no DSP in it). No algorithm, threshold, P0-A/B/C evidence file or earlier render pack was changed.

**Nobody has listened to these renders.** Everything below is measurement. The purpose of this document is to
get the pack in front of ears with the measured risks already known.

## 1. Summary

- 12 recordings inventoried; the AIFF and the FLAC were copied to 24-bit WAV with identical decoded audio.
- 3 recordings keep the default 1.00–1.75 s selection; 9 have a local sidecar.
- 12 of 12 captures render (14 listening files each; 168 renders, 288 measured, 0 non-finite, 0 denormals).
  One capture failed on the first attempt, and the two drum selections were re-cut after a review (§3, §6.1).
- No ghost render clips (loudest −5.54 dBFS). **Four BODY+GHOST mixes exceed 0 dBFS**, up to +1.02 dBFS, on the two
  sources that are themselves at full scale (§6.2).
- **S2 keep-low** holds the low band as a loop on every source (repetition 0.74–1.00 against ≤ 0.08 for CLOUD).
  On five sources that makes it nearly the plain loop, on three it makes it nearly CLOUD (§5.2).
- **S3** shows more fine-scale level movement than CLOUD on one source only (metallic percussion); on both drum
  recordings it shows slightly less.
  Six of the twelve recordings have under 1 % of their energy above 2 kHz, where S3's short grains act (§5.1).
- Sample licences are **not known**: no file carries a Freesound ID (§7).

## 2. Inventory

Levels are over the whole file. "Full-scale" counts samples at ±1 LSB of 0 dBFS and the longest run of them.
Silence is 50 ms blocks below −50 dBFS at the start / end, in seconds.

| file | format | fs | ch | s | peak dBFS | RMS dBFS | full-scale (run) | lead / trail silence | L/R corr | energy <250 / 250–2k / >2k Hz |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 01_distorted_guitar_chord.wav | PCM 16 | 48000 | 2 | 17.51 | −1.68 | −14.4 | 0 | 0.00 / 1.41 | 0.67 | 90 / 8 / 2 % |
| 02_clean_electric_guitar.wav | PCM 16 | 44100 | 1 | 10.75 | 0.00 | −18.4 | 1 (1) | 0.05 / 0.60 | – | 5 / 95 / 0.4 % |
| 03_acoustic_drum_break.wav | PCM 16 | 44100 | 2 | 11.04 | 0.00 | −13.7 | **471 (30)** | 0.00 / 0.04 | 0.90 | 80 / 13 / 7 % |
| 04_sustained_vocal.wav | PCM 24 | 48000 | 2 | 62.44 | −10.86 | −31.1 | 0 | 2.45 / 5.54 | −0.08 | 24 / 72 / 4 % |
| 05_evolving_synth_pad.wav | float 32 | 44100 | 2 | 52.29 | −17.70 | −31.4 | 0 | 0.15 / 0.24 | 1.00 | 88 / 12 / 0.1 % |
| 06_piano_chord.wav | PCM 24 | 48000 | 2 | 12.00 | −8.47 | −28.2 | 0 | 0.00 / 3.05 | 0.16 | 54 / 46 / 0.1 % |
| 07_bass_sustained.aiff → .wav | PCM 24 (BE → LE) | 44100 | 2 | 3.67 | −2.00 | −13.6 | 0 | 0.00 / 0.12 | 1.00 | 99.7 / 0.3 / 0 % |
| 08_spoken_voice.wav | PCM 16 | 44100 | 2 | 2.15 | −3.00 | −24.2 | 0 | 0.35 / 0.60 | 0.99 | 40 / 53 / 7 % |
| 09_metallic_percussion.wav | PCM 16 | 44100 | 2 | 3.02 | −3.37 | −28.6 | 0 | 0.00 / 2.47 | 0.74 | 0 / 0.4 / 99.6 % |
| 10_ambient_field_recording.wav | PCM 16 | 44100 | 2 | 90.09 | −15.80 | −35.1 | 0 | 0.00 / 0.04 | 0.21 | 35 / 50 / 15 % |
| 11_dense_rhythmic_percussion.wav | PCM 16 | 44100 | 2 | 6.86 | 0.00 | −15.8 | 2 (1) | 0.00 / 0.01 | 0.93 | 74 / 19 / 7 % |
| 12_single_acoustic_pluck.flac → .wav | FLAC 24 → PCM 24 | 44100 | 2 | 6.99 | −1.62 | −22.0 | 0 | 0.15 / 0.14 | 0.95 | 91 / 9 / 0 % |

Observations that matter later:

- **03 is clipped at source**: 471 full-scale samples, one run of 30 consecutive samples. 02 and 11 touch full scale.
- **04 (vocal)**: the first 1.7 s measure −67 to −77 dBFS, the level then rises and crosses −50 dBFS at 2.4 s
  (−37 dBFS at 2.8 s). The default selection 1.00–1.75 s is −76 dBFS. If the voice is audible to you from about 1 s,
  that disagrees with these numbers and I would like to know: it would mean the file I measured is not what you hear.
- 04, 06 and 10 are wide (L/R correlation −0.08 to 0.21); 05 and 07 are dual mono; 02 is mono.
- DC offset is below 0.0002 on every file. All sample rates are supported (44.1 / 48 kHz); nothing was resampled.
- "Distorted guitar" (01) has 90 % of its energy below 250 Hz and swells for 13 s. It is a low drone more than a chord.

Full figures, SHA-256 of every file and embedded tags: `experiments/p0-spectral-ghost/real-audio-inventory.json`.

### Conversion

`ffmpeg -i <src> -map_metadata 0 -c:a pcm_s24le <name>.wav`, written next to the originals. The originals are untouched
(SHA-256 unchanged: `ba026e5c…` AIFF, `c9313b50…` FLAC). Decoded-audio MD5 of source and copy are equal
(`b5c626c2…` for 07, `acb9ff08…` for 12), so the copies are lossless.

## 3. Capture regions

Criteria were written into `run_real.py` before any render (see its docstring):

- **sustained** — the default stands if its RMS is within 6 dB of the loudest 0.75 s window of the file and no 50 ms
  block is below −50 dBFS. Otherwise: the loudest steady 0.75 s (maximum of mean − standard deviation of 50 ms levels).
- **rhythmic** (03, 11) — always explicit: one period (onset autocorrelation) × the largest power of two that fits in
  1.5 s, **plus the 80 ms seam**, starting 90 ms before the strongest onset.
- **event** (08, 09) — always explicit: the span within 30 dB of the loudest 10 ms block.

| file | class | selection (s) | RMS dBFS | why |
|---|---|---|---:|---|
| 01 distorted guitar | sustained | 7.45–8.20 | −11.1 | default is 8.4 dB below the loudest window (still in the swell) |
| 02 clean guitar | sustained | 1.00–1.75 (default) | −15.2 | within 1.9 dB of the loudest window |
| 03 drum break | rhythmic | 2.67–4.13 | −14.0 | period 1.38 s (autocorrelation 0.65); loop comes out at 1.378 s |
| 04 vocal | sustained | 11.75–12.50 | −23.6 | default is −76 dBFS |
| 05 synth pad | sustained | 44.30–45.05 | −26.2 | default is 10.8 dB below the loudest window |
| 06 piano | sustained | 1.00–1.75 (default) | −22.1 | within 2.1 dB |
| 07 bass | sustained | 0.05–0.80 | −7.9 | default is 10.2 dB down the decay; see §6.1 for 0.05 |
| 08 spoken voice | event | 0.36–1.52 | −21.5 | the phrase; the default runs into the silent tail |
| 09 metallic percussion | event | 0.01–0.34 | −19.0 | the default is digital silence |
| 10 field recording | sustained | 68.95–69.70 | −30.3 | default is 11.7 dB below the loudest window |
| 11 dense percussion | rhythmic | 1.61–2.97 | −16.4 | period 1.28 s (autocorrelation 0.49, a weak estimate); loop comes out at 1.266 s |
| 12 acoustic pluck | sustained | 1.00–1.75 (default) | −19.9 | within 5.4 dB |

Each choice is stored with its reason in `inputs/<name>.json` (local, git-ignored) and in `real-audio-regions.json`.
For the three "default" files the sidecar repeats the default so that every source has one full-band case; the
harness default would otherwise add a 350 Hz–5 kHz case to those three only.

Two amendments were made after the first run, both recorded in the `run_real.py` docstring:

1. Sustained selections start at 0.05 s or later (§6.1).
2. The first drum selections were exactly one period long (2.75–4.13 s and 1.69–2.97 s). The loop engine removes the
   80 ms seam from the selection, so 03 looped at 1.286 s for a 1.38 s bar and 11 at 1.195 s for 1.28 s: every repeat
   94 ms and 85 ms early. The rule now adds the seam and starts 90 ms before the onset, so the crossfade blends the
   same position of two consecutive bars. Result: 1.378 s for 03; 1.266 s for 11, still 14 ms short because loop
   lengths move in 23 ms steps (the STFT hop). Everything was re-rendered; the numbers below are from the second run.
   The first hit of 03 in `trace.wav` peaks within 1.4 dB of the same hit in the recording.

This is a property of the engine, not of these files: **a selection loops about 80 ms shorter than it was drawn.**
On rhythmic material that is audible as a skipped fraction of a beat unless the selection allows for it.

Limits of this step: the regions were chosen by level, not by ear, and class labels come from the file names. The two
rhythmic selections are one bar each; a selection that is musically wrong (for example a bar that does not loop) will
show up in `trace.wav` first. Change `t0`/`t1` in the sidecar and re-run `render --only user_<name>`.

## 4. What was rendered

The unchanged P0-C experiment (`p0.split_experiment.run`), each source at its native rate, N = 4096, FULL source,
crossovers 250 Hz and 2 kHz, DISSOLVE = 1 for the static renders, 6 s ghosts (T60 5 s), 12 s progressions.
Per source, in `renders/real-audio/user_<name>/full_spectrum/`:

`trace`, `p0b_cloud` (CLOUD), `p0b_focus` (FOCUS), `split_s1`, `split_s2_keep_100`, `split_s3_100`, `conv_s1`,
`conv_s3_100`, `split_s1_detune`, `split_s1_octaves`, four `progression_*`, `mix_split_s1`, `mix_progression_s2_keep`,
`roi_oneshot`, and `../source.wav`.

Every ghost is matched to −23 dBFS RMS over its first 2 s before the decay envelope, as in P0-B and P0-C. Engines are
therefore compared at equal RMS, and the level relation to the dry recording is **not** the natural one (§6.3).

## 5. Measured comparisons

Figures are from `real-audio-metrics.json`;
`uv run python run_real.py summary` prints the full tables.

"Band repetition" is the autocorrelation of a band at the loop period: 1.00 means the band is still the loop,
0.00 means nothing of the loop's timing is left.

### 5.1 S3 against CLOUD and FOCUS

Two figures were fixed before rendering for "glitchy": the mean absolute level change between adjacent 10 ms blocks,
and the number of upward jumps over 6 dB per second (0.5–4 s of each file). Ripple is the 50 ms envelope range.

| source | energy > 2 kHz | 10 ms step: TRACE / CLOUD / FOCUS / S3 (dB) | jumps > 6 dB per s: CLOUD / FOCUS / S3 | ripple: CLOUD / FOCUS / S3 (dB) |
|---|---:|---|---|---|
| 01 distorted guitar | 0.5 % | 0.85 / 0.99 / 0.95 / 1.09 | 0 / 0 / 0 | 11.5 / 12.8 / 14.1 |
| 03 drum break | 10.0 % | 3.38 / 2.99 / 2.17 / 2.62 | 5.4 / 2.9 / 4.0 | 23.9 / 19.5 / 22.5 |
| 04 vocal | 10.0 % | 0.86 / 0.96 / 0.91 / 0.92 | 0 / 0 / 0 | 10.1 / 8.5 / 7.7 |
| 05 synth pad | 0.0 % | 2.34 / 1.93 / 1.85 / 1.80 | 0.6 / 0.3 / 0 | 12.4 / 13.9 / 11.4 |
| 02 clean guitar | 0.3 % | 0.91 / 1.09 / 1.10 / 1.13 | 0 / 0 / 0 | 11.3 / 9.6 / 11.4 |
| 06 piano | 0.2 % | 1.31 / 1.25 / 1.45 / 1.33 | 0 / 0 / 0 | 6.7 / 7.5 / 6.3 |
| 07 bass | 0.0 % | 0.18 / 0.77 / 0.88 / 0.75 | 0 / 0 / 0 | 18.0 / 21.1 / 20.1 |
| 08 spoken voice | 8.0 % | 3.52 / 2.65 / 2.05 / 2.50 | 4.9 / 1.4 / 4.3 | 36.3 / 24.8 / 29.0 |
| 09 metallic percussion | 99.9 % | 1.77 / 1.66 / 1.75 / **2.71** | 0.6 / 1.7 / **5.4** | 22.7 / 22.0 / 22.2 |
| 10 field recording | 25.2 % | 1.11 / 1.04 / 1.08 / 1.20 | 0 / 0 / 0 | 8.1 / 9.2 / 6.5 |
| 11 dense percussion | 7.1 % | 3.20 / 3.07 / 2.44 / 2.77 | 5.4 / 4.0 / 5.7 | 29.2 / 23.7 / 26.4 |
| 12 acoustic pluck | 0.0 % | 0.93 / 0.95 / 1.02 / 0.88 | 0 / 0 / 0 | 9.6 / 12.3 / 13.1 |

What the numbers support:

- S3 and CLOUD both destroy the loop in every band (repetition ≤ 0.10 everywhere), so neither keeps the source's rhythm.
- By these two figures S3 moves more than CLOUD on **09 only** (step 2.71 against 1.66 dB, 5.4 against 0.6 jumps per
  second). On the two drum recordings it moves slightly *less* than CLOUD (−0.4 dB on 03, −0.3 dB on 11). On the
  other nine the difference is within ±0.2 dB.
- That fits the design: S3's short, sparse grains live in the band above 2 kHz. Six recordings (01, 02, 05, 06, 07,
  12) hold under 1 % of their energy there, so on those S3 is mostly "CLOUD with 300 ms grains in the lows".
- These figures do not prove S3 sounds no different elsewhere. A 10 ms level statistic does not see pitch smear,
  spatial movement or grain texture at constant level. On bass-heavy sources it also partly measures the waveform
  itself (the pad's loop scores 2.34 dB).
- On transient sources (03, 08, 11) every cloud is *smoother* than the loop by these figures: the loop repeats the
  hits, the clouds scatter them.

### 5.2 S2 keep-low: what the low band does

| source | energy < 250 Hz | low-band repetition: CLOUD / S3 / S2 keep / S1 | low-band level, S2 keep re TRACE (dB) | S2 keep crest − TRACE crest (dB) |
|---|---:|---|---:|---:|
| 01 distorted guitar | 86.6 % | −0.05 / 0.03 / 0.91 / 0.98 | −0.5 | +1.6 |
| 03 drum break | 75.7 % | −0.02 / −0.05 / 0.96 / 0.99 | −0.1 | +2.3 |
| 04 vocal | 5.1 % | 0.05 / 0.04 / 0.97 / 0.99 | −0.2 | +0.6 |
| 05 synth pad | 77.9 % | 0.00 / 0.00 / **0.74** / 0.94 | −0.6 | +1.3 |
| 02 clean guitar | 11.4 % | −0.04 / −0.05 / 0.85 / 0.96 | −0.6 | 0.0 |
| 06 piano | 40.1 % | −0.01 / 0.00 / 0.99 / 1.00 | 0.0 | +2.4 |
| 07 bass | 99.6 % | −0.02 / −0.06 / 1.00 / 1.00 | 0.0 | +0.6 |
| 08 spoken voice | 36.7 % | −0.03 / 0.05 / 0.81 / 0.95 | −0.3 | −0.3 |
| 09 metallic percussion | 0.02 % | 0.05 / 0.10 / 0.97 / 0.99 | −0.1 | +4.4 |
| 10 field recording | 4.9 % | 0.03 / 0.02 / 0.99 / 1.00 | −0.1 | +1.6 |
| 11 dense percussion | 70.9 % | −0.02 / −0.03 / 0.98 / 0.99 | 0.0 | +1.5 |
| 12 acoustic pluck | 87.4 % | −0.02 / 0.05 / 0.97 / 0.99 | −0.1 | +1.7 |

What the numbers support:

- The low band stays a loop under S2 keep on all twelve (0.74–1.00) at its original level (within 0.6 dB). CLOUD and
  S3 leave no repetition there. The P0-C result on synthetic sources holds on real ones.
- The lowest figures are 05 (0.74), 08 (0.81) and 02 (0.85). Part of the measured band is the crossover's upper
  slope, which S2 does dissolve; I did not separate the two.
- **Where most of the sound is below 250 Hz, S2 keep is close to the plain loop.** 07 (99.6 % low): crest 5.4 dB against
  the loop's 4.8 dB, ripple 3.2 against 3.0 dB. Expect 01, 05, 07 and 12 to sound mostly looped, with a thin cloud on top.
- **Where almost nothing is below 250 Hz, S2 keep is close to CLOUD**: 04 (5 %), 10 (5 %), 09 (0.02 %).
- So with fixed 250 Hz / 2 kHz crossovers, how much "split" you hear depends on the recording. 03, 06, 08 and 11 are
  the sources where both halves carry real energy; listen to those first when judging S2.
- In the 12 s progressions the same holds over time: low-band repetition 0.87–1.00 for S2 keep against 0.37–0.48 for
  the parallel morph (which crossfades the whole signal).

### 5.3 Spectral against conventional bands (not in the blind pack)

P0-C found the two implementations no further apart than the same engine with another seed. On real audio that holds
for S3 on all twelve, and for S1 on most, with one clear exception:

| | S1 third-octave distance, spectral vs conventional (dB) | S1, same engine with another seed (dB) |
|---|---:|---:|
| 12 acoustic pluck | **2.74** | 0.58 |
| 07 bass | 0.59 | 0.30 |
| the other ten | 0.06–0.44 | 0.28–1.62 (10 of 10 at or below this within 0.1 dB) |

On the pluck the two implementations give measurably different long-term spectra. A band-by-band check of the two
files puts the difference at 320–510 Hz (up to 1.6 dB, in bands 13–28 dB below the strongest one), which is the upper
slope of the 250 Hz crossover: the 4th-order filters and the one-octave spectral mask do not have the same slope.
Both sources are 87–99.6 % below that crossover. I did not investigate further; the brief excludes algorithm work. `conv_s1.wav` and `split_s1.wav` are in the
case folders if you want to hear it.

## 6. Clipping, gain, capture failures and measured risks

### 6.1 Capture failure

`07_bass_sustained` was first selected at 0.00–0.75 s and **failed**: the capture needs audio before the selection,
and at t0 = 0 the harness raised `ValueError: operands could not be broadcast together with shapes (0,2) (3528,1)`
rather than a capture rejection. Selections starting at 0.02 s or later work. I moved the bass to 0.05 s (and wrote
that floor into the criteria as an amendment) and re-rendered. The failed run is kept as
`real-audio-manifest.first-run.json`; the full second run, without failures, is `real-audio-manifest.json`.

Product meaning: in a plugin the history always holds earlier audio (silence at worst), so this is a harness edge,
but it is an unhandled one and the error message says nothing useful. Not fixed here.

### 6.2 Clipping

| what | result |
|---|---|
| Source files at full scale | 03 (471 samples, longest run 30), 11 (2 samples), 02 (1 sample) |
| Ghost renders above 0 dBFS | none; loudest is 08 CLOUD at −5.54 dBFS |
| BODY+GHOST mixes above 0 dBFS | **03**: **+1.02** (`mix_split_s1`), +0.92 (`mix_progression_s2_keep`); **11**: +0.02, +0.64 |
| Mixes exactly at 0 dBFS | 02 (the source's own peak) |
| Non-finite samples, denormals | 0 of 288 |

The four mixes are 32-bit float files, so nothing is lost on disk, but they will clip in any fixed-point path or DAC.
Cause: a full-scale body plus a ghost at −23 dBFS RMS. No limiter was added. Turn the mixes down, do not judge
distortion from them.

### 6.3 Gain changes

The −23 dBFS match applies these gains to the raw engine output (TRACE row; the engines differ from it by under 2 dB
except FOCUS on 08 and 11, −3.0 dB each):

| | 07 | 01 | 03 | 02 | 11 | 12 | 09 | 08 | 06 | 04 | 05 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| match gain (dB) | −15.1 | −12.0 | −9.2 | −7.4 | −7.1 | −3.0 | −2.1 | −2.0 | −0.9 | +0.7 | +3.2 | **+7.3** |

- In the mixes the ghost of 07, 01 and 03 sits 8–15 dB **below** its natural level; the ghost of 10 sits 7 dB **above**
  it, and its 16-bit noise floor comes up by the same amount. Mixes are not a fair picture of wet/dry balance.
- At equal RMS the clouds have higher peaks than the loop. Crest factor rises by up to +7.0 dB (07, CLOUD), +5.3 dB
  (01, FOCUS and S3) and +4.3 dB (05, CLOUD). S2 keep and S1 add at most +2.4 dB except on 09 (+4.4 dB).
- Peak relative to the captured loop, top band transposed: +4.9 dB on 09 with octaves, +3.8 dB with detune; at most
  +1.8 dB on the others.
- FOCUS raises all three bands by 1–3.3 dB relative to the loop on 03, 08, 09 and 11 before matching (it concentrates
  grains on the loud part of the capture). The match hides this in the pack; a product without the match would get
  louder with FOCUS on transient material.

### 6.4 Measured risks to listen for

1. **Loop periodicity on transient sources.** The plain loop of 03, 08 and 11 has 33–43 dB of envelope ripple and 8–11
   jumps over 6 dB per second: a repeating bar or phrase. S1 and S2 keep retain that in the lows (ripple 27–31 dB).
   Whether that reads as rhythm or as a stuck sample is a listening question.
2. **Checked and not a risk: energy where the source has none.** On 05 the band above 2 kHz holds 0.0 % of the
   capture, and the band-level metric shows CLOUD, FOCUS and conventional S3 at +8 to +13 dB relative to the loop there.
   Measured on the files themselves, everything above 2 kHz is at −94 to −96 dBFS in the loop and in every cloud, 64 dB
   below the signal. The ratio is a ratio of two near-zero numbers.
3. **Mono fold-down.** 04, 06 and 10 lose 2.5–2.9 dB in mono in every engine, including the plain loop
   (−2.57 to −2.81 dB). That is the recordings' own width; no engine makes it worse by more than 0.2 dB. Worst
   engine-added change: 09 with S3, −1.36 dB against −0.54 dB for the loop.
4. **Octave transposition** aliases above fs/4 (P0-C, K-finding on pitch); 09 has 99.9 % of its energy above 2 kHz and
   is the worst case in this pack. `split_s1_octaves.wav` of 09 is the file to check.
5. **Clipped source.** 58 of 03's full-scale samples lie inside its selection, so the clipping is in every render of 03. Harshness there is the recording, not
   the engine.

Not measured: anything about the seam other than what P0-A/P0-C already verified on synthetic sources; realtime cost.

## 7. Licence and attribution

All twelve files carry the macOS download origin `https://freesound.org/` and nothing more specific. **No file carries a
Freesound sound ID, an author field I can trust as complete, or a licence.** Freesound hosts CC0, CC BY and CC BY-NC
material, so until this table is filled in the recordings and every render made from them stay local (they are
git-ignored), and nothing derived from them should ship or be published.

| file | SHA-256 (first 12) | embedded tags | Freesound URL | author | licence |
|---|---|---|---|---|---|
| 01_distorted_guitar_chord.wav | baafc951422e | none | ? | ? | ? |
| 02_clean_electric_guitar.wav | 6cb3def3cfd2 | none | ? | ? | ? |
| 03_acoustic_drum_break.wav | f9504ff86aea | encoder "FL Studio 12" | ? | ? | ? |
| 04_sustained_vocal.wav | 0b6c64911be6 | none | ? | ? | ? |
| 05_evolving_synth_pad.wav | e7bac8b7581e | none | ? | ? | ? |
| 06_piano_chord.wav | ce7e36cc386c | encoded by REAPER, date 2026-10-27 | ? | ? | ? |
| 07_bass_sustained.aiff | ba026e5c01ff | none | ? | ? | ? |
| 08_spoken_voice.wav | d0d9f99a3cbc | none | ? | ? | ? |
| 09_metallic_percussion.wav | e31a7ea4f2c9 | artist "InspectorJ (www.jshaw.co.uk)" | ? | tag suggests InspectorJ, unconfirmed | ? |
| 10_ambient_field_recording.wav | 38ac953473e8 | title "Mathews Hill", artist "tladb", 2017 | ? | tag suggests tladb, unconfirmed | ? |
| 11_dense_rhythmic_percussion.wav | 8f86e102e5e7 | none | ? | ? | ? |
| 12_single_acoustic_pluck.flac | c9313b509851 | none | ? | ? | ? |

Full hashes are in `real-audio-inventory.json`. The files were renamed after download, so the original Freesound file
names (which contain the sound ID and user name) are gone; the browser's download history is the quickest way back to
the URLs.

## 8. Listening instructions

Pack: `experiments/p0-spectral-ghost/renders/real-audio/` (292 WAVs, 850 MB, git-ignored).
Blind sets: `renders/real-audio/blind/`, 16 folders numbered in listening order.
Key: `renders/real-audio/blind-KEY-do-not-open.json`. Notes template: `experiments/p0-spectral-ghost/listening-notes-real.md`.

Rules:

- Fix the monitor level once, on `A.wav` of set 01, and leave it. All ghosts are at the same RMS (−23 dBFS).
- `reference_roi.wav` is the captured slice at its **recorded** level, from about −8 dBFS (bass) to −30 dBFS (field
  recording), so it can be up to 15 dB louder or 7 dB quieter than the ghosts. Expect the jump; do not re-set the level.
- Each set has that reference and shuffled `A`…`D`. Write notes before opening the key.
- Every file is a 6 s ghost decaying over 5 s (progressions: 12 s). Listen to whole files; S3 and CLOUD differ most
  after the first second.
- Headphones and speakers both, if possible: the low-end questions need speakers, the glitch questions are easier on
  headphones.

**First pass, about 25 minutes — sets 01–08, the four priority sources.**

| sets | source | contents | question |
|---|---|---|---|
| 01, 03, 05, 07 `…__engines` | guitar, drums, vocal, pad | CLOUD, FOCUS, S3, S2 keep-low (shuffled A–D) | Which would you play? Is one of them recognisably "glitchy", and is that good? Is one of them still anchored in the lows, and does that help or just sound like a stuck loop? |
| 02, 04, 06, 08 `…__progression` | same | parallel morph, S2 keep-low, S3 over 12 s (A–C) | Which journey from loop to cloud do you want? Does any of them stop evolving early? (P0-C: S2 keep-low does nothing in the top 30 % of the control.) |

**Second pass, about 15 minutes — sets 09–16**, one `engines` set each for clean guitar, piano, bass, spoken voice,
metallic percussion, field recording, dense percussion, acoustic pluck. Grouped by what they can show (numbers here are set numbers):

- **13 (metallic percussion)**: the only source where S3 measures clearly different from CLOUD. If S3's character is
  wanted anywhere, it should be audible here.
- **10 (piano), 12 (spoken voice), 15 (dense percussion)**: both halves of the split carry energy; best test of S2 keep-low.
- **11 (bass), 16 (acoustic pluck)**: S2 keep-low should be nearly the plain loop. Confirm or contradict.
- **09 (clean guitar), 14 (field recording)**: little low energy; S2 keep-low should be nearly CLOUD.

**Then, in each `user_<name>/full_spectrum/` folder, not blind:**

- `trace.wav` first, to check the selection loops sensibly. If it does not, the comparison on that source is void:
  tell me the times you want.
- `mix_split_s1.wav`, `mix_progression_s2_keep.wav`: body plus ghost. Turn down for 03 and 11 (§6.2), and remember the
  ghost level is matched, not natural (§6.3).
- Optional: `conv_s1.wav` against `split_s1.wav` on 12 (§5.3); `split_s1_octaves.wav` on 09 (§6.4).

**The decision this pack is meant to support** (provisional framing from P0-C, unchanged):

1. Is S3 a character worth keeping next to CLOUD and FOCUS, or is it CLOUD with extra cost?
2. Is S2 keep-low preferred to the plain parallel morph on real material, and on which kinds?
3. If S2 keep-low only works when the source has energy on both sides of 250 Hz, should the crossover follow the
   material? (That would be new DSP; nothing was changed here.)

## 9. Reproduce

From `experiments/p0-spectral-ghost`, with the recordings in `inputs/`:

```bash
uv run python run_real.py inventory
```
```bash
uv run python run_real.py regions
```
```bash
uv run python run_real.py render
```
```bash
uv run python run_real.py blind
```
```bash
uv run python run_real.py summary
```

`regions` rewrites every sidecar from the criteria. To use your own times, edit `inputs/<name>.json` and run
`uv run python run_real.py render --only user_<name>` (it merges into the existing metrics), then `blind` again.
`blind` uses a fixed seed, so the A–D mapping stays the same as long as the set of files does.

Warning for earlier phases: `run.py`, `run_p0b.py` and `run_p0c.py` also read `inputs/`. With the recordings present, a
plain `render` or `all` there adds twelve user sources and rewrites the committed P0-A/B/C manifests and metrics, and
`run_p0c.py blind` rewrites the P0-C blind key. Use `--only <synthetic names>` or move `inputs/` aside before re-running
them. I ran none of them; `git status` shows no tracked file changed.

Checks run: the 158 existing tests pass with the recordings present (they use temporary input folders).
`run_real.py` has no tests of its own; it selects regions, calls the P0-C runner and copies files.
