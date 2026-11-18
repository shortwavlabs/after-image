# P0-C listening notes

Status: **NOT YET FILLED IN.** The renders were produced by an automated agent
that cannot listen. Nothing in the repository about how a P0-C render sounds is
based on listening until a human completes this file.

Procedure: `docs/P0-C-FINAL-REPORT.md` section 13. Score before opening
`renders/p0c/blind-KEY-do-not-open.json`.

Every file is level-matched (-23 dBFS RMS over its first 2 s, before the MEMORY
envelope); the gain applied to each is in `p0c-manifest.json` (`match_gain_db`).
FULL renders are split at 250 Hz and 2 kHz. FILTERED renders are split at
log-thirds of the selected band (849 / 2061 Hz for 350-5000 Hz; 3420 / 5848 Hz
for 2-10 kHz), so a FULL-vs-FILTERED pair differs in material AND split points.

Listener: ____  Date: ____  Monitoring: ____  Level: ____

## Suggested first pass (preferred label, least liked, comments)

| set | preferred | least liked | comments |
|---|---|---|---|
| guitar_dist__full_spectrum__cloud_vs_split | | | |
| guitar__long_sustain__cloud_vs_split | | | |
| guitar_dist__full_spectrum__progression | | | |
| drums__full_spectrum__progression | | | |
| guitar_dist__full_spectrum__strategies | | | |
| guitar_dist__full_spectrum__implementation | | | |
| drums__full_spectrum__implementation | | | |
| guitar__long_sustain__source | | | |
| guitar_dist__full_spectrum__pitch | | | |

## Remaining sets (24)

| set | preferred | least liked | comments |
|---|---|---|---|
| | | | |

## Questions the listening test must answer

1. Does any SPLIT render keep the weight of the source while its top transforms? Which label, which source?
2. Is that better than CLOUD or FOCUS, or just closer to the dry loop?
3. Progressions: is a band-ordered dissolve (lows last, or lows never) preferred to the plain crossfade you chose in P0-B?
4. S1 vs S2 keep-low vs S3: is per-band grain behaviour (S3) worth having?
5. Implementation sets: can the two be told apart at all? (The measurements say no.)
6. FULL vs FILTERED with the same mode: are both wanted? Is the quieter, receding FILTERED ghost still the effect you liked?
7. Pitch in the top band: none, detune or octaves?
8. Artifacts: thinning near 250 Hz, pre-echo on drum hits, harsh peaks on the distorted chord, bass roughness?
9. In the BODY + GHOST mixes, does the ghost help the dry signal?

## Verdict (human)

SPLIT worth building: ____   As a mode or as a DISSOLVE shape: ____   Proceed to: ____
