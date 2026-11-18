# P0-A — spectral ghost feasibility harness

Offline NumPy/SciPy reference for the AFTERIMAGE spectral-memory idea. It is a
research prototype: no JUCE, no GUI, no realtime guarantees. Findings and the
verdict are in [`docs/P0-A-FINAL-REPORT.md`](../../docs/P0-A-FINAL-REPORT.md).

Licence: `AGPL-3.0-only` (all code here is original). No audio is committed.

## Reproduce

Requires [uv](https://docs.astral.sh/uv/). Python 3.13, NumPy 2.3.4 and
SciPy 1.16.3 are pinned in `pyproject.toml` / `uv.lock`.

```bash
cd experiments/p0-spectral-ghost
```

```bash
uv sync
```

```bash
uv run pytest -q
```

```bash
uv run python run.py all
```

```bash
uv run python run.py blind
```

`run.py all` takes about 20 s and writes about 0.9 GB of 32-bit float WAVs (`blind` adds 0.2 GB) to
`renders/` (git-ignored). Use `--fft 4096`, `--only guitar`, or `--no-wav` for
smaller runs; restricted runs write `*.partial.json` instead of the committed
evidence files.

## Layout

| Path | What |
|---|---|
| `p0/stft.py` | STFT/ISTFT, periodic sqrt-Hann, H = N/4, explicit frame indexing |
| `p0/capture.py` | 6 s history ring model, ROI validation, frequency/time masks |
| `p0/engines.py` | `freeze` (baseline), `loop` (candidate A), `sustain` (candidate B), shared envelope and level matching |
| `p0/fixtures.py` | Deterministic synthetic stand-ins: guitar, vocal, drums, synth |
| `p0/metrics.py` | Measurement definitions |
| `p0/verify.py` | Numerical checks with fixed PASS/FAIL thresholds |
| `p0/experiment.py` | A/B render pipeline, manifest, summary tables, blind pack |
| `run.py` | Command line |
| `experiments.json` | Experiment configuration (ROIs, FFT sizes, T60, levels) |
| `tests/` | pytest suite (same thresholds as `verify.py`) |
| `inputs/` | Put your own WAVs here — see `inputs/README.md` |

## Committed evidence (generated, deterministic)

| File | Content |
|---|---|
| `verification.json` | Every numerical check: value, limit, PASS / FAIL / info |
| `manifest.json` | Every render: source, ROI, frames, FFT, engine, SHA-256 of samples |
| `metrics.json` | Per-render measurements |
| `python-timing.json` | NumPy wall-clock; informational, machine-dependent, **not** a realtime figure |
| `listening-notes.md` | Template for the human listening test (empty) |

`manifest.json` and `metrics.json` contain no timestamps. Two runs of the same
commit on the same machine produce identical files and identical WAV bytes
(tested). `manifest.json` records the git commit it was generated from, so it
changes when the commit changes. Bit-identity across machines, BLAS/FFT builds
or OSes has not been tested; expect last-digit differences in float results.

## Render tree

```text
renders/<source>/source_fs<fs>.wav                      dry fixture or user file
renders/<source>/<case>/fs<fs>_N<fft>/roi_oneshot.wav   the masked capture, played once
renders/<source>/<case>/fs<fs>_N<fft>/<engine>.wav      ghost only, 6 s, T60 = 5 s
renders/<source>/<case>/fs48000_N4096/mix_<engine>.wav  BODY + GHOST (ghost starts at ROI end)
renders/blind/<source>__<case>/{A,B,C}.wav              shuffled primaries (after `run.py blind`)
```

Engines rendered at every FFT size: `freeze_delta`, `loop_ep80`,
`loop_aligned80`, `sustain_mean`. At N = 4096 also: `freeze_random`,
`loop_ep30`, `loop_lin80`, `loop_aligned30`, `sustain_scan`,
`sustain_mean_lock`, `sustain_mean_indep`.

All ghosts of one case share the ROI, mask, 30 ms onset fade, T60 and the level
rule (raw ghost RMS over its first 2 s matched to −23 dBFS before the envelope).

## P0-B: spectral granular cloud

P0-B adds a time-domain granular engine fed by the same captures, without
changing the P0-A commands above. See `docs/P0-B-FINAL-REPORT.md` and
`docs/P0-B-SPECTRAL-GRANULAR-ARCHITECTURE.md`.

```
uv run python run_p0b.py all        # p0b-verification.json, renders/p0b/, p0b-manifest.json, p0b-metrics.json
uv run python run_p0b.py blind      # renders/p0b/blind/, key in renders/p0b/blind-KEY-do-not-open.json
uv run python run_p0b.py summary    # report tables
```

New code: `p0/granular.py` (engine), `p0/verify_cloud.py` (checks, limits fixed
in the first commit of the branch), `p0/cloud_experiment.py` (listening matrix).
Listening notes go in `listening-notes-p0b.md`.
