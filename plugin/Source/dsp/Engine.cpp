// SPDX-License-Identifier: AGPL-3.0-only
#include "Engine.h"

#include <cmath>

namespace afterimage
{

void Engine::prepare (double sampleRate, int numChannels, int /*maxBlockSize*/)
{
    fs = sampleRate;
    numCh = numChannels;
    streamPos = 0;
    nonFinite = 0;
    wasBypassed = false;
    bodyGain.setLength ((int) std::lround (0.02 * fs));
    ghostGain.setLength ((int) std::lround (0.02 * fs));
    bodyGain.reset (1.0);
    ghostGain.reset (0.0);
}

void Engine::process (float* const* io, int nch, int n, const Params& p) noexcept
{
    if (wasBypassed)
    {
        bodyGain.reset (1.0);
        ghostGain.reset (0.0);
        wasBypassed = false;
    }
    bodyGain.setTarget (p.body);
    ghostGain.setTarget (p.ghost);

    for (int c = 0; c < nch; ++c)
        for (int i = 0; i < n; ++i)
            if (! std::isfinite (io[c][i]))
            {
                io[c][i] = 0.0f;
                ++nonFinite;
            }

    for (int i = 0; i < n; ++i)
    {
        const bool unity = bodyGain.atRest() && exactly (bodyGain.target, 1.0);
        const auto b = (float) bodyGain.next();
        ghostGain.next();
        if (! unity)
            for (int c = 0; c < nch; ++c)
                io[c][i] *= b;
    }
    streamPos += n;
}

void Engine::processBypassed (float* const*, int, int n) noexcept
{
    wasBypassed = true;
    streamPos += n;
}

} // namespace afterimage
