// SPDX-License-Identifier: AGPL-3.0-only
// FFT unit timing (shell stage). Release build only; numbers are for the machine that ran it.
#include <juce_dsp/juce_dsp.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <vector>

int main()
{
    using clock = std::chrono::steady_clock;
    for (int order : { 12, 13 })
    {
        const int N = 1 << order;
        juce::dsp::FFT fft (order);
        std::vector<float> buf ((size_t) (2 * N)), win ((size_t) N);
        for (int i = 0; i < N; ++i) win[(size_t) i] = std::sqrt (0.5f - 0.5f * std::cos (6.2831853f * (float) i / (float) N));
        std::vector<double> fwd, inv;
        for (int it = 0; it < 20000; ++it)
        {
            for (int i = 0; i < N; ++i) buf[(size_t) i] = win[(size_t) i] * std::sin (0.001f * (float) (i + it));
            auto t0 = clock::now();
            fft.performRealOnlyForwardTransform (buf.data(), true);
            auto t1 = clock::now();
            fft.performRealOnlyInverseTransform (buf.data());
            auto t2 = clock::now();
            fwd.push_back (std::chrono::duration<double, std::micro> (t1 - t0).count());
            inv.push_back (std::chrono::duration<double, std::micro> (t2 - t1).count());
        }
        for (auto* v : { &fwd, &inv })
        {
            std::sort (v->begin(), v->end());
            std::printf ("N=%d %s  median %.2f us  p99 %.2f us  p99.9 %.2f us  max %.2f us\n", N, v == &fwd ? "forward" : "inverse",
                         (*v)[v->size() / 2], (*v)[v->size() * 99 / 100], (*v)[v->size() * 999 / 1000], v->back());
        }
    }
    return 0;
}
