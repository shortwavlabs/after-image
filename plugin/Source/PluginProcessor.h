// SPDX-License-Identifier: AGPL-3.0-only
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "dsp/Engine.h"

class AfterimageProcessor final : public juce::AudioProcessor
{
public:
    AfterimageProcessor();

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout&) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    void processBlockBypassed (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "AFTERIMAGE"; }
    bool acceptsMidi() const override { return true; } // VST3 MIDI triggers (P1-B); the AU stays aufx
    bool producesMidi() const override { return false; }
    double getTailLengthSeconds() const override;

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock&) override;
    void setStateInformation (const void*, int) override;

    juce::AudioProcessorValueTreeState apvts;
    afterimage::Engine& engine() noexcept { return dsp; }

    /** Message thread (single producer): queue an IMPRINT/CLEAR for the audio thread. False if the queue is full. */
    bool postCommand (const afterimage::Command&);
    afterimage::Source currentSource() const noexcept { return source->load() > 0.5f ? afterimage::Source::Filtered : afterimage::Source::Full; }

    static constexpr double maxT60 = 30.0;

private:
    afterimage::Params readParams() const noexcept;
    void forwardTriggers (const juce::MidiBuffer&, bool bypassed) noexcept;

    afterimage::Engine dsp;
    juce::AbstractFifo commandFifo { 32 };
    std::array<afterimage::Command, 32> commands;
    std::atomic<float>* body = nullptr;
    std::atomic<float>* ghost = nullptr;
    std::atomic<float>* memory = nullptr;
    std::atomic<float>* dissolve = nullptr;
    std::atomic<float>* source = nullptr;
    std::vector<std::atomic<float>*> sched; // capture_mode .. auto_cooldown, in layout order
    std::atomic<bool> resyncImprint { true };
    std::atomic<uint32_t> restoreSeq { 0 }; // odd while setStateInformation runs (seqlock)
    uint32_t lastRestoreSeq = 0;
    float lastImprint = 0.0f;
    int cc64 = 0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (AfterimageProcessor)
};
