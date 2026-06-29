"""End-to-end CLI: listening history + GEMS scores -> dashboard.html.

    python analysis/run.py --history annas_listening_history.csv \
        --gems annas_tracks_gems_scored.csv --name "Anna" --out docs/dashboard.html

Runs the shared analysis engine (analyze.py) then renders the self-contained
dashboard (dashboard.py). Writes results.json next to the dashboard too.
"""
from __future__ import annotations

import argparse
import json
import os

from analyze import Config, analyze
from dashboard import build_html


def main():
    ap = argparse.ArgumentParser(description="Build a GEMS emotional dashboard")
    ap.add_argument("--history", required=True)
    ap.add_argument("--gems", required=True)
    ap.add_argument("--name", default="Listener")
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--weight", choices=["minutes", "plays"], default="minutes")
    ap.add_argument("--hemisphere", choices=["north", "south"], default="north")
    ap.add_argument("--results", default=None,
                    help="optional path to also write results.json")
    args = ap.parse_args()

    cfg = Config(weight=args.weight, hemisphere=args.hemisphere)
    results = analyze(args.history, args.gems, name=args.name, cfg=cfg)

    m = results["meta"]
    print(f"Join coverage: {m['coverage_plays_pct']}% plays / "
          f"{m['coverage_minutes_pct']}% minutes")
    print(f"Baseline (top emotions): " + ", ".join(
        f"{k} {v:.2f}" for k, v in sorted(
            results["baseline"]["emotions"].items(), key=lambda x: -x[1])[:4]))

    results_path = args.results or os.path.splitext(args.out)[0] + "_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    html = build_html(results)
    with open(args.out, "w") as f:
        f.write(html)

    print(f"Wrote {args.out} ({len(html)//1024} KB) and {results_path}")
    print(f"Findings ({len(results['findings'])}):")
    for i, fnd in enumerate(results["findings"], 1):
        print(f"  {i}. {fnd['sentence']}")


if __name__ == "__main__":
    main()
