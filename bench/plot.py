"""Grouped bar chart from bench/results.json.

  python -m bench.plot --results bench/results.json --out bench/results.png [--metric leak_rate]
matplotlib is optional; exits with a message if missing.
"""
from __future__ import annotations

import argparse
import json

CASES = ["explicit_start_end", "explicit_start_implicit_end", "retroactive", "implicit", "false_alarm", "ALL"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="bench/results.json")
    ap.add_argument("--out", default="bench/results.png")
    ap.add_argument("--metric", default="leak_rate",
                    choices=["leak_rate", "over_redaction", "summary_usefulness", "item_leak_rate"])
    a = ap.parse_args(argv)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed (pip install -r requirements-bench.txt)")
        return 1
    res = json.load(open(a.results, encoding="utf-8"))
    names = list(res["systems"])
    w = 0.8 / max(len(names), 1)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, n in enumerate(names):
        vals = [(res["systems"][n]["breakdown"].get(c, {}).get(a.metric) or 0) * 100 for c in CASES]
        ax.bar([x + i * w for x in range(len(CASES))], vals, w, label=n)
    ax.set_xticks([x + w * (len(names) - 1) / 2 for x in range(len(CASES))])
    ax.set_xticklabels([c.replace("_", "\n") for c in CASES], fontsize=8)
    ax.set_ylabel(a.metric.replace("_", " ") + " (%)")
    ax.set_title(f"OTR-Bench ({res['meta']['n_items']} synthetic items): {a.metric}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(a.out, dpi=150)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
