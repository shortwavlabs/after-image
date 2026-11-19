// SPDX-License-Identifier: AGPL-3.0-only
// AFTERIMAGE realtime engine. Owned and driven by the audio callback only; the UI talks to it through the
// command queue (Engine::submit, called on the audio thread after the processor's FIFO), the status atomics
// and the display FIFO. Design: docs/P1-A-REALTIME-ARCHITECTURE.md
#pragma once

#include <array>
#include <atomic>
#include <complex>
#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

#include <juce_core/juce_core.h>

namespace juce::dsp { class FFT; }

namespace afterimage
{

inline bool exactly (double a, double b) noexcept { return std::equal_to<double>() (a, b); }

enum class Source : int { Full = 0, Filtered = 1 };
enum class Mode : int { Manual = 0, Random = 1, Auto = 2 };

struct Params
{
    float body = 1.0f;      // linear BODY gain
    float ghost = 0.5f;     // linear GHOST gain
    float t60 = 5.0f;       // MEMORY, seconds
    float dissolve = 1.0f;  // 0 = TRACE, 1 = CLOUD
    // P1-B capture scheduler (docs/P1-B-CAPTURE-ARCHITECTURE.md)
    Mode mode = Mode::Manual;
    float lengthSeconds = 0.75f;   // MANUAL/RANDOM/AUTO capture length
    Source source = Source::Full;  // for triggered and automatic captures
    float bandCenterHz = 1000.0f, bandWidthOct = 3.0f;
    bool hold = false;
    float randomIntervalSeconds = 4.0f;
    float gateDb = -48.0f;         // activity gate, dBFS
    float sensitivity = 0.5f;      // AUTO
    float cooldownSeconds = 2.0f;  // AUTO
};

/** Linear ramp to a target over a fixed time; at rest it returns the target exactly. */
struct Ramp
{
    double value = 0.0, target = 0.0, step = 0.0;
    int remaining = 0, length = 1;

    void setLength (int samples) noexcept { length = samples > 0 ? samples : 1; }
    void reset (double v) noexcept { value = target = v; remaining = 0; }
    void setTarget (double t) noexcept
    {
        if (exactly (t, target)) return;
        target = t;
        remaining = length;
        step = (target - value) / length;
    }
    double next() noexcept
    {
        if (remaining > 0 && --remaining > 0) value += step;
        else value = target;
        return value;
    }
    bool atRest() const noexcept { return remaining == 0; }
};

/** SplitMix64; uniform() = (z >> 11) * 2^-53, as p1a_reference.SplitMix64. */
struct SplitMix64
{
    uint64_t s = 0;
    double uniform() noexcept
    {
        s += 0x9E3779B97F4A7C15ull;
        uint64_t z = s;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
        return (double) ((z ^ (z >> 31)) >> 11) * 0x1.0p-53;
    }
};

enum class Reject : int { None = 0, StaleEpoch, BeforeStream, TooShort, TooLong, Future, InvalidBand, TooFewBins, Expired, Busy, QueueFull };
const char* rejectName (Reject) noexcept;

enum class CaptureState : int { Idle = 0, Waiting, Building };

/** Who asked for a capture. */
enum class Origin : int { None = 0, Selection, Button, Midi, Automation, Random, Auto, Count };
/** What happened to a request (P1-B architecture 4.2). */
enum class Outcome : int { None = 0, Accepted, Completed, Rejected, SuppressedHold, SkippedBusy, NoCandidate, IgnoredBypass, DroppedRate, Count };
const char* originName (Origin) noexcept;
const char* outcomeName (Outcome) noexcept;

struct RequestRecord
{
    int64_t at = 0, s0 = 0, s1 = 0;
    double lowHz = 0, highHz = 0;
    Origin origin = Origin::None;
    Outcome outcome = Outcome::None;
    Reject reject = Reject::None;
    Source source = Source::Full;
    int attempts = 0; // RANDOM candidates examined
    int64_t startedAt = -1; // stream sample where the resulting voice started (COMPLETED only)
};

struct Command
{
    /** Imprint: the explicit selection [s0, s1). Trigger: MANUAL capture of the last capture-length of audio, ending at
        the sample where the command is applied (P1-B). Clear: fade the ghost out. */
    enum class Type : int { Imprint, Clear, Trigger };
    Type type = Type::Imprint;
    Origin origin = Origin::Selection;
    uint32_t epoch = 0;
    int64_t s0 = 0, s1 = 0;          // selection [s0, s1) in stream samples
    double lowHz = 0.0, highHz = 0.0; // FILTERED band; ignored for FULL
    Source source = Source::Full;
    int64_t at = 0;                   // apply when this stream sample is reached (0 = at once)
};

struct GrainRecord
{
    int64_t onset = 0;
    int length = 0;
    double pos = 0.0, amp = 1.0, gain = 1.0, gl = 1.0, gr = 1.0;
    bool reverse = false, dropped = false;
};

struct CaptureInfo
{
    int64_t s0 = 0, s1 = 0, period = 0, seam = 0, acceptedAt = 0, startedAt = 0;
    double rho = 0.0;
    Source source = Source::Full;
    int slot = -1;
    uint64_t seed = 0;
};

struct DisplayColumn
{
    static constexpr int bands = 160;
    int64_t endSample = 0;
    uint32_t epoch = 0;
    std::array<float, bands> db {};
};

class Engine
{
public:
    static constexpr int maxChannels = 2, maxGrainsPerVoice = 32, numVoices = 2, unitStride = 64, maxPendingCommands = 16;
    static constexpr double seamSeconds = 0.08, onsetFadeSeconds = 0.03, releaseSeconds = 0.05,
                            minSelectionSeconds = 0.20, maxSelectionSeconds = 1.50, historySeconds = 6.0, featherOct = 1.0 / 6.0;

    Engine();
    ~Engine();

    /** Allocates everything; not realtime. Starts a new epoch. */
    void prepare (double sampleRate, int numChannels, int maxBlockSize);

    /** In place. Non-finite input samples are replaced by 0 (counted) before BODY, analysis and capture. */
    void process (float* const* io, int numChannels, int numSamples, const Params& p) noexcept;

    /** Host bypass: output = input exactly; analysis and voices keep running, ghost muted. */
    void processBypassed (float* const* io, int numChannels, int numSamples, const Params& p) noexcept;

    /** Queue a command (audio thread). Applied at its `at` sample, in order. False if the queue is full. */
    bool submit (const Command&) noexcept;

    /** Audio thread: record a trigger the processor did not forward (DROPPED_RATE, IGNORED_BYPASS). */
    void noteUnforwarded (Origin, Outcome) noexcept;

    // configuration
    double sampleRate() const noexcept { return fs; }
    int channels() const noexcept { return numCh; }
    int fftSize() const noexcept { return N; }
    int hop() const noexcept { return H; }
    int64_t samplesSeen() const noexcept { return streamPos; }
    uint32_t epoch() const noexcept { return epochId; }
    int64_t historySamples() const noexcept { return rawCap; }
    uint64_t nonFiniteInputs() const noexcept { return nonFinite; }

    /** Written by the audio thread at the end of every block; read anywhere. */
    struct Status
    {
        std::atomic<int> state { 0 }, lastReject { 0 }, voices { 0 }, grains { 0 };
        std::atomic<uint32_t> epoch { 0 };
        std::atomic<int64_t> samplesSeen { 0 }, lastS0 { 0 }, lastS1 { 0 }, lastPeriod { 0 }, lastSeam { 0 }, lastDelay { 0 };
        std::atomic<float> lastRho { 0.0f }, blockPeak { 0.0f };
        std::atomic<uint64_t> rejects { 0 }, captures { 0 }, overs { 0 }, nonFinite { 0 };
        std::atomic<int> lastSource { 0 };
        // P1-B
        std::atomic<int> mode { 0 }, hold { 0 }, lastOrigin { 0 }, lastOutcome { 0 }, lastRequestReject { 0 }, autoState { 0 };
        std::atomic<int64_t> lastRequestS0 { 0 }, lastRequestS1 { 0 }, lastRequestAt { 0 }, randomDueIn { -1 };
        std::atomic<float> levelDb { -120.0f }, fluxDb { 0.0f };
        std::array<std::atomic<uint64_t>, (size_t) Outcome::Count> outcomes {};
    } status;

    /** Analysis columns for the display (audio thread writes, one reader). */
    juce::AbstractFifo displayFifo { 512 };
    std::array<DisplayColumn, 512> display;

    // ---- test and tool hooks (not used by the plugin) ----
    void setSeed (uint64_t s) noexcept { baseSeed = s; }
    static constexpr uint64_t defaultSchedulerSeed = 0xAF7E2026B1110001ull;
    void setSchedulerSeed (uint64_t s) noexcept { schedSeed = s; schedRng.s = s; }
    void setRequestLog (RequestRecord* records, int capacity) noexcept { reqLog = records; reqLogCap = capacity; reqLogCount = 0; }
    int requestLogCount() const noexcept { return reqLogCount; }
    int maxRandomAttempts() const noexcept { return maxAttemptsSeen; }
    /** AUTO onset threshold in dB of mean band rise for a sensitivity in [0, 1] (UX contract 6). */
    static double autoThresholdDb (double sensitivity) noexcept { return 3.0 + 9.0 * (1.0 - std::clamp (sensitivity, 0.0, 1.0)); }
    int jobsActive() const noexcept { return job.state != CaptureState::Idle; }
    void setGrainLog (GrainRecord* records, int capacity) noexcept { log = records; logCap = capacity; logCount = 0; }
    int grainLogCount() const noexcept { return logCount; }
    void setDensityOverride (double grainsPerSecond); // stress tests and benchmark; not realtime
    const CaptureInfo& lastCapture() const noexcept { return lastCap; }
    const float* loopChannel (int slot, int c) const noexcept { return slotData[(size_t) slot].data() + (size_t) c * (size_t) slotCap; }
    int maxActiveGrains() const noexcept { return maxActiveSeen; }
    int maxActiveGrainsTotal() const noexcept { return maxActiveTotalSeen; }
    CaptureState captureState() const noexcept { return job.state; }
    /** Stored analysis frame `m`, channel `c` (K bins), or nullptr if it is not in the ring. */
    const std::complex<float>* frame (int64_t m, int c) const noexcept
    {
        return frameAvailable (m) ? hist.data() + ((size_t) (m % histFrames) * (size_t) numCh + (size_t) c) * (size_t) K : nullptr;
    }

private:
    struct Grain
    {
        int64_t onset = 0, end = 0;
        double pos = 0.0;
        float amp = 1.0f, gl = 1.0f, gr = 1.0f;
        bool reverse = false;
        int logIndex = -1;
    };

    struct Voice
    {
        bool active = false, releasing = false;
        int slot = 0;
        int64_t R = 0, t = 0;
        double decay = 1.0, release = 1.0;
        int releaseAge = 0; // samples since REPLACE/CLEAR started the raised-cosine fade-out
        SplitMix64 rng;
        double tNominal = 0.0;
        std::array<Grain, 64> pending {};
        int nPending = 0;
        std::array<Grain, maxGrainsPerVoice> grains {};
        int nGrains = 0;
    };

    struct Job
    {
        CaptureState state = CaptureState::Idle;
        Command cmd;
        int slot = -1;
        int64_t R = 0, len = 0, mLo = 0, mHi = 0, nextM = 0, copied = 0, acceptedAt = 0;
        int requestIndex = -1; // request-log entry to mark COMPLETED
    };

    void processImpl (float* const* io, int nch, int n, const Params& p, bool bypassed) noexcept;
    void apply (const Command&) noexcept;
    Reject validate (const Command&) noexcept;
    void request (const Command&, Origin, int attempts = 0) noexcept;
    int record (const Command&, Origin, Outcome, Reject, int attempts) noexcept;
    void schedule() noexcept;
    void randomTick() noexcept;
    void autoHop (int64_t m, float levelDb, float flux) noexcept;
    void autoDecide() noexcept;
    void resetScheduler() noexcept;
    double meanHopPower (int64_t s0, int64_t s1) const noexcept;
    Command manualSelection (int64_t s1, Origin) const noexcept;
    void reject (Reject) noexcept;
    void analyse() noexcept;
    void captureUnit() noexcept;
    void expireJob() noexcept;
    void startVoice() noexcept;
    void renderVoice (Voice&, float* out) noexcept;
    bool generateGrains (Voice&, int64_t upTo) noexcept;
    int admitGrains (Voice&, int64_t upTo) noexcept;
    bool frameAvailable (int64_t m) const noexcept;
    int freeSlot() const noexcept;
    void computeMask (double low, double high) noexcept;
    float rawAt (int c, int64_t s) const noexcept { return raw[(size_t) c * (size_t) rawCap + (size_t) (((s % rawCap) + rawCap) % rawCap)]; }

    // configuration
    double fs = 0.0;
    int numCh = 0, N = 0, H = 0, K = 0, histFrames = 0, X = 0, onsetLen = 0, releaseLen = 0;
    int64_t rawCap = 0, slotCap = 0, minR = 0, maxR = 0;
    uint32_t epochId = 0;
    double invScale = 1.0;

    // grain configuration (CLOUD)
    int grainLen = 0;
    double interval = 0.0, spray = 1.0, scan = 1.0, jitter = 1.0, reverseProb = 0.5, spread = 0.8, grainGain = 1.0;
    std::vector<float> grainWin;

    // state
    int64_t streamPos = 0;
    uint64_t nonFinite = 0, baseSeed = 1, captureCount = 0;
    bool firstBlock = true, wasBypassed = false;
    Ramp bodyGain, ghostGain, dissolveRamp;
    double cD = 1.0, sD = 0.0;
    double decayK = 1.0;

    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> fftBuf, anaWin, synWin, mask;
    std::vector<std::complex<float>> hist;
    std::vector<int64_t> histIds;
    std::vector<float> raw;
    std::vector<int> bandOf;
    std::array<int, DisplayColumn::bands> bandBin {};
    float bandRef = 1.0f;
    std::array<std::vector<float>, numVoices> slotData;
    std::array<Voice, numVoices> voices;
    Job job;
    std::array<Command, maxPendingCommands> queue;
    int nQueued = 0;
    CaptureInfo lastCap;

    // P1-B scheduler
    Params cur;
    bool bypassedNow = false, firstSchedBlock = true;
    uint64_t schedSeed = defaultSchedulerSeed;
    SplitMix64 schedRng;
    int64_t randomDue = -1;
    double hopEnergy = 0.0;
    std::vector<float> hopPower; // mean square of each hop's new samples, aligned with the frame history
    std::array<float, DisplayColumn::bands> bandDb {}, prevBandDb {};
    // AUTO detector (P1-B architecture 8): 0 armed, 1 in event, 2 re-arming
    struct AutoDetector
    {
        int state = 0, quietHops = 0, calmHops = 0;
        int64_t s0 = 0, lastCapture = -1;
        bool pending = false;
        int64_t pendingS0 = 0, pendingS1 = 0;
    } autoDet;
    RequestRecord* reqLog = nullptr;
    int reqLogCap = 0, reqLogCount = 0, maxAttemptsSeen = 0;

    GrainRecord* log = nullptr;
    int logCap = 0, logCount = 0, maxActiveSeen = 0, maxActiveTotalSeen = 0;
    float peak = 0.0f;
    uint64_t overs = 0;
};

} // namespace afterimage
