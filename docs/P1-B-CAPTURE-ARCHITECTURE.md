# AFTERIMAGE — P1-B Capture Architecture

**Status:** design for P1-B on `feature/p1b-performance-capture`, branched from P1-A head `b0c437f`
(shortwavlabs/after-image#6, draft, not merged). Behaviour seen by the musician: [P1-B-UX-CONTRACT.md](P1-B-UX-CONTRACT.md).
Limits and results: [P1-B-QUALIFICATION.md](P1-B-QUALIFICATION.md).

P1-B adds a **capture scheduler**: it decides *what* to capture and *when*. It does not add a playback engine, buffer
format or DSP path. Every capture it requests goes through P1-A's validation, bounded build, post-roll loop contract,
voice slots and REPLACE fade unchanged ([P1-A-REALTIME-ARCHITECTURE.md](P1-A-REALTIME-ARCHITECTURE.md) §4–§7).

## 1. Flow

```text
input ─┬─ BODY (unchanged)
       └─ raw ring (6 s) ─ STFT history (6 s) ─┬─ display columns (unchanged)
                                               └─ per-hop features: level, band flux   (new, §3)
                                                        │
  GUI IMPRINT ──┐                                       ▼
  MIDI note/CC ─┼─► trigger events ─► ModeScheduler: MANUAL | RANDOM | AUTO, HOLD   (new, §4)
  automation ───┘                         │  at most one request at a time
                                          ▼
                              Engine::apply (P1-A validation, unchanged)
                                          │ accepted → Job → build units → seam → voice (P1-A)
                                          ▼
                                  ghost (CLOUD + TRACE, DISSOLVE, MEMORY: unchanged)
```

Everything runs on the audio thread inside `Engine::process`, in stream time. There is no worker thread, no new
lock, no allocation after `prepare`, no unbounded loop and no queue of pending captures.

## 2. Existing structures reused

- **History:** the 6 s raw ring (FULL) and 6 s complex history (FILTERED) already hold everything a scheduler may
  select. No new audio buffer is added. The scrolling display is not involved in capture validity at all.
- **Validation:** `Engine::apply` (epoch, length 0.20–1.50 s, `BEFORE_STREAM`, `FUTURE`, band checks, `EXPIRED`,
  `BUSY`). The scheduler builds a `Command` and calls the same function, so an automatic capture can be rejected for
  exactly the same reasons as a hand-drawn one, and a rejection never touches the playing voice.
- **Build:** one unit per 64 samples at stream sample ≡ 32 (mod 64), never on an analysis hop (P1-A §5).
- **Loop contract:** period = selection; 80 ms post-roll seam; the build waits for its post-roll (P1-A §4.2).

## 3. Features (computed at each analysis hop)

| Feature | Definition | Cost per hop |
|---|---|---|
| Hop level | `10 log10(mean x²)` over the hop's `H` new samples, channels pooled; accumulated per sample as one multiply-add per channel | O(1) |
| Band flux | mean over the 160 display bands of `max(dB_b(m) − dB_b(m−1), 0)`, counting only bands above −90 dB in frame `m` | 160 ops; reuses the band powers `analyse()` already computes (the per-band dB is now computed every hop, not only when the display FIFO has room) |

Stored: the hop level in a ring of `histFrames` floats aligned with the frame history (for RANDOM's activity gate),
and the previous frame's 160 band dB values (for flux). No extra FFT, no per-bin pass.

## 4. ModeScheduler

### 4.1 Where decisions run

- Features update at each hop (§3).
- **Decisions** (issue a RANDOM or AUTO request) run on a **build-unit slot** (stream sample ≡ 32 mod 64) when no
  capture job is active. Those slots carry no build work then, and are never on an analysis hop, so the scheduler adds
  no work to the existing worst-case sample. Stream-time slots make decisions independent of the host block size.
- **MANUAL** requests are applied at their own sample (§5) through the existing command queue.

### 4.2 Request lifecycle

Each request has an **origin** (GUI, MIDI, AUTOMATION, RANDOM, AUTO) and exactly one **outcome**:

| Outcome | Meaning |
|---|---|
| `ACCEPTED` | passed validation; a job exists (state WAITING for post-roll, then BUILDING) |
| `COMPLETED` | the job's voice started (REPLACE fade if a ghost was playing) |
| `REJECTED:<code>` | P1-A validation code, e.g. `BUSY`, `TOO_FEW_BINS`, `BEFORE_STREAM`, `EXPIRED` |
| `SUPPRESSED_HOLD` | RANDOM/AUTO wanted to capture but HOLD was on; nothing queued |
| `SKIPPED_BUSY` | RANDOM/AUTO due while a job was active or both voice slots were sounding; nothing queued |
| `NO_CANDIDATE` | RANDOM found no region above the activity gate within its attempt budget |
| `IGNORED_BYPASS` | trigger arrived while the host bypassed the plugin |
| `DROPPED_RATE` | a second MIDI trigger in the same block (one per block is accepted) |

Counters per origin and the last request (origin, outcome, selection, stream time) are published as atomics for the
UI and tests. "Queued" in the UI means `ACCEPTED` and still WAITING for its post-roll.

### 4.3 Bounds

| Item | Bound |
|---|---|
| Pending captures | 0 queued: one active job at most (P1-A), automatic requests while busy are skipped, not stored |
| MIDI triggers | 1 accepted per block; the rest counted `DROPPED_RATE` |
| GUI commands | P1-A FIFO (32) and engine queue (16); overflow counted `QUEUE_FULL` |
| RANDOM candidates | 8 per tick; each checks at most `ceil(1.5 s · Fs / H) + 1` hop levels (72) |
| AUTO | one event tracked at a time; O(1) state per hop |
| Memory added | `histFrames` floats + 160 floats + counters, allocated in `prepare` |

## 5. MANUAL

- Selection: `s1 = trigger sample`, `s0 = s1 − round(L · Fs)`, `L` from `capture_length` (250/500/750/1000/1500 ms).
  The capture **ends at the trigger**; there is no lookback offset. The build waits for the 80 ms post-roll (FULL) or
  for the frames up to `s1 + X + N` (FILTERED), so the ghost starts about 0.1 s (FULL) or 0.21–0.27 s (FILTERED) after
  the trigger (P1-A §5 measurement).
- `s0 < 0` (less than `L` of audio since the stream started) is rejected `BEFORE_STREAM`; the selection is never
  shortened.
- Source and band are read at the trigger: SOURCE, and for FILTERED `band_center` and `band_width`
  (`low = c / 2^(w/2)`, `high = min(c · 2^(w/2), Fs/2)`).
- Trigger sample per origin:

| Origin | Trigger sample |
|---|---|
| GUI button | first sample of the block in which the processor reads the command from its FIFO |
| MIDI (VST3) | block start + the event's sample offset (sample-accurate). Note On with velocity > 0 on any channel and any note, or CC 64 rising from < 64 to ≥ 64 |
| Automation (`imprint` parameter) | first sample of the first block whose value is ≥ 0.5 after a block whose value was < 0.5 (rising edge, block resolution) |

- **Automation edge rules:** the previous value is resynchronised, without triggering, after `prepareToPlay`, after
  `setStateInformation` and on the first block after a bypass. A pulse shorter than one processing block can be missed
  (hosts deliver the last automation value per block); a footswitch held for more than a block is always seen.
- **Busy:** a MANUAL request while a job is active is rejected `BUSY`, as in P1-A. Nothing is queued.

## 6. HOLD

A latched boolean parameter `hold`.

- When on, RANDOM and AUTO keep analysing and keep their timers and detector state, but every request they would issue
  is recorded `SUPPRESSED_HOLD` and dropped.
- An explicit IMPRINT (GUI, MIDI, automation) still replaces the ghost; HOLD stays on, so the new ghost is the held one.
- CLEAR still clears.
- HOLD does not sustain: the held ghost still decays with MEMORY and follows DISSOLVE. When it has decayed and retired,
  HOLD stays on and nothing automatic happens until it is released.
- HOLD before any ghost exists: automatic modes produce nothing; MANUAL works.
- Releasing HOLD: RANDOM's next attempt is scheduled one jittered interval after the release; AUTO re-arms. Nothing
  suppressed during HOLD is replayed.

## 7. RANDOM

- Ticks at a jittered interval: `next = now + I · (0.75 + 0.5 u)`, `I` = `random_interval` (1–16 s). The first tick is
  one interval after RANDOM is selected or after a reset. A tick that falls due during HOLD or while busy is dropped
  and the next one scheduled (no backlog).
- Randomised per capture: the **position** (selection end `s1` uniform in `[now − 4 s, now − D]`, `D = X + N + H`, so
  the post-roll is already in history and the build starts at once) and, for FILTERED only, the **band centre**
  (`band_center · 2^(2u − 1)`, ±1 octave). Not randomised: length (`capture_length`), width, SOURCE.
- Activity gate: the mean power of the hop levels covering `[s0, s1)` must reach `activity_gate` (dBFS). Up to 8
  candidates per tick; the first that passes is requested; if none pass the tick records `NO_CANDIDATE`.
- PRNG: SplitMix64 with its own seed (documented constant `0xAF7E2026B1110001`, reset at `prepare`), separate from the
  grain seeds, consumed only at ticks: identical input and parameters give identical captures for any block size.

## 8. AUTO (experimental)

A conservative energy-and-flux event detector, measured in P1-B-QUALIFICATION §1.5 and kept **experimental** unless it
meets those limits.

- **Onset:** at a hop with band flux ≥ θ(sensitivity), hop level ≥ `activity_gate`, detector armed, and the cooldown
  since the last AUTO capture elapsed. θ's scale is fixed in Stage D on synthetic fixtures and documented in the UX
  contract.
- **Event:** start `s0 = (first sample of the detecting hop) − 2H − 10 ms`, so an attack that the flux reports up to two
  hops late is still inside the capture. Clamped at stream sample 0 (audio before the stream start is silence, P1-A §4.3);
  this is the only place a capture may start later than its rule says, and it never removes audio. (Added in Stage D: onsets
  in the first 70 ms of a stream were otherwise rejected `BEFORE_STREAM`.) End `s1 = s0 + L` (L = `capture_length`), or earlier when the hop
  level stays below the gate for 2 hops after at least 0.25 s.
- **Issue:** at the first decision slot after `s1` (the build then waits for its post-roll), subject to HOLD and busy.
- **Hysteresis:** after an onset the detector disarms; it re-arms after 2 consecutive hops with flux < θ/2 *and* the
  event has ended. `auto_cooldown` (0.5–8 s) is the minimum time between AUTO captures.
- No machine learning, no pitch or phrase recognition, no extra FFT.

## 9. Bypass, transport, rate changes, state

| Situation | Behaviour |
|---|---|
| Host bypass | output = input; analysis continues; IMPRINT from any origin `IGNORED_BYPASS`; RANDOM/AUTO paused; on resume RANDOM reschedules one interval later, AUTO re-arms, the automation edge resyncs |
| Transport stop/start | not used: AFTERIMAGE never reads the playhead. It keeps working on whatever audio the host passes; silence keeps the activity gate shut |
| Sample-rate or buffer-size change | `prepareToPlay`: new epoch, history and voices reset (P1-A), scheduler reset, edge resync |
| State restore | restores parameters only; never triggers a capture (edge resync) |

## 10. MIDI and AU type

- The VST3 gains a MIDI input (`NEEDS_MIDI_INPUT TRUE`).
- The AU **stays `aufx`** (`AU_MAIN_TYPE kAudioUnitType_Effect`), so sessions saved with the P1-A preview reload.
  Logic does not send MIDI to `aufx` effects, so in Logic the footswitch path is a controller assignment to the
  automatable `imprint` (and `hold`) parameter. Switching to `aumf` (Logic's "MIDI-controlled effect") is possible
  later; it changes the AU identity.

## 11. Deferred: FREEZE VIEW

A cosmetic freeze of the scrolling display would let the selected audio expire from the 6 s history. A coherent freeze
needs a snapshot of the raw ring (up to 4.6 MB at 96 kHz stereo) copied in bounded units, plus FILTERED builds that
recompute the forward FFT from that snapshot (doubling build cost). That is feasible but not needed for hands-free
capture, so it is **deferred**. The P1-A drag-to-select (view held while dragging) remains.
