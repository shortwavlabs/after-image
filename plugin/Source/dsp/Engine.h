// SPDX-License-Identifier: AGPL-3.0-only
// AFTERIMAGE realtime engine. Owned and driven by the audio callback only.
// Design: docs/P1-A-REALTIME-ARCHITECTURE.md
#pragma once

#include <cstdint>
#include <functional>

namespace afterimage
{

inline bool exactly (double a, double b) noexcept { return std::equal_to<double>() (a, b); }

struct Params
{
    float body = 1.0f;      // linear BODY gain
    float ghost = 0.5f;     // linear GHOST gain
    float t60 = 5.0f;       // MEMORY, seconds
    float dissolve = 1.0f;  // 0 = TRACE, 1 = CLOUD
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

class Engine
{
public:
    void prepare (double sampleRate, int numChannels, int maxBlockSize);

    /** In-place processing of `numChannels` channels. Non-finite input samples are replaced by 0
        (counted); with BODY at rest at exactly 1 and no sounding ghost the buffer is left untouched. */
    void process (float* const* io, int numChannels, int numSamples, const Params& p) noexcept;

    /** Host bypass: output = input exactly; gains restart from (BODY 1, GHOST 0) on resume. */
    void processBypassed (float* const* io, int numChannels, int numSamples) noexcept;

    double sampleRate() const noexcept { return fs; }
    int channels() const noexcept { return numCh; }
    int64_t samplesSeen() const noexcept { return streamPos; }
    uint64_t nonFiniteInputs() const noexcept { return nonFinite; }

private:
    double fs = 0.0;
    int numCh = 0;
    int64_t streamPos = 0;
    uint64_t nonFinite = 0;
    bool wasBypassed = false;
    Ramp bodyGain, ghostGain;
};

} // namespace afterimage
