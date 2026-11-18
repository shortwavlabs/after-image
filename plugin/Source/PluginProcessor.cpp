// SPDX-License-Identifier: AGPL-3.0-only
#include "PluginProcessor.h"

namespace
{
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
             std::make_unique<AudioParameterChoice> (ParameterID { "source", 1 }, "Source", StringArray { "FULL", "FILTERED" }, 0) };
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
}

afterimage::Params AfterimageProcessor::readParams() const noexcept
{
    return { body->load(), ghost->load(), memory->load(), dissolve->load() };
}

void AfterimageProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int nch = juce::jmin (getMainBusNumOutputChannels(), buffer.getNumChannels());
    for (int c = nch; c < buffer.getNumChannels(); ++c)
        buffer.clear (c, 0, buffer.getNumSamples());
    commandFifo.read (commandFifo.getNumReady()).forEach ([this] (int i) { dsp.submit (commands[(size_t) i]); });
    dsp.process (buffer.getArrayOfWritePointers(), nch, buffer.getNumSamples(), readParams());
}

void AfterimageProcessor::processBlockBypassed (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int nch = juce::jmin (getMainBusNumOutputChannels(), buffer.getNumChannels());
    commandFifo.read (commandFifo.getNumReady()).forEach ([this] (int i) { dsp.submit (commands[(size_t) i]); });
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
    return new juce::GenericAudioProcessorEditor (*this);
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
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AfterimageProcessor();
}
