# User-owned input audio

Drop your own WAV files here to run the same A/B comparison on real material
(distorted guitar, voice, acoustic drums, synth). Nothing in this folder except
this README is tracked by git, so recordings are never committed.

Only use audio you own or are licensed to use.

Requirements

- WAV, mono or stereo, 16/24/32-bit PCM or 32-bit float
- sample rate 44.1, 48, 88.2 or 96 kHz (other rates are skipped and listed in
  `manifest.json` under `skipped_inputs`; they are not resampled)
- at least 2 s long for the default selections

Each `name.wav` becomes the source `user_name`. By default two selections are
rendered (1.00-1.75 s, full band and 350 Hz-5 kHz). To choose your own, put a
`name.json` next to the WAV:

```json
{"cases": [
  {"name": "chord_tail", "t0": 2.10, "t1": 3.00, "low_hz": 350, "high_hz": 5000},
  {"name": "air",        "t0": 2.10, "t1": 3.00, "low_hz": 4000, "high_hz": null}
]}
```

`t0`/`t1` are seconds from the start of the file, selections must be 0.20-1.50 s
long, and `high_hz: null` means Nyquist.

```bash
uv run python run.py render --only user_name
```

Recordings here are read **only** by a run that names them (`--only user_<name>`)
or by `run_real.py`. A default `run.py` / `run_p0b.py` / `run_p0c.py` run uses the
synthetic fixtures alone, so local recordings can never reach the committed evidence.

A restricted run (`--only`/`--fft`) writes `manifest.partial.json` and
`metrics.partial.json` so the committed full-run evidence is not overwritten.
