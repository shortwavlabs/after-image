// SPDX-License-Identifier: AGPL-3.0-only
// AFTERIMAGE C++ unit tests. Plain checks, no framework; exit code = number of failed checks.
#include <PluginProcessor.h>

#include <cstdio>
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
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;
    const char* only = argc > 1 ? argv[1] : nullptr;
    struct T { const char* name; void (*fn)(); };
    const T tests[] = { { "layouts", testLayouts }, { "dry", testDryPathExact }, { "bypass", testVariableBlocksAndBypass },
                        { "body", testBodyGainRamp }, { "nonfinite", testNonFinite }, { "state", testStateRestore },
                        { "tail", testTail } };
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
