// SPDX-License-Identifier: AGPL-3.0-only
// Minimal development interface for auditioning P1-A. Not the product UI (docs/UI-CONCEPT.md).
// Everything shown comes from the engine: the spectrogram from its analysis columns, the status from its atomics.
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "PluginProcessor.h"

#include <deque>

/** One parameter <-> one control, in normalised units. Host automation off the message thread only sets a flag;
    a timer applies it (juce-plugin skill: host-automation-and-editor-sync). */
class ParameterLink final : private juce::AudioProcessorParameter::Listener
{
public:
    ParameterLink (juce::RangedAudioParameter& p, std::function<void (float)> setControl);
    ~ParameterLink() override;
    void refresh() { set (parameter.getValue()); }
    void poll() { if (dirty.exchange (false)) refresh(); }
    void begin() { parameter.beginChangeGesture(); }
    void end() { parameter.endChangeGesture(); }
    void setNormalised (float v, bool completeGesture);

    juce::RangedAudioParameter& parameter;

private:
    void parameterValueChanged (int, float) override;
    void parameterGestureChanged (int, bool) override {}
    std::function<void (float)> set;
    const juce::Thread::ThreadID messageThread = juce::Thread::getCurrentThreadId();
    std::atomic<bool> dirty { false };
};

class SpectrogramView final : public juce::Component
{
public:
    explicit SpectrogramView (AfterimageProcessor&);
    void pull();                 // message thread: drain the engine's display FIFO
    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;

    struct Selection { bool valid = false; int64_t s0 = 0, s1 = 0; double lowHz = 0, highHz = 0; uint32_t epoch = 0; };
    Selection selection() const { return sel; }
    void setSelectionForTest (int64_t s0, int64_t s1, double lo, double hi)
    {
        sel = { true, s0, s1, lo, hi, cols.empty() ? 0u : cols.back().epoch };
    }

    // test hooks
    size_t numColumns() const { return cols.size(); }
    float columnX (size_t i) const { return (float) ((double) i * getWidth() / (double) (cols.size() - 1)); }
    int64_t centre (size_t i) const;
    int64_t sampleAtX (float x) const;
    float xForSample (int64_t s) const;

private:
    double hzAtY (float y) const;
    float yForHz (double hz) const;
    void updateSelection();

    AfterimageProcessor& proc;
    std::deque<afterimage::DisplayColumn> cols;
    bool frozen = false;
    juce::Point<float> a, b;
    Selection sel;
};

class AfterimageEditor final : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit AfterimageEditor (AfterimageProcessor&);
    ~AfterimageEditor() override;
    void paint (juce::Graphics&) override;
    void resized() override;

    // test hooks
    void refreshNow() { timerCallback(); }
    juce::String statusText() const { return status.getText(); }
    double knobValue (int i) const { return knobs[(size_t) i].slider->getValue(); }
    void select (int64_t s0, int64_t s1, double lowHz, double highHz) { spectrogram.setSelectionForTest (s0, s1, lowHz, highHz); }
    void pressImprint() { imprint(); }
    SpectrogramView& view() { return spectrogram; }

private:
    void timerCallback() override;
    void addKnob (const char* id, const char* name);
    void imprint();

    AfterimageProcessor& proc;
    SpectrogramView spectrogram;
    struct Knob { std::unique_ptr<juce::Slider> slider; std::unique_ptr<juce::Label> label; std::unique_ptr<ParameterLink> link; };
    std::vector<Knob> knobs;
    juce::ComboBox source;
    std::unique_ptr<ParameterLink> sourceLink;
    juce::TextButton imprintButton { "IMPRINT" }, clearButton { "CLEAR" };
    juce::Label status, selectionInfo;
    float peakHold = 0.0f;
    int peakHoldTicks = 0;
};
