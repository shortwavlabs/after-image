// SPDX-License-Identifier: AGPL-3.0-only
// Worst-case callback benchmark (docs/P1-A-QUALIFICATION.md 1.4, docs/P1-B-QUALIFICATION.md 1.6). Release build only.
//   afterimage_bench [out=bench.json] [runs=3] [seconds=20] [scenarios=p1a,manual,random,auto] [cpu=1]
// p1a is the unchanged P1-A scenario (runOnce). manual / random / auto are the P1-B stress scenarios (runP1b).
// cpu=1 (E5, evidence only, never a gate) also reads the thread's CPU time around every call.
// Times every processBlock of the real processor: 7 s of noise to fill the history, then an IMPRINT of a
// maximum-length selection every 0.5 s (alternating FULL / FILTERED), DISSOLVE 0.5, at the CLOUD density and at
// a stress density that keeps every voice at its grain ceiling. Also times single FFTs for reference.
#include <PluginProcessor.h>
#include <juce_dsp/juce_dsp.h>

#include <algorithm>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <mach/thread_policy.h>
#include <chrono>
#include <cstdio>
#include <ctime>
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

double threadCpuMicros()
{
    timespec ts {};
    clock_gettime (CLOCK_THREAD_CPUTIME_ID, &ts);
    return (double) ts.tv_sec * 1e6 + (double) ts.tv_nsec * 1e-3;
}

struct CpuEvidence { double maxWall = 0, cpuAtMaxWall = 0, maxCpu = 0, p999Cpu = 0; int preempted = 0; };

/** P1-B stress scenarios through the real processor (MIDI, parameters, scheduler), same timing as runOnce. */
RunResult runP1b (double fs, int block, double density, double seconds, unsigned seed, const juce::String& scenario, CpuEvidence* cpu)
{
    AfterimageProcessor proc;
    proc.setRateAndBufferSizeDetails (fs, block);
    proc.prepareToPlay (fs, block);
    auto setParam = [&] (const char* id, float v) { proc.apvts.getParameter (id)->setValueNotifyingHost (v); };
    setParam ("dissolve", 0.5f);
    setParam ("capture_length", 1.0f); // 1500 ms: the longest build
    if (scenario == "random") { setParam ("capture_mode", 0.5f); setParam ("random_interval", 0.0f); setParam ("activity_gate", 0.0f); }
    if (scenario == "auto") { setParam ("capture_mode", 1.0f); setParam ("auto_cooldown", 0.0f); setParam ("auto_sensitivity", 1.0f); }
    if (density > 0) proc.engine().setDensityOverride (density);

    juce::AudioBuffer<float> buf (2, block);
    juce::MidiBuffer midi, note;
    note.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 0);
    std::mt19937 rng (seed);
    std::uniform_real_distribution<float> u (-0.3f, 0.3f);
    const auto hitEvery = (int64_t) (0.25 * fs);
    const auto warm = (int64_t) (7.0 * fs), total = warm + (int64_t) (seconds * fs);
    std::vector<double> times, cpus;
    times.reserve ((size_t) ((total - warm) / block + 2));
    cpus.reserve (times.capacity());
    int64_t pos = 0, nextNote = warm, nextFlip = warm;
    int flips = 0;
    while (pos < total)
    {
        for (int c = 0; c < 2; ++c)
            for (int i = 0; i < block; ++i)
            {
                const int64_t n = pos + i;
                float v = u (rng);
                if (scenario == "auto") // percussive: a decaying hit every 250 ms over quiet noise
                {
                    const double t = (double) (n % hitEvery) / fs;
                    v = (float) (0.02 * v + std::exp (-t / 0.03) * (0.6 * std::sin (6.283185307 * 70.0 * t) + v));
                }
                buf.setSample (c, i, v);
            }
        if (pos >= nextFlip) { setParam ("source", (flips++ % 2) ? 1.0f : 0.0f); nextFlip += (int64_t) fs; } // alternate FULL / FILTERED
        const bool trigger = scenario == "manual" && pos >= nextNote;
        if (trigger) nextNote += (int64_t) (0.15 * fs);
        const double c0 = cpu != nullptr ? threadCpuMicros() : 0.0;
        const auto t0 = Clock::now();
        proc.processBlock (buf, trigger ? note : midi);
        const auto t1 = Clock::now();
        const double c1 = cpu != nullptr ? threadCpuMicros() : 0.0;
        if (pos >= warm)
        {
            const double wall = std::chrono::duration<double, std::micro> (t1 - t0).count();
            times.push_back (wall);
            if (cpu != nullptr)
            {
                cpus.push_back (c1 - c0);
                if (wall > cpu->maxWall) { cpu->maxWall = wall; cpu->cpuAtMaxWall = c1 - c0; }
                cpu->preempted += wall > 2.0 * (c1 - c0) + 50.0; // wall clock far beyond the thread's own CPU time
            }
        }
        pos += block;
    }
    RunResult r;
    r.s = stats (times);
    r.captures = proc.engine().status.captures.load();
    r.rejects = proc.engine().status.rejects.load();
    r.maxGrainsTotal = proc.engine().maxActiveGrainsTotal();
    if (cpu != nullptr) { auto cs = stats (cpus); cpu->maxCpu = cs.max; cpu->p999Cpu = cs.p999; }
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

/** Diagnostic only: the Mach time-constraint policy audio threads use. Period = the block's duration. */
static bool makeRealtime (double periodSeconds)
{
    mach_timebase_info_data_t tb;
    mach_timebase_info (&tb);
    const double toAbs = 1e9 * tb.denom / tb.numer;
    thread_time_constraint_policy_data_t pol;
    pol.period = (uint32_t) (periodSeconds * toAbs);
    pol.computation = (uint32_t) (0.5 * periodSeconds * toAbs);
    pol.constraint = (uint32_t) (periodSeconds * toAbs);
    pol.preemptible = 1;
    return thread_policy_set (mach_thread_self(), THREAD_TIME_CONSTRAINT_POLICY, (thread_policy_t) &pol,
                              THREAD_TIME_CONSTRAINT_POLICY_COUNT) == KERN_SUCCESS;
}

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juceInit;
    juce::String out = "bench.json";
    int runs = 3;
    double seconds = 20.0;
    bool rt = false; // rt=1: supplementary run on the Mach time-constraint policy (not the pre-set gate)
    bool cpu = false;
    juce::StringArray scenarios { "p1a" };
    for (int i = 1; i < argc; ++i)
    {
        const juce::String a (argv[i]);
        if (a.startsWith ("out=")) out = a.fromFirstOccurrenceOf ("=", false, false);
        if (a.startsWith ("runs=")) runs = a.fromFirstOccurrenceOf ("=", false, false).getIntValue();
        if (a.startsWith ("seconds=")) seconds = a.fromFirstOccurrenceOf ("=", false, false).getDoubleValue();
        if (a == "rt=1") rt = true;
        if (a == "cpu=1") cpu = true;
        if (a.startsWith ("scenarios=")) scenarios = juce::StringArray::fromTokens (a.fromFirstOccurrenceOf ("=", false, false), ",", "");
        if (a.startsWith ("diagnose="))  // diagnose=fs,block,density,repeats[,rt]: max of each repeat, no gate
        {
            auto t = juce::StringArray::fromTokens (a.fromFirstOccurrenceOf ("=", false, false), ",", "");
            const double fs = t[0].getDoubleValue(), density = t[2].getDoubleValue();
            const int block = t[1].getIntValue(), repeats = t[3].getIntValue();
            const bool useRt = t[4] == "rt" && makeRealtime (block / fs);
            std::printf ("diagnostic fs=%.0f block=%d density=%.0f realtime_policy=%s\n", fs, block, density, useRt ? "yes" : "no");
            for (int r = 0; r < repeats; ++r)
            {
                auto res = runOnce (fs, block, density, seconds, (unsigned) r + 1);
                std::printf ("  repeat %2d: max %8.2f us  p99.9 %6.2f us\n", r + 1, res.s.max, res.s.p999);
            }
            return 0;
        }
    }
    juce::String json = "{\n \"note\": \"worst of " + juce::String (runs) + " runs per row; microseconds per processBlock call; "
                        + (rt ? "SUPPLEMENTARY: Mach time-constraint thread policy, not the pre-set gate" : "ordinary thread, no realtime priority (pre-set gate)") + "\",\n";
    fftTiming (json);
    json << " \"rows\": [";
    bool first = true;
    for (auto& scenario : scenarios)
    for (double density : { 0.0, 1000.0 })
        for (double fs : { 44100.0, 48000.0, 88200.0, 96000.0 })
            for (int block : { 1, 16, 32, 64, 1024 })
            {
                RunResult worst;
                CpuEvidence ev;
                if (rt) makeRealtime (block / fs);
                for (int r = 0; r < runs; ++r)
                {
                    CpuEvidence e1;
                    auto res = scenario == "p1a" ? runOnce (fs, block, density, seconds, (unsigned) r + 1)
                                                 : runP1b (fs, block, density, seconds, (unsigned) r + 1, scenario, cpu ? &e1 : nullptr);
                    if (e1.maxWall > ev.maxWall) { ev.maxWall = e1.maxWall; ev.cpuAtMaxWall = e1.cpuAtMaxWall; }
                    ev.maxCpu = std::max (ev.maxCpu, e1.maxCpu);
                    ev.p999Cpu = std::max (ev.p999Cpu, e1.p999Cpu);
                    ev.preempted += e1.preempted;
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
                json << (first ? "" : ",") << "\n  {\"scenario\": \"" << scenario << "\", \"density\": \"" << (density > 0 ? "stress 1000/s" : "CLOUD 20/s") << "\", \"fs\": " << (int) fs
                     << ", \"block\": " << block << ", \"deadline_us\": " << juce::String (deadline, 2) << ", \"max_us\": " << juce::String (worst.s.max, 2)
                     << ", \"p999_us\": " << juce::String (worst.s.p999, 2) << ", \"p99_us\": " << juce::String (worst.s.p99, 2)
                     << ", \"median_us\": " << juce::String (worst.s.median, 2) << ", \"mean_us\": " << juce::String (worst.s.mean, 3)
                     << ", \"max_pct_of_deadline\": " << juce::String (100 * worst.s.max / deadline, 1)
                     << ", \"p999_pct_of_deadline\": " << juce::String (100 * worst.s.p999 / deadline, 1)
                     << ", \"callbacks\": " << (juce::int64) worst.s.callbacks << ", \"captures\": " << (juce::int64) worst.captures
                     << ", \"rejects\": " << (juce::int64) worst.rejects << ", \"max_grains_total\": " << worst.maxGrainsTotal
                     << ", \"gate\": \"" << (cpu ? "evidence only" : gated ? (pass ? "PASS" : "FAIL") : (block == 16 ? "reported" : "correctness only")) << "\"";
                if (cpu)
                    json << ", \"cpu_max_us\": " << juce::String (ev.maxCpu, 2) << ", \"cpu_p999_us\": " << juce::String (ev.p999Cpu, 2)
                         << ", \"cpu_at_max_wall_us\": " << juce::String (ev.cpuAtMaxWall, 2) << ", \"callbacks_wall_over_2x_cpu_plus_50us\": " << ev.preempted;
                json << "}";
                first = false;
                std::printf ("%-7s %-7s fs=%6.0f block=%5d  max %8.2f us (%5.1f%%)  p99.9 %7.2f us (%5.1f%%)  median %6.2f us  %s",
                             scenario.toRawUTF8(), density > 0 ? "stress" : "CLOUD", fs, block, worst.s.max, 100 * worst.s.max / deadline, worst.s.p999,
                             100 * worst.s.p999 / deadline, worst.s.median, cpu ? "" : gated ? (pass ? "PASS" : "FAIL") : "-");
                if (cpu) std::printf ("  cpu max %.1f, cpu at max wall %.1f, preempted callbacks %d", ev.maxCpu, ev.cpuAtMaxWall, ev.preempted);
                std::printf ("\n");
                std::fflush (stdout);
            }
    json << "\n ]\n}\n";
    juce::File (out).replaceWithText (json);
    return 0;
}
