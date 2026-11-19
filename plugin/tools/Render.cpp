// SPDX-License-Identifier: AGPL-3.0-only
// Offline renderer for the parity fixtures: runs the realtime Engine over a WAV with sample-stamped commands.
//
//   afterimage_render in=x.wav out=prefix [body=0 ghost=1 dissolve=1 t60=5 seed=1 block=256 pad=2 density=0]
//                     [imprint=at,s0,s1,full|filtered,low,high ...] [clear=at ...] [frames=m0,m1] [grainlog=1]
//
// Writes prefix.out.wav (float32), prefix.loop.wav (last capture's loop), prefix.json, and with options
// prefix.frames.f32 (complex64, frames x channels x K) and prefix.grains.csv.
#include <dsp/Engine.h>
#include <juce_audio_formats/juce_audio_formats.h>

#include <cstdio>
#include <map>
#include <vector>

using namespace afterimage;

namespace
{
bool writeWav (const juce::File& f, const juce::AudioBuffer<float>& b, double fs)
{
    f.deleteFile();
    std::unique_ptr<juce::OutputStream> os = std::make_unique<juce::FileOutputStream> (f);
    auto opts = juce::AudioFormatWriterOptions().withSampleRate (fs).withNumChannels (b.getNumChannels()).withBitsPerSample (32)
                    .withSampleFormat (juce::AudioFormatWriterOptions::SampleFormat::floatingPoint);
    auto w = juce::WavAudioFormat().createWriterFor (os, opts);
    return w != nullptr && w->writeFromAudioSampleBuffer (b, 0, b.getNumSamples());
}
} // namespace

int main (int argc, char** argv)
{
    std::map<juce::String, juce::String> opt;
    std::vector<Command> cmds;
    for (int i = 1; i < argc; ++i)
    {
        const juce::String a (argv[i]);
        const auto key = a.upToFirstOccurrenceOf ("=", false, false), val = a.fromFirstOccurrenceOf ("=", false, false);
        if (key == "imprint" || key == "clear")
        {
            auto t = juce::StringArray::fromTokens (val, ",", "");
            Command c;
            c.type = key == "clear" ? Command::Type::Clear : Command::Type::Imprint;
            c.at = t[0].getLargeIntValue();
            if (key == "imprint")
            {
                c.s0 = t[1].getLargeIntValue();
                c.s1 = t[2].getLargeIntValue();
                c.source = t[3] == "filtered" ? Source::Filtered : Source::Full;
                c.lowHz = t[4].getDoubleValue();
                c.highHz = t[5].getDoubleValue();
            }
            cmds.push_back (c);
        }
        else
            opt[key] = val;
    }
    auto num = [&] (const char* k, double d) { return opt.count (k) ? opt[k].getDoubleValue() : d; };

    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (juce::File (opt["in"])));
    if (reader == nullptr) { std::fprintf (stderr, "cannot read %s\n", opt["in"].toRawUTF8()); return 2; }
    const double fs = reader->sampleRate;
    const int nch = (int) reader->numChannels;
    const int nIn = (int) reader->lengthInSamples, n = nIn + (int) (num ("pad", 0.0) * fs);
    juce::AudioBuffer<float> io (nch, n);
    io.clear();
    reader->read (&io, 0, nIn, 0, true, true);

    Engine e;
    e.prepare (fs, nch, 4096);
    e.setSeed ((uint64_t) num ("seed", 1));
    if (num ("density", 0) > 0) e.setDensityOverride (num ("density", 0));
    std::vector<GrainRecord> grains (opt.count ("grainlog") ? 400000 : 0);
    if (! grains.empty()) e.setGrainLog (grains.data(), (int) grains.size());
    for (auto& c : cmds)
    {
        c.epoch = e.epoch();
        e.submit (c);
    }

    Params p { (float) num ("body", 0), (float) num ("ghost", 1), (float) num ("t60", 5), (float) num ("dissolve", 1) };
    const int block = (int) num ("block", 256);
    juce::String json = "{\n \"fs\": " + juce::String (fs) + ", \"N\": " + juce::String (e.fftSize()) + ", \"H\": " + juce::String (e.hop())
                        + ", \"channels\": " + juce::String (nch) + ",\n \"captures\": [";
    juce::StringArray rejects;
    uint64_t seenCaptures = 0, seenRejects = 0;
    juce::Random jitter (7);
    for (int pos = 0; pos < n;)
    {
        const int b = std::min (block > 0 ? block : 1 + jitter.nextInt (700), n - pos);
        float* ptr[2] = { io.getWritePointer (0) + pos, io.getWritePointer (nch - 1) + pos };
        e.process (ptr, nch, b, p);
        pos += b;
        if (e.status.captures.load() != seenCaptures)
        {
            seenCaptures = e.status.captures.load();
            const auto& c = e.lastCapture();
            json << (seenCaptures > 1 ? "," : "") << "\n  {\"s0\": " << c.s0 << ", \"s1\": " << c.s1 << ", \"period\": " << c.period
                 << ", \"seam\": " << c.seam << ", \"rho\": " << juce::String (c.rho, 12) << ", \"accepted_at\": " << c.acceptedAt
                 << ", \"started_at\": " << c.startedAt << ", \"seed\": " << (juce::int64) c.seed << ", \"slot\": " << c.slot
                 << ", \"source\": \"" << (c.source == Source::Full ? "full" : "filtered") << "\"}";
            juce::AudioBuffer<float> loop (nch, (int) c.period);
            for (int ch = 0; ch < nch; ++ch) loop.copyFrom (ch, 0, e.loopChannel (c.slot, ch), (int) c.period);
            writeWav (juce::File (opt["out"] + ".loop.wav"), loop, fs);
        }
        if (e.status.rejects.load() != seenRejects)
        {
            seenRejects = e.status.rejects.load();
            rejects.add ("\"" + juce::String (rejectName ((Reject) e.status.lastReject.load())) + "\"");
        }
    }
    json << "\n ],\n \"rejects\": [" << rejects.joinIntoString (", ") << "],\n \"max_active_grains\": " << e.maxActiveGrains()
         << ", \"max_active_grains_total\": " << e.maxActiveGrainsTotal() << ", \"overs\": " << (juce::int64) e.status.overs.load()
         << ", \"non_finite\": " << (juce::int64) e.nonFiniteInputs() << "\n}\n";
    juce::File (opt["out"] + ".json").replaceWithText (json);
    writeWav (juce::File (opt["out"] + ".out.wav"), io, fs);

    if (opt.count ("frames"))
    {
        auto t = juce::StringArray::fromTokens (opt["frames"], ",", "");
        juce::FileOutputStream fo (juce::File (opt["out"] + ".frames.f32"));
        fo.truncate();
        for (auto m = t[0].getLargeIntValue(); m <= t[1].getLargeIntValue(); ++m)
            for (int ch = 0; ch < nch; ++ch)
            {
                const auto* f = e.frame (m, ch);
                if (f == nullptr) { std::fprintf (stderr, "frame %lld not in history\n", (long long) m); return 3; }
                fo.write (f, sizeof (std::complex<float>) * (size_t) (e.fftSize() / 2 + 1));
            }
    }
    if (! grains.empty())
    {
        juce::String csv = "onset,length,pos,amp,gain,gl,gr,reverse,dropped\n";
        for (int i = 0; i < e.grainLogCount(); ++i)
        {
            const auto& g = grains[(size_t) i];
            csv << (juce::int64) g.onset << "," << g.length << "," << juce::String (g.pos, 12) << "," << juce::String (g.amp, 12) << ","
                << juce::String (g.gain, 12) << "," << juce::String (g.gl, 12) << "," << juce::String (g.gr, 12) << "," << (int) g.reverse
                << "," << (int) g.dropped << "\n";
        }
        juce::File (opt["out"] + ".grains.csv").replaceWithText (csv);
    }
    return 0;
}
