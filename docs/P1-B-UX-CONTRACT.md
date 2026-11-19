# AFTERIMAGE — P1-B UX Contract

What a musician can expect from the P1-B development build. Mechanism:
[P1-B-CAPTURE-ARCHITECTURE.md](P1-B-CAPTURE-ARCHITECTURE.md). This is a development interface for auditioning, not
the product UI ([UI-CONCEPT.md](UI-CONCEPT.md) remains the target for that).

## 1. What plays

There is **one playback engine: CLOUD**, a granular cloud over the captured loop. **DISSOLVE** crossfades from the
captured loop itself (TRACE, at 0) to the cloud (at 1). FOCUS and GLITCH are research engines and are **not** in this
build; the UI does not offer them.

## 2. Capture modes

| Mode | You do | AFTERIMAGE does |
|---|---|---|
| **MANUAL** (default) | Play, then press IMPRINT (button, footswitch, or MIDI) | Captures the last *capture length* of audio, ending at the moment of the press, and plays it as the new ghost about 0.1 s later (FULL) or 0.2–0.27 s later (FILTERED) |
| **RANDOM** | Play | Every *interval* (±25 %), picks a random stretch of the last 4 s that is loud enough, and replaces the ghost with it |
| **AUTO** (experimental) | Play | Detects the start of a new note or hit, captures from just before it, and replaces the ghost, at most once per *cooldown* |

In every mode, IMPRINT still works as an explicit capture, and the spectrogram's drag-to-select + IMPRINT SELECTION
still works for precise editing. Nothing requires touching the spectrogram.

## 3. Controls

| Control | Parameter ID | Range / values | Default | Automatable |
|---|---|---|---|---|
| MODE | `capture_mode` | MANUAL, RANDOM, AUTO | MANUAL | yes |
| LENGTH | `capture_length` | 250, 500, 750, 1000, 1500 ms | 750 ms | yes |
| SOURCE | `source` (P1-A) | FULL, FILTERED | FULL | yes |
| BAND CENTRE | `band_center` | 80 Hz – 8 kHz | 1 kHz | yes (FILTERED only) |
| BAND WIDTH | `band_width` | 0.5 – 8 octaves | 3 oct | yes (FILTERED only) |
| HOLD | `hold` | off / on (latched) | off | yes |
| IMPRINT (trigger) | `imprint` | off / on; a rising edge captures | off | yes |
| INTERVAL | `random_interval` | 1 – 16 s | 4 s | yes (RANDOM) |
| GATE | `activity_gate` | −72 to −24 dBFS | −48 dBFS | yes (RANDOM, AUTO) |
| SENSITIVITY | `auto_sensitivity` | 0 – 1, scale in §6 | 0.5 | yes (AUTO) |
| COOLDOWN | `auto_cooldown` | 0.5 – 8 s | 2 s | yes (AUTO) |
| BODY, GHOST, MEMORY, DISSOLVE | P1-A | unchanged | unchanged | yes |

Parameter IDs are development IDs (version 1); there is no preset contract yet.

## 4. Triggering IMPRINT

| Path | Works in | Timing |
|---|---|---|
| IMPRINT button in the plugin window | all hosts | start of the next audio block |
| MIDI Note On (any note, any channel, velocity > 0) or CC 64 (sustain pedal) pressed | **VST3** hosts that route MIDI to an audio effect (e.g. Ableton Live: a MIDI track's "MIDI To" set to the audio track, then AFTERIMAGE) | the exact sample of the MIDI event |
| Host automation / controller assignment of **IMPRINT (trigger)** | AU and VST3, all hosts (e.g. Logic: learn a footswitch or MIDI controller to the parameter) | start of the block in which the value goes from below 0.5 to 0.5 or above |

- The AU is a normal audio effect (`aufx`) and receives no MIDI. **In Logic, use the automation/controller path.**
- One MIDI trigger per audio block is accepted; extra ones in the same block are counted and ignored.
- The automation trigger fires on the *rising edge* only. Releasing does nothing. Loading a session or preset,
  changing the sample rate, or un-bypassing never fires it, even if it was saved "on". A pulse shorter than one audio
  block may be missed.
- If a capture is still being built (about 0.1–0.3 s after the previous one), a new IMPRINT is refused (`BUSY`) and
  shown as rejected. It is not queued.
- In the first *capture length* after the plugin starts there is not enough audio; IMPRINT is refused
  (`BEFORE_STREAM`) rather than capturing less.

## 5. HOLD

- HOLD on: RANDOM and AUTO keep listening but **never replace the ghost**. The UI shows each blocked capture as
  "suppressed by HOLD".
- An explicit IMPRINT (button, MIDI, trigger parameter) **does** replace the ghost under HOLD, and the new ghost is
  then the held one. CLEAR still clears.
- HOLD is not a freeze: the held ghost still fades with MEMORY and follows DISSOLVE. For a longer ghost, raise MEMORY.
- HOLD with no ghost yet: nothing automatic happens until HOLD is released; IMPRINT works.
- Releasing HOLD: nothing that was suppressed is replayed. RANDOM waits one interval; AUTO waits for the next new note.

## 6. AUTO sensitivity scale

Set in Stage D from synthetic fixtures (P1-B-QUALIFICATION §1.5). Documented here once fixed.

## 7. Status the UI must show

- The playback engine (CLOUD with TRACE → CLOUD DISSOLVE).
- Capture state: IDLE / WAITING FOR AUDIO (accepted, waiting for post-roll) / BUILDING / PLAYING.
- The last request: its origin (BUTTON, MIDI, AUTOMATION, RANDOM, AUTO), outcome (accepted, completed, rejected with
  reason, suppressed by HOLD, skipped while busy, no loud-enough candidate, ignored while bypassed) and its length.
- HOLD on/off; RANDOM's time to next attempt; AUTO's state (armed, in event, cooldown) and the input level against the
  gate.
- Output peak and overs (P1-A).

## 8. Bypass, transport, sessions

- Bypassed: dry audio passes unchanged; IMPRINT from any source is ignored; RANDOM and AUTO pause.
- Transport is never read. The effect works on whatever the host plays through it, stopped or running.
- Sessions and presets restore the controls, never a captured ghost and never a capture.

## 9. Deferred (not in P1-B)

FREEZE VIEW for the spectrogram, MIDI to the AU (`aumf`), MIDI learn inside the plugin, the PERFORMANCE PAD (X/Y),
ghost scrubbing, live band manipulation, touch gestures, FOCUS and GLITCH engines, pitch, the production UI.
