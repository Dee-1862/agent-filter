"""Evaluation harness.

  python -m bench.run_eval --systems A,B,C --llm none --out bench/results.json
  python -m bench.run_eval --systems C --hold-seconds 0,5,15,30        # sweep for system C
  python -m bench.run_eval --systems A,B --llm ollama:qwen2.5:3b

Writes <out> (JSON) and <out stem>.md (markdown table) and prints the table.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import metrics, systems

BENCH = Path(__file__).with_name("otr_bench.jsonl")
CASES = ["explicit_start_end", "explicit_start_implicit_end", "retroactive", "implicit", "false_alarm", "ALL"]


def load_items(path: Path = BENCH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(fn, items: list[dict], llm=None, **kw) -> dict:
    rows = [metrics.score_item(it, fn(it, llm, **kw)) for it in items]
    return {"breakdown": metrics.breakdown(rows), "items": rows}


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def to_markdown(results: dict) -> str:
    names = list(results["systems"])
    out = []
    for title, key in [("Leak rate (private segments reaching notes, lower is better)", "leak_rate"),
                       ("Over-redaction (public segments missing, lower is better)", "over_redaction"),
                       ("Summary usefulness (public facts present, higher is better)", "summary_usefulness")]:
        out += [f"**{title}**", "", "| case type | " + " | ".join(names) + " |",
                "|---|" + "---|" * len(names)]
        for c in CASES:
            out.append(f"| {c} | " + " | ".join(
                _pct(results["systems"][n]["breakdown"].get(c, {}).get(key)) for n in names) + " |")
        out.append("")
    out += ["**Item-level leak rate (items with any leak / items with private content)**", "",
            "| system | item leak |", "|---|---|"]
    for n in names:
        out.append(f"| {n} | {_pct(results['systems'][n]['breakdown']['ALL']['item_leak_rate'])} |")
    out += ["", f"_n={results['meta']['n_items']} synthetic items; early evidence only. "
            "B-stub is a heuristic stand-in, not an LLM._"]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default="A,B,C")
    ap.add_argument("--llm", default="none", help="none | ollama:<model>")
    ap.add_argument("--bench", default=str(BENCH))
    ap.add_argument("--out", default="bench/results.json")
    ap.add_argument("--hold-seconds", default=None,
                    help="comma list for system C, e.g. 0,5,15,30 (default: single run at 30)")
    a = ap.parse_args(argv)

    items = load_items(Path(a.bench))
    llm = systems.make_llm(a.llm)
    res = {"meta": {"n_items": len(items), "llm": a.llm, "systems_requested": a.systems}, "systems": {}}

    for name in [s.strip() for s in a.systems.split(",") if s.strip()]:
        if name not in systems.SYSTEMS:
            print(f"unknown system {name}", file=sys.stderr)
            return 2
        fn = systems.SYSTEMS[name]
        try:
            if name == "C" and a.hold_seconds:
                for h in [float(x) for x in a.hold_seconds.split(",")]:
                    res["systems"][f"C@hold={h:g}s"] = evaluate(fn, items, llm, hold_seconds=h)
            else:
                res["systems"][systems.label(name, llm)] = evaluate(fn, items, llm)
        except ImportError as e:
            print(f"[skip] system {name}: {e}", file=sys.stderr)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = to_markdown(res)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
