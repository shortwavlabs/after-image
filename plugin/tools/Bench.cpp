// SPDX-License-Identifier: AGPL-3.0-only
// Worst-case callback benchmark (docs/P1-A-QUALIFICATION.md 1.4). Release build only.
//   afterimage_bench [out=bench.json] [runs=3] [seconds=20]
// Times every processBlock of the real processor: 7 s of noise to fill the history, then an IMPRINT of a
// maximum-length selection every 0.5 s (alternating FULL / FILTERED), DISSOLVE 0.5, at the CLOUD density and at
// a stress density that keeps every voice at its grain ceiling. Also times single FFTs for reference.
#include <PluginProcessor.h>
#include <juce_dsp/juce_dsp.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <vector>

namespace
{
using Clock = std::chrono::steady_clock;

struct Stats { double max = 0, p999 = 0, p99 = 0, median = 0, mean = 0; size_t callbacks = 0; };

Stats stats (std::vector<double>& v)
{
    std::sort (v.begin(), v.end());
    Stats s;
    s.callbacks = v.size();
    s.max = v.back();
    s.p999 = v[v.size() * 999 / 1000];
    s.p99 = v[v.size() * 99 / 100];
    s.median = v[v.size() / 2];
    for (auto x : v) s.mean += x;
    s.mean /= (double) v.size();
    return s;
}

struct RunResult { Stats s; uint64_t captures = 0, rejects = 0; int maxGrainsTotal = 0; };

RunResult runOnce (double fs, int block, double density, double seconds, unsigned seed)
{
    AfterimageProcessor proc;
    proc.setRateAndBufferSizeDetails (fs, block);
    proc.prepareToPlay (fs, block);
    auto* d = proc.apvts.getParameter ("dissolve");
    d->setValueNotifyingHost (0.5f);
    if (density > 0) proc.engine().setDensityOverride (density);

    juce::AudioBuffer<float> buf (2, block);
    juce::MidiBuffer midi;
    std::mt19937 rng (seed);
    std::uniform_real_distribution<float> u (-0.3f, 0.3f);
    auto fill = [&] { for (int c = 0; c < 2; ++c) for (int i = 0; i < block; ++i) buf.setSample (c, i, u (rng)); };

    const auto warm = (int64_t) (7.0 * fs), total = warm + (int64_t) (seconds * fs), every = (int64_t) (0.5 * fs);
    const auto selLen = (int64_t) std::nearbyint (1.5 * fs);
    std::vector<double> times;
    times.reserve ((size_t) ((total - warm) / block + 2));
    int64_t pos = 0, nextImprint = warm;
    int k = 0;
    while (pos < total)
    {
        if (pos >= nextImprint)
        {
            afterimage::Command c;
            c.epoch = proc.engine().epoch();
            c.s1 = pos - (int64_t) (0.2 * fs);
            c.s0 = c.s1 - selLen;
            c.source = (k++ % 2) ? afterimage::Source::Filtered : afterimage::Source::Full;
            c.lowHz = 100.0;
            c.highHz = 8000.0;
            proc.postCommand (c);
            nextImprint += every;
        }
        fill();
        const auto t0 = Clock::now();
        proc.processBlock (buf, midi);
        const auto t1 = Clock::now();
        if (pos >= warm) times.push_back (std::chrono::duration<double, std::micro> (t1 - t0).count());
        pos += block;
    }
    RunResult r;
    r.s = stats (times);
    r.captures = proc.engine().status.captures.load();
    r.rejects = proc.engine().status.rejects.load();
    r.maxGrainsTotal = proc.engine().maxActiveGrainsTotal();
    return r;
}

void fftTiming (juce::String& json)
{
    json << " \"fft_us\": {";
    for (int order : { 12, 13 })
    {
        const int N = 1 << order;
        juce::dsp::FFT fft (order);
        std::vector<float> b ((size_t) (2 * N));
        std::vector<double> f, inv;
        for (int it = 0; it < 20000; ++it)
        {
            for (int i = 0; i < N; ++i) b[(size_t) i] = std::sin (0.001f * (float) (i + it));
            auto t0 = Clock::now();
            fft.performRealOnlyForwardTransform (b.data(), true);
            auto t1 = Clock::now();
            fft.performRealOnlyInverseTransform (b.data());
            auto t2 = Clock::now();
            f.push_back (std::chrono::duration<double, std::micro> (t1 - t0).count());
            inv.push_back (std::chrono::duration<double, std::micro> (t2 - t1).count());
        }
        auto sf = stats (f), si = stats (inv);
        json << (order == 13 ? ", " : "") << "\"" << N << "\": {\"forward_median\": " << juce::String (sf.median, 2) << ", \"forward_max\": "
             << juce::String (sf.max, 2) << ", \"inverse_median\": " << juce::String (si.median, 2) << ", \"inverse_max\": " << juce::String (si.max, 2) << "}";
    }
    json << "},\n";
}
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juceInit;
    juce::String out = "bench.json";
    int runs = 3;
    double seconds = 20.0;
    for (int i = 1; i < argc; ++i)
    {
        const juce::String a (argv[i]);
        if (a.startsWith ("out=")) out = a.fromFirstOccurrenceOf ("=", false, false);
        if (a.startsWith ("runs=")) runs = a.fromFirstOccurrenceOf ("=", false, false).getIntValue();
        if (a.startsWith ("seconds=")) seconds = a.fromFirstOccurrenceOf ("=", false, false).getDoubleValue();
    }
    juce::String json = "{\n \"note\": \"worst of " + juce::String (runs) + " runs per row; microseconds per processBlock call; ordinary thread, no realtime priority\",\n";
    fftTiming (json);
    json << " \"rows\": [";
    bool first = true;
    for (double density : { 0.0, 1000.0 })
        for (double fs : { 44100.0, 48000.0, 88200.0, 96000.0 })
            for (int block : { 1, 16, 32, 64, 1024 })
            {
                RunResult worst;
                for (int r = 0; r < runs; ++r)
                {
                    auto res = runOnce (fs, block, density, seconds, (unsigned) r + 1);
                    if (r == 0 || res.s.max > worst.s.max) worst.s.max = res.s.max;
                    worst.s.p999 = std::max (worst.s.p999, res.s.p999);
                    worst.s.p99 = std::max (worst.s.p99, res.s.p99);
                    worst.s.median = std::max (worst.s.median, res.s.median);
                    worst.s.mean = std::max (worst.s.mean, res.s.mean);
                    worst.s.callbacks = res.s.callbacks;
                    worst.captures = std::max (worst.captures, res.captures);
                    worst.rejects = std::max (worst.rejects, res.rejects);
                    worst.maxGrainsTotal = std::max (worst.maxGrainsTotal, res.maxGrainsTotal);
                }
                const double deadline = 1e6 * block / fs;
                const bool gated = block >= 32;
                const bool pass = worst.s.max <= 0.5 * deadline && worst.s.p999 <= 0.25 * deadline;
                json << (first ? "" : ",") << "\n  {\"density\": \"" << (density > 0 ? "stress 1000/s" : "CLOUD 20/s") << "\", \"fs\": " << (int) fs
                     << ", \"block\": " << block << ", \"deadline_us\": " << juce::String (deadline, 2) << ", \"max_us\": " << juce::String (worst.s.max, 2)
                     << ", \"p999_us\": " << juce::String (worst.s.p999, 2) << ", \"p99_us\": " << juce::String (worst.s.p99, 2)
                     << ", \"median_us\": " << juce::String (worst.s.median, 2) << ", \"mean_us\": " << juce::String (worst.s.mean, 3)
                     << ", \"max_pct_of_deadline\": " << juce::String (100 * worst.s.max / deadline, 1)
                     << ", \"p999_pct_of_deadline\": " << juce::String (100 * worst.s.p999 / deadline, 1)
                     << ", \"callbacks\": " << (juce::int64) worst.s.callbacks << ", \"captures\": " << (juce::int64) worst.captures
                     << ", \"rejects\": " << (juce::int64) worst.rejects << ", \"max_grains_total\": " << worst.maxGrainsTotal
                     << ", \"gate\": \"" << (gated ? (pass ? "PASS" : "FAIL") : (block == 16 ? "reported" : "correctness only")) << "\"}";
                first = false;
                std::printf ("%-14s fs=%6.0f block=%5d  max %8.2f us (%5.1f%%)  p99.9 %7.2f us (%5.1f%%)  median %6.2f us  %s\n",
                             density > 0 ? "stress" : "CLOUD", fs, block, worst.s.max, 100 * worst.s.max / deadline, worst.s.p999,
                             100 * worst.s.p999 / deadline, worst.s.median, gated ? (pass ? "PASS" : "FAIL") : "-");
                std::fflush (stdout);
            }
    json << "\n ]\n}\n";
    juce::File (out).replaceWithText (json);
    return 0;
}
