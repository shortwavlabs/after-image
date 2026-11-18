# SPDX-License-Identifier: AGPL-3.0-only
"""AFTERIMAGE P0-C command line (run.py and run_p0c.py are unchanged).

  uv run python run_p0c.py verify     numerical checks -> p0c-verification.json
  uv run python run_p0c.py render     listening pack -> renders/p0c/, p0c-manifest.json, p0c-metrics.json
  uv run python run_p0c.py all        both
  uv run python run_p0c.py summary    markdown tables from p0c-metrics.json
  uv run python run_p0c.py blind      shuffled blind sets -> renders/p0c/blind/
Options for render: --only guitar user_mytake ...   --no-wav   --out DIR
"""
import argparse
import json
import sys
from pathlib import Path

from p0 import split_experiment, experiment, verify_split

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["verify", "render", "all", "summary", "blind"])
    ap.add_argument("--out", default=str(ROOT / "renders" / "p0c"))
    ap.add_argument("--only", nargs="*", help="source names")
    ap.add_argument("--no-wav", action="store_true", help="compute metrics without writing audio")
    a = ap.parse_args()
    status = 0
    if a.command == "summary":
        print(split_experiment.summarize(json.loads((ROOT / "p0c-metrics.json").read_text())))
        return 0
    if a.command == "blind":
        n = split_experiment.blind_pack(Path(a.out))
        print(f"blind sets: {n} (key: {Path(a.out) / 'blind-KEY-do-not-open.json'})")
        return 0 if n else 1
    if a.command in ("verify", "all"):
        result = verify_split.run_all()
        experiment.dump(result, ROOT / "p0c-verification.json")
        experiment.dump({"note": "NumPy wall-clock on the machine that ran this; not a realtime indicator.",
                         "rows": verify_split.python_timing()}, ROOT / "p0c-python-timing.json")
        print("verification:", result["summary"])
        for r in result["rows"]:
            if r["result"] == "FAIL":
                print("  FAIL", r["check"], r["case"], r["value"], r["unit"])
        status = 1 if result["summary"]["FAIL"] else 0
    if a.command in ("render", "all"):
        manifest, metrics = split_experiment.run(a.out, inputs_dir=experiment.evidence_inputs(a.only), only=a.only, write_audio=not a.no_wav)
        suffix = ".partial" if a.only else ""  # never overwrite the committed full-run evidence
        experiment.dump(manifest, ROOT / f"p0c-manifest{suffix}.json")
        experiment.dump(metrics, ROOT / f"p0c-metrics{suffix}.json")
        bad = [k for k, m in metrics.items() if isinstance(m, dict) and m.get("finite") is False]
        print(f"renders: {len(manifest['renders'])}  failures: {len(manifest['failures'])}  non-finite: {len(bad)}")
        status = status or (1 if bad or manifest["failures"] else 0)
    return status


if __name__ == "__main__":
    sys.exit(main())
