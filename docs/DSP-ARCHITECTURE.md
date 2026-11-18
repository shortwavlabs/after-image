# AFTERIMAGE — DSP System Architecture

**Document ID:** DSP-ARCH-001  
**Revision:** 0.1 (2026-11-18)  
**Status:** **PROPOSED — NOT IMPLEMENTED OR VALIDATED** (2026-11-18: partly superseded, see note below)  
**Scope:** P0 sonic experiments through realtime MVP and Jam qualification  
**Product:** Shortwav Labs AFTERIMAGE  
**Related:** [PRD](PRD.md) · [RFC-001](RFC-001-spectral-engine.md) · [UI concept](UI-CONCEPT.md) · [Roadmap](ROADMAP.md)

> **Status update (2026-11-18):** offline research P0-A, P0-B, P0-C and real-audio qualification is complete and consolidated in [RESEARCH-CONSOLIDATION.md](RESEARCH-CONSOLIDATION.md). The GHOST is now **granular** (CLOUD core engine, FOCUS later, GLITCH experimental) over a captured buffer, with a parallel TRACE → CLOUD DISSOLVE and FULL / FILTERED SOURCE. Sections 6–7 (spectral Loop / Sustain as the GHOST) and the engine rows of §0 and §2.1 are kept for history and is superseded by the consolidation record and `P1-A-REALTIME-ARCHITECTURE.md` (added with P1-A on `feature/p1a-realtime-core`). The BODY contract (§1), STFT indexing (§3.1), history and capture safety (§4), realtime rules (§10) and host contract (§11) remain normative.

> **Design invariant:** An undelayed BODY plus one independently synthesized GHOST. Users paint a time–frequency fragment in recent audio history; AFTERIMAGE captures it and makes it persist as a transformable, fading voice.

---

## 0. Executive engineering decisions

| Topic | Proposed P0/P1 choice | Why / caveat |
|---|---|---|
| Signal model | **Additive wet GHOST + zero-latency BODY** | Responsive live playing. *Not* destructive source separation or live complementary spectral masks. |
| Reported plugin latency | **0 samples for MVP** | Only BODY is through audio; spectral GHOST is a consciously delayed/generated effect. Verify actual passthrough sample 0. If architecture changes to a processed-through signal, re-evaluate host PDC. |
| Analysis | Complex stereo STFT; N=4096, H=1024 at 44.1/48 kHz; N=8192, H=2048 at 88.2/96 kHz | Comparable ~85–93 ms analysis windows across rates, 75% overlap. Provisional; P0 compares alternatives. |
| Rolling history | **~6 s internal**, **4 s displayed** | ~2 s safety margin for asynchronous-looking but audio-owned incremental copy. |
| Capturable region | **0.20–1.50 s**, adjustable frequency band, feathered edges | Bounded memory and response time; selectable position anywhere in visible four seconds. These are MVP caps, not hard product limits. |
| Imprint transfer | Audio thread copies at most **8 frames per STFT hop** into preallocated inactive voice | Avoids one multi-megabyte copy in a callback; copied oldest-first with frame-sequence checks. Profile and lower the budget if unsafe. |
| Ghost modes | Prototype A: crossfaded spectral-frame loop; B: phase-continuous spectral sustain | **No winner selected.** Same captured-frame representation for fair A/B. |
| Voices | One audible GHOST, two preallocated voice slots for click-free replacement | Old/new may overlap briefly during REPLACE; not a user-facing multivoice instrument. |
| Memory knob | Finite amplitude decay time **T60 = 0.25–30 s** | No infinite hold in baseline; honest finite tail reporting. |
| UI | Real log-frequency spectral history via decimated snapshots | JUCE renders actual source/ghost state; Blender assets are purely presentation. |
| Hard boundaries | No heap allocations, locks, blocking tasks, file IO, or UI calls in `processBlock` | Explicit bounded work per callback; all heavy data structures prepared beforehand. |
| Serialization | Save parameters/modes, **not** captured sound | Deterministic restoration semantics, manageable preset size. |

**Supersession:** Where [RFC-001](RFC-001-spectral-engine.md) says “delay-compensated BODY,” or that STFT delay must necessarily be reported as global plugin latency, **this document supersedes it** for the additive MVP. Spectral-processing latency exists inside the GHOST generator but is *not* imposed on the main through path. RFC-001 otherwise remains useful as an early design exploration.

**No assurance of “zero latency” for GHOST:** IMPRINT must copy/preprocess a capture and generate a phase-coherent onset. The user hears a deliberate memory effect after that work; the zero-latency claim applies **only** to BODY and the host through-path.

## 1. Non-negotiable audio contract

### 1.1 Output equation

For output channel `c` at sample `n`:

```text
y_c[n] = smooth(BODY)[n] * x_c[n]
       + smooth(GHOST)[n] * envelope[n] * ghost_c[n]
```

`x_c[n]` is the current direct input sample; `ghost_c[n]` is produced from **historical captured frames** and can continue during input silence. Limiting/saturation is **not** silently applied to BODY. Captured content is never mistaken for a live notch-filter subtraction.

- BODY=unity and GHOST=zero must be **sample-exact** pass-through (within float representation); no delay, STFT modification, or arbitrary reverb wet/dry gain rule.
- BODY=zero, GHOST>zero must output only the synthesized ghost.
- Both gains can sum above 0 dBFS: keep processing finite and document headroom. Do not claim guaranteed unclipped output without implementing an explicitly controlled safety stage.
- Bypass returns unmodified incoming audio with no ghost and no hidden latency. Fade transitions when host callbacks permit; do not promise a fade if a host stops invoking the effect outright.

### 1.2 Channel/rate contract

- First-class layouts: **mono→mono** and **stereo→stereo**. Reject unsupported bus configurations cleanly; mono→stereo is an optional later feature.
- Target sample rates: **44,100 / 48,000 / 88,200 / 96,000 Hz**. Rates outside qualified range must safely pass dry audio and signal that capture is unavailable, *not* crash or silently alias.
- Support blocks of `0, 1, 16, 64, 128, 256, 512, 1024,` and non-power-of-two sizes; some hosts vary sizes between calls.
- No assumption that transport is running or that audio always arrives while the plugin window is open.
- Stereo capture must preserve interchannel relationship; a mono recording should not unexpectedly move across the soundstage.

### 1.3 Latency and tail policy

- Global host latency compensation: **`setLatencySamples(0)`**, subject to the dry impulse/null gate. This is valid only while BODY is direct and the effect is additive.
- The spectral capture window can be long without delaying BODY. IMPRINT-to-first-GHOST delay must be **measured**, including up to one STFT hop of scheduling, copying time, preparation, and synthesis fill.
- `getTailLengthSeconds()` should reflect maximum finite tail behavior (MEMORY upper limit + fade/processing safety margin), not zero. Confirm how qualified hosts handle stopped transport and suspended processing.
- HOLD / infinite sustain are **not** baseline; enabling them later changes tail and host policy.

## 2. Processing graph and thread topology

```text
              AUDIO CALLBACK (sole DSP/buffer owner)
Input ────────┬───── Smoothed BODY gain ──────────────────────────────────┐
              │                                                          │
              └─ Input ring → stereo windowed FFT @ each hop              │
                                │                                         │
                                ├─ 6 s complex-history ring              │
                                │     [frame_id, end_sample, complex bins]│
                                │             │                           │
UI editor ─── Capture Command ───→ Validate ROI → bounded frame copy      │
                                │             │                           │
                                │        inactive GhostSlot              │
                                │             │                           │
                                │        spectral preparation            │
                                │             │                           │
                                │   synth engine A or B → IFFT → WOLA    │
                                │             │                           │
                                │       fade/envelope/MOTION/WIDTH        │
                                │             │                           │
                                │        smoothed GHOST gain ─────────────┤
                                │                                         ▼
                                └─ decimated state → snapshot queue     Mix → output
                                                      │
                                              UI message thread
                                                      │
                                         JUCE 2D spectrogram + Blender art
```

**Only the audio callback reads/writes complex history and mutable voice state.** The UI owns selections and renders snapshots; it must never read history memory directly. Controls with host automation use stable atomic parameter values sampled by the audio callback. An editor-originated capture/clear request is delivered through a bounded one-producer/one-consumer command queue; if multiple producers are added later (MIDI or automation), implement a defined serialization layer rather than silently treating it as SPSC.

### 2.1 Component and file boundaries (proposed)

```text
Source/
  PluginProcessor.{h,cpp}            // JUCE buses, lifecycle, params, state, sample scheduling
  PluginEditor.{h,cpp}               // UI; no direct raw DSP buffer access
  dsp/
    AudioEngine.{h,cpp}              // sample loop, routing, bounded work scheduler
    StftAnalyzer.{h,cpp}             // window/input ring/FFT, timestamps
    SpectralHistory.{h,cpp}          // fixed-size complex-frame ring, epoch checks
    SpectralSelection.{h,cpp}        // ROI mapping, feathered time-frequency mask
    ImprintController.{h,cpp}        // command validation, chunked snapshot, state machine
    GhostVoice.{h,cpp}               // interface and preallocated engine state
    LoopGhost.{h,cpp}                // candidate A
    SustainGhost.{h,cpp}             // candidate B
    GhostWola.{h,cpp}                // synthesis overlap/add/output FIFO
    StereoField.{h,cpp}              // wet-only stereo options
    ParameterSmoother.{h,cpp}        // sample smoothing and finite bounds
  ui/
    SpectralSnapshotBridge.{h,cpp}   // decimated audio→editor messages
    SpectrogramComponent.{h,cpp}     // log-frequency view and ROI interaction
    HardwareControls.{h,cpp}        // Blender sprites and JUCE handles
Tests/
  dsp/                               // deterministic engine and numerical tests
  host/                              // pluginval, AU validation, offline render scripts
experiments/
  p0-spectral-ghost/                 // offline reference algorithms and A/B exports
docs/
  DSP-ARCHITECTURE.md                // this document
```

These are **planned paths**, not existing implementation. Keep candidate engines independently testable from JUCE rendering or host state.

## 3. STFT analysis subsystem

### 3.1 Discrete indexing (one unambiguous contract)

Let `Fs` be sample rate, `N` FFT size, `H=N/4` hop, `K=N/2+1` positive-frequency bins. Maintain a monotonic 64-bit input sample counter and a monotonic 64-bit frame ID during the same prepared processing epoch.

When `H` new samples are collected, create frame `m` from input samples **`[end_sample - N, end_sample)`**, zero-padded before the first full window. `end_sample` is the exclusive right endpoint; keep it stored with each frame. Window center is roughly `end_sample - N/2`. The display should not label it as if the window were a zero-latency measurement.

```text
X[m,k,c] = FFT_N { w_a[n] * x_c[end_sample-N+n] }
for k ∈ [0, N/2], c ∈ [0, channel_count)
```

Frequency bin `k` has center frequency `f_k=k*Fs/N`. Preserve **complex** coefficients; a magnitude-only history cannot reproduce original phase or permit a fair A/B comparison.

- FFT choice: start with JUCE `dsp::FFT`; construct/configure FFT objects and scratch **outside** `processBlock`. Check real-FFT packed layout and inverse scale of the actual JUCE version under test.
- Use a **periodic** sqrt-Hann analysis/synthesis window candidate, with overlap sum normalization. For `H=N/4`, theoretical steady-state sum of window products is approximately 2; measure exact sample-domain reconstruction with chosen implementation and startup handling.
- Avoid assuming different `dsp::FFT` backends have identical numerical scaling. Calibrate the inverse FFT gain once per plan/configuration.
- DC (`k=0`) and Nyquist (`k=N/2`) must maintain real-only constraints in a real IFFT; enforce conjugate symmetry as required by chosen FFT API.
- No fftsize/hop changes inside a single `processBlock`; reconfigure when the host changes rate/layout.

### 3.2 Rate-dependent proposal

| Host Fs | FFT N | Hop H | FFT window | Hop duration | Frequency bin width |
|---:|---:|---:|---:|---:|---:|
| 44.1 kHz | 4096 | 1024 | 92.9 ms | 23.2 ms | 10.77 Hz |
| 48 kHz | 4096 | 1024 | 85.3 ms | 21.3 ms | 11.72 Hz |
| 88.2 kHz | 8192 | 2048 | 92.9 ms | 23.2 ms | 10.77 Hz |
| 96 kHz | 8192 | 2048 | 85.3 ms | 21.3 ms | 11.72 Hz |

**P0 must also compare `N=2048` and `N=8192` at 48 kHz.** The chosen N/H is contingent on pitch stability, transient smear, capture responsiveness, and measured worst-case cost.

### 3.3 Live display products

Build a compact view from analysis magnitudes: stereo reduction policy (e.g. max or mean power, explicitly chosen), floor clamp in dB, log-frequency interpolation, and time binning. Do **not** pass full FFT frames to the UI. A possible fixed-size snapshot is ~256 frequency rows × 192 time columns, 8-bit intensity; the renderer may render its own colors. Send only changed columns and compact status where practical. UI frame rate can be 20–30 Hz independently of STFT hop cadence.

## 4. Ring history, memory, and capture consistency

### 4.1 History layout

Use a **preallocated ring of frame records**, indexed by `frame_id % capacity`, with immutable contents between audio-thread writes and the next overwrite. Each record includes:

```cpp
struct FrameHeader {
    uint64_t id;
    uint64_t endSample;
    uint32_t processingEpoch;
    // fixed-size or indexed complex-bin payload (stereo/mono as prepared)
};
```

`processingEpoch` changes on preparation/reset/sample-rate changes. UI selection and snapshot commands carry frame IDs and epoch; a frame is valid only if header matches **both**. No UI pointer into the ring.

**Display 4.0 seconds; allocate ~6.0 seconds plus guard frames.** The extra 2 s is explicitly reserved for capture copy and UI/command scheduling. This avoids a frequent race: a user clicks the oldest visible frame exactly as it is overwritten. A late command still fails cleanly rather than reading a different sound.

### 4.2 Memory sizing (float32 complex)

Per stored frame: `K * channels * sizeof(complex<float>)`. Budgets assume stereo, `K=N/2+1`, history capacity `ceil(6*Fs/H)+2`, each voice slot `ceil(1.5*Fs/H)+2` frames.

| Sample rate | History frames | History | One voice slot | History + two voice slots |
|---:|---:|---:|---:|---:|
| 44.1 kHz | 261 | 8.16 MiB | 2.09 MiB | 12.35 MiB |
| 48 kHz | 284 | 8.88 MiB | 2.28 MiB | 13.44 MiB |
| 88.2 kHz | 261 | 16.32 MiB | 4.19 MiB | 24.69 MiB |
| 96 kHz | 284 | 17.75 MiB | 4.56 MiB | 26.88 MiB |

**Not total per-instance memory.** Add input/output rings, FFT scratch, phase/state arrays, UI snapshots, temporary masks, allocator overhead, and any extra loop-crossfade renderer. Profile total RSS; prefer ~20–40 MiB working target for this configuration, not a guaranteed limit. Mono has roughly half the complex frame payload.

### 4.3 Two-stage capture without unbounded callback work

The live ring and both slots are **audio-thread owned and allocated before processing**. On IMPRINT:

1. The UI sends a small value-only `CaptureRequest {epoch, firstFrame, lastFrame, lowHz, highHz, requestId}`. It freezes the ROI at the moment of clicking; subsequent drawing must not mutate that request.
2. Audio callback validates epoch, frame ID range, sample rate, min/max selection duration, and finite frequency bounds. Derive sample/bin bounds from *current* prepared configuration; reject stale/invalid ranges explicitly.
3. Reserve the inactive `GhostSlot` and set `CAPTURING`. Current GHOST continues playing if present.
4. At each following analysis hop, copy **at most eight** historical frames, **oldest first**, into the slot. Recheck each header immediately before copy. Optionally multiply a precomputed feathered frequency/time mask while copying, but keep work bounded and measured.
5. Once all frames are copied, prepare the selected synthesis engine **incrementally with a bounded per-hop budget** (not a large one-shot modal analysis). Transition to `READY` only when complete.
6. At the next safe synthesis boundary, fade in the new ghost and (for replace) fade out the previous one. Advance to `ACTIVE` only after successful handoff. Publish an acknowledgement with request ID; do **not** flash “CAPTURED” at enqueue time.

If the source range expires or the queue/slot is unavailable, reject the request and leave the previous ghost intact. Copy completion must occur well within the ~2 s history reserve, even under worst-case valid ROI; latency is measured, not assumed. A 1.5 s selection represents roughly 67–73 frames under the table above: at 8 frames per hop, **~0.19–0.21 s just for copy scheduling**, before preparation and WOLA fill. Benchmark responsiveness; an optimized safe copy limit may be higher or lower.

**Do not do:** `memcpy` of a whole multi-MiB capture in a single callback; UI read locks around complex history; send raw ring pointers via a queue; background thread reads data that audio thread can overwrite; call expensive spectral feature extraction on all frames in one callback.

### 4.4 Event queue and back-pressure

Editor→audio: single producer/single consumer fixed-capacity command queue, each command a trivially copyable struct. On full queue, *reject and show a clear busy/error state*; never spin/block and never silently claim a capture. CLEAR may be prioritized through a dedicated atomic command flag if justified by tests, but avoid undefined interaction between clearing and queued capture commands.

Audio→editor: bounded/status snapshot queue or safely published triple-buffered **copy**; never heap-allocate per frame or hand out writable DSP pointers. UI may drop intermediate visualization frames; audio must not stall if the editor is not consuming. Include `requestId`, `epoch`, current voice state, and real output energy for accurate status.

## 5. ROI semantics and spectral masking

A user draws a rectangle in a **time × log-frequency** display. Convert into absolute stored frame IDs and Hz, not arbitrary viewport pixel coordinates.

- **Time:** choose frames with timestamps intersecting the selection; preserve fractional/feathered boundaries. Clamp minimum duration (~200 ms) and maximum duration (1.5 s) visibly in the UI.
- **Frequency:** `f_low` to `f_high`, with a sensible floor above DC, and bounded at `Fs/2`. Require at least a few supported bins; selected narrow low-frequency bands may be rejected or widened explicitly rather than creating an empty “ghost.”
- **Feather:** `M[m,k]=T[m]*F[k]` using e.g. raised-cosine transitions in time and log frequency. Prevent hard vertical/horizontal spectral cuts with audible ringing.
- Preserve DC/Nyquist/real-FFT symmetry constraints; mask magnitude and corresponding complex coefficient together rather than making unrelated random phase modifications.

The ROI chooses **what the ghost remembers**. It does **not** subtract that material from BODY in the MVP. The UI should avoid implying that the BODY path has a corresponding frequency hole.

## 6. Ghost resynthesis A — phase-aware loop + crossfade

**Intent:** retain recognizable captured texture, including modest movement, while sustaining beyond original duration.

**Input:** fixed ordered sequence of complex STFT frames, masked at copy/preparation time. **Output:** a ghost-only stream of synthesis frames to inverse FFT/WOLA.

Conceptual method:

1. Resynthesize selected complex frames with WOLA in their original temporal order, using preserved analysis phase.
2. Loop this reconstructed material as a voice; a naive hard wrap creates a phase/sample discontinuity.
3. Use a **time-domain, equal-power crossfade between overlapping loop voices** near the seam. The crossfade requires two read heads or a precomputed overlap region; it must be sample-continuous and avoid doubling peaks unexpectedly.
4. Choose seam/crossfade placement from usable middle frames, not a zero-energy masked edge. Include a safe fallback if ROI duration is too short for the required overlap.
5. Apply independent per-voice gain envelope and optional controlled long-period motion.

**Technical warning:** FFT-frame overlap/add alone does *not* guarantee a loop seam is phase continuous. Each loop pass can be locally reconstructable and still click when wrapped. Test sample discontinuity, short loops, loop period audibility, and stereo image. Preserve captured stereo phase; verify that independent L/R crossfades do not create an unstable wandering center.

**Likely result:** better source identity and transient texture than a pure freeze, but may sound like an obvious repeating grain. That is acceptable for P0 evaluation, **not a promise of final product quality**.

## 7. Ghost resynthesis B — phase-continuous harmonic sustain

**Intent:** a stable, evolving *afterimage*, potentially more “vocal pad” than loop.

### 7.1 Per-bin frequency estimation

For adjacent non-silent analysis frames with phases `phi[m,k]` and `phi[m-1,k]`, subtract the expected bin rotation:

```text
expected[k] = 2π * k * H / N
delta[k] = wrapToPi(phi[m,k] - phi[m-1,k] - expected[k])
omega_est[m,k] = 2π*k/N + delta[k]/H     // radians per input sample
```

At successive **output** synthesis hops `H_s`, phase can be advanced as:

```text
theta_out[q,k] = wrapToPi(theta_out[q-1,k] + omega_est[k]*H_s)
Y[q,k] = amplitude[q,k] * exp(j * theta_out[q,k])
```

For a sustained ghost with unchanged rate, propose `H_s=H`. Interpolate/smooth magnitudes and frequency estimates over a selected patch; avoid taking unstable phases from near-zero bins. Initialize phases from a selected stable frame (or a robust peak-centered state), not zeroing all bins arbitrarily.

These equations define **candidate behavior**, not a validated phase-vocoder implementation. Wrap conventions and gain normalization must be proven in tests.

### 7.2 Coherence and quality safeguards

- Detect dominant spectral peaks and consider **identity phase locking** in neighborhoods to reduce smearing. Keep a basic per-bin phase accumulator as the first reference.
- Detect unstable low-energy bins and gate/smooth their frequency estimates; never divide by tiny amplitudes or emit NaN.
- Preserve relative stereo phase as much as feasible. Experiment with shared peak phase increments and per-channel offsets; compare against independent L/R synthesis to detect stereo wandering and cancellation.
- Modulate spectral envelopes slowly and **coherently across groups of bins**, not independent random phase jitter per bin per hop.
- For noise/transients, harmonic sustains may become metallic or tonal. Measure whether a separate residual/noise renderer is justified; it is **stretch**, not part of baseline.
- Short capture durations may not provide stable phase/frequency estimates. Fail gently, use a fallback, or automatically blend toward Loop mode only after controlled evaluation.

**Likely result:** smoother shimmering harmonic tails, but greater risk of synthetic/metallic timbre and washed-out percussion.

### 7.3 Decision criteria A vs B

Same input stems, identical selected `firstFrame/lastFrame/fLow/fHigh`, matched loudness, identical MEMORY time, identical fades, identical dry/wet output level. Score: source recognizability, musical sustained quality, seam clicks, transient smear, stereo stability, CPU, worst-case peak, and ease of immediate use.

Do not prematurely add a combined mode: it costs more engineering and creates new phase/transition cases. Pick a winner after the P0 listening gate.

## 8. Common ghost synthesis and modulation

### 8.1 IFFT and weighted overlap/add

IFFT the selected/synthesized spectral frame, multiply by synthesis window, then write into a **fixed-size overlap/add ring**. Maintain a sample counter and per-voice read/write pointers. Sum window products and normalize the startup/tail as needed; no division by zero.

For unmodified test frames, periodic sqrt-Hann windowing with `H=N/4` should reconstruct with calibrated normalization in steady state. For *altered* phase/magnitude, WOLA is just synthesis—not a perfect-reconstruction guarantee.

Use deterministic timing for new voice start: wait for frame-ready and buffer-fill, then fade up. Do not emit unwritten or stale overlap-buffer samples; zero consumed samples.

### 8.2 Envelope / MEMORY

Define MEMORY by `T60`: duration until amplitude has dropped by 60 dB from the onset of the ghost's decay.

```text
a = exp(-ln(1000) / (T60 * Fs))
g[n+1] = a * g[n]
```

Map knob perceptually/logarithmically over proposed `T60=0.25..30 s`. Smooth retargeting of T60 and/or envelope gain so automation never jumps. Below a measured -80 to -100 dBFS floor, retire voice state deterministically; retain option to fade at retirement.

Distinct from the 4 s capture window: **history duration** limits what can be selected; **MEMORY** sets how long the resulting voice fades.

### 8.3 MOTION

Start with one conservative, deterministic evolving dimension: e.g. slowly moving, band-correlated amplitude/diffusion modulation. Keep maximum depth bounded and preserve perceived pitch. No uncorrelated random per-bin phase changes at audio rate. Generate deterministic modulation state for repeatable offline renders and tests.

A more ambitious spectral-frequency drift or “dissolution” model becomes P2 only if measured artifacts and CPU are acceptable.

### 8.4 WIDTH

Apply after ghost reconstruction, never on BODY. Basic stereo mid/side control:

```text
M = 0.5*(L+R); S = 0.5*(L-R)
L' = M + width*S; R' = M - width*S
```

Propose `width ∈ [0,1.5]`, with `1.0` unchanged stereo, `0` mono. A centered mono source has `S=0`; this formula **cannot create stereo width** from identical L/R. An optional gentle, tested wet-only decorrelator is necessary if the product promises widening mono material; otherwise document/indicate its limited action. Verify mono sum, peak levels, and channel energy; do not invent a widening effect merely in the UI.

### 8.5 Fades and hard control cases

- IMPRINT new ghost onset: proposed 20–50 ms fade, tuned in P0.
- CLEAR: bounded 20–50 ms fade; release voice after fade.
- REPLACE: old + new play concurrently only within bounded crossfade, then retire old. Schedule at a hop or sample boundary so envelopes are continuous.
- Rapid double IMPRINT: reject or coalesce deterministically if inactive slot is busy; never overwrite currently read voice memory.
- Parameter changes during capture: snapshot only selection; live parameter smoothing applies to resulting voice unless explicitly defined otherwise.
- Safety: finite-float checks, denormal guards, amplitude bounds within the wet algorithm, no uncontrolled feedback.

## 9. Detailed voice/capture state machines

### 9.1 Capture controller

```text
IDLE ──IMPRINT(valid)──→ COPYING ──complete──→ PREPARING ──ready──→ SWAP_PENDING
  ↑                         │                  │                      │
  │                         └─invalid/expired──┴─failure──────────────┘
  └────────── acknowledgement / cleanup ←────────────────────────────────
```

A new IMPRINT is rejected with `BUSY` if a capture is already copying or preparing. A CLEAR during COPY cancels pending work and fades the active ghost; do not accidentally activate the abandoned capture later. Each request gets a monotonic ID; stale UI responses ignored by matching ID/epoch.

### 9.2 Voice lifecycle

```text
EMPTY → READY → ATTACK → DECAYING → RELEASE / CLEAR → EMPTY
                  ↑                     │
                  └──── REPLACE ────────┘  (old/new slots overlap briefly)
```

Do not expose `HOLD` state until there is a finite and tested sustain/hold contract. When last input goes silent, the current ghost continues under its own envelope (subject to host continuing to call the plugin).

### 9.3 Public UI-state snapshot

```cpp
struct UiAudioState {
    uint32_t epoch;
    uint64_t latestFrameId;
    uint64_t acknowledgedRequestId;
    uint8_t captureState;   // idle, copying, preparing, ready, rejected
    uint8_t voiceState;     // empty, attack, decay, release
    uint8_t rejectionCode;  // stale, busy, out-of-range, unsupported
    float ghostRms;         // measured, smoothed, finite
    float captureProgress;  // [0,1], copied/prepared work
};
```

The exact ABI is not final; prefer value messages with no pointers. UI may embellish highlights but must distinguish animation from measured energy.

## 10. Scheduling, bounded cost, and real-time implementation rules

### 10.1 Streaming scheduler

```cpp
void AudioEngine::process(float** inputs, float** outputs, int count) noexcept {
    // Pseudocode: do not copy into shipping DSP without tests.
    for (int i = 0; i < count; ++i) {
        readAndSmoothParameters();
        const auto dry = readInputSampleAndPushToRing(inputs, i);
        const auto wet = consumePreparedGhostSample();

        writeOutput(outputs, i, bodyGain * dry + ghostGain * wet);

        if (hopBoundaryReached()) {
            analyzeOneStereoFrame();         // bounded, allocated scratch
            serviceCaptureCommands();        // bounded queue consumption
            copyAtMostEightHistoryFrames();  // bounded memory transfer
            prepareGhostWithinBudget();      // bounded state preparation
            synthesizeNeededGhostFrames();   // fixed worst-case voice count
            publishCompactUiDataIfDue();     // bounded, drop when full
        }
    }
}
```

**The pseudocode demonstrates ordering, not an API or proven zero-allocation loop.** For efficiency, load control targets once per block and smooth per sample rather than performing atomic loads per sample. The order of hop work vs sample consumption must be finalized and impulse-tested to avoid stale output or frame off-by-one errors.

### 10.2 Explicit cost ceilings

At nominal 48 kHz with 1024-sample hops, a hop occurs every ~21.33 ms. Typical stereo STFT work: 2 forward transforms per hop; normally 2 inverse transforms for one GHOST. During REPLACE or loop seam rendering there may be **additional simultaneous inverse transforms**. Write down and test the actual maximum (including old/new ghost + seam crossfade), not the average.

Suggested early measurement goals (engineering gates, not claims about achieved performance):

- Peak `processBlock` execution **<25% of the per-block audio deadline** on the slowest agreed target machine during worst-case capture/replace and active UI. Aim much lower in normal play.
- No callback deadline misses over long randomized stress runs and stress-tested host buffer sizes.
- Measure P50, P95, P99, **max**, per-hop transform times, memory copy burst time, UI frame times, and total per-instance RSS.
- If one hop occasionally exceeds a small host block deadline, move bounded work to a finer-grained amortized schedule or revise N/H/capture budget; a 21 ms average is not enough to guarantee a 64-sample callback at 48 kHz (~1.33 ms).
- Record actual CPU and allocation evidence per platform; do not interpret sanitizer-only performance as release performance.

**Important scheduler refinement:** performing the entire hop's FFT+capture+resynthesis at the end of one 64-sample block can cause a CPU spike; benchmark and consider splitting preparation/extra synthesis work into fixed work units while keeping STFT frame timing deterministic. If a worst-case frame transform itself violates the deadline, the selected FFT backend/size or architecture is unsuitable without further work.

### 10.3 Allocation and concurrency

- Allocate rings, workspaces, temporary FFT arrays, crossfade slots, and visualization snapshots in `prepareToPlay` (and destruct only outside `processBlock`). Account for reinitialization and transport resets.
- No `new`, `malloc`, resize, `std::vector::push_back`, mutex, blocking queue, filesystem, logging strings, or UI calls on the audio thread.
- No GUI→DSP pointer passing; no GUI access to non-atomic voice state.
- Avoid expensive `APVTS::copyState` in the audio callback; state serialization belongs in host-state handling with defined thread constraints.
- Use atomics for parameter targets; implement a **correct** lock-free handoff for multi-field state (never assume several independent atomics produce one coherent snapshot).
- If capture becomes worker-thread based later, do not let a worker read a changing ring. It needs its own immutable copied snapshot or a verified lifetime/pinning scheme.

## 11. Host parameter and persistence contract

Proposed stable IDs (choose final names before writing presets; no renaming lightly):

| ID | Units / range | Parameter type | Automatable? | Stored? |
|---|---|---|---|---|
| `body` | normalized gain 0..1 | continuous | Yes | Yes |
| `ghost` | normalized gain 0..1 | continuous | Yes | Yes |
| `memory_t60` | seconds, log mapping 0.25..30 | continuous | Yes | Yes |
| `motion` | 0..1 | continuous | Yes | Yes |
| `width` | 0..1.5 | continuous | Yes | Yes |
| `engine_mode` | A/B | **development only** | No public param yet | N/A |
| `imprint` | value command | UI event | **Not in MVP** | No |
| `clear` | value command | UI event | **Not in MVP** | No |
| `roi` | recent frame interval + Hz band | UI ephemeral | No | No |

- **Why IMPRINT is not automatable in MVP:** a latched/serialized momentary boolean can retrigger unexpectedly on host state restore. Proper host/MIDI triggering needs a distinct edge/event contract and tests; keep the P0/P1 capture UI command deterministic. PRD originally floated MIDI/automation as an option; treat it as deferred.
- `getStateInformation` persists continuous parameter targets and schema version; no raw FFT frames or history.
- `setStateInformation` restores parameters and resets ephemeral captured material on reload/creation. Preset browsing should not unexpectedly retrigger capture.
- Host bypass: output unprocessed input; ensure both default bypass callbacks and normal bypass path agree.
- Sample-rate/layout change: invalidate history/ROI with a new epoch; release old voice without use-after-free. A ghost can be cleared rather than resampled until that feature is qualified.

## 12. P0 research plan: prove the sound first

**Deliverable:** deterministic offline test harness, not a JUCE plugin or Blender GUI.

**Input stems:** a recorded distorted guitar chord (strummed and palm-muted), spoken/sung voice, acoustic drums, synth chord. Use owned or clearly licensed recordings. Keep dry stems and input gain documented.

**Factorial sweep:**
- FFT: 2048/4096/8192 at 48 kHz; H=N/4.
- ROI: full-band vs 350 Hz–5 kHz vs one narrow harmonic band; 0.25/0.75/1.5 s durations.
- Engine A: two seam strategies/crossfade lengths (e.g. 30 and 80 ms), with phase-coherent source frames.
- Engine B: plain per-bin phase accumulation vs a peak/identity-phase-locked variant where feasible.
- T60: 1/5/15 s, matched wet levels; no MOTION first, then restrained MOTION on winner.

**Artifacts (naming proposal):**

```text
experiments/p0-spectral-ghost/
  README.md                 // commands, fixed seeds, input rights, expected outputs
  manifest.json             // fs, FFT, hop, ROI, engine params, revision/commit
  renders/                  // ignored generated WAVs; share separately if licence requires
  metrics.json              // peaks, rms, clicks, CPU, reconstruction error
  listening-notes.md        // blind preference and perceived failure modes
```

**A/B conditions:** identical input, ROI, window, timing, T60, fades, output loudness. Compare with a simple ordinary spectral freeze reference implemented in the harness so that the novelty claim is testable.

**Stop/choose:** select whichever engine yields an unmistakably useful ghost on at least guitar + one non-guitar source **and** passes stability/cost gates. If both are metallic or generic, adjust the sound design/engine before any major UI asset build.

## 13. Qualification matrix and quantitative gates

| Gate | Test | Proposed acceptance |
|---|---|---|
| Dry transparency | BODY=1, GHOST=0, bypass and normal | sample-aligned to input, no added latency, float-accurate null; test impulse at **sample 0** |
| STFT sanity | fixed tones, DC, silence, impulse, chirp, random noise | finite output; exact/expected bins within tolerance; no invalid DC/Nyquist |
| WOLA reconstruction | unmodified frames through separate offline STFT/ISTFT reference | account for known STFT delay and boundaries; RMS error target < −90 dBFS normalized to reference; adjust to observed float/backend precision |
| Capture identity | ROI at oldest visible frame, ring wrap, rate changes | stale data never captured; epoch+frame IDs exact |
| RT work | random block sizes, fast controls, stress captures/replace | zero RT allocations/locks, bounded callback, no missed deadlines on agreed target |
| Onsets/seams | repeated loop seam + rapid clear/replace | no unintended clicks; discontinuity test plus listening |
| Stereo | center mono, anti-phase, panned material | bounded level; stable center and mono sum; no undefined width behavior |
| Silence / numerical safety | extended silence, denormal-heavy decay, invalid host input | no NaN/Inf runaway, no stuck voice, silence floor |
| Gesture/UI | editor open/closed/resize while DSP active | identical audio output and stable CPU budget |
| State/host | Logic AU, Reaper VST3, Windows VST3 host, pluginval/auval | no crash, restore continuous params, no accidental IMPRINT on reload |
| Musical test | guitar, voice, drums, synth, blind A/B against freeze | at least two useful cases with distinguishable, repeatable ghost character |

All numbers above are **proposed engineering targets**, not measured outcomes. Record host, OS, CPU, interface, session size, sample rate, plugin format, build SHA, test duration, and metrics in final reports. Do not label a gate PASS without an artifact and reproduction instructions.

## 14. Known risks and escape hatches

| Risk | Why it matters | Mitigation / fallback |
|---|---|---|
| Capture feels sluggish | Incremental copy + preparation + spectral output fill | Reduce max ROI, increase **measured safe** per-hop copy budget, optimize prep |
| Metallic sustain | Independent bin-phase smearing | Phase locking, shorter/longer N comparison; choose loop mode if clearly superior |
| Obviously repeated loop | Captured texture periodicity | Longer ROI, better seam placement and crossfade; choose sustain if superior |
| Drum transient wash | Long STFT window | Transient-sensitive WOLA strategy or explicitly target more sustained sources |
| Clicks or pops | Loop wrap / active-slot replacement | Dual-renderer seam, fades, deterministic buffer initialization |
| CPU spikes at tiny host buffers | FFT/snapshot job lands in one short callback | Profile, amortize work, lower N/voices, use efficient FFT implementation |
| Memory pressure at 96 kHz | 8k FFT and stereo complex ring | Lower window/history cap or compress **only after** fidelity tests |
| ROI silently expires | UI selected IDs wrap in audio ring | Epoch+ID checking, visible expiry and explicit rejection |
| Host surprises | Tail and bypass/restore variability | Conservative host contract; host-qualification matrix |
| JUCE licence uncertainty | Public Jam requires compatible source/reuse rights | Resolve repository/framework licence before importing JUCE code |

## 15. Ordered implementation tickets

**P0 — Offline reference (no JUCE required)**
1. Create immutable input fixture metadata and deterministic render harness.
2. Implement STFT/ISTFT reconstruction proof, window/FFT scaling tests.
3. Implement rectangular ROI + time/frequency feathering with complex history.
4. Implement LoopGhost + seam tests and SustainGhost + phase/coherence tests.
5. Export blinded matched-level A/B and metrics; publish evidence; record selected or rejected approach.

**P1-A — Realtime core**
6. JUCE 9/CMake shell after licence approval; basic mono/stereo/BODY-only zero-latency gate.
7. History ring, per-hop analysis, sample/frame timestamp/epoch contract.
8. UI-free command simulator and bounded staged capture with failure semantics.
9. Selected voice and fixed WOLA FIFO; fades and replacement; bounded cost proof.
10. Parameter IDs, finite tail, state serialization, host bypass.

**P1-B — UI integration**
11. Audio→UI decimated snapshot bridge with missed-frame policy.
12. Spectrogram ROI mapping, expiration validation, capture acknowledgements.
13. Blender asset compositing, control registration, HiDPI tests.

**P2 — Polishing/qualification**
14. Scoped MOTION/WIDTH tuning with controlled A/B.
15. Test matrix, performance harness, pluginval/auval, Logic/Reaper/Windows qualification.
16. Presets, demo stems, open-source release/notices, signed/notarized builds, submission.

## 16. Reference reading and provenance

These are references for **engineering validation**, not copied code or proof that our engine passes.

- [JUCE `dsp::FFT` reference](https://docs.juce.com/master/classjuce_1_1dsp_1_1FFT.html): real-only forward/inverse transforms, FFT API and implementation-specific layout checks.
- [JUCE `AudioProcessor` reference](https://docs.juce.com/master/classjuce_1_1AudioProcessor.html): process lifecycle, latency reporting, tail handling, bypass/state responsibilities.
- [Julius O. Smith, *Spectral Audio Signal Processing*: WOLA](https://www.dsprelated.com/freebooks/sasp/Weighted_Overlap_Add.html): COLA, WOLA and root-window reconstruction.
- [Julius O. Smith, *Spectral Audio Signal Processing*: COLA examples](https://www.dsprelated.com/freebooks/SASP/COLA_Examples.html): verify exact window/hop overlap before claiming reconstruction.
- Laroche & Dolson, “Improved Phase Vocoder Time-Scale Modification of Audio,” IEEE Transactions on Speech and Audio Processing (1999): identity phase locking and phase-coherence techniques. Consult an authorized copy; do not import third-party code by implication.

---

### Decision register (open until P0 evidence)

- **D-01:** A (spectral loop) vs B (phase-continuous sustain). **OPEN**.
- **D-02:** N/H per sample rate and root-Hann normalization. **PROPOSED**; measurements needed.
- **D-03:** 1.5 s max ROI, 6 s history, 8 frames/hop capture budget. **PROPOSED**; responsiveness and deadline proof needed.
- **D-04:** WIDTH from mono source: truthful limited action vs DSP decorrelator. **OPEN**.
- **D-05:** Snapshot bridge implementation details (SPSC vs triple buffer). **OPEN**; concurrency tests required.
- **D-06:** Open-source licence compatible with JUCE and Jam terms. **OPEN**, owner decision required.
- **D-07:** IMPRINT/MIDI/host automation beyond GUI action. **DEFERRED** until event/restore contract is designed.
- **D-08:** Global host latency 0 for additive BODY/GHOST topology. **PROPOSED**; dry impulse/null tests required.

**Shipping gate:** No claim that an audio algorithm, UI, host, or platform is functional based on this architecture document alone.
