// SPDX-License-Identifier: AGPL-3.0-only
#include "PluginEditor.h"

using afterimage::DisplayColumn;

// ---------------------------------------------------------------------------------------------
ParameterLink::ParameterLink (juce::RangedAudioParameter& p, std::function<void (float)> setControl)
    : parameter (p), set (std::move (setControl))
{
    parameter.addListener (this);
}

ParameterLink::~ParameterLink() { parameter.removeListener (this); }

void ParameterLink::setNormalised (float v, bool completeGesture)
{
    if (juce::approximatelyEqual (parameter.getValue(), v)) return;
    if (completeGesture) parameter.beginChangeGesture();
    parameter.setValueNotifyingHost (v);
    if (completeGesture) parameter.endChangeGesture();
}

void ParameterLink::parameterValueChanged (int, float)
{
    if (juce::Thread::getCurrentThreadId() == messageThread) refresh(); // state restore, the editor itself
    else dirty.store (true);                                            // host automation: one atomic store
}

// ---------------------------------------------------------------------------------------------
namespace
{
constexpr double visibleSeconds = 4.0;
const juce::Colour bg (0xff0d0f14), cyan (0xff7fe7f2), violet (0xffb48cff), magenta (0xffff5fd2), amber (0xffffb347);

double bandHz (double band, double fs) { return 20.0 * std::pow (fs / 40.0, band / DisplayColumn::bands); }
} // namespace

SpectrogramView::SpectrogramView (AfterimageProcessor& p) : proc (p) {}

void SpectrogramView::pull()
{
    auto& e = proc.engine();
    const auto scope = e.displayFifo.read (e.displayFifo.getNumReady());
    if (frozen) return; // columns arriving while the user drags are dropped, so the drag maps to a fixed view
    scope.forEach ([&] (int i) {
        const auto& c = e.display[(size_t) i];
        if (! cols.empty() && cols.back().epoch != c.epoch) cols.clear();
        cols.push_back (c);
    });
    const auto maxCols = (size_t) std::ceil (visibleSeconds * e.sampleRate() / std::max (1, e.hop())) + 1;
    while (cols.size() > maxCols) cols.pop_front();
}

int64_t SpectrogramView::sampleAtX (float x) const
{
    // a column's time is its window centre (end_sample - N/2), as in p0.capture.frames_for_interval
    if (cols.size() < 2) return 0;
    const auto half = proc.engine().fftSize() / 2;
    const double t0 = (double) (cols.front().endSample - half), t1 = (double) (cols.back().endSample - half);
    return (int64_t) std::llround (t0 + (t1 - t0) * juce::jlimit (0.0f, 1.0f, x / (float) getWidth()));
}

float SpectrogramView::xForSample (int64_t s) const
{
    if (cols.size() < 2) return 0.0f;
    const auto half = proc.engine().fftSize() / 2;
    const double t0 = (double) (cols.front().endSample - half), t1 = (double) (cols.back().endSample - half);
    return (float) (((double) s - t0) / (t1 - t0) * getWidth());
}

double SpectrogramView::hzAtY (float y) const
{
    return bandHz ((1.0 - juce::jlimit (0.0f, 1.0f, y / (float) getHeight())) * DisplayColumn::bands, proc.engine().sampleRate());
}

float SpectrogramView::yForHz (double hz) const
{
    const double fs = proc.engine().sampleRate();
    return (float) ((1.0 - std::log (hz / 20.0) / std::log (fs / 40.0)) * getHeight());
}

void SpectrogramView::paint (juce::Graphics& g)
{
    g.fillAll (bg);
    if (cols.empty())
    {
        g.setColour (juce::Colours::grey);
        g.drawText ("no analysis data yet (the spectrogram shows only frames the engine has analysed)", getLocalBounds(), juce::Justification::centred);
        return;
    }
    const float w = (float) getWidth() / (float) std::max<size_t> (cols.size() - 1, 1), bh = (float) getHeight() / DisplayColumn::bands;
    for (size_t i = 0; i < cols.size(); ++i)
        for (int band = 0; band < DisplayColumn::bands; ++band)
        {
            const float v = juce::jlimit (0.0f, 1.0f, (cols[i].db[(size_t) band] + 90.0f) / 90.0f);
            if (v <= 0.02f) continue;
            g.setColour (cyan.withAlpha (v));
            g.fillRect ((float) i * w - 0.5f * w, (float) getHeight() - (float) (band + 1) * bh, w + 0.5f, bh + 0.5f);
        }

    auto& st = proc.engine().status;
    if (st.voices.load() > 0) // the region the sounding voice was captured from, if still in view
    {
        const float x0 = xForSample (st.lastS0.load()), x1 = xForSample (st.lastS1.load());
        if (x1 > 0 && x0 < (float) getWidth())
        {
            g.setColour (magenta.withAlpha (0.8f));
            g.drawRect (juce::Rectangle<float> (x0, 0.0f, x1 - x0, (float) getHeight()), 1.0f);
        }
    }
    if (sel.valid) // drawn from the selected samples and band, so it moves with the audio once scrolling resumes
    {
        const auto r = juce::Rectangle<float> (juce::Point<float> (xForSample (sel.s0), yForHz (sel.highHz)),
                                               juce::Point<float> (xForSample (sel.s1), yForHz (sel.lowHz)));
        g.setColour (violet.withAlpha (0.18f));
        g.fillRect (r);
        g.setColour (violet);
        g.drawRect (r, 1.5f);
    }
    g.setFont (11.0f);
    for (double hz : { 100.0, 1000.0, 10000.0 })
    {
        const auto r = juce::Rectangle<int> (2, (int) yForHz (hz) - 7, 46, 14);
        g.setColour (bg.withAlpha (0.75f));
        g.fillRect (r);
        g.setColour (juce::Colours::lightgrey);
        g.drawText (hz >= 1000 ? juce::String (hz / 1000, 0) + " kHz" : juce::String ((int) hz) + " Hz", r.reduced (2, 0), juce::Justification::left);
    }
    g.setColour (juce::Colours::grey);
    g.drawText ("past " + juce::String (visibleSeconds, 0) + " s", 4, getHeight() - 16, 100, 14, juce::Justification::left);
    g.drawText ("now", getWidth() - 40, getHeight() - 16, 36, 14, juce::Justification::right);
    if (frozen)
    {
        g.setColour (amber);
        g.drawText ("view held while selecting", getWidth() - 200, 4, 196, 14, juce::Justification::right);
    }
}

void SpectrogramView::mouseDown (const juce::MouseEvent& e)
{
    frozen = true;
    a = b = e.position;
    sel.valid = false;
    repaint();
}

void SpectrogramView::mouseDrag (const juce::MouseEvent& e)
{
    b = e.position.withX (juce::jlimit (0.0f, (float) getWidth(), e.position.x)).withY (juce::jlimit (0.0f, (float) getHeight(), e.position.y));
    updateSelection();
    repaint();
}

void SpectrogramView::mouseUp (const juce::MouseEvent&)
{
    updateSelection();
    frozen = false;
    repaint();
}

void SpectrogramView::updateSelection()
{
    if (cols.size() < 2) { sel.valid = false; return; }
    const auto x0 = std::min (a.x, b.x), x1 = std::max (a.x, b.x), y0 = std::min (a.y, b.y), y1 = std::max (a.y, b.y);
    sel.s0 = sampleAtX (x0);
    sel.s1 = sampleAtX (x1);
    sel.highHz = hzAtY (y0);
    sel.lowHz = hzAtY (y1);
    sel.epoch = cols.back().epoch;
    sel.valid = sel.s1 > sel.s0;
}

// ---------------------------------------------------------------------------------------------
AfterimageEditor::AfterimageEditor (AfterimageProcessor& p) : AudioProcessorEditor (&p), proc (p), spectrogram (p)
{
    addAndMakeVisible (spectrogram);
    addKnob ("body", "BODY");
    addKnob ("ghost", "GHOST");
    addKnob ("memory_t60", "MEMORY");
    addKnob ("dissolve", "DISSOLVE");

    auto* srcParam = dynamic_cast<juce::RangedAudioParameter*> (proc.apvts.getParameter ("source"));
    source.addItemList ({ "FULL", "FILTERED" }, 1);
    sourceLink = std::make_unique<ParameterLink> (*srcParam, [this] (float v) { source.setSelectedItemIndex (v > 0.5f ? 1 : 0, juce::dontSendNotification); });
    source.onChange = [this] { sourceLink->setNormalised ((float) source.getSelectedItemIndex(), true); };
    sourceLink->refresh();
    addAndMakeVisible (source);

    imprintButton.onClick = [this] { imprint(); };
    clearButton.onClick = [this] {
        afterimage::Command c;
        c.type = afterimage::Command::Type::Clear;
        proc.postCommand (c);
    };
    imprintButton.setColour (juce::TextButton::buttonColourId, violet.darker (0.6f));
    addAndMakeVisible (imprintButton);
    addAndMakeVisible (clearButton);
    for (auto* l : { &status, &selectionInfo })
    {
        l->setFont (juce::FontOptions (13.0f));
        l->setColour (juce::Label::textColourId, juce::Colours::lightgrey);
        l->setJustificationType (juce::Justification::topLeft);
        addAndMakeVisible (*l);
    }
    setSize (960, 600);
    startTimerHz (30);
}

AfterimageEditor::~AfterimageEditor() { stopTimer(); }

void AfterimageEditor::addKnob (const char* id, const char* name)
{
    auto* param = dynamic_cast<juce::RangedAudioParameter*> (proc.apvts.getParameter (id));
    Knob k;
    k.slider = std::make_unique<juce::Slider> (juce::Slider::RotaryHorizontalVerticalDrag, juce::Slider::TextBoxBelow);
    k.slider->setRange (0.0, 1.0);
    k.slider->textFromValueFunction = [param] (double v) { return juce::String (param->convertFrom0to1 ((float) v), 2) + " " + param->getLabel(); };
    k.slider->setDoubleClickReturnValue (true, param->getDefaultValue());
    auto* s = k.slider.get();
    k.link = std::make_unique<ParameterLink> (*param, [s] (float v) { s->setValue (v, juce::dontSendNotification); });
    auto* link = k.link.get();
    s->onDragStart = [link] { link->begin(); };
    s->onDragEnd = [link] { link->end(); };
    s->onValueChange = [link, s] { link->setNormalised ((float) s->getValue(), ! s->isMouseButtonDown()); };
    link->refresh();
    k.label = std::make_unique<juce::Label> ("", name);
    k.label->setJustificationType (juce::Justification::centred);
    addAndMakeVisible (*k.slider);
    addAndMakeVisible (*k.label);
    knobs.push_back (std::move (k));
}

void AfterimageEditor::imprint()
{
    const auto sel = spectrogram.selection();
    if (! sel.valid) return;
    afterimage::Command c;
    c.epoch = sel.epoch;
    c.s0 = sel.s0;
    c.s1 = sel.s1;
    c.source = proc.currentSource();
    c.lowHz = sel.lowHz;
    c.highHz = std::min (sel.highHz, proc.engine().sampleRate() / 2);
    proc.postCommand (c);
}

void AfterimageEditor::timerCallback()
{
    for (auto& k : knobs) k.link->poll();
    sourceLink->poll();
    spectrogram.pull();
    spectrogram.repaint();

    auto& e = proc.engine();
    auto& st = e.status;
    const double fs = e.sampleRate() > 0 ? e.sampleRate() : 1.0;
    const auto ms = [fs] (int64_t n) { return juce::String (1000.0 * (double) n / fs, 1) + " ms"; };
    const float peak = st.blockPeak.load();
    if (peak >= peakHold || --peakHoldTicks <= 0) { peakHold = peak; peakHoldTicks = 45; }
    const char* states[] = { "IDLE", "WAITING FOR AUDIO", "BUILDING" };
    const auto rej = (afterimage::Reject) st.lastReject.load();

    juce::String s;
    s << "CAPTURE  " << states[juce::jlimit (0, 2, st.state.load())] << "    voices " << st.voices.load() << "    grains " << st.grains.load() << "\n";
    s << "last reject  " << (rej == afterimage::Reject::None ? "none" : afterimage::rejectName (rej)) << "   (total " << (juce::int64) st.rejects.load() << ")\n";
    if (st.captures.load() > 0)
        s << "last capture  " << (st.lastSource.load() ? "FILTERED" : "FULL") << ", selected " << ms (st.lastS1.load() - st.lastS0.load())
          << ", loop period " << ms (st.lastPeriod.load()) << " (" << (juce::int64) st.lastPeriod.load() << " samples), seam " << ms (st.lastSeam.load())
          << " post-roll, rho " << juce::String (st.lastRho.load(), 3) << ", request-to-sound " << ms (st.lastDelay.load()) << "\n";
    else
        s << "last capture  none\n";
    s << "output peak  " << (peakHold > 0 ? juce::String (juce::Decibels::gainToDecibels (peakHold), 1) + " dBFS" : juce::String ("-inf")) << "   overs > 0 dBFS: "
      << (juce::int64) st.overs.load() << (peakHold > 1.0f ? "   OVER 0 dBFS (no limiter)" : "") << "\n";
    s << "non-finite input samples replaced: " << (juce::int64) st.nonFinite.load() << "\n";
    s << juce::String (fs, 0) << " Hz, N " << e.fftSize() << ", hop " << e.hop() << ", epoch " << (int) st.epoch.load() << ", latency 0 samples";
    status.setText (s, juce::dontSendNotification);
    status.setColour (juce::Label::textColourId, peakHold > 1.0f ? amber : juce::Colours::lightgrey);

    const auto sel = spectrogram.selection();
    const auto dur = sel.s1 - sel.s0;
    selectionInfo.setText (sel.valid ? "selection " + ms (dur) + " (" + juce::String ((juce::int64) dur) + " samples)  ->  loop period "
                                           + ms (dur) + ";  " + juce::String (sel.lowHz, 0) + "-" + juce::String (sel.highHz, 0) + " Hz"
                                           + (proc.currentSource() == afterimage::Source::Full ? " (band ignored: SOURCE FULL)" : "")
                                           + (dur < (int64_t) (0.2 * fs) || dur > (int64_t) (1.5 * fs) ? "  -- outside 0.20-1.50 s, will be rejected" : "")
                                     : juce::String ("drag on the spectrogram to select a time-frequency region (0.20-1.50 s), then IMPRINT"),
                           juce::dontSendNotification);
    imprintButton.setEnabled (sel.valid);
}

void AfterimageEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff16181d));
    g.setColour (juce::Colours::white);
    g.setFont (juce::FontOptions (18.0f, juce::Font::bold));
    g.drawText ("AFTERIMAGE", 16, 8, 300, 24, juce::Justification::left);
    g.setColour (juce::Colours::grey);
    g.setFont (juce::FontOptions (12.0f));
    g.drawText ("P1-A development interface -- not the product UI", getWidth() - 416, 12, 400, 18, juce::Justification::right);
}

void AfterimageEditor::resized()
{
    auto r = getLocalBounds().reduced (16);
    r.removeFromTop (28);
    spectrogram.setBounds (r.removeFromTop (280));
    r.removeFromTop (6);
    selectionInfo.setBounds (r.removeFromTop (20));
    r.removeFromTop (6);
    auto row = r.removeFromTop (120);
    auto buttons = row.removeFromRight (180);
    imprintButton.setBounds (buttons.removeFromTop (40).reduced (4));
    clearButton.setBounds (buttons.removeFromTop (40).reduced (4));
    source.setBounds (buttons.removeFromTop (34).reduced (4));
    const int w = row.getWidth() / (int) knobs.size();
    for (auto& k : knobs)
    {
        auto cell = row.removeFromLeft (w);
        k.label->setBounds (cell.removeFromTop (18));
        k.slider->setBounds (cell);
    }
    status.setBounds (r.reduced (0, 6));
}
