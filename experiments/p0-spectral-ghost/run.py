# SPDX-License-Identifier: AGPL-3.0-only
"""AFTERIMAGE P0-A command line.

  uv run python run.py verify            numerical checks -> verification.json
  uv run python run.py render            A/B renders -> renders/, manifest.json, metrics.json
  uv run python run.py all               both
  uv run python run.py summary           markdown tables from metrics.json / verification.json
  uv run python run.py blind             shuffled A/B/C copies of the rendered primaries -> renders/blind/
Options for render: --only guitar vocal ...   --fft 4096 ...   --no-wav   --out DIR
"""
import argparse
import sys
from pathlib import Path

from p0 import experiment, verify

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["verify", "render", "all", "summary", "blind"])
    ap.add_argument("--out", default=str(ROOT / "renders"))
    ap.add_argument("--only", nargs="*", help="source names (e.g. guitar user_mytake)")
    ap.add_argument("--fft", nargs="*", type=int, help="restrict FFT sizes")
    ap.add_argument("--no-wav", action="store_true", help="compute metrics without writing audio")
    a = ap.parse_args()
    status = 0
    if a.command == "summary":
        import json
        print(experiment.summarize(json.loads((ROOT / "metrics.json").read_text()),
                                   json.loads((ROOT / "verification.json").read_text())))
        return 0
    if a.command == "blind":
        n = experiment.blind_pack(Path(a.out))
        print(f"blind sets: {n} (key in {Path(a.out) / 'blind' / 'KEY-do-not-open.json'})")
        return 0 if n else 1
    if a.command in ("verify", "all"):
        result = verify.run_all()
        timing = verify.python_timing()
        experiment.dump(result, ROOT / "verification.json")
        experiment.dump({"note": "NumPy wall-clock on the machine that ran this; not a realtime indicator.",
                         "rows": timing}, ROOT / "python-timing.json")
        print("verification:", result["summary"])
        for r in result["rows"]:
            if r["result"] == "FAIL":
                print("  FAIL", r["check"], r["case"], r["value"], r["unit"])
        status = 1 if result["summary"]["FAIL"] else 0
    if a.command in ("render", "all"):
        manifest, metrics = experiment.run(a.out, only=a.only, fft_sizes=a.fft, write_audio=not a.no_wav)
        partial = bool(a.only or a.fft)
        suffix = ".partial" if partial else ""  # never overwrite the committed full-run evidence
        experiment.dump(manifest, ROOT / f"manifest{suffix}.json")
        experiment.dump(metrics, ROOT / f"metrics{suffix}.json")
        bad = [k for k, m in metrics.items() if m.get("finite") is False]
        print(f"renders: {len(manifest['renders'])}  failures: {len(manifest['failures'])}  non-finite: {len(bad)}")
        status = status or (1 if bad else 0)
    return status


if __name__ == "__main__":
    sys.exit(main())
