# SPDX-License-Identifier: AGPL-3.0-only
"""AFTERIMAGE P0-B command line (P0-A's run.py is unchanged).

  uv run python run_p0b.py verify     numerical checks -> p0b-verification.json
  uv run python run_p0b.py render     listening pack -> renders/p0b/, p0b-manifest.json, p0b-metrics.json
  uv run python run_p0b.py all        both
  uv run python run_p0b.py summary    markdown tables from p0b-metrics.json
  uv run python run_p0b.py blind      shuffled blind sets -> renders/p0b/blind/
Options for render: --only guitar user_mytake ...   --no-wav   --out DIR
"""
import argparse
import json
import sys
from pathlib import Path

from p0 import cloud_experiment, experiment, verify_cloud

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["verify", "render", "all", "summary", "blind"])
    ap.add_argument("--out", default=str(ROOT / "renders" / "p0b"))
    ap.add_argument("--only", nargs="*", help="source names")
    ap.add_argument("--no-wav", action="store_true", help="compute metrics without writing audio")
    a = ap.parse_args()
    status = 0
    if a.command == "summary":
        print(cloud_experiment.summarize(json.loads((ROOT / "p0b-metrics.json").read_text())))
        return 0
    if a.command == "blind":
        n = cloud_experiment.blind_pack(Path(a.out))
        print(f"blind sets: {n} (key: {Path(a.out) / 'blind-KEY-do-not-open.json'})")
        return 0 if n else 1
    if a.command in ("verify", "all"):
        result = verify_cloud.run_all()
        experiment.dump(result, ROOT / "p0b-verification.json")
        experiment.dump({"note": "NumPy wall-clock on the machine that ran this; not a realtime indicator.",
                         "rows": verify_cloud.python_timing()}, ROOT / "p0b-python-timing.json")
        print("verification:", result["summary"])
        for r in result["rows"]:
            if r["result"] == "FAIL":
                print("  FAIL", r["check"], r["case"], r["value"], r["unit"])
        status = 1 if result["summary"]["FAIL"] else 0
    if a.command in ("render", "all"):
        manifest, metrics = cloud_experiment.run(a.out, inputs_dir=experiment.evidence_inputs(a.only), only=a.only, write_audio=not a.no_wav)
        suffix = ".partial" if a.only else ""  # never overwrite the committed full-run evidence
        experiment.dump(manifest, ROOT / f"p0b-manifest{suffix}.json")
        experiment.dump(metrics, ROOT / f"p0b-metrics{suffix}.json")
        bad = [k for k, m in metrics.items() if isinstance(m, dict) and m.get("finite") is False]
        print(f"renders: {len(manifest['renders'])}  failures: {len(manifest['failures'])}  non-finite: {len(bad)}")
        status = status or (1 if bad or manifest["failures"] else 0)
    return status


if __name__ == "__main__":
    sys.exit(main())
