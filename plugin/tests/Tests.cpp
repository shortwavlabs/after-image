// SPDX-License-Identifier: AGPL-3.0-only
// AFTERIMAGE C++ unit tests. Plain checks, no framework; exit code = number of failed checks.
#include <PluginProcessor.h>
#include <PluginEditor.h>

#include <thread>
#include <malloc/malloc.h>
#include <pthread.h>

#include <cstdio>
#include <functional>
#include <utility>
#include <cstring>
#include <random>
#include <vector>

namespace
{
int failures = 0, checks = 0;
const char* currentTest = "";

#define CHECK(cond)                                                                        \
    do {                                                                                   \
        ++checks;                                                                          \
        if (! (cond)) { ++failures; std::printf ("  FAIL [%s] %s:%d  %s\n", currentTest, __FILE__, __LINE__, #cond); } \
    } while (0)

constexpr double rates[] = { 44100.0, 48000.0, 88200.0, 96000.0 };
constexpr int blockSizes[] = { 1, 16, 32, 64, 1024 };

struct Rig
{
    AfterimageProcessor proc;
    juce::MidiBuffer midi;
    int nch;

    Rig (double fs, int channels, int block) : nch (channels)
    {
        const auto set = channels == 1 ? juce::AudioChannelSet::mono() : juce::AudioChannelSet::stereo();
        juce::AudioProcessor::BusesLayout layout;
        layout.inputBuses.add (set);
        layout.outputBuses.add (set);
        proc.setBusesLayout (layout);
        proc.setRateAndBufferSizeDetails (fs, block);
        proc.prepareToPlay (fs, block);
    }

    void set (const char* id, float plain)
    {
        auto* p = proc.apvts.getParameter (id);
        p->setValueNotifyingHost (p->convertTo0to1 (plain));
    }

    /** Runs `x` (channels x samples) through the processor in blocks of `block` (0 = varying). */
    std::vector<std::vector<float>> run (const std::vector<std::vector<float>>& x, int block, bool bypassed = false)
    {
        auto y = x;
        const int n = (int) x[0].size();
        std::mt19937 rng (7);
        for (int pos = 0; pos < n;)
        {
            const int b = std::min (block > 0 ? block : 1 + (int) (rng() % 700), n - pos);
            juce::AudioBuffer<float> buf (nch, b);
            for (int c = 0; c < nch; ++c)
                std::memcpy (buf.getWritePointer (c), y[(size_t) c].data() + pos, sizeof (float) * (size_t) b);
            if (bypassed) proc.processBlockBypassed (buf, midi);
            else proc.processBlock (buf, midi);
            for (int c = 0; c < nch; ++c)
                std::memcpy (y[(size_t) c].data() + pos, buf.getReadPointer (c), sizeof (float) * (size_t) b);
            pos += b;
        }
        return y;
    }
};

std::vector<std::vector<float>> noise (int nch, int n, unsigned seed, float amp = 0.5f)
{
    std::mt19937 rng (seed);
    std::uniform_real_distribution<float> u (-amp, amp);
    std::vector<std::vector<float>> x ((size_t) nch, std::vector<float> ((size_t) n));
    for (auto& ch : x)
        for (auto& v : ch) v = u (rng);
    return x;
}

bool bitIdentical (const std::vector<std::vector<float>>& a, const std::vector<std::vector<float>>& b)
{
    for (size_t c = 0; c < a.size(); ++c)
        if (std::memcmp (a[c].data(), b[c].data(), a[c].size() * sizeof (float)) != 0) return false;
    return true;
}

// ---------------------------------------------------------------------------------------------
void testLayouts()
{
    currentTest = "layouts";
    AfterimageProcessor p;
    auto layout = [] (juce::AudioChannelSet in, juce::AudioChannelSet out)
    {
        juce::AudioProcessor::BusesLayout l;
        l.inputBuses.add (in);
        l.outputBuses.add (out);
        return l;
    };
    using S = juce::AudioChannelSet;
    CHECK (p.checkBusesLayoutSupported (layout (S::mono(), S::mono())));
    CHECK (p.checkBusesLayoutSupported (layout (S::stereo(), S::stereo())));
    CHECK (! p.checkBusesLayoutSupported (layout (S::mono(), S::stereo())));
    CHECK (! p.checkBusesLayoutSupported (layout (S::stereo(), S::mono())));
    CHECK (! p.checkBusesLayoutSupported (layout (S::create5point1(), S::create5point1())));
}

void testDryPathExact()
{
    currentTest = "dry path exact, zero latency";
    for (double fs : rates)
        for (int nch : { 1, 2 })
            for (int block : blockSizes)
            {
                Rig rig (fs, nch, block);
                CHECK (rig.proc.getLatencySamples() == 0);
                auto x = noise (nch, (int) (0.25 * fs), 11);
                x[0][0] = 1.0e-40f;      // denormal
                x[0][1] = -0.0f;         // negative zero
                x[0][100] = 1.0f;        // impulse: must appear at the same index
                auto y = rig.run (x, block);
                CHECK (bitIdentical (x, y));
            }
}

void testVariableBlocksAndBypass()
{
    currentTest = "variable blocks, bypass";
    Rig rig (48000.0, 2, 512);
    auto x = noise (2, 48000, 3);
    CHECK (bitIdentical (x, rig.run (x, 0)));
    CHECK (bitIdentical (x, rig.run (x, 64, true)));
    rig.set ("body", 0.25f);
    auto y = rig.run (x, 64, true); // bypass ignores BODY
    CHECK (bitIdentical (x, y));
}

void testBodyGainRamp()
{
    currentTest = "BODY gain ramp";
    Rig rig (48000.0, 1, 256);
    rig.set ("body", 0.5f);
    auto x = noise (1, 4800, 5);
    auto y = rig.run (x, 256);
    const int ramp = 960; // 20 ms
    float maxStep = 0.0f;
    for (int i = ramp + 1; i < 4800; ++i) CHECK (afterimage::exactly (y[0][(size_t) i], 0.5f * x[0][(size_t) i]));
    for (int i = 1; i < ramp; ++i)
        maxStep = std::max (maxStep, std::abs (y[0][(size_t) i] / (afterimage::exactly (x[0][(size_t) i], 0) ? 1 : x[0][(size_t) i])
                                               - y[0][(size_t) i - 1] / (afterimage::exactly (x[0][(size_t) i - 1], 0) ? 1 : x[0][(size_t) i - 1])));
    CHECK (maxStep < 1.0e-3f);
}

void testNonFinite()
{
    currentTest = "non-finite input";
    Rig rig (48000.0, 2, 64);
    auto x = noise (2, 4800, 9);
    auto ref = x;
    x[0][10] = std::numeric_limits<float>::quiet_NaN();
    x[1][20] = std::numeric_limits<float>::infinity();
    x[1][21] = -std::numeric_limits<float>::infinity();
    ref[0][10] = ref[1][20] = ref[1][21] = 0.0f;
    auto y = rig.run (x, 64);
    CHECK (bitIdentical (ref, y));
    CHECK (rig.proc.engine().nonFiniteInputs() == 3);
}

void testStateRestore()
{
    currentTest = "state restore";
    Rig a (48000.0, 2, 64);
    a.set ("body", 0.3f);
    a.set ("ghost", 0.8f);
    a.set ("memory_t60", 12.0f);
    a.set ("dissolve", 0.4f);
    a.set ("source", 1.0f);
    juce::MemoryBlock state;
    a.proc.getStateInformation (state);

    Rig b (48000.0, 2, 64);
    b.proc.setStateInformation (state.getData(), (int) state.getSize());
    for (auto* id : { "body", "ghost", "memory_t60", "dissolve", "source" })
        CHECK (std::abs (a.proc.apvts.getRawParameterValue (id)->load() - b.proc.apvts.getRawParameterValue (id)->load()) < 1.0e-6f);
    b.proc.setStateInformation ("garbage", 7); // malformed state is ignored
    CHECK (std::abs (b.proc.apvts.getRawParameterValue ("body")->load() - 0.3f) < 1.0e-6f);
}

void testTail()
{
    currentTest = "tail";
    AfterimageProcessor p;
    CHECK (p.getTailLengthSeconds() >= 50.0);
}

// ---------------------------------------------------------------------------------------------
// Engine-level tests (sample-stamped commands)
using afterimage::Command;
using afterimage::Engine;
using afterimage::Reject;
using afterimage::Source;
using Sig = std::vector<std::vector<float>>;

Sig sine (int nch, int n, double fs, double hz = 220.0, float amp = 0.5f)
{
    Sig x ((size_t) nch, std::vector<float> ((size_t) n));
    for (int c = 0; c < nch; ++c)
        for (int i = 0; i < n; ++i) x[(size_t) c][(size_t) i] = amp * (float) std::sin (2.0 * 3.141592653589793 * hz * i / fs + 0.3 * c);
    return x;
}

Command imprint (const Engine& e, int64_t at, int64_t s0, int64_t s1, Source src = Source::Full, double lo = 0, double hi = 0)
{
    Command c;
    c.epoch = e.epoch();
    c.at = at;
    c.s0 = s0;
    c.s1 = s1;
    c.source = src;
    c.lowHz = lo;
    c.highHz = hi;
    return c;
}

Command clearAt (int64_t at)
{
    Command c;
    c.type = Command::Type::Clear;
    c.at = at;
    return c;
}

/** Runs `x` through a fresh engine; returns the output. `setup` submits commands after prepare. */
template <typename Setup>
Sig runEngine (Engine& e, double fs, const Sig& x, afterimage::Params p, int block, Setup&& setup, double density = 0.0)
{
    const int nch = (int) x.size(), n = (int) x[0].size();
    e.prepare (fs, nch, 4096);
    if (density > 0) e.setDensityOverride (density);
    setup (e);
    auto y = x;
    std::mt19937 rng (3);
    for (int pos = 0; pos < n;)
    {
        const int b = std::min (block > 0 ? block : 1 + (int) (rng() % 700), n - pos);
        float* ptr[2] = { y[0].data() + pos, y[(size_t) nch - 1].data() + pos };
        e.process (ptr, nch, b, p);
        pos += b;
    }
    return y;
}

afterimage::Params ghostOnly (float d = 1.0f, float t60 = 5.0f) { return { 0.0f, 1.0f, t60, d }; }

bool allFinite (const Sig& y)
{
    for (auto& ch : y)
        for (auto v : ch)
            if (! std::isfinite (v)) return false;
    return true;
}

double rms (const float* x, int n)
{
    double s = 0;
    for (int i = 0; i < n; ++i) s += (double) x[i] * x[i];
    return std::sqrt (s / std::max (n, 1));
}

void testLoopPeriodAndSeam()
{
    currentTest = "loop period and seam";
    for (double fs : rates)
        for (auto src : { Source::Full, Source::Filtered })
            for (double dur : { 0.20, 0.75, 1.50 })
            {
                auto e = std::make_unique<Engine>();
                auto x = noise (2, (int) (4.0 * fs), 21);
                const auto s0 = (int64_t) (1.0 * fs), s1 = s0 + (int64_t) std::nearbyint (dur * fs);
                runEngine (*e, fs, x, ghostOnly(), 512, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (3.6 * fs), s0, s1, src, 0.0, fs / 2)); });
                const auto& c = e->lastCapture();
                CHECK (c.period == s1 - s0);
                CHECK (c.seam == (int64_t) std::nearbyint (0.08 * fs));
                const float* l0 = e->loopChannel (c.slot, 0);
                const auto R = c.period;
                if (src == Source::Full)
                {
                    CHECK (afterimage::exactly (l0[0], x[0][(size_t) s1]));         // wrap continues the recording
                    CHECK (afterimage::exactly (l0[R - 1], x[0][(size_t) s1 - 1]));
                }
                else // unmasked FILTERED reconstruction matches the audio within float error
                {
                    double err = 0, ref = 0;
                    for (int64_t i = c.seam; i < R; ++i)
                    {
                        err += std::pow (l0[i] - x[0][(size_t) (s0 + i)], 2.0);
                        ref += std::pow (x[0][(size_t) (s0 + i)], 2.0);
                    }
                    CHECK (10 * std::log10 (err / ref) <= -90.0);
                    CHECK (std::abs (l0[0] - x[0][(size_t) s1]) <= 1e-4f);
                }
            }
}

void testStartOfHistory()
{
    currentTest = "capture at start of history";
    for (double fs : rates)
        for (auto src : { Source::Full, Source::Filtered })
        {
            const int H = fs <= 48000 ? 1024 : 2048;
            for (int64_t s0 : { (int64_t) 0, (int64_t) 1, (int64_t) H - 1 })
            {
                auto e = std::make_unique<Engine>();
                auto x = sine (2, (int) (2.0 * fs), fs);
                const auto s1 = s0 + (int64_t) (0.5 * fs);
                auto y = runEngine (*e, fs, x, ghostOnly (0.5f), 256, [&] (Engine& en) { en.submit (imprint (en, s1, s0, s1, src, 0.0, fs / 2)); });
                CHECK (e->status.captures.load() == 1);
                CHECK (e->lastCapture().period == s1 - s0);
                CHECK (allFinite (y));
                CHECK (rms (y[0].data() + e->lastCapture().startedAt, (int) (0.3 * fs)) > 0.05);
            }
            auto e = std::make_unique<Engine>();
            runEngine (*e, fs, sine (2, (int) fs, fs), ghostOnly(), 256, [&] (Engine& en) { en.submit (imprint (en, 0, -1, (int64_t) (0.5 * fs), src, 0.0, fs / 2)); });
            CHECK (e->status.lastReject.load() == (int) Reject::BeforeStream);
            CHECK (e->status.captures.load() == 0);
        }
}

void testRejections()
{
    currentTest = "rejections";
    const double fs = 48000;
    const int n = (int) (8.0 * fs);
    auto x = noise (2, n, 5);
    const int64_t s0 = (int64_t) (6.5 * fs), s1 = s0 + (int64_t) (0.5 * fs);
    // reference: one capture that plays
    auto ref = std::make_unique<Engine>();
    auto yRef = runEngine (*ref, fs, x, ghostOnly(), 256, [&] (Engine& e) { e.submit (imprint (e, (int64_t) (7.0 * fs), s0, s1)); });
    struct Case { Reject code; std::function<Command (const Engine&)> make; };
    const int64_t at = (int64_t) (7.5 * fs);
    std::vector<Case> cases {
        { Reject::StaleEpoch, [&] (const Engine& e) { auto c = imprint (e, at, s0, s1); c.epoch += 1; return c; } },
        { Reject::TooShort, [&] (const Engine& e) { return imprint (e, at, s0, s0 + (int64_t) std::nearbyint (0.2 * fs) - 1); } },
        { Reject::TooLong, [&] (const Engine& e) { return imprint (e, at, s0 - (int64_t) fs, s0 - (int64_t) fs + (int64_t) std::nearbyint (1.5 * fs) + 1); } },
        { Reject::Future, [&] (const Engine& e) { return imprint (e, at, at - 1000, at + 20000); } },
        { Reject::InvalidBand, [&] (const Engine& e) { return imprint (e, at, s0, s1, Source::Filtered, 5000, 300); } },
        { Reject::InvalidBand, [&] (const Engine& e) { return imprint (e, at, s0, s1, Source::Filtered, 100, fs); } },
        { Reject::InvalidBand, [&] (const Engine& e) { return imprint (e, at, s0, s1, Source::Filtered, std::nan (""), 1000); } },
        { Reject::TooFewBins, [&] (const Engine& e) { return imprint (e, at, s0, s1, Source::Filtered, 20.0, 20.5); } },
        { Reject::Expired, [&] (const Engine& e) { return imprint (e, at, (int64_t) (0.5 * fs), (int64_t) (1.0 * fs)); } },
        { Reject::Expired, [&] (const Engine& e) { return imprint (e, at, (int64_t) (0.5 * fs), (int64_t) (1.0 * fs), Source::Filtered, 100, 5000); } },
    };
    for (auto& k : cases)
    {
        auto e = std::make_unique<Engine>();
        auto y = runEngine (*e, fs, x, ghostOnly(), 256, [&] (Engine& en) {
            en.submit (imprint (en, (int64_t) (7.0 * fs), s0, s1));
            en.submit (k.make (en));
        });
        CHECK (e->status.lastReject.load() == (int) k.code);
        CHECK (e->status.captures.load() == 1);
        CHECK (bitIdentical (y, yRef)); // the playing voice is untouched
    }
    // busy: a second IMPRINT while the first is still waiting or building
    auto e = std::make_unique<Engine>();
    runEngine (*e, fs, x, ghostOnly(), 256, [&] (Engine& en) {
        en.submit (imprint (en, (int64_t) (7.0 * fs), s0, s1));
        en.submit (imprint (en, (int64_t) (7.0 * fs) + 10, s0, s1));
    });
    CHECK (e->status.lastReject.load() == (int) Reject::Busy);
    CHECK (e->status.captures.load() == 1);
}

void testDeterminismAcrossBlocks()
{
    currentTest = "determinism across block sizes";
    for (double fs : { 44100.0, 96000.0 })
    {
        auto x = noise (2, (int) (5.0 * fs), 8);
        auto setup = [&] (Engine& e) {
            e.submit (imprint (e, (int64_t) (2.0 * fs), (int64_t) (1.0 * fs), (int64_t) (1.6 * fs), Source::Filtered, 200, 6000));
            e.submit (imprint (e, (int64_t) (3.0 * fs), (int64_t) (2.0 * fs), (int64_t) (2.5 * fs)));
            e.submit (clearAt ((int64_t) (4.2 * fs)));
        };
        afterimage::Params p { 0.7f, 0.8f, 3.0f, 0.5f };
        auto e0 = std::make_unique<Engine>();
        auto y0 = runEngine (*e0, fs, x, p, 1024, setup);
        CHECK (e0->status.captures.load() == 2);
        for (int block : { 1, 16, 32, 64, 0 })
        {
            auto e = std::make_unique<Engine>();
            CHECK (bitIdentical (y0, runEngine (*e, fs, x, p, block, setup)));
        }
    }
}

void testGrainCeiling()
{
    currentTest = "grain ceiling";
    const double fs = 48000;
    auto x = noise (2, (int) (6.0 * fs), 4);
    auto e = std::make_unique<Engine>();
    auto y = runEngine (*e, fs, x, ghostOnly(), 128, [&] (Engine& en) {
        en.submit (imprint (en, (int64_t) (2.0 * fs), (int64_t) (1.0 * fs), (int64_t) (1.8 * fs)));
        en.submit (imprint (en, (int64_t) (3.5 * fs), (int64_t) (2.5 * fs), (int64_t) (3.2 * fs)));
    }, 1000.0);
    CHECK (e->maxActiveGrains() == Engine::maxGrainsPerVoice);       // the stress density reaches the ceiling
    CHECK (e->maxActiveGrainsTotal() > Engine::maxGrainsPerVoice);   // REPLACE overlap
    CHECK (e->maxActiveGrainsTotal() <= Engine::numVoices * Engine::maxGrainsPerVoice);
    CHECK (allFinite (y));
}

/** Largest |second difference| of channel 0 in [a, b). */
double maxD2 (const Sig& y, int64_t a, int64_t b)
{
    double m = 0;
    for (int64_t i = std::max<int64_t> (a, 2); i < b; ++i)
        m = std::max (m, (double) std::abs (y[0][(size_t) i] - 2 * y[0][(size_t) i - 1] + y[0][(size_t) i - 2]));
    return m;
}

void testClearReplaceClicks()
{
    currentTest = "clear and replace clicks";
    for (double fs : rates)
        for (float d : { 0.0f, 1.0f })
        {
            const double limit = d == 0.0f ? 1.5 : 2.0;
            auto x = sine (2, (int) (6.0 * fs), fs);
            const auto ms = [&] (double v) { return (int64_t) (v * fs / 1000.0); };
            // REPLACE: second capture starts while the first plays
            auto e = std::make_unique<Engine>();
            auto y = runEngine (*e, fs, x, ghostOnly (d, 30.0f), 256, [&] (Engine& en) {
                en.submit (imprint (en, (int64_t) (1.5 * fs), (int64_t) (0.5 * fs), (int64_t) (1.2 * fs)));
                en.submit (imprint (en, (int64_t) (3.0 * fs), (int64_t) (2.0 * fs), (int64_t) (2.6 * fs)));
            });
            auto ev = e->lastCapture().startedAt;
            const double rRep = maxD2 (y, ev - ms (5), ev + ms (5)) / maxD2 (y, ev - ms (200), ev - ms (5));
            CHECK (rRep <= limit);
            // CLEAR
            auto e2 = std::make_unique<Engine>();
            const auto clearT = (int64_t) (3.0 * fs);
            auto y2 = runEngine (*e2, fs, x, ghostOnly (d, 30.0f), 256, [&] (Engine& en) {
                en.submit (imprint (en, (int64_t) (1.5 * fs), (int64_t) (0.5 * fs), (int64_t) (1.2 * fs)));
                en.submit (clearAt (clearT));
            });
            const double rClr = maxD2 (y2, clearT - ms (5), clearT + ms (5)) / maxD2 (y2, clearT - ms (200), clearT - ms (5));
            CHECK (rClr <= limit);
            std::printf ("    fs=%.0f D=%.0f: second-difference ratio REPLACE %.3f, CLEAR %.3f (limit %.1f)\n", fs, (double) d, rRep, rClr, limit);
            CHECK (afterimage::exactly (rms (y2[0].data() + clearT + ms (60), (int) ms (100)), 0.0)); // gone after the 50 ms fade
        }
}

void testRapidParameters()
{
    currentTest = "rapid parameter changes";
    const double fs = 48000;
    std::mt19937 rng (9);
    std::uniform_real_distribution<float> u (0.0f, 1.0f);
    // BODY only, DC input: the per-sample step never exceeds the 20 ms ramp slope
    Engine e;
    e.prepare (fs, 1, 64);
    std::vector<float> dc (64);
    float prev = 0.0f, maxStep = 0.0f;
    for (int b = 0; b < (int) (10.0 * fs / 64); ++b)
    {
        std::fill (dc.begin(), dc.end(), 0.5f);
        float* ptr[1] = { dc.data() };
        e.process (ptr, 1, 64, { u (rng), u (rng), 0.25f + 29.0f * u (rng), u (rng) });
        if (b == 0) prev = dc[0];
        for (float v : dc) { maxStep = std::max (maxStep, std::abs (v - prev)); prev = v; }
    }
    std::printf ("    max BODY step %.3g (ramp slope %.3g)\n", (double) maxStep, 0.5 / 960.0);
    CHECK (maxStep <= 0.5f / 960.0f * 1.0001f);
    // with a sounding ghost: finite and bounded
    auto x = noise (2, (int) (10.0 * fs), 2);
    Engine g;
    g.prepare (fs, 2, 64);
    g.submit (imprint (g, (int64_t) fs, (int64_t) (0.2 * fs), (int64_t) (0.9 * fs)));
    float peak = 0.0f;
    for (int pos = 0; pos + 64 <= (int) x[0].size(); pos += 64)
    {
        float* ptr[2] = { x[0].data() + pos, x[1].data() + pos };
        g.process (ptr, 2, 64, { u (rng), u (rng), 0.25f + 29.0f * u (rng), u (rng) });
        for (int i = 0; i < 64; ++i) peak = std::max ({ peak, std::abs (ptr[0][i]), std::abs (ptr[1][i]) });
    }
    CHECK (allFinite (x));
    CHECK (peak < 8.0f);
}

void testNonFiniteNeverStored()
{
    currentTest = "non-finite never stored";
    const double fs = 48000;
    auto x = sine (2, (int) (3.0 * fs), fs);
    for (int i = 0; i < 500; ++i) x[(size_t) (i % 2)][(size_t) (60000 + i)] = (i % 3 == 0) ? std::numeric_limits<float>::infinity() : std::nanf ("");
    for (auto src : { Source::Full, Source::Filtered })
    {
        Engine e;
        auto y = runEngine (e, fs, x, { 1.0f, 1.0f, 5.0f, 0.5f }, 256, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (2.0 * fs), 50000, 90000, src, 100, 8000)); });
        CHECK (e.status.captures.load() == 1);
        bool finiteLoop = true;
        for (int c = 0; c < 2; ++c)
            for (int64_t i = 0; i < e.lastCapture().period; ++i) finiteLoop &= std::isfinite (e.loopChannel (e.lastCapture().slot, c)[i]);
        CHECK (finiteLoop);
        CHECK (allFinite (y));
        CHECK (e.nonFiniteInputs() == 500);
    }
}

void testGainContract()
{
    currentTest = "gain contract";
    const double fs = 48000;
    auto x = noise (2, (int) (8.0 * fs), 12, 0.3f);
    for (float d : { 0.0f, 0.5f, 1.0f })
    {
        Engine e;
        auto y = runEngine (e, fs, x, ghostOnly (d, 30.0f), 256, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (2.0 * fs), (int64_t) (0.5 * fs), (int64_t) (1.5 * fs))); });
        const auto& c = e.lastCapture();
        // undo the MEMORY decay analytically, after the onset fade
        std::vector<float> flat;
        for (int64_t k = (int64_t) (0.1 * fs); k < (int64_t) (5.0 * fs); ++k)
            flat.push_back ((float) (y[0][(size_t) (c.startedAt + k)] / std::pow (10.0, -3.0 * (double) k / (30.0 * fs))));
        const double ratio = 20 * std::log10 (rms (flat.data(), (int) flat.size()) / rms (e.loopChannel (c.slot, 0), (int) c.period));
        CHECK (std::abs (ratio) <= (d == 0.0f ? 0.1 : d == 1.0f ? 1.5 : 1.0));
        std::printf ("    D=%.1f ghost RMS re loop: %+.3f dB\n", d, ratio);
    }
}

void testPostRollSeam()
{
    currentTest = "post-roll seam cases";
    const double fs = 48000;
    // continuing tone: rho close to 1; silent post-roll: rho 0 and the loop fades in
    auto x = sine (2, (int) (4.0 * fs), fs, 200.0);
    Engine a;
    runEngine (a, fs, x, ghostOnly(), 256, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (3.0 * fs), (int64_t) (1.0 * fs), (int64_t) (1.5 * fs))); });
    CHECK (a.lastCapture().rho > 0.9);
    auto s = x;
    for (auto& ch : s) std::fill (ch.begin() + (long) (1.5 * fs), ch.end(), 0.0f);
    Engine b;
    auto y = runEngine (b, fs, s, ghostOnly (0.0f), 256, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (3.0 * fs), (int64_t) (1.0 * fs), (int64_t) (1.5 * fs))); });
    CHECK (std::abs (b.lastCapture().rho) < 1e-9);
    CHECK (std::abs (b.loopChannel (b.lastCapture().slot, 0)[0]) == 0.0f);
    CHECK (allFinite (y));
    std::printf ("    rho: continuing tone %.4f, silent post-roll %.4f\n", a.lastCapture().rho, b.lastCapture().rho);
}

void testCaptureDelay()
{
    currentTest = "capture delay";
    for (double fs : rates)
        for (auto src : { Source::Full, Source::Filtered })
        {
            // worst case: a maximum-length selection ending at the newest sample
            Engine e;
            const auto at = (int64_t) (3.0 * fs);
            runEngine (e, fs, noise (2, (int) (4.0 * fs), 1), ghostOnly(), 256, [&] (Engine& en) {
                en.submit (imprint (en, at, at - (int64_t) std::nearbyint (1.5 * fs), at, src, 100, 8000)); });
            const auto d = e.lastCapture().startedAt - e.lastCapture().acceptedAt;
            CHECK (e.status.captures.load() == 1);
            CHECK (d < (int64_t) (0.5 * fs));
            std::printf ("    fs=%.0f %s: request-to-sound %.1f ms\n", fs, src == Source::Full ? "FULL    " : "FILTERED", 1000.0 * (double) d / fs);
        }
}

void testStateNeverImprints()
{
    currentTest = "state restore never imprints";
    Rig a (48000.0, 2, 256);
    juce::MemoryBlock state;
    a.proc.getStateInformation (state);
    Rig b (48000.0, 2, 256);
    b.run (noise (2, 48000, 1), 256);
    b.proc.setStateInformation (state.getData(), (int) state.getSize());
    b.run (noise (2, 96000, 2), 256);
    CHECK (b.proc.engine().status.captures.load() == 0);
    CHECK (b.proc.engine().status.voices.load() == 0);
    CHECK (b.proc.engine().captureState() == afterimage::CaptureState::Idle);
}

void testBypassResumesGhostFromZero()
{
    currentTest = "bypass resume";
    Rig rig (48000.0, 2, 256);
    rig.set ("body", 0.0f);
    rig.set ("ghost", 1.0f);
    rig.set ("dissolve", 0.0f);
    rig.set ("memory_t60", 30.0f); // 1.5 s of bypass and play = 3 dB of decay
    auto x = sine (2, (int) (2.0 * 48000), 48000.0);
    afterimage::Command c;
    c.epoch = rig.proc.engine().epoch();
    c.s0 = 10000;
    c.s1 = 40000;
    rig.run (x, 256);
    rig.proc.postCommand (c);
    auto silent = Sig (2, std::vector<float> (48000, 0.0f));
    auto playing = rig.run (silent, 256);
    CHECK (rig.proc.engine().status.voices.load() == 1);
    auto byp = rig.run (silent, 256, true);
    CHECK (bitIdentical (byp, silent));
    auto resumed = rig.run (Sig (2, std::vector<float> (4800, 0.0f)), 256);
    const double steady = rms (playing[0].data() + 24000, 4800);
    const double after = rms (resumed[0].data() + 2400, 960);
    std::printf ("    steady %.5f, first resumed sample %.6f, resumed after 50 ms %.5f\n", steady, (double) resumed[0][0], after);
    CHECK (std::abs (resumed[0][0]) <= 0.01 * steady * 4);
    CHECK (after > 0.5 * steady * 0.5);
}

void testNoDenormalsAfterDecay()
{
    currentTest = "denormals after decay";
    Rig rig (48000.0, 2, 512);
    rig.set ("memory_t60", 0.25f);
    auto x = noise (2, 48000, 6, 0.5f);
    rig.run (x, 512);
    afterimage::Command c;
    c.epoch = rig.proc.engine().epoch();
    c.s0 = 10000;
    c.s1 = 30000;
    rig.proc.postCommand (c);
    auto y = rig.run (Sig (2, std::vector<float> ((size_t) (60 * 48000), 0.0f)), 512);
    int denormals = 0;
    for (auto& ch : y)
        for (float v : ch) denormals += std::fpclassify (v) == FP_SUBNORMAL;
    CHECK (rig.proc.engine().status.captures.load() == 1);
    CHECK (denormals == 0);
    CHECK (rig.proc.engine().status.voices.load() == 0);
}

const char* snapshotPath = nullptr;

void testEditor()
{
    currentTest = "development editor";
    Rig rig (48000.0, 2, 512);
    rig.set ("body", 0.8f);
    rig.set ("ghost", 1.0f);
    rig.set ("dissolve", 0.6f);
    std::unique_ptr<AfterimageEditor> ed (dynamic_cast<AfterimageEditor*> (rig.proc.createEditor()));
    CHECK (ed != nullptr);
    if (ed == nullptr) return;

    auto x = sine (2, 3 * 48000, 48000.0, 330.0, 0.3f);
    auto n = noise (2, 3 * 48000, 4, 0.1f);
    for (int c = 0; c < 2; ++c)
        for (size_t i = 0; i < x[0].size(); ++i) x[(size_t) c][i] += n[(size_t) c][i];
    rig.run (x, 512);
    ed->refreshNow();
    CHECK (ed->statusText().contains ("CAPTURE  IDLE"));
    CHECK (ed->statusText().contains ("last capture  none"));

    // a rejected selection shows its code
    ed->select (100, 200, 100, 5000); // 2 ms: too short
    ed->pressImprint();
    rig.run (noise (2, 4800, 5, 0.1f), 512);
    ed->refreshNow();
    CHECK (ed->statusText().contains ("TOO_SHORT"));

    // a valid FILTERED selection: status shows the capture the engine actually made
    rig.set ("source", 1.0f);
    ed->select (48000, 84000, 200, 4000);
    ed->pressImprint();
    rig.run (x, 512);
    ed->refreshNow();
    CHECK (ed->statusText().contains ("voices 1"));
    CHECK (ed->statusText().contains ("FILTERED, selected 750.0 ms, loop period 750.0 ms (36000 samples)"));

    // polled attachment: an off-thread change reaches the control only on the next poll
    const double before = ed->knobValue (0);
    std::thread t ([&] { auto* p = rig.proc.apvts.getParameter ("body"); p->setValueNotifyingHost (0.25f); });
    t.join();
    CHECK (afterimage::exactly (ed->knobValue (0), before));
    ed->refreshNow();
    CHECK (std::abs (ed->knobValue (0) - 0.25) < 1e-6);

    if (snapshotPath != nullptr)
    {
        // a capture inside the visible 4 s (magenta) and a pending selection (violet), on real engine data
        rig.set ("source", 0.0f);
        const auto now = rig.proc.engine().samplesSeen();
        ed->select (now - 96000, now - 60000, 20, 24000);
        ed->pressImprint();
        rig.run (sine (2, 24000, 48000.0, 220.0, 0.2f), 512);
        ed->refreshNow();
        const auto now2 = rig.proc.engine().samplesSeen();
        ed->select (now2 - 40000, now2 - 12000, 250, 2500);
        ed->refreshNow();
        auto img = ed->createComponentSnapshot (ed->getLocalBounds(), true, 1.0f);
        juce::File f (snapshotPath);
        f.deleteFile();
        juce::FileOutputStream os (f);
        CHECK (juce::PNGImageFormat().writeImageToStream (img, os));
    }
}

void testSpectrogramMapping()
{
    currentTest = "spectrogram time mapping";
    Rig rig (48000.0, 2, 512);
    std::unique_ptr<AfterimageEditor> ed (dynamic_cast<AfterimageEditor*> (rig.proc.createEditor()));
    rig.run (noise (2, 48000, 1, 0.1f), 512);
    ed->refreshNow();
    rig.run (noise (2, 15 * 48000, 2, 0.1f), 512); // nobody reads: the display FIFO fills and drops columns
    ed->refreshNow();
    rig.run (noise (2, 48000, 3, 0.1f), 512);
    ed->refreshNow();
    auto& v = ed->view();
    const int H = rig.proc.engine().hop();
    bool gap = false;
    double worstSample = 0, worstX = 0;
    for (size_t i = 0; i < v.numColumns(); ++i)
    {
        if (i > 0) gap |= v.centre (i) - v.centre (i - 1) > H;
        worstSample = std::max (worstSample, (double) std::abs (v.sampleAtX (v.columnX (i)) - v.centre (i)));
        worstX = std::max (worstX, (double) std::abs (v.xForSample (v.centre (i)) - v.columnX (i)));
    }
    CHECK (gap); // the scenario really has a time gap
    CHECK (worstSample <= 1.0);
    CHECK (worstX <= 0.01);
    std::printf ("    %zu columns with a gap; worst x->sample %.0f samples, sample->x %.4f px\n", v.numColumns(), worstSample, worstX);
}

void testSilentAndTransientCaptures()
{
    currentTest = "silent and transient captures";
    for (double fs : { 48000.0, 96000.0 })
        for (auto src : { Source::Full, Source::Filtered })
        {
            // digital silence: plays, exactly zero, finite
            Engine e;
            auto y = runEngine (e, fs, Sig (2, std::vector<float> ((size_t) (3.0 * fs), 0.0f)), ghostOnly (0.5f), 256,
                                [&] (Engine& en) { en.submit (imprint (en, (int64_t) (2.0 * fs), (int64_t) (0.5 * fs), (int64_t) (1.2 * fs), src, 100, 8000)); });
            CHECK (e.status.captures.load() == 1);
            CHECK (afterimage::exactly (e.lastCapture().rho, 0.0));
            CHECK (allFinite (y));
            bool zero = true;
            for (auto& ch : y) for (float v : ch) zero &= afterimage::exactly (v, 0.0);
            CHECK (zero);

            // an impulse inside the selection: TRACE repeats it exactly once per period
            Sig x (2, std::vector<float> ((size_t) (5.0 * fs), 0.0f));
            const auto s0 = (int64_t) (1.0 * fs), s1 = s0 + (int64_t) (0.5 * fs), at = s0 + (int64_t) (0.2 * fs);
            x[0][(size_t) at] = x[1][(size_t) at] = 0.9f;
            Engine t;
            auto z = runEngine (t, fs, x, ghostOnly (0.0f, 30.0f), 256, [&] (Engine& en) { en.submit (imprint (en, (int64_t) (2.0 * fs), s0, s1, src, 20, fs / 2)); });
            const auto start = t.lastCapture().startedAt, R = t.lastCapture().period;
            std::vector<int64_t> peaks;
            for (int k = 0; k < 4; ++k)
            {
                int64_t best = 0;
                for (int64_t i = 0; i < R; ++i)
                    if (std::abs (z[0][(size_t) (start + k * R + i)]) > std::abs (z[0][(size_t) (start + k * R + best)])) best = i;
                peaks.push_back (best);
            }
            CHECK (peaks[1] == peaks[0] && peaks[2] == peaks[0] && peaks[3] == peaks[0]);
            CHECK (peaks[0] == at - s0);
            CHECK (allFinite (z));
        }
}

// ---- allocation gate on the audio thread (juce-plugin skill: host-automation-and-editor-sync) ----
using MallocLogger = void (uint32_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t, uint32_t);
extern "C" MallocLogger* malloc_logger;
std::atomic<pthread_t> watched { nullptr };
std::atomic<int> watchedAllocs { 0 };
void countAllocs (uint32_t type, uintptr_t, uintptr_t, uintptr_t, uintptr_t, uint32_t)
{
    if ((type & 2) != 0 && pthread_equal (pthread_self(), watched.load())) watchedAllocs.fetch_add (1); // 2 = allocation
}

/** Runs `blocks` processBlock calls on a separate thread, which also automates every parameter like a host,
    and counts that thread's allocations while it does so. */
int allocationsOnAudioThread (Rig& rig, int blocks, bool positiveControl)
{
    int result = -1;
    std::thread audio ([&] {
        juce::AudioBuffer<float> buf (2, 64);
        juce::MidiBuffer midi;
        std::vector<juce::RangedAudioParameter*> params;
        for (auto* id : { "body", "ghost", "memory_t60", "dissolve", "source" })
            params.push_back (dynamic_cast<juce::RangedAudioParameter*> (rig.proc.apvts.getParameter (id)));
        std::mt19937 rng (4);
        std::uniform_real_distribution<float> u (0.0f, 1.0f);
        std::vector<float> noiseBlock (64);
        for (auto& v : noiseBlock) v = u (rng) - 0.5f; // prepared before counting starts
        watchedAllocs = 0;
        watched = pthread_self();
        malloc_logger = countAllocs;
        if (positiveControl)
        {
            void* volatile p = std::malloc (64); // volatile: the compiler may not elide the pair
            std::free (p);
        }
        for (int b = 0; b < blocks; ++b)
        {
            for (int c = 0; c < 2; ++c) buf.copyFrom (c, 0, noiseBlock.data(), 64);
            if (b % 50 == 0) params[(size_t) (b / 50) % params.size()]->setValueNotifyingHost (u (rng)); // host automation
            rig.proc.processBlock (buf, midi);
        }
        malloc_logger = nullptr;
        watched = nullptr;
        result = watchedAllocs.load();
    });
    audio.join();
    return result;
}

void testNoAllocationsInCallback()
{
    currentTest = "no allocations on the audio thread";
    Rig rig (48000.0, 2, 64);
    rig.run (noise (2, 3 * 48000, 1, 0.2f), 64);
    // captures, a REPLACE and a CLEAR fall inside the counted window
    for (int k = 0; k < 3; ++k)
    {
        afterimage::Command c;
        c.epoch = rig.proc.engine().epoch();
        c.s0 = 20000 + k * 1000;
        c.s1 = c.s0 + 30000;
        c.source = k == 1 ? afterimage::Source::Filtered : afterimage::Source::Full;
        c.lowHz = 100;
        c.highHz = 8000;
        rig.proc.postCommand (c);
    }
    afterimage::Command clear;
    clear.type = afterimage::Command::Type::Clear;
    CHECK (allocationsOnAudioThread (rig, 1, true) >= 1); // positive control: the counter sees a malloc
    const int closed = allocationsOnAudioThread (rig, 3000, false);
    rig.proc.postCommand (clear);
    std::unique_ptr<juce::AudioProcessorEditor> ed (rig.proc.createEditor());
    const int open = allocationsOnAudioThread (rig, 3000, false);
    std::printf ("    allocations on the audio thread: editor closed %d, editor open %d (3000 blocks each, with automation)\n", closed, open);
    CHECK (rig.proc.engine().status.captures.load() >= 1);
    CHECK (closed == 0);
    CHECK (open == 0);
}

// =============================================================================================
// P1-B Stage B: MANUAL and HOLD (docs/P1-B-QUALIFICATION.md 1.2)
using afterimage::Mode;
using afterimage::Origin;
using afterimage::Outcome;
using afterimage::RequestRecord;

constexpr float lengthsSec[] = { 0.25f, 0.5f, 0.75f, 1.0f, 1.5f };

Command triggerAt (int64_t at, Origin o = Origin::Button)
{
    Command c;
    c.type = Command::Type::Trigger;
    c.origin = o;
    c.at = at;
    return c;
}

/** Engine run where parameters may change at block boundaries: paramsAt (blockStart) -> Params. */
template <typename Setup, typename ParamsAt>
Sig runEngineVar (Engine& e, double fs, const Sig& x, int block, Setup&& setup, ParamsAt&& paramsAt)
{
    const int nch = (int) x.size(), n = (int) x[0].size();
    e.prepare (fs, nch, 4096);
    setup (e);
    auto y = x;
    std::mt19937 rng (3);
    for (int pos = 0; pos < n;)
    {
        const int b = std::min (block > 0 ? block : 1 + (int) (rng() % 700), n - pos);
        float* ptr[2] = { y[0].data() + pos, y[(size_t) nch - 1].data() + pos };
        e.process (ptr, nch, b, paramsAt ((int64_t) pos));
        pos += b;
    }
    return y;
}

int count (const std::vector<RequestRecord>& log, int n, Origin o, Outcome out)
{
    int k = 0;
    for (int i = 0; i < n; ++i) k += log[(size_t) i].origin == o && log[(size_t) i].outcome == out;
    return k;
}

void testManualExactness()
{
    currentTest = "B3 MANUAL selection exactness (engine)";
    for (double fs : rates)
        for (float L : lengthsSec)
        {
            Engine e;
            std::vector<RequestRecord> log (16);
            const auto at = (int64_t) (2.0 * fs) + 37;
            afterimage::Params p = ghostOnly();
            p.lengthSeconds = L;
            runEngine (e, fs, noise (2, (int) (3.5 * fs), 2), p, 256, [&] (Engine& en) {
                en.setRequestLog (log.data(), 16);
                en.submit (triggerAt (at));
            });
            CHECK (e.requestLogCount() == 1);
            CHECK (log[0].s1 == at);
            CHECK (log[0].s0 == at - (int64_t) std::nearbyint ((double) L * fs));
            CHECK (log[0].outcome == Outcome::Completed);
            CHECK (e.lastCapture().period == log[0].s1 - log[0].s0);
        }
    // not enough audio yet: refused, never shortened
    Engine e;
    std::vector<RequestRecord> log (4);
    afterimage::Params p = ghostOnly();
    p.lengthSeconds = 1.0f;
    runEngine (e, 48000.0, noise (2, 48000, 1), p, 256, [&] (Engine& en) { en.setRequestLog (log.data(), 4); en.submit (triggerAt (30000)); });
    CHECK (log[0].outcome == Outcome::Rejected && log[0].reject == Reject::BeforeStream);
    CHECK (e.status.captures.load() == 0);
}

/** One processor block with MIDI events (sample offset, message). */
void blockWithMidi (Rig& rig, const std::vector<float>& in, int offsetInSig, int block, const std::vector<std::pair<int, juce::MidiMessage>>& events,
                    bool bypassed = false)
{
    juce::AudioBuffer<float> buf (rig.nch, block);
    for (int c = 0; c < rig.nch; ++c) buf.copyFrom (c, 0, in.data() + offsetInSig, block);
    juce::MidiBuffer midi;
    for (auto& [o, m] : events) midi.addEvent (m, o);
    if (bypassed) rig.proc.processBlockBypassed (buf, midi);
    else rig.proc.processBlock (buf, midi);
}

void testTriggerOrigins()
{
    currentTest = "B3 MIDI and automation triggers (processor)";
    for (int block : { 64, 512 })
    {
        Rig rig (48000.0, 2, block);
        std::vector<RequestRecord> log (64);
        rig.proc.engine().setRequestLog (log.data(), 64);
        auto x = noise (2, 60 * 48000, 4, 0.3f);
        int pos = 0;
        auto runFor = [&] (double seconds) {
            for (int k = 0; k < (int) (seconds * 48000) / block; ++k, pos += block) blockWithMidi (rig, x[0], pos, block, {});
        };
        runFor (2.0);
        int expected = 0;
        for (int offset : { 0, 1, 17, block - 1 })
            for (int kind = 0; kind < 2; ++kind)
            {
                const auto start = rig.proc.engine().samplesSeen();
                const auto msg = kind == 0 ? juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100) : juce::MidiMessage::controllerEvent (1, 64, 127);
                blockWithMidi (rig, x[0], pos, block, { { offset, msg } });
                pos += block;
                ++expected;
                const auto& r = log[(size_t) rig.proc.engine().requestLogCount() - 1];
                CHECK (rig.proc.engine().requestLogCount() == expected);
                CHECK (r.origin == Origin::Midi && r.s1 == start + offset && r.s0 == r.s1 - 36000);
                if (kind == 1) blockWithMidi (rig, x[0], pos, block, { { 0, juce::MidiMessage::controllerEvent (1, 64, 0) } }), pos += block;
                runFor (0.6);
            }
        // a note-off, a second note in the same block, and CC 64 staying down never add a capture
        const int before = rig.proc.engine().requestLogCount();
        blockWithMidi (rig, x[0], pos, block, { { 0, juce::MidiMessage::controllerEvent (1, 64, 100) }, { 1, juce::MidiMessage::controllerEvent (1, 64, 120) },
                                                { 2, juce::MidiMessage::noteOn (1, 62, (juce::uint8) 90) }, { 3, juce::MidiMessage::noteOff (1, 62) } });
        pos += block;
        CHECK (count (log, rig.proc.engine().requestLogCount(), Origin::Midi, Outcome::DroppedRate) == 1); // the note in the same block
        CHECK (rig.proc.engine().requestLogCount() == before + 2);
        runFor (0.6);
        // automation: rising edge at block start
        const auto start = rig.proc.engine().samplesSeen();
        rig.set ("imprint", 1.0f);
        runFor (0.6);
        const auto& r = log[(size_t) rig.proc.engine().requestLogCount() - 1];
        CHECK (r.origin == Origin::Automation && r.s1 == start);
    }
}

int automationRequests (Rig& rig, std::vector<RequestRecord>& log)
{
    int k = 0;
    for (int i = 0; i < rig.proc.engine().requestLogCount(); ++i) k += log[(size_t) i].origin == Origin::Automation;
    return k;
}

void testAutomationEdges()
{
    currentTest = "B4 automation trigger edges";
    std::vector<RequestRecord> log (64);
    {
        Rig rig (48000.0, 2, 128);
        rig.proc.engine().setRequestLog (log.data(), 64);
        rig.run (noise (2, 96000, 1), 128);
        rig.set ("imprint", 1.0f);
        rig.run (noise (2, 100 * 128, 2), 128); // held on for 100 blocks
        CHECK (automationRequests (rig, log) == 1);
        rig.set ("imprint", 0.0f);
        rig.run (noise (2, 128, 3), 128);
        rig.set ("imprint", 1.0f); // a one-block pulse
        rig.run (noise (2, 128, 3), 128);
        rig.set ("imprint", 0.0f);
        rig.run (noise (2, 48000, 3), 128);
        CHECK (automationRequests (rig, log) == 2);

        // "on" saved in the state and restored: never an edge
        rig.set ("imprint", 1.0f);
        juce::MemoryBlock state;
        rig.proc.getStateInformation (state);
        Rig other (48000.0, 2, 128);
        std::vector<RequestRecord> log2 (16);
        other.proc.engine().setRequestLog (log2.data(), 16);
        other.run (noise (2, 96000, 4), 128);
        other.proc.setStateInformation (state.getData(), (int) state.getSize());
        other.run (noise (2, 48000, 5), 128);
        CHECK (automationRequests (other, log2) == 0);
        CHECK (other.proc.apvts.getRawParameterValue ("imprint")->load() > 0.5f);
    }
    {
        // "on" across prepareToPlay (rate change): never an edge
        Rig rig (48000.0, 2, 128);
        rig.set ("imprint", 1.0f);
        rig.run (noise (2, 48000, 1), 128);
        rig.proc.prepareToPlay (96000.0, 64);
        rig.proc.engine().setRequestLog (log.data(), 64);
        rig.run (noise (2, 96000, 2), 64);
        CHECK (automationRequests (rig, log) == 0);
    }
    {
        // turned on while bypassed: ignored, and no capture after resume
        Rig rig (48000.0, 2, 128);
        rig.proc.engine().setRequestLog (log.data(), 64);
        rig.run (noise (2, 96000, 1), 128);
        rig.set ("imprint", 1.0f);
        rig.run (noise (2, 1280, 2), 128, true);
        rig.run (noise (2, 48000, 3), 128);
        CHECK (rig.proc.engine().status.captures.load() == 0);
        CHECK (count (log, rig.proc.engine().requestLogCount(), Origin::Automation, Outcome::IgnoredBypass) == 1);
    }
}

afterimage::Params sched (Mode m, bool hold = false, float interval = 1.0f, float gate = -60.0f)
{
    afterimage::Params p = ghostOnly (1.0f, 5.0f);
    p.mode = m;
    p.hold = hold;
    p.randomIntervalSeconds = interval;
    p.gateDb = gate;
    return p;
}

void testHold()
{
    currentTest = "B5 HOLD";
    const double fs = 48000;
    auto x = noise (2, (int) (22.0 * fs), 7, 0.3f);
    std::vector<RequestRecord> log (512);
    {   // (a) HOLD before any ghost: no automatic capture; MANUAL still works
        Engine e;
        runEngine (e, fs, x, sched (Mode::Random, true), 256, [&] (Engine& en) {
            en.setRequestLog (log.data(), 512);
            en.submit (triggerAt ((int64_t) (12.0 * fs)));
        });
        const int n = e.requestLogCount();
        CHECK (count (log, n, Origin::Random, Outcome::Completed) + count (log, n, Origin::Random, Outcome::Accepted) == 0);
        CHECK (count (log, n, Origin::Random, Outcome::SuppressedHold) >= 15);
        CHECK (count (log, n, Origin::Button, Outcome::Completed) == 1);
    }
    {   // (b) HOLD with a ghost keeps it; (c) explicit IMPRINT replaces it under HOLD
        Engine e;
        runEngineVar (e, fs, x, 256, [&] (Engine& en) {
            en.setRequestLog (log.data(), 512);
            en.submit (triggerAt ((int64_t) (1.5 * fs)));
            en.submit (triggerAt ((int64_t) (15.0 * fs)));
        }, [&] (int64_t pos) { return sched (pos < (int64_t) (1.0 * fs) ? Mode::Manual : Mode::Random, true); });
        const int n = e.requestLogCount();
        CHECK (count (log, n, Origin::Random, Outcome::Completed) == 0);
        CHECK (count (log, n, Origin::Button, Outcome::Completed) == 2);
        CHECK (e.status.captures.load() == 2);
        CHECK (e.lastCapture().s1 == (int64_t) (15.0 * fs));
    }
    {   // (d) 100 toggles at random block boundaries: no RANDOM capture within 0.75 * interval of a release
        Engine e;
        std::mt19937 rng (11);
        std::vector<int64_t> toggles;
        for (int k = 0; k < 100; ++k) toggles.push_back ((int64_t) (0.5 * fs) + (int64_t) (rng() % (uint32_t) (10.0 * fs)));
        std::sort (toggles.begin(), toggles.end());
        auto holdAt = [&] (int64_t pos) { return (std::upper_bound (toggles.begin(), toggles.end(), pos) - toggles.begin()) % 2 == 1; };
        std::vector<int64_t> releases;
        bool prev = false;
        auto y = runEngineVar (e, fs, x, 128, [&] (Engine& en) { en.setRequestLog (log.data(), 512); }, [&] (int64_t pos) {
            const bool h = holdAt (pos);
            if (prev && ! h) releases.push_back (pos);
            prev = h;
            return sched (Mode::Random, h, 1.0f);
        });
        CHECK (allFinite (y));
        bool ok = true;
        for (int i = 0; i < e.requestLogCount(); ++i)
            if (log[(size_t) i].origin == Origin::Random && (log[(size_t) i].outcome == Outcome::Accepted || log[(size_t) i].outcome == Outcome::Completed))
                for (auto t : releases)
                    if (log[(size_t) i].at >= t && log[(size_t) i].at < t + (int64_t) (0.75 * fs)) ok = false;
        CHECK (ok);
        CHECK (releases.size() >= 40);
    }
    {   // (e) the held ghost still retires with MEMORY
        Engine e;
        afterimage::Params p = sched (Mode::Random, true);
        p.t60 = 0.5f;
        runEngine (e, fs, noise (2, (int) (5.0 * fs), 2, 0.3f), p, 256, [&] (Engine& en) { en.submit (triggerAt ((int64_t) (1.0 * fs))); });
        CHECK (e.status.captures.load() == 1);
        CHECK (e.status.voices.load() == 0); // 0.5 s T60 falls 100 dB in 0.83 s
    }
}

void testBusy()
{
    currentTest = "B6 busy";
    const double fs = 48000;
    Engine e;
    std::vector<RequestRecord> log (256);
    afterimage::Params p = ghostOnly();
    p.source = Source::Filtered; // the longest build
    runEngine (e, fs, noise (2, (int) (5.0 * fs), 2), p, 64, [&] (Engine& en) {
        en.setRequestLog (log.data(), 256);
        for (int k = 0; k < 16; ++k) en.submit (triggerAt ((int64_t) (1.0 * fs) + (int64_t) (k * 0.02 * fs)));
    });
    int accepted = 0, busy = 0;
    int64_t lastAccepted = -1000000;
    bool spaced = true;
    for (int i = 0; i < e.requestLogCount(); ++i)
    {
        const auto& r = log[(size_t) i];
        if (r.outcome == Outcome::Completed || r.outcome == Outcome::Accepted)
        {
            spaced &= r.at - lastAccepted >= (int64_t) (0.2 * fs); // a FILTERED build takes > 0.2 s
            lastAccepted = r.at;
            ++accepted;
        }
        busy += r.outcome == Outcome::Rejected && r.reject == Reject::Busy;
    }
    CHECK (e.requestLogCount() == 16);
    CHECK (accepted >= 1 && accepted <= 2);
    CHECK (busy == 16 - accepted);
    CHECK (spaced);
}

void testBypassIgnoresTriggers()
{
    currentTest = "B7 bypass ignores triggers";
    Rig rig (48000.0, 2, 128);
    std::vector<RequestRecord> log (32);
    rig.proc.engine().setRequestLog (log.data(), 32);
    auto x = noise (2, 4 * 48000, 1, 0.3f);
    int pos = 0;
    for (; pos < 96000; pos += 128) blockWithMidi (rig, x[0], pos, 128, {});
    afterimage::Command c;
    c.type = afterimage::Command::Type::Trigger;
    c.origin = Origin::Button;
    rig.proc.postCommand (c);
    rig.set ("imprint", 1.0f);
    blockWithMidi (rig, x[0], pos, 128, { { 5, juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100) } }, true);
    pos += 128;
    for (; pos < 4 * 48000 - 128; pos += 128) blockWithMidi (rig, x[0], pos, 128, {});
    const int n = rig.proc.engine().requestLogCount();
    CHECK (rig.proc.engine().status.captures.load() == 0);
    CHECK (count (log, n, Origin::Button, Outcome::IgnoredBypass) == 1);
    CHECK (count (log, n, Origin::Midi, Outcome::IgnoredBypass) == 1);
    CHECK (count (log, n, Origin::Automation, Outcome::IgnoredBypass) == 1);
    CHECK (n == 3);
}

void testAutomaticReplacementAudio()
{
    currentTest = "B8 automatic replacements, BODY, mode switching";
    const double fs = 48000;
    const auto ms = [&] (double v) { return (int64_t) (v * fs / 1000.0); };
    for (float d : { 0.0f, 1.0f })
    {
        Engine e;
        std::vector<RequestRecord> log (256);
        afterimage::Params p = sched (Mode::Random, false, 1.0f);
        p.dissolve = d;
        p.t60 = 30.0f;
        auto y = runEngine (e, fs, sine (2, (int) (12.0 * fs), fs), p, 256, [&] (Engine& en) { en.setRequestLog (log.data(), 256); });
        double worst = 0;
        int replacements = 0;
        bool first = true;
        for (int i = 0; i < e.requestLogCount(); ++i)
            if (log[(size_t) i].outcome == Outcome::Completed)
            {
                if (std::exchange (first, false)) continue; // the first ghost replaces nothing
                const auto ev = log[(size_t) i].startedAt;
                worst = std::max (worst, maxD2 (y, ev - ms (5), ev + ms (5)) / maxD2 (y, ev - ms (200), ev - ms (5)));
                ++replacements;
            }
        CHECK (replacements >= 6);
        CHECK (worst <= (d == 0.0f ? 1.5 : 2.0));
        CHECK (allFinite (y));
        std::printf ("    RANDOM replacements at D=%.0f: %d, worst second-difference ratio %.3f\n", (double) d, replacements, worst);
    }
    {   // BODY untouched in RANDOM mode when the input never reaches the gate
        Engine e;
        afterimage::Params p = sched (Mode::Random, false, 1.0f, -48.0f);
        p.body = 1.0f;
        p.ghost = 0.5f;
        auto quiet = noise (2, (int) (8.0 * fs), 3, 1.0e-4f);
        CHECK (bitIdentical (quiet, runEngine (e, fs, quiet, p, 256, [] (Engine&) {})));
        CHECK (e.status.captures.load() == 0);
    }
    {   // mode switched every 0.5 s for 20 s, then MANUAL: finite, and every voice retires on time
        Engine e;
        auto y = runEngineVar (e, fs, noise (2, (int) (23.0 * fs), 9, 0.3f), 256, [&] (Engine& en) {
            for (int k = 0; k < 10; ++k) en.submit (triggerAt ((int64_t) ((1.0 + 2.0 * k) * fs)));
        }, [&] (int64_t pos) {
            const auto m = pos < (int64_t) (20.0 * fs) ? (Mode) ((pos / (int64_t) (0.5 * fs)) % 3) : Mode::Manual;
            afterimage::Params p = sched (m, false, 1.0f);
            p.t60 = 1.0f; // 100 dB in 1.67 s
            return p;
        });
        CHECK (allFinite (y));
        CHECK (e.status.captures.load() >= 10);
        CHECK (e.status.voices.load() == 0);
    }
}

void testNoAllocationsWithTriggers()
{
    currentTest = "B9 no allocations with triggers and RANDOM";
    Rig rig (48000.0, 2, 64);
    rig.set ("capture_mode", 1.0f); // RANDOM
    rig.set ("random_interval", 1.0f);
    rig.set ("activity_gate", -72.0f);
    rig.run (noise (2, 3 * 48000, 1, 0.2f), 64);
    auto runCounted = [&] (int blocks) {
        int result = -1;
        std::thread audio ([&] {
            juce::AudioBuffer<float> buf (2, 64);
            juce::MidiBuffer midi, empty;
            midi.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 10);
            auto* imprint = rig.proc.apvts.getParameter ("imprint");
            auto* hold = rig.proc.apvts.getParameter ("hold");
            std::vector<float> blockNoise (64, 0.1f);
            for (int i = 0; i < 64; ++i) blockNoise[(size_t) i] = 0.2f * (float) std::sin (0.3 * i);
            watchedAllocs = 0;
            watched = pthread_self();
            malloc_logger = countAllocs;
            for (int b = 0; b < blocks; ++b)
            {
                for (int c = 0; c < 2; ++c) buf.copyFrom (c, 0, blockNoise.data(), 64);
                if (b % 60 == 0) imprint->setValueNotifyingHost (imprint->getValue() > 0.5f ? 0.0f : 1.0f);
                if (b % 400 == 0) hold->setValueNotifyingHost (hold->getValue() > 0.5f ? 0.0f : 1.0f);
                rig.proc.processBlock (buf, b % 40 == 0 ? midi : empty);
            }
            malloc_logger = nullptr;
            watched = nullptr;
            result = watchedAllocs.load();
        });
        audio.join();
        return result;
    };
    const int closed = runCounted (4000);
    std::unique_ptr<juce::AudioProcessorEditor> ed (rig.proc.createEditor());
    const int open = runCounted (4000);
    std::printf ("    allocations: editor closed %d, open %d (4000 blocks each: MIDI, automation trigger, HOLD toggles, RANDOM)\n", closed, open);
    CHECK (rig.proc.engine().status.captures.load() >= 2);
    CHECK (closed == 0 && open == 0);
}

void testEditorLifecycle()
{
    currentTest = "B10 editor lifecycle during captures";
    Rig rig (48000.0, 2, 256);
    rig.set ("capture_mode", 1.0f);
    rig.set ("random_interval", 1.0f);
    rig.set ("activity_gate", -72.0f);
    rig.run (noise (2, 2 * 48000, 1, 0.3f), 256);
    for (int k = 0; k < 20; ++k)
    {
        std::unique_ptr<AfterimageEditor> ed (dynamic_cast<AfterimageEditor*> (rig.proc.createEditor()));
        rig.run (noise (2, 12000, (unsigned) k, 0.3f), 256);
        ed->refreshNow();
        CHECK (ed->statusText().contains ("MODE  RANDOM"));
    }
    std::unique_ptr<AfterimageEditor> ed (dynamic_cast<AfterimageEditor*> (rig.proc.createEditor()));
    ed->pressTrigger();
    rig.run (noise (2, 512, 9, 0.3f), 256); // the button's capture is now waiting or building
    CHECK (rig.proc.engine().jobsActive() == 1);
    ed.reset(); // destroyed while a capture is in flight
    rig.run (noise (2, 48000, 10, 0.3f), 256);
    CHECK (rig.proc.engine().status.captures.load() >= 3);
    CHECK (rig.proc.engine().status.outcomes[(size_t) Outcome::Completed].load() == rig.proc.engine().status.captures.load());
}

// =============================================================================================
// P1-B Stage C: RANDOM (docs/P1-B-QUALIFICATION.md 1.3)
std::vector<RequestRecord> randomRun (Engine& e, double fs, const Sig& x, int block, afterimage::Params p, Sig* out = nullptr,
                                      std::function<void (Engine&)> extra = {})
{
    std::vector<RequestRecord> log (2048);
    auto y = runEngine (e, fs, x, p, block, [&] (Engine& en) {
        en.setRequestLog (log.data(), 2048);
        if (extra) extra (en);
    });
    log.resize ((size_t) e.requestLogCount());
    if (out != nullptr) *out = y;
    return log;
}

bool isRandomCapture (const RequestRecord& r) { return r.origin == Origin::Random && (r.outcome == Outcome::Accepted || r.outcome == Outcome::Completed); }

/** Mean of hop mean-squares over the hops covering [s0, s1), as the engine's activity gate computes it. */
double hopLevelDb (const Sig& x, int H, int64_t s0, int64_t s1)
{
    double sum = 0;
    int n = 0;
    for (int64_t h = s0 / H; h <= (s1 - 1) / H; ++h, ++n)
    {
        double e = 0;
        for (auto& ch : x)
            for (int64_t i = h * H; i < (h + 1) * H; ++i) e += (double) ch[(size_t) i] * ch[(size_t) i];
        sum += e / ((double) H * (double) x.size());
    }
    return 10 * std::log10 (sum / n + 1e-30);
}

Sig bursts (int nch, double fs, double seconds, double on, double period, unsigned seed)
{
    auto x = noise (nch, (int) (seconds * fs), seed, 0.3f);
    for (auto& ch : x)
        for (size_t i = 0; i < ch.size(); ++i)
            if (std::fmod ((double) i / fs, period) >= on) ch[i] = 0.0f;
    return x;
}

void testRandomDeterminism()
{
    currentTest = "C1 RANDOM determinism";
    for (double fs : { 44100.0, 96000.0 })
    {
        auto x = bursts (2, fs, 12.0, 2.0, 3.0, 4);
        afterimage::Params p = sched (Mode::Random, false, 1.0f, -48.0f);
        p.source = Source::Filtered;
        Engine e0;
        Sig y0;
        auto ref = randomRun (e0, fs, x, 1024, p, &y0);
        CHECK (std::count_if (ref.begin(), ref.end(), isRandomCapture) >= 5);
        for (int block : { 1, 32, 0 })
        {
            Engine e;
            Sig y;
            auto log = randomRun (e, fs, x, block, p, &y);
            bool same = log.size() == ref.size();
            for (size_t i = 0; same && i < log.size(); ++i)
                same = log[i].at == ref[i].at && log[i].s0 == ref[i].s0 && log[i].s1 == ref[i].s1 && log[i].outcome == ref[i].outcome
                       && afterimage::exactly (log[i].lowHz, ref[i].lowHz) && afterimage::exactly (log[i].highHz, ref[i].highHz);
            CHECK (same);
            CHECK (bitIdentical (y, y0));
        }
    }
}

void testRandomBoundsAndValidity()
{
    currentTest = "C2/C3/C5 RANDOM attempts, interval, validity";
    for (double fs : rates)
    {
        const int H = fs <= 48000 ? 1024 : 2048, N = 4 * H, X = (int) std::nearbyint (0.08 * fs);
        auto x = noise (2, (int) (30.0 * fs), 5, 0.3f);
        const float I = 2.0f;
        afterimage::Params p = sched (Mode::Random, false, I, -48.0f);
        p.lengthSeconds = 1.5f;
        Engine e;
        auto log = randomRun (e, fs, x, 256, p);
        CHECK (e.maxRandomAttempts() <= 8);
        std::vector<int64_t> at;
        bool onSlots = true, valid = true;
        for (auto& r : log)
        {
            if (r.origin != Origin::Random) continue;
            onSlots &= r.at % 64 == 32;
            if (r.outcome == Outcome::Rejected) valid &= r.reject != Reject::Expired && r.reject != Reject::Future && r.reject != Reject::BeforeStream;
            if (! isRandomCapture (r)) continue;
            at.push_back (r.at);
            valid &= r.s1 >= r.at - (int64_t) std::nearbyint (4.0 * fs) && r.s1 <= r.at - (X + N + H);
            valid &= hopLevelDb (x, H, r.s0, r.s1) >= -48.0;
            valid &= r.s1 - r.s0 == (int64_t) std::nearbyint (1.5 * fs);
        }
        double minGap = 1e9, maxGap = 0;
        for (size_t i = 1; i < at.size(); ++i)
        {
            minGap = std::min (minGap, (double) (at[i] - at[i - 1]) / fs);
            maxGap = std::max (maxGap, (double) (at[i] - at[i - 1]) / fs);
        }
        CHECK (onSlots);
        CHECK (valid);
        CHECK (at.size() >= 10);
        CHECK (minGap >= 0.75 * I);
        CHECK (maxGap <= 1.25 * I + 0.5);
        std::printf ("    fs=%.0f: %zu RANDOM captures, gaps %.2f-%.2f s (I = %.1f s), max attempts %d\n", fs, at.size(), minGap, maxGap, (double) I, e.maxRandomAttempts());
    }
}

void testRandomSilence()
{
    currentTest = "C4 RANDOM silence";
    for (float amp : { 0.0f, 1.4e-4f }) // silence, and noise at about -80 dBFS RMS
    {
        Engine e;
        auto log = randomRun (e, 48000.0, noise (2, 20 * 48000, 3, amp), 256, sched (Mode::Random, false, 1.0f, -48.0f));
        int captures = 0, none = 0;
        for (auto& r : log) { captures += isRandomCapture (r); none += r.origin == Origin::Random && r.outcome == Outcome::NoCandidate; }
        CHECK (captures == 0);
        CHECK (none >= 15);
        CHECK (e.maxRandomAttempts() == 8);
    }
}

void testRandomNoBacklog()
{
    currentTest = "C6 RANDOM drops busy and held ticks";
    const double fs = 48000;
    const float I = 1.0f;
    afterimage::Params p = sched (Mode::Random, false, I, -60.0f);
    p.source = Source::Filtered; // long builds: most RANDOM ticks fall while a manual capture is building
    Engine e;
    std::vector<RequestRecord> log (4096);
    auto x = noise (2, (int) (30.0 * fs), 6, 0.3f);
    e.prepare (fs, 2, 4096);
    e.setRequestLog (log.data(), 4096);
    int64_t nextTrigger = (int64_t) fs;
    for (int pos = 0; pos + 128 <= (int) x[0].size(); pos += 128)
    {
        if (pos >= nextTrigger) { e.submit (triggerAt (nextTrigger)); nextTrigger += (int64_t) (0.15 * fs); } // a host delivering triggers live
        float* ptr[2] = { x[0].data() + pos, x[1].data() + pos };
        e.process (ptr, 2, 128, p);
    }
    log.resize ((size_t) e.requestLogCount());
    int skipped = 0, ticks = 0;
    bool ok = true;
    int64_t lastRandom = -1;
    for (auto& r : log)
    {
        if (r.origin != Origin::Random) continue;
        ++ticks;
        if (lastRandom >= 0) ok &= r.at - lastRandom >= (int64_t) (0.75 * I * fs); // every tick reschedules from itself
        lastRandom = r.at;
        skipped += r.outcome == Outcome::SkippedBusy;
    }
    CHECK (skipped >= 5);
    CHECK (ok);
    std::printf ("    %d RANDOM ticks, %d skipped while busy, none replayed\n", ticks, skipped);
}

void testRandomSparseActivity()
{
    currentTest = "C7 RANDOM sparse activity";
    const double fs = 48000;
    auto x = bursts (2, fs, 40.0, 1.0, 4.0, 8);
    afterimage::Params p = sched (Mode::Random, false, 1.0f, -48.0f);
    p.lengthSeconds = 0.5f;
    Engine e;
    auto log = randomRun (e, fs, x, 256, p);
    int captures = 0;
    bool active = true;
    for (auto& r : log)
        if (isRandomCapture (r))
        {
            ++captures;
            active &= hopLevelDb (x, 1024, r.s0, r.s1) >= -48.0;
        }
    CHECK (captures >= 3);
    CHECK (active);
    std::printf ("    %d RANDOM captures, all over the gate\n", captures);
}

// =============================================================================================
// P1-B Stage D: AUTO experiment (docs/P1-B-QUALIFICATION.md 1.5); fixtures generated here
constexpr double twoPi = 6.283185307179586;

Sig plucked (double fs, int notes, double spacing, std::vector<double>& onsets)
{
    const int n = (int) ((1.0 + notes * spacing + 1.0) * fs);
    Sig x (2, std::vector<float> ((size_t) n, 0.0f));
    const double f0s[] = { 196.0, 246.94, 293.66, 329.63 };
    for (int k = 0; k < notes; ++k)
    {
        const double t0 = 1.0 + k * spacing;
        onsets.push_back (t0 * fs);
        for (int i = (int) (t0 * fs); i < n; ++i)
        {
            const double t = i / fs - t0, env = std::min (1.0, t / 0.003) * std::pow (10.0, -t / 2.0); // -10 dB/s
            double v = 0;
            for (int h = 1; h <= 6; ++h) v += std::sin (twoPi * f0s[k % 4] * h * t) / h;
            x[0][(size_t) i] += (float) (0.25 * env * v);
            x[1][(size_t) i] += (float) (0.23 * env * v);
        }
    }
    return x;
}

Sig tremoloChord (double fs, double seconds)
{
    const int n = (int) (seconds * fs);
    Sig x (2, std::vector<float> ((size_t) n, 0.0f));
    for (int i = (int) (0.5 * fs); i < n; ++i)
    {
        const double t = i / fs, fade = std::min (1.0, (t - 0.5) / 0.05), trem = std::pow (10.0, 3.0 * std::sin (twoPi * 5.0 * t) / 20.0);
        double v = 0;
        for (double f : { 196.0, 246.94, 293.66 })
            for (int h = 1; h <= 4; ++h) v += std::sin (twoPi * f * h * t) / h;
        x[0][(size_t) i] = x[1][(size_t) i] = (float) (0.1 * fade * trem * v);
    }
    return x;
}

Sig drums (double fs, double seconds, double period, std::vector<double>& hits)
{
    const int n = (int) (seconds * fs);
    Sig x (2, std::vector<float> ((size_t) n, 0.0f));
    std::mt19937 rng (5);
    std::uniform_real_distribution<float> u (-1.0f, 1.0f);
    for (double t0 = 1.0; t0 < seconds - 0.5; t0 += period)
    {
        hits.push_back (t0 * fs);
        for (int i = (int) (t0 * fs); i < std::min (n, (int) ((t0 + 0.4) * fs)); ++i)
        {
            const double t = i / fs - t0;
            const float v = (float) (0.6 * std::sin (twoPi * 60.0 * t) * std::exp (-t / 0.08) + 0.3 * u (rng) * std::exp (-t / 0.01));
            x[0][(size_t) i] += v;
            x[1][(size_t) i] += v;
        }
    }
    return x;
}

std::vector<RequestRecord> autoCaptures (const std::vector<RequestRecord>& log)
{
    std::vector<RequestRecord> c;
    for (auto& r : log)
        if (r.origin == Origin::Auto && (r.outcome == Outcome::Accepted || r.outcome == Outcome::Completed)) c.push_back (r);
    return c;
}

afterimage::Params autoParams()
{
    afterimage::Params p = ghostOnly();
    p.mode = Mode::Auto; // defaults: gate -48 dBFS, sensitivity 0.5, cooldown 2 s, length 0.75 s
    return p;
}

/** Distance from each capture start to the nearest event at or after it; also the worst event coverage. */
void startErrors (const std::vector<RequestRecord>& caps, const std::vector<double>& events, double& worstLead, bool& allBefore)
{
    worstLead = 0;
    allBefore = true;
    for (auto& r : caps)
    {
        double best = 1e18;
        for (double t : events)
            if (t >= (double) r.s0) best = std::min (best, t - (double) r.s0);
        allBefore &= best < 1e17;
        worstLead = std::max (worstLead, best);
    }
}

void testAutoNotes()
{
    currentTest = "D1/D2 AUTO plucked notes";
    for (double fs : { 48000.0, 96000.0 })
    {
        std::vector<double> onsets;
        auto x = plucked (fs, 10, 3.0, onsets);
        Engine e;
        auto caps = autoCaptures (randomRun (e, fs, x, 256, autoParams()));
        const double H = fs <= 48000 ? 1024 : 2048, limit = 3 * H + 0.01 * fs;
        double lead = 0;
        bool before = true;
        startErrors (caps, onsets, lead, before);
        int perNoteMax = 0;
        for (size_t k = 0; k < onsets.size(); ++k)
        {
            const double a = onsets[k] - limit, b = k + 1 < onsets.size() ? onsets[k + 1] - limit : 1e18;
            perNoteMax = std::max (perNoteMax, (int) std::count_if (caps.begin(), caps.end(), [&] (auto& r) { return (double) r.s0 >= a && (double) r.s0 < b; }));
        }
        CHECK (caps.size() >= 9);
        CHECK (before && lead <= limit);
        CHECK (perNoteMax <= 1);
        std::printf ("    fs=%.0f: %zu of 10 notes captured, worst start %.1f ms before its onset (limit %.1f), max per note %d\n", fs, caps.size(),
                     1000 * lead / fs, 1000 * limit / fs, perNoteMax);
    }
}

void testAutoSustainedAndSilence()
{
    currentTest = "D3/D4 AUTO sustained tremolo, silence, low noise";
    const double fs = 48000;
    {
        Engine e;
        auto caps = autoCaptures (randomRun (e, fs, tremoloChord (fs, 20.0), 256, autoParams()));
        CHECK (caps.size() <= 1);
        std::printf ("    tremolo chord: %zu captures (limit 1)\n", caps.size());
    }
    for (float amp : { 0.0f, 5.5e-4f }) // silence; uniform noise at about -70 dBFS RMS
    {
        Engine e;
        auto caps = autoCaptures (randomRun (e, fs, noise (2, (int) (20 * fs), 2, amp), 256, autoParams()));
        CHECK (caps.empty());
    }
}

void testAutoDrums()
{
    currentTest = "D5/D6 AUTO drums and determinism";
    for (double fs : { 44100.0, 96000.0 })
    {
        std::vector<double> hits;
        auto x = drums (fs, 21.0, 0.5, hits);
        Engine e0;
        Sig y0;
        auto log0 = randomRun (e0, fs, x, 1024, autoParams(), &y0);
        auto caps = autoCaptures (log0);
        const double H = fs <= 48000 ? 1024 : 2048, limit = 3 * H + 0.01 * fs;
        double lead = 0;
        bool before = true;
        startErrors (caps, hits, lead, before);
        CHECK (caps.size() >= 8 && caps.size() <= 11);
        CHECK (before && lead <= limit);
        std::printf ("    fs=%.0f: %zu captures from %zu hits, worst start %.1f ms before a hit (limit %.1f)\n", fs, caps.size(), hits.size(), 1000 * lead / fs,
                     1000 * limit / fs);
        for (int block : { 1, 32, 0 })
        {
            Engine e;
            Sig y;
            auto log = randomRun (e, fs, x, block, autoParams(), &y);
            bool same = log.size() == log0.size();
            for (size_t i = 0; same && i < log.size(); ++i) same = log[i].at == log0[i].at && log[i].s0 == log0[i].s0 && log[i].s1 == log0[i].s1;
            CHECK (same);
            CHECK (bitIdentical (y, y0));
        }
    }
}

void testAutoHold()
{
    currentTest = "B5 HOLD with AUTO";
    std::vector<double> hits;
    auto x = drums (48000.0, 21.0, 0.5, hits);
    afterimage::Params p = autoParams();
    p.hold = true;
    Engine e;
    auto log = randomRun (e, 48000.0, x, 256, p);
    int suppressed = 0;
    for (auto& r : log) suppressed += r.origin == Origin::Auto && r.outcome == Outcome::SuppressedHold;
    CHECK (autoCaptures (log).empty());
    CHECK (suppressed >= 5);
}
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;
    const char* only = argc > 1 ? argv[1] : nullptr;
    snapshotPath = argc > 2 ? argv[2] : nullptr; // afterimage_tests editor <png>
    struct T { const char* name; void (*fn)(); };
    const T tests[] = { { "layouts", testLayouts }, { "dry", testDryPathExact }, { "bypass", testVariableBlocksAndBypass },
                        { "body", testBodyGainRamp }, { "nonfinite", testNonFinite }, { "state", testStateRestore },
                        { "tail", testTail }, { "loop", testLoopPeriodAndSeam }, { "start", testStartOfHistory },
                        { "reject", testRejections }, { "determinism", testDeterminismAcrossBlocks }, { "ceiling", testGrainCeiling },
                        { "clicks", testClearReplaceClicks }, { "rapid", testRapidParameters }, { "nonfinite2", testNonFiniteNeverStored },
                        { "gain", testGainContract }, { "postroll", testPostRollSeam }, { "delay", testCaptureDelay },
                        { "statecap", testStateNeverImprints }, { "bypass2", testBypassResumesGhostFromZero },
                        { "denormal", testNoDenormalsAfterDecay }, { "editor", testEditor }, { "mapping", testSpectrogramMapping },
                        { "silence", testSilentAndTransientCaptures }, { "alloc", testNoAllocationsInCallback },
                        // P1-B Stage B
                        { "b3", testManualExactness }, { "b3midi", testTriggerOrigins }, { "b4", testAutomationEdges }, { "b5", testHold },
                        { "b6", testBusy }, { "b7", testBypassIgnoresTriggers }, { "b8", testAutomaticReplacementAudio },
                        { "b9", testNoAllocationsWithTriggers }, { "b10", testEditorLifecycle },
                        // P1-B Stage C
                        { "c1", testRandomDeterminism }, { "c235", testRandomBoundsAndValidity }, { "c4", testRandomSilence },
                        { "c6", testRandomNoBacklog }, { "c7", testRandomSparseActivity },
                        // P1-B Stage D (experiment limits)
                        { "d12", testAutoNotes }, { "d34", testAutoSustainedAndSilence }, { "d56", testAutoDrums }, { "b5auto", testAutoHold } };
    for (auto& t : tests)
        if (only == nullptr || std::strcmp (only, t.name) == 0)
        {
            const int before = failures;
            t.fn();
            std::printf ("%-10s %s\n", t.name, failures == before ? "ok" : "FAILED");
        }
    std::printf ("%d checks, %d failed\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
