// SPDX-License-Identifier: AGPL-3.0-only
// AFTERIMAGE C++ unit tests. Plain checks, no framework; exit code = number of failed checks.
#include <PluginProcessor.h>

#include <cstdio>
#include <functional>
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
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;
    const char* only = argc > 1 ? argv[1] : nullptr;
    struct T { const char* name; void (*fn)(); };
    const T tests[] = { { "layouts", testLayouts }, { "dry", testDryPathExact }, { "bypass", testVariableBlocksAndBypass },
                        { "body", testBodyGainRamp }, { "nonfinite", testNonFinite }, { "state", testStateRestore },
                        { "tail", testTail }, { "loop", testLoopPeriodAndSeam }, { "start", testStartOfHistory },
                        { "reject", testRejections }, { "determinism", testDeterminismAcrossBlocks }, { "ceiling", testGrainCeiling },
                        { "clicks", testClearReplaceClicks }, { "rapid", testRapidParameters }, { "nonfinite2", testNonFiniteNeverStored },
                        { "gain", testGainContract }, { "postroll", testPostRollSeam }, { "delay", testCaptureDelay },
                        { "statecap", testStateNeverImprints }, { "bypass2", testBypassResumesGhostFromZero },
                        { "denormal", testNoDenormalsAfterDecay } };
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
