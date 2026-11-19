// SPDX-License-Identifier: AGPL-3.0-only
// P1-B hosting harness (docs/P1-B-QUALIFICATION.md 1.6). NOT a DAW: it loads the real AU/VST3 binaries through
// JUCE's plugin-hosting code and drives them directly (E2) or from a real CoreAudio device callback (E3).
//
//   afterimage_host devices
//   afterimage_host e2 vst3=/path/AFTERIMAGE.vst3 [out=e2.json]
//   afterimage_host e3 vst3=/path/AFTERIMAGE.vst3 device="BlackHole 2ch" rate=48000 block=64 seconds=60
//                   [editor=0|1] [instances=1] [control=0|1] [out=e3.json]
#include <juce_audio_utils/juce_audio_utils.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <thread>

namespace
{
using Clock = std::chrono::steady_clock;
juce::StringPairArray opts;
juce::String opt (const char* k, const char* d = "") { return opts.getValue (k, d); }
int fails = 0;

void report (juce::String& json, const juce::String& id, bool ok, const juce::String& detail)
{
    fails += ok ? 0 : 1;
    std::printf ("%-6s %-58s %s\n", ok ? "PASS" : "FAIL", id.toRawUTF8(), detail.toRawUTF8());
    json << (json.endsWith ("[") ? "" : ",") << "\n  {\"check\": \"" << id << "\", \"result\": \"" << (ok ? "PASS" : "FAIL") << "\", \"detail\": \""
         << detail.replace ("\"", "'") << "\"}";
}

std::unique_ptr<juce::AudioPluginInstance> load (juce::AudioPluginFormatManager& fm, const juce::String& format, double fs, int block)
{
    juce::OwnedArray<juce::PluginDescription> found;
    for (auto* f : fm.getFormats())
        if (f->getName() == format)
        {
            const juce::String id = format == "VST3" ? opt ("vst3") : juce::String ("AudioUnit:Effects/aufx,Aftr,SwLb");
            f->findAllTypesForFile (found, id);
        }
    if (found.isEmpty()) return nullptr;
    juce::String err;
    auto p = fm.createPluginInstance (*found[0], fs, block, err);
    if (p == nullptr) std::printf ("load %s failed: %s\n", format.toRawUTF8(), err.toRawUTF8());
    return p;
}

juce::AudioProcessorParameter* param (juce::AudioPluginInstance& p, const char* name)
{
    for (auto* q : p.getParameters())
        if (q->getName (64) == name) return q;
    return nullptr;
}

void set (juce::AudioPluginInstance& p, const char* name, float normalised)
{
    if (auto* q = param (p, name)) q->setValue (normalised);
    else std::printf ("  (no parameter '%s')\n", name);
}

void prepare (juce::AudioPluginInstance& p, double fs, int block)
{
    p.setPlayConfigDetails (2, 2, fs, block);
    p.prepareToPlay (fs, block);
}

/** Sample-index-encoded input: ch0 = 0.5 * n / 2^20, ch1 = 0.5, so a TRACE ghost reveals which samples it holds. */
float encoded (int ch, int64_t n) { return ch == 0 ? (float) (0.5 * (double) (n % (1 << 20)) / (double) (1 << 20)) : 0.5f; }

struct Run
{
    juce::AudioBuffer<float> out;
    std::vector<float> in0;
};

/** Runs `seconds` of encoded input in blocks; `eventsAt` (block index -> MIDI) and `beforeBlock` hooks. */
template <typename Hook>
Run run (juce::AudioPluginInstance& p, double fs, int block, double seconds, int64_t& stream, Hook&& beforeBlock)
{
    const int n = (int) (seconds * fs) / block * block;
    Run r { juce::AudioBuffer<float> (2, n), std::vector<float> ((size_t) n) };
    juce::AudioBuffer<float> buf (2, block);
    for (int pos = 0, b = 0; pos < n; pos += block, ++b)
    {
        juce::MidiBuffer midi;
        beforeBlock (b, midi);
        for (int c = 0; c < 2; ++c)
            for (int i = 0; i < block; ++i) buf.setSample (c, i, encoded (c, stream + i));
        for (int i = 0; i < block; ++i) r.in0[(size_t) (pos + i)] = buf.getSample (0, i);
        p.processBlock (buf, midi);
        for (int c = 0; c < 2; ++c) r.out.copyFrom (c, pos, buf, c, 0, block);
        stream += block;
    }
    return r;
}

/** The selection end s1 decoded from a TRACE ghost (-1 if no loop is found). By the loop contract (P1-A 4.2) the loop
    plays audio[s1 - R .. s1 - 1] and then loop[0] = audio[s1] exactly, after which the seam blend starts, so the last
    sample of each run of consecutive indices is s1. */
int64_t decodeLoopEnd (const juce::AudioBuffer<float>& out, int& wraps)
{
    std::vector<int64_t> v ((size_t) out.getNumSamples(), -1);
    for (int i = 0; i < out.getNumSamples(); ++i)
    {
        const float a = out.getSample (0, i), b = out.getSample (1, i);
        if (std::abs (b) > 1.0e-6f) v[(size_t) i] = (int64_t) std::llround ((double) a / (double) b * (double) (1 << 20));
    }
    int64_t end = -1;
    wraps = 0;
    for (size_t i = 2; i + 1 < v.size(); ++i)
        if (v[i] >= 0 && v[i] - v[i - 1] == 1 && v[i - 1] - v[i - 2] == 1 && v[i + 1] - v[i] != 1)
        {
            if (end >= 0 && end != v[i]) return -2; // two different ends: inconsistent
            end = v[i];
            ++wraps;
        }
    return end;
}

bool silent (const juce::AudioBuffer<float>& b)
{
    for (int c = 0; c < b.getNumChannels(); ++c)
        for (int i = 0; i < b.getNumSamples(); ++i)
            if (! std::equal_to<float>() (b.getSample (c, i), 0.0f)) return false;
    return true;
}

// ---------------------------------------------------------------------------------------------
int e2()
{
    juce::AudioPluginFormatManager fm;
    juce::addDefaultFormatsToManager (fm);
    juce::String json = "{\n \"note\": \"E2: real AU/VST3 binaries through JUCE plugin hosting (not a DAW)\",\n \"rows\": [";
    for (auto format : { juce::String ("VST3"), juce::String ("AudioUnit") })
    {
        const double fs = 48000.0;
        for (int block : { 64, 512 })
        {
            auto p = load (fm, format, fs, block);
            report (json, format + " load (block " + juce::String (block) + ")", p != nullptr, p ? p->getName() + ", accepts MIDI " + (p->acceptsMidi() ? "yes" : "no") : "not found");
            if (p == nullptr) continue;
            prepare (*p, fs, block);
            int64_t stream = 0;
            // dry path at BODY 1 (defaults), no capture
            auto dry = run (*p, fs, block, 1.0, stream, [] (int, juce::MidiBuffer&) {});
            bool same = true;
            for (int i = 0; i < dry.out.getNumSamples(); ++i) same &= std::equal_to<float>() (dry.out.getSample (0, i), dry.in0[(size_t) i]);
            report (json, format + " dry path bit-identical (block " + juce::String (block) + ")", same, "1 s at BODY 1");

            // MIDI and automation triggers: the TRACE ghost reveals the selection's last sample
            for (int kind = 0; kind < 3; ++kind)
                for (int offset : { 0, 17, block - 1 })
                {
                    if (kind == 2 && offset != 0) continue; // automation is block-resolution
                    auto q = load (fm, format, fs, block);
                    set (*q, "Body", 0.0f);
                    set (*q, "Ghost", 1.0f);
                    set (*q, "Dissolve", 0.0f);
                    prepare (*q, fs, block);
                    int64_t s = 0, expected = -1;
                    const int trigBlock = (int) (2.0 * fs) / block;
                    auto r = run (*q, fs, block, 4.0, s, [&] (int b, juce::MidiBuffer& m) {
                        if (b != trigBlock) return;
                        expected = (int64_t) b * block + (kind == 2 ? 0 : offset);
                        if (kind == 0) m.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), offset);
                        if (kind == 1) m.addEvent (juce::MidiMessage::controllerEvent (1, 64, 127), offset);
                        if (kind == 2) set (*q, "Imprint (trigger)", 1.0f);
                    });
                    int wraps = 0;
                    const auto end = decodeLoopEnd (r.out, wraps);
                    const char* what[] = { "MIDI Note On", "MIDI CC 64", "automation trigger" };
                    const bool captured = end >= 0;
                    const juce::String id = format + " " + what[kind] + " offset " + juce::String (offset) + " block " + juce::String (block);
                    if (format == "AudioUnit" && kind < 2)
                        report (json, id + " (observed, not a gate)", true, captured ? "capture, s1 = " + juce::String (end) + " (expected " + juce::String (expected) + ")" : "no capture: the aufx AU receives no MIDI here");
                    else
                        report (json, id, captured && end == expected,
                                captured ? "s1 = " + juce::String (end) + ", expected " + juce::String (expected) + ", " + juce::String (wraps) + " loop wraps decoded" : "no capture decoded");
                }
        }
        // state restore with IMPRINT saved "on": never captures
        {
            auto a = load (fm, format, fs, 256);
            set (*a, "Body", 0.0f);
            set (*a, "Ghost", 1.0f);
            set (*a, "Imprint (trigger)", 1.0f);
            prepare (*a, fs, 256);
            int64_t s = 0;
            run (*a, fs, 256, 0.5, s, [] (int, juce::MidiBuffer&) {});
            juce::MemoryBlock state;
            a->getStateInformation (state);
            auto b = load (fm, format, fs, 256);
            prepare (*b, fs, 256);
            b->setStateInformation (state.getData(), (int) state.getSize());
            s = 0;
            auto r = run (*b, fs, 256, 3.0, s, [] (int, juce::MidiBuffer&) {});
            report (json, format + " state restore with IMPRINT saved on", silent (r.out) && param (*b, "Imprint (trigger)")->getValue() > 0.5f,
                    silent (r.out) ? "restored on, no capture (output silent at BODY 0)" : "ghost appeared after restore");
        }
        // bypass: output = input, triggers ignored
        {
            auto p = load (fm, format, fs, 256);
            prepare (*p, fs, 256);
            auto* bypass = p->getBypassParameter();
            int64_t s = 0;
            if (bypass == nullptr)
                report (json, format + " bypass", false, "no bypass parameter exposed");
            else
            {
                bypass->setValue (1.0f);
                run (*p, fs, 256, 1.0, s, [] (int, juce::MidiBuffer&) {});
                auto r = run (*p, fs, 256, 0.5, s, [&] (int b, juce::MidiBuffer& m) {
                    if (b == 10) { m.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 5); set (*p, "Imprint (trigger)", 1.0f); }
                });
                bool same = true;
                for (int i = 0; i < r.out.getNumSamples(); ++i) same &= std::equal_to<float>() (r.out.getSample (0, i), r.in0[(size_t) i]);
                bypass->setValue (0.0f);
                set (*p, "Body", 0.0f);
                set (*p, "Ghost", 1.0f);
                auto after = run (*p, fs, 256, 2.0, s, [] (int, juce::MidiBuffer&) {});
                // BODY ramps from 1 to 0 over 20 ms after a bypass (P1-A contract), so judge from 50 ms on
                juce::AudioBuffer<float> tail (2, after.out.getNumSamples() - (int) (0.05 * fs));
                for (int c = 0; c < 2; ++c) tail.copyFrom (c, 0, after.out, c, (int) (0.05 * fs), tail.getNumSamples());
                int wraps = 0;
                const bool none = silent (tail) && decodeLoopEnd (tail, wraps) == -1; // the BODY ramp itself decodes as dry input
                const auto end = decodeLoopEnd (tail, wraps);
                report (json, format + " bypass", same && none, juce::String (same ? "output = input" : "output differs") + ", "
                                                                    + (none ? "no capture after resume" : "a capture appeared after resume: s1 = " + juce::String (end)
                                                                       + " (bypass ran samples 0-" + juce::String (s - (int64_t) (2.0 * fs) / 256 * 256) + ", resumed there)"));
            }
        }
        // re-prepare 44.1 kHz / 512 -> 96 kHz / 32
        {
            auto p = load (fm, format, 44100.0, 512);
            prepare (*p, 44100.0, 512);
            int64_t s = 0;
            run (*p, 44100.0, 512, 0.5, s, [] (int, juce::MidiBuffer&) {});
            p->releaseResources();
            prepare (*p, 96000.0, 32);
            s = 0;
            auto r = run (*p, 96000.0, 32, 1.0, s, [] (int, juce::MidiBuffer&) {});
            bool same = true;
            for (int i = 0; i < r.out.getNumSamples(); ++i) same &= std::equal_to<float>() (r.out.getSample (0, i), r.in0[(size_t) i]) && std::isfinite (r.out.getSample (1, i));
            report (json, format + " re-prepare 44.1k/512 -> 96k/32", same, same ? "dry, finite, no capture" : "output differs");
        }
    }
    json << "\n ],\n \"failures\": " << fails << "\n}\n";
    if (opt ("out").isNotEmpty()) juce::File (opt ("out")).replaceWithText (json);
    std::printf ("%d failed\n", fails);
    return fails == 0 ? 0 : 1;
}

// ---------------------------------------------------------------------------------------------
struct DeviceCallback final : juce::AudioIODeviceCallback
{
    std::vector<std::unique_ptr<juce::AudioPluginInstance>>& plugins;
    juce::AudioBuffer<float> buf;
    juce::MidiBuffer midi, empty;
    std::vector<float> table;
    std::vector<double> times;
    std::atomic<size_t> count { 0 };
    int64_t stream = 0, nextNote = 0, stallAt = -1;
    double fs = 48000;
    int block = 64;

    explicit DeviceCallback (std::vector<std::unique_ptr<juce::AudioPluginInstance>>& p) : plugins (p) {}

    void audioDeviceAboutToStart (juce::AudioIODevice* d) override
    {
        fs = d->getCurrentSampleRate();
        block = d->getCurrentBufferSizeSamples();
        buf.setSize (2, std::max (block, 4096));
        for (auto& p : plugins) prepare (*p, fs, block);
        midi.ensureSize (256);
    }
    void audioDeviceStopped() override {}

    void audioDeviceIOCallbackWithContext (const float* const*, int, float* const* out, int numOut, int n, const juce::AudioIODeviceCallbackContext&) override
    {
        for (int c = 0; c < 2; ++c)
            for (int i = 0; i < n; ++i) buf.setSample (c, i, table[(size_t) ((stream + i + c * 7919) & 65535)]);
        midi.clear();
        if (stream + n > nextNote) { midi.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), (int) std::max<int64_t> (0, nextNote - stream)); nextNote += (int64_t) (0.3 * fs); }
        juce::AudioBuffer<float> view (buf.getArrayOfWritePointers(), 2, n);
        const auto t0 = Clock::now();
        for (auto& p : plugins) p->processBlock (view, midi);
        const auto t1 = Clock::now();
        if (stallAt >= 0 && stream >= stallAt) { stallAt = -1; while (Clock::now() - t1 < std::chrono::duration<double> (3.0 * n / fs)) {} } // positive control
        const auto k = count.load (std::memory_order_relaxed);
        if (k < times.size()) times[k] = std::chrono::duration<double, std::micro> (t1 - t0).count();
        count.store (k + 1, std::memory_order_relaxed);
        for (int c = 0; c < numOut; ++c) juce::FloatVectorOperations::clear (out[c], n); // silent output
        stream += n;
    }
};

int e3()
{
    juce::AudioPluginFormatManager fm;
    juce::addDefaultFormatsToManager (fm);
    const double fs = opt ("rate", "48000").getDoubleValue(), seconds = opt ("seconds", "60").getDoubleValue();
    const int block = opt ("block", "64").getIntValue(), instances = opt ("instances", "1").getIntValue();
    const bool editor = opt ("editor", "0") == "1", control = opt ("control", "0") == "1";

    std::vector<std::unique_ptr<juce::AudioPluginInstance>> plugins;
    for (int i = 0; i < instances; ++i)
    {
        auto p = load (fm, "VST3", fs, block);
        if (p == nullptr) return 2;
        set (*p, "Capture mode", 0.5f);      // RANDOM
        set (*p, "Random interval", 0.0f);   // 1 s
        set (*p, "Activity gate", 0.0f);     // -72 dBFS: every candidate qualifies
        set (*p, "Dissolve", 0.5f);
        plugins.push_back (std::move (p));
    }
    juce::AudioDeviceManager dm;
    dm.initialise (0, 2, nullptr, false);
    auto setup = dm.getAudioDeviceSetup();
    setup.outputDeviceName = opt ("device", "BlackHole 2ch");
    setup.inputDeviceName = {};
    setup.sampleRate = fs;
    setup.bufferSize = block;
    const auto err = dm.setAudioDeviceSetup (setup, true);
    auto* dev = dm.getCurrentAudioDevice();
    if (err.isNotEmpty() || dev == nullptr) { std::printf ("device: %s\n", err.toRawUTF8()); return 3; }
    const double actualFs = dev->getCurrentSampleRate();
    const int actualBlock = dev->getCurrentBufferSizeSamples();
    std::printf ("device %s: %.0f Hz, %d samples (requested %.0f / %d), editor %d, instances %d, control %d\n", dev->getName().toRawUTF8(), actualFs,
                 actualBlock, fs, block, (int) editor, instances, (int) control);
    if (std::abs (actualFs - fs) > 0.5 || actualBlock != block) { std::printf ("NOT ASSESSED: the device did not accept this configuration\n"); return 4; }

    DeviceCallback cb (plugins);
    cb.table.resize (65536);
    juce::Random rng (3);
    for (auto& v : cb.table) v = 0.3f * (rng.nextFloat() * 2.0f - 1.0f);
    cb.times.resize ((size_t) (seconds * fs / block) + 1024);
    if (control) cb.stallAt = (int64_t) (5.0 * fs);

    std::unique_ptr<juce::DocumentWindow> window;
    std::unique_ptr<juce::AudioProcessorEditor> ed;
    if (editor)
    {
        ed.reset (plugins[0]->createEditorAndMakeActive());
        window = std::make_unique<juce::DocumentWindow> ("AFTERIMAGE (E3 harness)", juce::Colours::black, 0);
        window->setContentNonOwned (ed.get(), true);
        window->setTopLeftPosition (40, 40);
        window->setVisible (true);
    }
    const int xr0 = dev->getXRunCount();
    dm.addAudioCallback (&cb);
    auto* source = param (*plugins[0], "Source");
    for (int t = 0; t < (int) seconds; ++t)
    {
        if (source != nullptr) source->setValue (t % 2 == 0 ? 0.0f : 1.0f); // alternate FULL / FILTERED for RANDOM's captures
        juce::MessageManager::getInstance()->runDispatchLoopUntil (1000);
    }
    dm.removeAudioCallback (&cb);
    const int xruns = dev->getXRunCount() - xr0;
    window.reset();
    if (ed != nullptr) plugins[0]->editorBeingDeleted (ed.get());
    ed.reset();

    const size_t n = std::min (cb.count.load(), cb.times.size());
    std::vector<double> v (cb.times.begin(), cb.times.begin() + (long) n);
    std::sort (v.begin(), v.end());
    const double period = 1e6 * actualBlock / actualFs, mx = v.back(), p999 = v[v.size() * 999 / 1000], p99 = v[v.size() * 99 / 100], med = v[v.size() / 2];
    const bool pass = xruns == 0 && mx <= 0.5 * period && p999 <= 0.25 * period;
    std::printf ("callbacks %zu, xruns %d, inside callback: max %.1f us (%.1f%%), p99.9 %.1f us (%.1f%%), p99 %.1f us, median %.2f us -> %s\n", n, xruns, mx,
                 100 * mx / period, p999, 100 * p999 / period, p99, med, control ? "(positive control run, not a gate)" : pass ? "PASS" : "FAIL");
    if (opt ("out").isNotEmpty())
        juce::File (opt ("out")).replaceWithText ("{\"device\": \"" + dev->getName() + "\", \"rate\": " + juce::String (actualFs) + ", \"block\": " + juce::String (actualBlock)
                                                  + ", \"editor\": " + juce::String ((int) editor) + ", \"instances\": " + juce::String (instances)
                                                  + ", \"control\": " + juce::String ((int) control) + ", \"seconds\": " + juce::String (seconds)
                                                  + ", \"callbacks\": " + juce::String ((juce::int64) n) + ", \"xruns\": " + juce::String (xruns)
                                                  + ", \"period_us\": " + juce::String (period, 2) + ", \"max_us\": " + juce::String (mx, 2)
                                                  + ", \"p999_us\": " + juce::String (p999, 2) + ", \"p99_us\": " + juce::String (p99, 2)
                                                  + ", \"median_us\": " + juce::String (med, 3) + ", \"result\": \""
                                                  + (control ? "CONTROL" : pass ? "PASS" : "FAIL") + "\"}\n");
    return control ? (xruns > 0 ? 0 : 5) : (pass ? 0 : 1);
}

int devices()
{
    juce::AudioDeviceManager dm;
    dm.initialise (0, 2, nullptr, false);
    for (auto* type : dm.getAvailableDeviceTypes())
    {
        type->scanForDevices();
        for (auto& name : type->getDeviceNames())
        {
            std::unique_ptr<juce::AudioIODevice> d (type->createDevice (name, {}));
            if (d == nullptr) continue;
            juce::String rates, sizes;
            for (auto r : d->getAvailableSampleRates()) rates << juce::String (r, 0) << " ";
            for (auto b : d->getAvailableBufferSizes()) sizes << b << " ";
            std::printf ("%s / %s\n  rates: %s\n  buffers: %s\n", type->getTypeName().toRawUTF8(), name.toRawUTF8(), rates.toRawUTF8(), sizes.toRawUTF8());
        }
    }
    return 0;
}
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI init;
    for (int i = 2; i < argc; ++i)
    {
        const juce::String a (argv[i]);
        opts.set (a.upToFirstOccurrenceOf ("=", false, false), a.fromFirstOccurrenceOf ("=", false, false));
    }
    const juce::String cmd = argc > 1 ? argv[1] : "";
    if (cmd == "devices") return devices();
    if (cmd == "e2") return e2();
    if (cmd == "e3") return e3();
    std::puts ("usage: afterimage_host devices | e2 vst3=PATH | e3 vst3=PATH device=NAME rate=R block=B seconds=S [editor=1] [instances=N] [control=1]");
    return 1;
}
