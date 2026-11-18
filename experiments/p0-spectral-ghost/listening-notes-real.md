# Real-audio listening notes

Status: **NOT YET FILLED IN.** The renders were produced by an automated agent
that cannot listen. Nothing in the repository about how these renders sound is
based on listening until a human completes this file.

Procedure: `docs/REAL-AUDIO-QUALIFICATION.md` section 8. Score before opening
`renders/real-audio/blind-KEY-do-not-open.json`. Every file is level-matched
(-23 dBFS RMS over its first 2 s, before the MEMORY envelope).

Listener: ____  Date: ____  Monitoring: ____  Level: ____

## First pass: priority sources

| set | preferred | least liked | which is "glitchy"? | which keeps the lows? | comments |
|---|---|---|---|---|---|
| 01__01_distorted_guitar_chord__engines | | | | | |
| 02__01_distorted_guitar_chord__progression | | | - | - | |
| 03__03_acoustic_drum_break__engines | | | | | |
| 04__03_acoustic_drum_break__progression | | | - | - | |
| 05__04_sustained_vocal__engines | | | | | |
| 06__04_sustained_vocal__progression | | | - | - | |
| 07__05_evolving_synth_pad__engines | | | | | |
| 08__05_evolving_synth_pad__progression | | | - | - | |

## Second pass

| set | preferred | least liked | which is "glitchy"? | which keeps the lows? | comments |
|---|---|---|---|---|---|
| 09__02_clean_electric_guitar__engines | | | | | |
| 10__06_piano_chord__engines | | | | | |
| 11__07_bass_sustained__engines | | | | | |
| 12__08_spoken_voice__engines | | | | | |
| 13__09_metallic_percussion__engines | | | | | |
| 14__10_ambient_field_recording__engines | | | | | |
| 15__11_dense_rhythmic_percussion__engines | | | | | |
| 16__12_single_acoustic_pluck__engines | | | | | |

## Not blind

| check | notes |
|---|---|
| Does each `trace.wav` loop sensibly? List sources whose selection should move (with times). | |
| `mix_split_s1.wav`, `mix_progression_s2_keep.wav` (turn down 03 and 11) | |
| Hiss or grain noise on the synth pad clouds? | |
| `split_s1_octaves.wav` on 09: aliasing? | |

## Decisions

1. S3: keep as a character next to CLOUD/FOCUS, or drop? ____
2. S2 keep-low against the plain parallel morph: preferred on which material? ____
3. Should the crossover follow the material? ____
