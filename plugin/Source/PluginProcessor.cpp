// SPDX-License-Identifier: AGPL-3.0-only
#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
juce::NormalisableRange<float> logRange (float lo, float hi)
{
    juce::NormalisableRange<float> r (lo, hi);
    r.setSkewForCentre (std::sqrt (lo * hi));
    return r;
}

constexpr float lengths[] = { 0.25f, 0.5f, 0.75f, 1.0f, 1.5f };

juce::AudioProcessorValueTreeState::ParameterLayout makeLayout()
{
    using namespace juce;
    NormalisableRange<float> t60 (0.25f, (float) AfterimageProcessor::maxT60, 0.0f);
    t60.setSkewForCentre (5.0f);
    return { std::make_unique<AudioParameterFloat> (ParameterID { "body", 1 }, "Body", NormalisableRange<float> (0.0f, 1.0f), 1.0f),
             std::make_unique<AudioParameterFloat> (ParameterID { "ghost", 1 }, "Ghost", NormalisableRange<float> (0.0f, 1.0f), 0.5f),
             std::make_unique<AudioParameterFloat> (ParameterID { "memory_t60", 1 }, "Memory", t60, 5.0f,
                                                    AudioParameterFloatAttributes().withLabel ("s")),
             std::make_unique<AudioParameterFloat> (ParameterID { "dissolve", 1 }, "Dissolve", NormalisableRange<float> (0.0f, 1.0f), 1.0f),
             std::make_unique<AudioParameterChoice> (ParameterID { "source", 1 }, "Source", StringArray { "FULL", "FILTERED" }, 0),
             // P1-B capture scheduler (docs/P1-B-UX-CONTRACT.md 3)
             std::make_unique<AudioParameterChoice> (ParameterID { "capture_mode", 1 }, "Capture mode", StringArray { "MANUAL", "RANDOM", "AUTO" }, 0),
             std::make_unique<AudioParameterChoice> (ParameterID { "capture_length", 1 }, "Capture length",
                                                     StringArray { "250 ms", "500 ms", "750 ms", "1000 ms", "1500 ms" }, 2),
             std::make_unique<AudioParameterFloat> (ParameterID { "band_center", 1 }, "Band centre", logRange (80.0f, 8000.0f), 1000.0f,
                                                    AudioParameterFloatAttributes().withLabel ("Hz")),
             std::make_unique<AudioParameterFloat> (ParameterID { "band_width", 1 }, "Band width", NormalisableRange<float> (0.5f, 8.0f), 3.0f,
                                                    AudioParameterFloatAttributes().withLabel ("oct")),
             std::make_unique<AudioParameterBool> (ParameterID { "hold", 1 }, "Hold", false),
             std::make_unique<AudioParameterBool> (ParameterID { "imprint", 1 }, "Imprint (trigger)", false),
             std::make_unique<AudioParameterFloat> (ParameterID { "random_interval", 1 }, "Random interval", logRange (1.0f, 16.0f), 4.0f,
                                                    AudioParameterFloatAttributes().withLabel ("s")),
             std::make_unique<AudioParameterFloat> (ParameterID { "activity_gate", 1 }, "Activity gate", NormalisableRange<float> (-72.0f, -24.0f), -48.0f,
                                                    AudioParameterFloatAttributes().withLabel ("dBFS")),
             std::make_unique<AudioParameterFloat> (ParameterID { "auto_sensitivity", 1 }, "Auto sensitivity", NormalisableRange<float> (0.0f, 1.0f), 0.5f),
             std::make_unique<AudioParameterFloat> (ParameterID { "auto_cooldown", 1 }, "Auto cooldown", logRange (0.5f, 8.0f), 2.0f,
                                                    AudioParameterFloatAttributes().withLabel ("s")) };
}
} // namespace

AfterimageProcessor::AfterimageProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "AFTERIMAGE", makeLayout())
{
    body = apvts.getRawParameterValue ("body");
    ghost = apvts.getRawParameterValue ("ghost");
    memory = apvts.getRawParameterValue ("memory_t60");
    dissolve = apvts.getRawParameterValue ("dissolve");
    source = apvts.getRawParameterValue ("source");
    for (auto* id : { "capture_mode", "capture_length", "band_center", "band_width", "hold", "imprint", "random_interval",
                      "activity_gate", "auto_sensitivity", "auto_cooldown" })
        sched.push_back (apvts.getRawParameterValue (id));
}

bool AfterimageProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto in = layouts.getMainInputChannelSet(), out = layouts.getMainOutputChannelSet();
    return in == out && (out == juce::AudioChannelSet::mono() || out == juce::AudioChannelSet::stereo());
}

void AfterimageProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    setLatencySamples (0);
    dsp.prepare (sampleRate, getMainBusNumOutputChannels(), samplesPerBlock);
    resyncImprint = true; // an "on" trigger value is never an edge after (re)preparation
    cc64 = 0;
}

afterimage::Params AfterimageProcessor::readParams() const noexcept
{
    afterimage::Params p { body->load(), ghost->load(), memory->load(), dissolve->load() };
    p.mode = (afterimage::Mode) juce::jlimit (0, 2, (int) sched[0]->load());
    p.lengthSeconds = lengths[juce::jlimit (0, 4, (int) sched[1]->load())];
    p.source = currentSource();
    p.bandCenterHz = sched[2]->load();
    p.bandWidthOct = sched[3]->load();
    p.hold = sched[4]->load() > 0.5f;
    p.randomIntervalSeconds = sched[6]->load();
    p.gateDb = sched[7]->load();
    p.sensitivity = sched[8]->load();
    p.cooldownSeconds = sched[9]->load();
    return p;
}

void AfterimageProcessor::forwardTriggers (const juce::MidiBuffer& midi, bool bypassed) noexcept
{
    using afterimage::Command;
    using afterimage::Origin;
    using afterimage::Outcome;
    commandFifo.read (commandFifo.getNumReady()).forEach ([this] (int i) { dsp.submit (commands[(size_t) i]); });

    // automation trigger: rising edge at block resolution (P1-B architecture 5)
    const float v = sched[5]->load();
    if (resyncImprint.exchange (false)) lastImprint = v;
    else if (lastImprint < 0.5f && v >= 0.5f)
    {
        Command c;
        c.type = Command::Type::Trigger;
        c.origin = Origin::Automation;
        if (bypassed) dsp.noteUnforwarded (Origin::Automation, Outcome::IgnoredBypass);
        else dsp.submit (c);
    }
    lastImprint = v;

    // MIDI (VST3): Note On or CC 64 rising, sample-accurate, one per block
    bool sent = false;
    for (const auto m : midi)
    {
        const auto msg = m.getMessage();
        bool trigger = msg.isNoteOn();
        if (msg.isController() && msg.getControllerNumber() == 64)
        {
            trigger = cc64 < 64 && msg.getControllerValue() >= 64;
            cc64 = msg.getControllerValue();
        }
        if (! trigger) continue;
        if (bypassed) { dsp.noteUnforwarded (Origin::Midi, Outcome::IgnoredBypass); continue; }
        if (sent) { dsp.noteUnforwarded (Origin::Midi, Outcome::DroppedRate); continue; }
        Command c;
        c.type = Command::Type::Trigger;
        c.origin = Origin::Midi;
        c.at = dsp.samplesSeen() + m.samplePosition;
        dsp.submit (c);
        sent = true;
    }
}

void AfterimageProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    const int nch = juce::jmin (getMainBusNumOutputChannels(), buffer.getNumChannels());
    for (int c = nch; c < buffer.getNumChannels(); ++c)
        buffer.clear (c, 0, buffer.getNumSamples());
    forwardTriggers (midi, false);
    dsp.process (buffer.getArrayOfWritePointers(), nch, buffer.getNumSamples(), readParams());
}

void AfterimageProcessor::processBlockBypassed (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    const int nch = juce::jmin (getMainBusNumOutputChannels(), buffer.getNumChannels());
    forwardTriggers (midi, true);
    dsp.processBypassed (buffer.getArrayOfWritePointers(), nch, buffer.getNumSamples(), readParams());
}

bool AfterimageProcessor::postCommand (const afterimage::Command& c)
{
    auto scope = commandFifo.write (1);
    if (scope.blockSize1 == 0) return false;
    commands[(size_t) scope.startIndex1] = c;
    return true;
}

double AfterimageProcessor::getTailLengthSeconds() const
{
    // MEMORY envelope falls 100 dB in (100 / 60) * T60; plus onset and release fades.
    return maxT60 * 100.0 / 60.0 + 0.1;
}

juce::AudioProcessorEditor* AfterimageProcessor::createEditor()
{
    return new AfterimageEditor (*this);
}

void AfterimageProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    if (auto xml = apvts.copyState().createXml())
        copyXmlToBinary (*xml, dest);
}

void AfterimageProcessor::setStateInformation (const void* data, int size)
{
    if (auto xml = getXmlFromBinary (data, size))
        if (xml->hasTagName (apvts.state.getType()))
        {
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
            resyncImprint = true; // a restored "on" trigger never captures
        }
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AfterimageProcessor();
}
