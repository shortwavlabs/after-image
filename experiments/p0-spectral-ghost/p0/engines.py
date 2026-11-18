# SPDX-License-Identifier: AGPL-3.0-only
"""Ghost engines operating on one Capture. Each returns (audio, info).

  freeze()  - baseline: conventional single-frame spectral freeze
  loop()    - candidate A: WOLA resynthesis of the captured frames, looped
              with a time-domain crossfade (DSP-ARCHITECTURE 6)
  sustain() - candidate B: phase-vocoder sustain with per-bin instantaneous
              frequency and phase accumulation (DSP-ARCHITECTURE 7)

Audio is (n_samples, channels), raw (no envelope, no level matching). Sample 0
is the first fully overlapped synthesis sample. All engines are deterministic.
"""
import numpy as np

from .stft import hop, istft_buffer


class EngineError(Exception):
    pass


def _synth_frame_count(n_samples, N):
    return -(-n_samples // hop(N)) + 3


def _render(Y, N, n_samples):
    return istft_buffer(Y, N)[N - hop(N):N - hop(N) + n_samples]


def _expected_advance(N):
    """Phase advance per hop of each bin centre: 2*pi*k*H/N."""
    return 2 * np.pi * np.arange(N // 2 + 1) * hop(N) / N


def oneshot(cap):
    """The capture itself, with the full time x frequency mask, played once."""
    return istft_buffer(cap.masked_frames.astype(np.complex128), cap.N)


# --------------------------------------------------------------------------
# Baseline: conventional spectral freeze
# --------------------------------------------------------------------------
def freeze(cap, n_samples, frame=None, phase_mode="delta", seed=0):
    """Hold one frame's magnitudes forever.

    phase_mode "delta":  each bin keeps rotating by the phase step measured
                         between the frozen frame and its predecessor.
    phase_mode "random": new uniformly random phase offset per bin per frame
                         (shared by both channels), the other common variant.
    """
    F = cap.frames.astype(np.complex128)
    c = max(len(F) // 2 if frame is None else frame, 1)
    A, theta0 = np.abs(F[c]), np.angle(F[c])
    Q = _synth_frame_count(n_samples, cap.N)
    if phase_mode == "delta":
        dphi = np.angle(F[c] * np.conj(F[c - 1]))
        theta = theta0 + np.arange(Q)[:, None, None] * dphi
    elif phase_mode == "random":
        rng = np.random.default_rng(seed)
        theta = theta0 + rng.uniform(-np.pi, np.pi, (Q, 1, A.shape[-1]))
    else:
        raise ValueError(phase_mode)
    return _render(A * np.exp(1j * theta), cap.N, n_samples), {"frame": c, "phase_mode": phase_mode}


# --------------------------------------------------------------------------
# Candidate A: spectral loop
# --------------------------------------------------------------------------
def loop(cap, n_samples, xfade_s=0.08, strategy="equal_power", max_lag_s=0.025):
    """Loop the fully overlapped interior of the resynthesised capture.

    The ISTFT of M captured frames is only fully overlapped (and therefore a
    faithful copy of the masked source) over (M - 3) hops; the partial-overlap
    head and tail are discarded. The time feather of the capture is not used:
    the seam crossfade replaces it.

    One loop period is precomputed: per[0:X] crossfades the material following
    the loop end (fading out) into the loop start (fading in), so the stream is
    exactly periodic with period R and both channels share R, X and the gains.

    strategy:
      "hard"        no crossfade (negative control, expected to click)
      "equal_power" sin/cos gains, loop end fixed
      "linear"      linear gains, loop end fixed
      "aligned"     loop end searched within max_lag_s for the highest
                    correlation rho between the overlapped regions, then
                    linear gains normalised by sqrt(a^2 + b^2 + 2*rho*a*b) so
                    the expected power stays constant through the seam
    """
    N, H, fs = cap.N, hop(cap.N), cap.fs
    M = cap.frames.shape[0]
    P = (M - 3) * H
    if P < 2:
        raise EngineError(f"capture of {M} frames has no fully overlapped interior at N={N}")
    seg = istft_buffer(cap.frames.astype(np.complex128), N)[N - H:M * H]
    X_req = 0 if strategy == "hard" else int(round(xfade_s * fs))
    X = min(X_req, P // 2)  # fallback: a loop must be at least twice its crossfade
    R, rho, lag = P - X, None, 0
    if X > 0:
        head = seg[:X]

        def corr(r):
            t = seg[r:r + X]
            d = np.sqrt(np.sum(head ** 2) * np.sum(t ** 2))
            return float(np.sum(head * t) / d) if d > 0 else 0.0

        if strategy == "aligned":
            lo = max(X, P - X - int(max_lag_s * fs))
            cands = np.arange(lo, P - X + 1)
            scores = np.array([corr(r) for r in cands])
            R = int(cands[np.argmax(scores)])
            lag = P - X - R
        rho = corr(R)
        t = np.arange(X) / X
        if strategy == "equal_power":
            a, b = np.sin(0.5 * np.pi * t), np.cos(0.5 * np.pi * t)
        elif strategy == "linear":
            a, b = t, 1 - t
        elif strategy == "aligned":
            a, b = t, 1 - t
            g = np.sqrt(a ** 2 + b ** 2 + 2 * max(rho, 0.0) * a * b)
            a, b = a / g, b / g
        else:
            raise ValueError(strategy)
        per = seg[:R].copy()
        per[:X] = seg[:X] * a[:, None] + seg[R:R + X] * b[:, None]
    elif strategy == "hard":
        per = seg[:R].copy()
    else:
        raise EngineError(f"interior of {P} samples is too short for any crossfade")
    reps = -(-n_samples // R)
    out = np.tile(per, (reps, 1))[:n_samples]
    seams = [s for i in range(reps + 1) for s in (i * R, i * R + X) if 0 < s < n_samples]
    info = {"period_samples": R, "period_s": R / fs, "interior_samples": P, "xfade_samples": X,
            "xfade_requested_samples": X_req, "fallback_short_xfade": bool(X < X_req),
            "seam_correlation": rho, "align_lag_samples": lag, "strategy": strategy, "seams": seams}
    return out, info


# --------------------------------------------------------------------------
# Candidate B: spectral sustain
# --------------------------------------------------------------------------
def bin_frequencies(cap, stereo="shared"):
    """Per-bin instantaneous frequency from the capture (radians per hop).

    Uses the energy-weighted circular mean of the heterodyned frame-to-frame
    phase step: angle(sum_m T X[m] conj(X[m-1]) exp(-j*expected)). No division by
    magnitudes, so silent bins are safe (they resolve to the bin centre).

    Returns (omega_hop, coherence): omega_hop is (1 or C, K); coherence in [0,1]
    is |sum| / sum|.| per bin - 1 for a stable sinusoid, low for noise.
    """
    F = cap.frames.astype(np.complex128)
    if len(F) < 2:
        raise EngineError("sustain needs at least two frames")
    expected = _expected_advance(cap.N)
    w = np.sqrt(cap.time_mask[1:] * cap.time_mask[:-1])[:, None, None]
    cross = w * F[1:] * np.conj(F[:-1]) * np.exp(-1j * expected)
    if stereo == "shared":
        cross = cross.sum(axis=1, keepdims=True)
    elif stereo != "independent":
        raise ValueError(stereo)
    acc = cross.sum(axis=0)
    mag = np.abs(cross).sum(axis=0)
    coherence = np.divide(np.abs(acc), mag, out=np.zeros_like(mag), where=mag > 0)
    return expected + np.angle(acc), coherence


def sustain(cap, n_samples, magnitude="mean", stereo="shared", phase_lock=False, scan_speed=1.0):
    """Phase-vocoder sustain.

    magnitude "mean": time-mask-weighted RMS magnitude of the whole capture,
                      one frequency per bin, phases start at the loudest frame.
    magnitude "scan": ping-pong through the captured magnitude frames (linear
                      interpolation) using each frame pair's own frequency
                      estimate; phase is accumulated so there is no seam.
    stereo "shared":  one frequency per bin for both channels (interchannel
                      phase of every bin is frozen at its initial value).
    stereo "independent": per-channel frequency estimates (reference only).
    phase_lock:       identity phase locking (Laroche & Dolson 1999) around
                      magnitude peaks; only meaningful with magnitude="mean".
    """
    N, H = cap.N, hop(cap.N)
    F = cap.frames.astype(np.complex128)
    M, C, K = F.shape
    Q = _synth_frame_count(n_samples, N)
    q = np.arange(Q)[:, None, None]
    info = {"magnitude": magnitude, "stereo": stereo, "phase_lock": bool(phase_lock)}

    if magnitude == "mean":
        omega, coh = bin_frequencies(cap, stereo)
        T = cap.time_mask[:, None, None]
        A = np.sqrt(np.sum(T * np.abs(F) ** 2, axis=0) / np.sum(T))
        ref = int(np.argmax(cap.time_mask * np.sum(np.abs(F) ** 2, axis=(1, 2))))
        theta0 = np.angle(F[ref])
        if phase_lock:
            # Each bin follows the frequency of its nearest magnitude peak, which
            # keeps the phase relation it had to that peak in the reference frame.
            env = A.sum(axis=0) if stereo == "shared" else A
            omega_l = np.empty((env.shape[0] if env.ndim == 2 else 1, K))
            for ch, e in enumerate(np.atleast_2d(env)):
                pk = np.flatnonzero((e[2:-2] > e[1:-3]) & (e[2:-2] > e[:-4])
                                    & (e[2:-2] >= e[3:-1]) & (e[2:-2] >= e[4:])) + 2
                if len(pk) == 0:
                    omega_l[ch] = omega[ch]
                    continue
                nearest = pk[np.argmin(np.abs(np.arange(K)[:, None] - pk[None, :]), axis=1)]
                # same true frequency for the whole region, expressed per bin
                omega_l[ch] = omega[ch, nearest]
            omega = omega_l
            info["peaks"] = int(len(pk))
        theta = theta0 + q * omega
        Y = A * np.exp(1j * theta)
        e = np.sum(A ** 2, axis=0)
        info["phase_coherence"] = float(np.sum(coh.mean(axis=0) * e) / e.sum()) if e.sum() > 0 else 0.0
        info["reference_frame"] = ref
    elif magnitude == "scan":
        if M < 2:
            raise EngineError("sustain needs at least two frames")
        expected = _expected_advance(N)
        cross = F[1:] * np.conj(F[:-1]) * np.exp(-1j * expected)
        if stereo == "shared":
            cross = cross.sum(axis=1, keepdims=True)
        omega_m = expected + np.angle(cross)  # (M-1, 1|C, K); pair i <-> frame i+1
        u = (np.arange(Q) * scan_speed) % (2 * (M - 1))
        p = np.where(u <= M - 1, u, 2 * (M - 1) - u)
        i0 = np.minimum(p.astype(int), M - 2)
        frac = (p - i0)[:, None, None]
        mags = np.abs(F)
        A = (1 - frac) * mags[i0] + frac * mags[i0 + 1]
        step = omega_m[np.clip(np.rint(p).astype(int) - 1, 0, M - 2)]
        theta = np.angle(F[0]) + np.concatenate([np.zeros_like(step[:1]), np.cumsum(step[:-1], axis=0)])
        Y = A * np.exp(1j * theta)
        info["scan_speed"] = scan_speed
    else:
        raise ValueError(magnitude)
    return _render(Y, N, n_samples), info


# --------------------------------------------------------------------------
# Shared post-processing so every engine is compared under identical conditions
# --------------------------------------------------------------------------
def match_level(x, fs, target_dbfs=-20.0, window_s=2.0):
    """Scale so the RMS of the first `window_s` seconds (channels pooled) hits
    the target. Returns (scaled, gain). Silent input is returned unchanged."""
    r = np.sqrt(np.mean(x[:int(window_s * fs)] ** 2)) if len(x) else 0.0
    if not np.isfinite(r) or r <= 0:
        return x, 1.0
    g = 10 ** (target_dbfs / 20) / r
    return x * g, float(g)


def envelope(n_samples, fs, t60_s, onset_fade_s=0.03, retire_db=-100.0):
    """MEMORY decay g[n] = 10^(-3 n / (T60 fs)) with a raised-cosine onset fade.
    The voice is retired (exact zeros) once the decay passes `retire_db`."""
    n = np.arange(n_samples)
    env = 10.0 ** (-3.0 * n / (t60_s * fs))
    env[env < 10 ** (retire_db / 20)] = 0.0
    k = min(int(onset_fade_s * fs), n_samples)
    env[:k] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / max(k, 1))
    return env[:, None]
