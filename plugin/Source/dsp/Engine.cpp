// SPDX-License-Identifier: AGPL-3.0-only
#include "Engine.h"

#include <juce_dsp/juce_dsp.h>

#include <algorithm>
#include <cmath>
#include <cstring>

namespace afterimage
{
namespace
{
constexpr double pi = 3.14159265358979323846;

double smooth01 (double x) noexcept
{
    x = std::clamp (x, 0.0, 1.0);
    return x * x * (3.0 - 2.0 * x);
}

/** Python's float `%`: result has the sign of the divisor. */
double pyMod (double a, double b) noexcept
{
    double m = std::fmod (a, b);
    if (! exactly (m, 0.0) && (m < 0.0) != (b < 0.0)) m += b;
    return m;
}

int64_t pyRound (double x) noexcept { return (int64_t) std::nearbyint (x); } // half to even, like Python round()
} // namespace

const char* rejectName (Reject r) noexcept
{
    switch (r)
    {
        case Reject::None: return "NONE";
        case Reject::StaleEpoch: return "STALE_EPOCH";
        case Reject::BeforeStream: return "BEFORE_STREAM";
        case Reject::TooShort: return "TOO_SHORT";
        case Reject::TooLong: return "TOO_LONG";
        case Reject::Future: return "FUTURE";
        case Reject::InvalidBand: return "INVALID_BAND";
        case Reject::TooFewBins: return "TOO_FEW_BINS";
        case Reject::Expired: return "EXPIRED";
        case Reject::Busy: return "BUSY";
        case Reject::QueueFull: return "QUEUE_FULL";
    }
    return "?";
}

const char* originName (Origin o) noexcept
{
    switch (o)
    {
        case Origin::Selection: return "SELECTION";
        case Origin::Button: return "BUTTON";
        case Origin::Midi: return "MIDI";
        case Origin::Automation: return "AUTOMATION";
        case Origin::Random: return "RANDOM";
        case Origin::Auto: return "AUTO";
        case Origin::None:
        case Origin::Count: return "-";
    }
    return "-";
}

const char* outcomeName (Outcome o) noexcept
{
    switch (o)
    {
        case Outcome::Accepted: return "ACCEPTED";
        case Outcome::Completed: return "COMPLETED";
        case Outcome::Rejected: return "REJECTED";
        case Outcome::SuppressedHold: return "SUPPRESSED_HOLD";
        case Outcome::SkippedBusy: return "SKIPPED_BUSY";
        case Outcome::NoCandidate: return "NO_CANDIDATE";
        case Outcome::IgnoredBypass: return "IGNORED_BYPASS";
        case Outcome::DroppedRate: return "DROPPED_RATE";
        case Outcome::None:
        case Outcome::Count: return "-";
    }
    return "-";
}

Engine::Engine() = default;
Engine::~Engine() = default;

void Engine::prepare (double sampleRate, int numChannels, int /*maxBlockSize*/)
{
    fs = sampleRate;
    numCh = std::clamp (numChannels, 1, maxChannels);
    N = fs <= 48000.0 ? 4096 : 8192; // DSP-ARCHITECTURE 3.2
    H = N / 4;
    K = N / 2 + 1;
    histFrames = (int) std::ceil (historySeconds * fs / H) + 2;
    rawCap = (int64_t) histFrames * H;
    X = (int) pyRound (seamSeconds * fs);
    onsetLen = (int) (onsetFadeSeconds * fs); // int() truncation, as p0.engines.envelope
    releaseLen = (int) pyRound (releaseSeconds * fs);
    minR = pyRound (minSelectionSeconds * fs);
    maxR = pyRound (maxSelectionSeconds * fs);
    slotCap = maxR + X;

    int order = 0;
    while ((1 << order) < N) ++order;
    fft = std::make_unique<juce::dsp::FFT> (order);
    fftBuf.assign ((size_t) (2 * N), 0.0f);
    anaWin.resize ((size_t) N);
    synWin.resize ((size_t) N);
    for (int i = 0; i < N; ++i)
    {
        anaWin[(size_t) i] = (float) std::sqrt (0.5 - 0.5 * std::cos (2.0 * pi * i / N)); // periodic sqrt-Hann
        synWin[(size_t) i] = anaWin[(size_t) i] * 0.5f;                                     // / WOLA_GAIN
    }
    // inverse scale calibration: forward then inverse of an impulse must return the impulse
    std::fill (fftBuf.begin(), fftBuf.end(), 0.0f);
    fftBuf[3] = 1.0f;
    fft->performRealOnlyForwardTransform (fftBuf.data(), true);
    fft->performRealOnlyInverseTransform (fftBuf.data());
    invScale = 1.0 / fftBuf[3];

    hist.assign ((size_t) histFrames * (size_t) numCh * (size_t) K, {});
    histIds.assign ((size_t) histFrames, -1);
    raw.assign ((size_t) numCh * (size_t) rawCap, 0.0f);
    mask.assign ((size_t) K, 0.0f);
    for (auto& s : slotData) s.assign ((size_t) numCh * (size_t) slotCap, 0.0f);
    hopPower.assign ((size_t) histFrames, 0.0f);

    // display: 160 log bands, 20 Hz .. fs/2
    bandOf.assign ((size_t) K, -1);
    for (int k = 1; k < K; ++k)
    {
        const double f = k * fs / N;
        if (f >= 20.0)
            bandOf[(size_t) k] = std::min (DisplayColumn::bands - 1, (int) (DisplayColumn::bands * std::log (f / 20.0) / std::log (fs / 40.0)));
    }
    // bands narrower than a bin (the lowest ones) show their nearest bin instead of staying empty
    for (int b = 0; b < DisplayColumn::bands; ++b)
    {
        const double centre = 20.0 * std::pow (fs / 40.0, (b + 0.5) / DisplayColumn::bands);
        bandBin[(size_t) b] = std::clamp ((int) std::lround (centre * N / fs), 1, K - 1);
    }
    double wsum = 0.0;
    for (auto w : anaWin) wsum += w;
    bandRef = (float) ((wsum / 2) * (wsum / 2));

    // CLOUD = p0.granular.dissolve_params(1.0) with pitch off (p1a_reference.cloud_params)
    const double D = 1.0;
    const auto L0 = 2 * pyRound ((0.12 + 0.08 * D) * fs / 2);
    const double grainS = (double) L0 / fs;
    grainLen = (int) std::max<int64_t> (2 * pyRound (grainS * fs / 2), 2);
    spray = D * D;
    jitter = D;
    scan = 1.0;
    reverseProb = 0.5 * smooth01 ((D - 0.25) / 0.75);
    spread = 0.8 * D;
    grainWin.resize ((size_t) grainLen);
    for (int i = 0; i < grainLen; ++i) grainWin[(size_t) i] = (float) (0.5 - 0.5 * std::cos (2.0 * pi * i / grainLen));
    setDensityOverride ((2.0 + 2.0 * smooth01 ((D - 0.1) / 0.6)) * fs / (double) L0);

    // state
    ++epochId;
    streamPos = 0;
    nonFinite = 0;
    captureCount = 0;
    firstBlock = true;
    wasBypassed = false;
    bodyGain.setLength ((int) pyRound (0.02 * fs));
    ghostGain.setLength ((int) pyRound (0.02 * fs));
    dissolveRamp.setLength ((int) pyRound (0.05 * fs));
    for (auto& v : voices) v = Voice {};
    job = Job {};
    nQueued = 0;
    lastCap = CaptureInfo {};
    maxActiveSeen = maxActiveTotalSeen = 0;
    overs = 0;
    displayFifo.reset();
    hopEnergy = 0.0;
    schedRng.s = schedSeed;
    firstSchedBlock = true;
    bypassedNow = false;
    randomDue = -1;
    reqLogCount = 0;
    maxAttemptsSeen = 0;
    for (auto& o : status.outcomes) o = 0;
    status.lastOrigin = 0;
    status.lastOutcome = 0;
    status.epoch = epochId;
    status.state = 0;
    status.lastReject = 0;
    status.samplesSeen = 0;
}

void Engine::setDensityOverride (double grainsPerSecond)
{
    interval = fs / grainsPerSecond;
    // p0.granular.nominal_gain with amp_var 0, coherence 0
    double mw2 = 0.0;
    for (int i = 0; i < grainLen; ++i)
    {
        const double w = 0.5 - 0.5 * std::cos (2.0 * pi * i / grainLen);
        mw2 += w * w;
    }
    mw2 /= grainLen;
    const double ov = grainsPerSecond * grainLen / fs;
    grainGain = 1.0 / std::sqrt (std::max (ov * mw2, 0.75));
}

bool Engine::submit (const Command& c) noexcept
{
    if (nQueued >= maxPendingCommands)
    {
        reject (Reject::QueueFull);
        return false;
    }
    queue[(size_t) nQueued++] = c;
    return true;
}

void Engine::reject (Reject r) noexcept
{
    status.lastReject = (int) r;
    status.rejects.fetch_add (1, std::memory_order_relaxed);
}

void Engine::computeMask (double low, double high) noexcept
{
    // p0.capture.frequency_mask with feather > 0
    for (int k = 0; k < K; ++k)
    {
        const double f = k * fs / N;
        const double lf = std::log2 (std::max (f, 1e-9));
        double m = 1.0;
        if (low > 0.0)
            m *= 0.5 + 0.5 * std::cos (pi * std::clamp ((std::log2 (low) - lf) / featherOct, 0.0, 1.0));
        if (high < fs / 2)
            m *= 0.5 + 0.5 * std::cos (pi * std::clamp ((lf - std::log2 (high)) / featherOct, 0.0, 1.0));
        mask[(size_t) k] = (float) m;
    }
    if (low > 0.0) mask[0] = 0.0f;
}

bool Engine::frameAvailable (int64_t m) const noexcept
{
    return m >= 0 && histIds[(size_t) (m % histFrames)] == m;
}

int Engine::freeSlot() const noexcept
{
    for (int s = 0; s < numVoices; ++s)
    {
        bool used = false;
        for (auto& v : voices) used |= v.active && v.slot == s;
        if (! used) return s;
    }
    return -1;
}

void Engine::apply (const Command& c) noexcept
{
    if (c.type == Command::Type::Clear)
    {
        job.state = CaptureState::Idle;
        for (auto& v : voices)
            if (v.active && ! v.releasing)
            {
                v.releasing = true;
                v.releaseAge = 0;
            }
        return;
    }
    if (bypassedNow)
    {
        record (c, c.origin, Outcome::IgnoredBypass, Reject::None, 0);
        return;
    }
    request (c.type == Command::Type::Trigger ? manualSelection (streamPos, c.origin) : c, c.origin);
}

Command Engine::manualSelection (int64_t s1, Origin origin) const noexcept
{
    // P1-B architecture 5: the last capture-length of audio, ending exactly at the trigger sample
    Command c;
    c.origin = origin;
    c.epoch = epochId;
    c.s1 = s1;
    c.s0 = s1 - pyRound ((double) cur.lengthSeconds * fs);
    c.source = cur.source;
    const double half = std::pow (2.0, 0.5 * (double) cur.bandWidthOct);
    c.lowHz = (double) cur.bandCenterHz / half;
    c.highHz = std::min ((double) cur.bandCenterHz * half, fs / 2);
    return c;
}

void Engine::request (const Command& c, Origin origin, int attempts) noexcept
{
    const auto r = validate (c);
    if (r != Reject::None)
    {
        reject (r);
        record (c, origin, Outcome::Rejected, r, attempts);
        return;
    }
    status.lastReject = (int) Reject::None;
    job.requestIndex = record (c, origin, Outcome::Accepted, Reject::None, attempts);
}

int Engine::record (const Command& c, Origin origin, Outcome outcome, Reject r, int attempts) noexcept
{
    status.outcomes[(size_t) outcome].fetch_add (1, std::memory_order_relaxed);
    status.lastOrigin.store ((int) origin, std::memory_order_relaxed);
    status.lastOutcome.store ((int) outcome, std::memory_order_relaxed);
    status.lastRequestReject.store ((int) r, std::memory_order_relaxed);
    status.lastRequestS0.store (c.s0, std::memory_order_relaxed);
    status.lastRequestS1.store (c.s1, std::memory_order_relaxed);
    status.lastRequestAt.store (streamPos, std::memory_order_relaxed);
    if (reqLog == nullptr || reqLogCount >= reqLogCap) return -1;
    reqLog[reqLogCount] = { streamPos, c.s0, c.s1, c.lowHz, c.highHz, origin, outcome, r, c.source, attempts, -1 };
    return reqLogCount++;
}

void Engine::noteUnforwarded (Origin origin, Outcome outcome) noexcept
{
    Command c;
    record (c, origin, outcome, Reject::None, 0);
}

Reject Engine::validate (const Command& c) noexcept
{
    if (c.epoch != epochId) return Reject::StaleEpoch;
    if (c.s0 < 0) return Reject::BeforeStream;
    const int64_t R = c.s1 - c.s0;
    if (R < minR) return Reject::TooShort;
    if (R > maxR) return Reject::TooLong;
    if (c.s1 > streamPos) return Reject::Future;
    Job j;
    j.cmd = c;
    j.R = R;
    j.len = R + X;
    j.acceptedAt = streamPos;
    if (c.source == Source::Filtered)
    {
        if (! std::isfinite (c.lowHz) || ! std::isfinite (c.highHz) || c.lowHz < 0.0 || c.highHz > fs / 2 || c.lowHz >= c.highHz)
            return Reject::InvalidBand;
        if (job.state != CaptureState::Idle) return Reject::Busy;
        computeMask (c.lowHz, c.highHz);
        int bins = 0;
        for (auto m : mask) bins += m >= 0.5f;
        if (bins < 3) return Reject::TooFewBins;
        j.mLo = c.s0 / H;
        j.mHi = (c.s0 + j.len - 1 + N) / H - 1;
        if (j.mLo <= (streamPos / H - 1) - histFrames) return Reject::Expired;
    }
    else if (c.s0 < streamPos - rawCap)
        return Reject::Expired;
    if (job.state != CaptureState::Idle) return Reject::Busy;
    j.nextM = j.mLo;
    j.state = CaptureState::Waiting;
    job = j;
    return Reject::None;
}

// ---------------------------------------------------------------------------------------------
// P1-B scheduler (docs/P1-B-CAPTURE-ARCHITECTURE.md 4, 7)
void Engine::resetScheduler() noexcept
{
    const double I = std::clamp ((double) cur.randomIntervalSeconds, 1.0, 16.0) * fs;
    randomDue = streamPos + (int64_t) (I * (0.75 + 0.5 * schedRng.uniform()));
}

double Engine::meanHopPower (int64_t s0, int64_t s1) const noexcept
{
    const int64_t h0 = s0 / H, h1 = (s1 - 1) / H, latest = streamPos / H - 1;
    double sum = 0.0;
    int n = 0;
    for (int64_t h = h0; h <= h1; ++h)
        if (h >= 0 && h <= latest && h > latest - histFrames)
        {
            sum += hopPower[(size_t) (h % histFrames)];
            ++n;
        }
    return n > 0 ? sum / n : 0.0;
}

void Engine::randomTick() noexcept
{
    if (randomDue < 0) resetScheduler();
    status.randomDueIn.store (randomDue - streamPos, std::memory_order_relaxed);
    if (streamPos < randomDue) return;
    const double I = std::clamp ((double) cur.randomIntervalSeconds, 1.0, 16.0) * fs;
    randomDue = streamPos + (int64_t) (I * (0.75 + 0.5 * schedRng.uniform())); // every tick reschedules: no backlog
    Command none;
    if (cur.hold) { record (none, Origin::Random, Outcome::SuppressedHold, Reject::None, 0); return; }
    if (job.state != CaptureState::Idle || freeSlot() < 0) { record (none, Origin::Random, Outcome::SkippedBusy, Reject::None, 0); return; }

    const int64_t L = pyRound ((double) cur.lengthSeconds * fs), D = X + N + H, W = pyRound (4.0 * fs);
    const double gate = std::pow (10.0, 0.1 * (double) cur.gateDb);
    constexpr int maxAttempts = 8;
    for (int a = 1; a <= maxAttempts; ++a)
    {
        const double u = schedRng.uniform(), ub = schedRng.uniform(); // two draws per attempt, always
        Command c = manualSelection (streamPos - D - (int64_t) (u * (double) std::max<int64_t> (W - D, 0)), Origin::Random);
        c.s0 = c.s1 - L;
        if (c.source == Source::Filtered)
        {
            const double half = std::pow (2.0, 0.5 * (double) cur.bandWidthOct), centre = (double) cur.bandCenterHz * std::pow (2.0, 2.0 * ub - 1.0);
            c.lowHz = centre / half;
            c.highHz = std::min (centre * half, fs / 2);
        }
        maxAttemptsSeen = std::max (maxAttemptsSeen, a);
        if (c.s0 < 0 || meanHopPower (c.s0, c.s1) < gate) continue;
        return request (c, Origin::Random, a);
    }
    record (none, Origin::Random, Outcome::NoCandidate, Reject::None, maxAttempts);
}

void Engine::schedule() noexcept
{
    if (cur.mode == Mode::Random) randomTick();
    else status.randomDueIn.store (-1, std::memory_order_relaxed);
}

void Engine::analyse() noexcept
{
    const int64_t m = streamPos / H - 1;
    const auto slot = (size_t) (m % histFrames);
    hopPower[slot] = (float) (hopEnergy / ((double) H * numCh)); // the hop's new samples [mH, (m+1)H)
    status.levelDb.store ((float) (10.0 * std::log10 (hopEnergy / ((double) H * numCh) + 1e-12)), std::memory_order_relaxed);
    hopEnergy = 0.0;
    const int64_t first = (m + 1) * H - N;
    std::array<float, DisplayColumn::bands> power {};
    for (int c = 0; c < numCh; ++c)
    {
        for (int i = 0; i < N; ++i)
            fftBuf[(size_t) i] = rawAt (c, first + i) * anaWin[(size_t) i];
        std::fill (fftBuf.begin() + N, fftBuf.end(), 0.0f);
        fft->performRealOnlyForwardTransform (fftBuf.data(), true);
        auto* dst = hist.data() + (slot * (size_t) numCh + (size_t) c) * (size_t) K;
        for (int k = 0; k < K; ++k)
        {
            dst[k] = { fftBuf[(size_t) (2 * k)], fftBuf[(size_t) (2 * k + 1)] };
            if (const int b = bandOf[(size_t) k]; b >= 0)
                power[(size_t) b] = std::max (power[(size_t) b], std::norm (dst[k]));
        }
        for (int b = 0; b < DisplayColumn::bands; ++b)
            power[(size_t) b] = std::max (power[(size_t) b], std::norm (dst[bandBin[(size_t) b]]));
    }
    histIds[slot] = m;

    const auto scope = displayFifo.write (1);
    if (scope.blockSize1 > 0)
    {
        auto& col = display[(size_t) scope.startIndex1];
        col.endSample = (m + 1) * H;
        col.epoch = epochId;
        for (int b = 0; b < DisplayColumn::bands; ++b)
            col.db[(size_t) b] = 10.0f * std::log10 (power[(size_t) b] / bandRef + 1.0e-12f);
    }
}

void Engine::captureUnit() noexcept
{
    if (job.state == CaptureState::Idle) return;
    const auto& c = job.cmd;
    if (job.state == CaptureState::Waiting)
    {
        const bool ready = c.source == Source::Full ? streamPos >= c.s1 + X : streamPos >= (job.mHi + 1) * H;
        if (! ready) return;
        job.slot = freeSlot();
        if (job.slot < 0) return; // a REPLACE fade still holds both slots
        job.state = CaptureState::Building;
        std::fill (slotData[(size_t) job.slot].begin(), slotData[(size_t) job.slot].end(), 0.0f);
        return; // the clear is this slot's unit of work
    }

    auto* slot = slotData[(size_t) job.slot].data();
    if (c.source == Source::Full)
    {
        if (job.copied < job.len)
        {
            if (c.s0 < streamPos - rawCap) { job.state = CaptureState::Idle; return expireJob(); }
            const int64_t n = std::min<int64_t> (4096, job.len - job.copied);
            for (int ch = 0; ch < numCh; ++ch)
                for (int64_t i = 0; i < n; ++i)
                    slot[(size_t) ch * (size_t) slotCap + (size_t) (job.copied + i)] = rawAt (ch, c.s0 + job.copied + i);
            job.copied += n;
            return;
        }
    }
    else if (job.nextM <= job.mHi)
    {
        const int64_t m = job.nextM++;
        if (! frameAvailable (m)) { job.state = CaptureState::Idle; return expireJob(); }
        const auto hslot = (size_t) (m % histFrames);
        const int64_t off = (m + 1) * H - N - c.s0;
        const int64_t a = std::max<int64_t> (off, 0), b = std::min<int64_t> (off + N, job.len);
        for (int ch = 0; ch < numCh; ++ch)
        {
            const auto* src = hist.data() + (hslot * (size_t) numCh + (size_t) ch) * (size_t) K;
            for (int k = 0; k < K; ++k)
            {
                fftBuf[(size_t) (2 * k)] = src[k].real() * mask[(size_t) k];
                fftBuf[(size_t) (2 * k + 1)] = src[k].imag() * mask[(size_t) k];
            }
            std::fill (fftBuf.begin() + 2 * K, fftBuf.end(), 0.0f);
            fft->performRealOnlyInverseTransform (fftBuf.data());
            auto* dst = slot + (size_t) ch * (size_t) slotCap;
            for (int64_t i = a; i < b; ++i)
                dst[i] += (float) (fftBuf[(size_t) (i - off)] * invScale) * synWin[(size_t) (i - off)];
        }
        return;
    }

    // seam: p0.engines.loop_period(seg, fs, 0.08, "aligned", period=R)
    double hh = 0.0, tt = 0.0, ht = 0.0;
    for (int ch = 0; ch < numCh; ++ch)
    {
        const auto* s = slot + (size_t) ch * (size_t) slotCap;
        for (int i = 0; i < X; ++i)
        {
            const double h = s[i], t = s[job.R + i];
            hh += h * h;
            tt += t * t;
            ht += h * t;
        }
    }
    const double d = std::sqrt (hh * tt);
    const double rho = d > 0.0 ? ht / d : 0.0;
    for (int ch = 0; ch < numCh; ++ch)
    {
        auto* s = slot + (size_t) ch * (size_t) slotCap;
        for (int i = 0; i < X; ++i)
        {
            const double ta = (double) i / X, tb = 1.0 - ta;
            const double g = std::sqrt (ta * ta + tb * tb + 2.0 * std::max (rho, 0.0) * ta * tb);
            s[i] = (float) (s[i] * (ta / g) + s[job.R + i] * (tb / g));
        }
    }
    lastCap.rho = rho;
    startVoice();
}

void Engine::expireJob() noexcept
{
    reject (Reject::Expired);
    if (reqLog != nullptr && job.requestIndex >= 0) { reqLog[job.requestIndex].outcome = Outcome::Rejected; reqLog[job.requestIndex].reject = Reject::Expired; }
    status.outcomes[(size_t) Outcome::Rejected].fetch_add (1, std::memory_order_relaxed);
}

void Engine::startVoice() noexcept
{
    for (auto& v : voices)
        if (v.active && ! v.releasing)
        {
            v.releasing = true;
            v.releaseAge = 0;
        }
    Voice* nv = nullptr;
    for (auto& v : voices)
        if (! v.active) { nv = &v; break; }
    if (nv == nullptr) { job.state = CaptureState::Idle; return; } // unreachable: the slot was free

    *nv = Voice {};
    nv->active = true;
    nv->slot = job.slot;
    nv->R = job.R;
    nv->rng.s = baseSeed + captureCount;
    nv->tNominal = -(double) grainLen;

    lastCap.s0 = job.cmd.s0;
    lastCap.s1 = job.cmd.s1;
    lastCap.period = job.R;
    lastCap.seam = X;
    lastCap.acceptedAt = job.acceptedAt;
    lastCap.startedAt = streamPos;
    lastCap.source = job.cmd.source;
    lastCap.slot = job.slot;
    lastCap.seed = nv->rng.s;
    ++captureCount;
    job.state = CaptureState::Idle;

    status.lastS0 = lastCap.s0;
    status.lastS1 = lastCap.s1;
    status.lastPeriod = lastCap.period;
    status.lastSeam = lastCap.seam;
    status.lastDelay = lastCap.startedAt - lastCap.acceptedAt;
    status.lastRho = (float) lastCap.rho;
    status.lastSource = (int) lastCap.source;
    status.captures.fetch_add (1, std::memory_order_relaxed);
    status.outcomes[(size_t) Outcome::Completed].fetch_add (1, std::memory_order_relaxed);
    if (reqLog != nullptr && job.requestIndex >= 0)
    {
        reqLog[job.requestIndex].outcome = Outcome::Completed;
        reqLog[job.requestIndex].startedAt = streamPos;
    }
    if (status.lastRequestS1.load (std::memory_order_relaxed) == lastCap.s1) status.lastOutcome.store ((int) Outcome::Completed, std::memory_order_relaxed);
}

bool Engine::generateGrains (Voice& v, int64_t upTo) noexcept
{
    // p0.granular.schedule, streamed: grains in nominal-time order, kept sorted by onset (stable)
    while (v.tNominal < (double) upTo + interval && v.nPending < (int) v.pending.size())
    {
        double u[8];
        for (auto& x : u) x = v.rng.uniform();
        Grain g;
        g.onset = pyRound (v.tNominal + jitter * (u[0] - 0.5) * interval);
        g.end = g.onset + grainLen;
        g.pos = pyMod ((double) g.onset * scan + spray * (double) v.R * (u[6] - 0.5), (double) v.R);
        g.reverse = u[3] < reverseProb;
        const double a = (spread * (2.0 * u[4] - 1.0) + 1.0) * pi / 4.0;
        const double gl = std::sqrt (2.0) * std::cos (a), gr = std::sqrt (2.0) * std::sin (a);
        g.amp = (float) grainGain;
        g.gl = (float) gl;
        g.gr = (float) gr;
        if (log != nullptr && logCount < logCap)
        {
            log[logCount] = { g.onset, grainLen, g.pos, 1.0, grainGain, gl, gr, g.reverse, false };
            g.logIndex = logCount++;
        }
        int i = v.nPending++;
        while (i > 0 && v.pending[(size_t) i - 1].onset > g.onset)
        {
            v.pending[(size_t) i] = v.pending[(size_t) i - 1];
            --i;
        }
        v.pending[(size_t) i] = g;
        v.tNominal += interval;
    }
    return v.tNominal < (double) upTo + interval; // stopped early: pending list full
}

int Engine::admitGrains (Voice& v, int64_t upTo) noexcept
{
    int admitted = 0;
    while (v.nPending > 0 && v.pending[0].onset <= upTo)
    {
        const Grain g = v.pending[0];
        std::move (v.pending.begin() + 1, v.pending.begin() + v.nPending, v.pending.begin());
        --v.nPending;
        for (int i = 0; i < v.nGrains;) // retire grains that end at or before this onset
            if (v.grains[(size_t) i].end <= g.onset) v.grains[(size_t) i] = v.grains[(size_t) --v.nGrains];
            else ++i;
        if (v.nGrains < maxGrainsPerVoice) v.grains[(size_t) v.nGrains++] = g;
        else if (g.logIndex >= 0) log[g.logIndex].dropped = true;
        ++admitted;
    }
    return admitted;
}

void Engine::renderVoice (Voice& v, float* out) noexcept
{
    const double env = v.decay * (v.t < onsetLen ? 0.5 - 0.5 * std::cos (pi * (double) v.t / onsetLen) : 1.0) * v.release;
    // a dense setting can need more grains at once than the pending list holds (voice start pre-roll)
    while (generateGrains (v, v.t) && admitGrains (v, v.t) > 0) {}
    admitGrains (v, v.t);

    float trace[maxChannels] {}, cloud[maxChannels] {};
    const auto* loop = slotData[(size_t) v.slot].data();
    const auto R = v.R;
    for (int c = 0; c < numCh; ++c)
        trace[c] = loop[(size_t) c * (size_t) slotCap + (size_t) (v.t % R)];

    for (int i = 0; i < v.nGrains;)
    {
        auto& g = v.grains[(size_t) i];
        if (g.end <= v.t) { g = v.grains[(size_t) --v.nGrains]; continue; }
        const int64_t k = v.t - g.onset;
        const double p = g.pos + (double) (g.reverse ? grainLen - 1 - k : k);
        const double fl = std::floor (p);
        const auto f = (float) (p - fl);
        const auto i1 = (int64_t) fl;
        const auto w = grainWin[(size_t) k] * g.amp;
        for (int c = 0; c < numCh; ++c)
        {
            const auto* b = loop + (size_t) c * (size_t) slotCap;
            const float y0 = b[(i1 - 1 + R) % R], y1 = b[i1 % R], y2 = b[(i1 + 1) % R], y3 = b[(i1 + 2) % R];
            float y = y1 + 0.5f * f * (y2 - y0 + f * (2.0f * y0 - 5.0f * y1 + 4.0f * y2 - y3 + f * (3.0f * (y1 - y2) + y3 - y0)));
            y *= w;
            if (numCh == 2) y *= c == 0 ? g.gl : g.gr;
            cloud[c] += y;
        }
        ++i;
    }
    maxActiveSeen = std::max (maxActiveSeen, v.nGrains);

    for (int c = 0; c < numCh; ++c)
        out[c] += (float) (env * (cD * trace[c] + sD * cloud[c]));

    ++v.t;
    v.decay *= decayK;
    if (v.releasing) // raised cosine: no slope discontinuity where the fade starts or ends
        v.release = 0.5 + 0.5 * std::cos (pi * (double) ++v.releaseAge / releaseLen);
    if (v.decay < 1.0e-5 || (v.releasing && v.releaseAge >= releaseLen)) v.active = false;
}

void Engine::process (float* const* io, int nch, int n, const Params& p) noexcept { processImpl (io, nch, n, p, false); }
void Engine::processBypassed (float* const* io, int nch, int n, const Params& p) noexcept { processImpl (io, nch, n, p, true); }

void Engine::processImpl (float* const* io, int nch, int n, const Params& p, bool bypassed) noexcept
{
    nch = std::min (nch, numCh);
    const bool resumed = wasBypassed && ! bypassed;
    const bool modeChanged = p.mode != cur.mode, holdReleased = cur.hold && ! p.hold;
    cur = p;
    bypassedNow = bypassed;
    if (firstSchedBlock || modeChanged || holdReleased || resumed) resetScheduler(); // never replays a backlog
    firstSchedBlock = false;
    status.mode.store ((int) p.mode, std::memory_order_relaxed);
    status.hold.store (p.hold ? 1 : 0, std::memory_order_relaxed);
    if (firstBlock || resumed)
    {
        bodyGain.reset (firstBlock ? p.body : 1.0);
        ghostGain.reset (firstBlock ? p.ghost : 0.0);
        if (firstBlock) dissolveRamp.reset (p.dissolve);
        firstBlock = false;
    }
    wasBypassed = bypassed;
    bodyGain.setTarget (p.body);
    ghostGain.setTarget (p.ghost);
    dissolveRamp.setTarget (std::clamp ((double) p.dissolve, 0.0, 1.0));
    decayK = std::pow (10.0, -3.0 / (std::clamp ((double) p.t60, 0.25, 30.0) * fs));

    for (int i = 0; i < n; ++i)
    {
        while (nQueued > 0 && queue[0].at <= streamPos)
        {
            const Command c = queue[0];
            std::move (queue.begin() + 1, queue.begin() + nQueued, queue.begin());
            --nQueued;
            apply (c);
        }

        float x[maxChannels] {};
        bool sanitized = false;
        for (int c = 0; c < nch; ++c)
        {
            x[c] = io[c][i];
            if (! std::isfinite (x[c])) { x[c] = 0.0f; ++nonFinite; sanitized = true; }
            hopEnergy += (double) x[c] * x[c];
        }

        const bool unityBody = bodyGain.atRest() && exactly (bodyGain.target, 1.0);
        const auto b = (float) bodyGain.next();
        const auto gg = (float) ghostGain.next();
        if (! dissolveRamp.atRest() || i == 0)
        {
            const double d = dissolveRamp.next();
            cD = std::cos (0.5 * pi * d);
            sD = std::sin (0.5 * pi * d);
        }

        float g[maxChannels] {};
        bool anyVoice = false;
        int activeTotal = 0;
        for (auto& v : voices)
            if (v.active)
            {
                renderVoice (v, g);
                anyVoice = true;
                activeTotal += v.nGrains;
            }
        maxActiveTotalSeen = std::max (maxActiveTotalSeen, activeTotal);

        if (! bypassed && (! unityBody || anyVoice || sanitized))
            for (int c = 0; c < nch; ++c)
            {
                const float y = (unityBody ? x[c] : x[c] * b) + (anyVoice ? gg * g[c] : 0.0f);
                io[c][i] = y;
                peak = std::max (peak, std::abs (y));
                overs += std::abs (y) > 1.0f;
            }
        else
            for (int c = 0; c < nch; ++c)
                peak = std::max (peak, std::abs (io[c][i]));

        for (int c = 0; c < numCh; ++c)
            raw[(size_t) c * (size_t) rawCap + (size_t) (streamPos % rawCap)] = x[c < nch ? c : 0];
        ++streamPos;
        if (streamPos % H == 0) analyse();
        if (streamPos % unitStride == unitStride / 2)
        {
            captureUnit();
            if (! bypassed) schedule();
        }
    }

    int nv = 0, ng = 0;
    for (auto& v : voices) { nv += v.active; ng += v.active ? v.nGrains : 0; }
    status.voices.store (nv, std::memory_order_relaxed);
    status.grains.store (ng, std::memory_order_relaxed);
    status.state.store ((int) job.state, std::memory_order_relaxed);
    status.samplesSeen.store (streamPos, std::memory_order_relaxed);
    status.blockPeak.store (peak, std::memory_order_relaxed);
    status.overs.store (overs, std::memory_order_relaxed);
    status.nonFinite.store (nonFinite, std::memory_order_relaxed);
    peak = 0.0f;
}

} // namespace afterimage
