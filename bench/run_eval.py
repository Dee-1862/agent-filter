"""Evaluation harness.

  python -m bench.run_eval --set dev --systems A,B,C --llm none --out bench/results.json
  python -m bench.run_eval --set heldout                    # A, B, B+, B/causal, B+/causal, C on the held-out set
  python -m bench.run_eval --set all                        # dev, heldout, heldout_noisy -> results*.json
  python -m bench.run_eval --set heldout --llm ollama:granite4.2:3b --systems B+,C --limit 3   # smoke test only
  python -m bench.run_eval --systems C --hold-seconds 0,5,15,30        # sweep for system C

Systems: A rules; B / B+ one-pass LLM (hindsight = sees the whole transcript, 'X/causal' = sees only
text up to t_end + hold seconds, the same lag as C); C our pipeline. With --llm none, B and B+ are
heuristic STUBS (labelled -stub) and say nothing about a real LLM.

Writes <out> (JSON: meta, per-system breakdown, per-item rows, pairwise McNemar, per-stage log for C),
<out stem>.md and (if matplotlib is installed) <out stem>.png, a leak vs omit scatter.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

from . import metrics, systems

HERE = Path(__file__).parent
BENCH = HERE / "otr_bench.jsonl"
V2 = HERE / "data_v2"
SETS = {"dev": BENCH, "heldout": HERE / "heldout" / "heldout.jsonl",
        "heldout_noisy": HERE / "heldout" / "heldout_noisy.jsonl",
        # OTR-Bench v2 (bench/data_v2/README.md). sealed2* are gitignored; results are aggregates only.
        "dev2": V2 / "dev" / "otr2_dev.jsonl", "dev2_noisy": V2 / "dev" / "otr2_dev_noisy.jsonl",
        "sealed2": V2 / "sealed" / "otr2_sealed.jsonl", "sealed2_noisy": V2 / "sealed" / "otr2_sealed_noisy.jsonl"}
DEFAULT_OUT = {"dev": "bench/results.json", "heldout": "bench/results_heldout.json",
               "heldout_noisy": "bench/results_heldout_noisy.json",
               "dev2": "bench/results_v2_dev.json", "dev2_noisy": "bench/results_v2_dev_noisy.json",
               "sealed2": "bench/results_v2_sealed.json", "sealed2_noisy": "bench/results_v2_sealed_noisy.json"}
V2_SETS = {"dev2", "dev2_noisy", "sealed2", "sealed2_noisy"}
SEALED_SETS = {"sealed2", "sealed2_noisy"}
CASES = ["explicit_start_end", "explicit_start_implicit_end", "retroactive", "implicit", "false_alarm",
         "public", "ALL"]
DEFAULT_SYSTEMS = "A,B,B+,B/causal,B+/causal,C"


def load_items(path: Path = BENCH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def md5_file(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def evaluate(fn, items: list[dict], llm=None, **kw) -> dict:
    import time
    rows, secs = [], []
    for it in items:
        t0 = time.perf_counter()
        notes = fn(it, llm, **kw)
        secs.append((time.perf_counter() - t0) / max(1, len(it["segments"])))
        rows.append(metrics.score_item(it, notes))
    out = {"breakdown": metrics.breakdown(rows), "items": rows}
    secs.sort()
    out["latency_per_segment_s"] = {"mean": sum(secs) / len(secs), "p50": secs[len(secs) // 2],
                                    "p95": secs[min(len(secs) - 1, int(0.95 * len(secs)))]} if secs else None
    if any("subtype" in it for it in items):   # OTR-Bench v2 extra breakdowns
        by = {k: {} for k in ("subtype", "group", "domain", "difficulty")}
        for it, r in zip(items, rows):
            keys = {"subtype": it.get("subtype", it["case_type"]),
                    "group": ("unseen-author" if it.get("inserted_by") in {"P7", "P8"} else
                              "confaide" if it.get("inserted_by") == "confaide-authors" else "seen-author"),
                    "domain": it.get("provenance", {}).get("domain", "confaide"),
                    "difficulty": it.get("difficulty", "?")}
            for k, v in keys.items():
                by[k].setdefault(v, []).append(r)
        out["by"] = {k: {v: metrics.aggregate(rs) for v, rs in sorted(d.items())} for k, d in by.items()}
    st = metrics.stage_summary(rows)
    if st is not None:
        out["stages"] = st
    return out


# ----------------------------------------------------------------------------- formatting
def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _cell(p: dict) -> str:
    if not p or not p.get("n"):
        return "n/a"
    return f"{p['k']}/{p['n']} = {_pct(p['rate'])} [{_pct(p['lo'])}-{_pct(p['hi'])}]"


def to_markdown(results: dict) -> str:
    meta = results["meta"]
    names = list(results["systems"])
    out = [f"### Set `{meta.get('set', '?')}`: n = {meta['n_items']} items, "
           f"{results['systems'][names[0]]['breakdown']['ALL']['n_clusters']} clusters, llm = `{meta['llm']}`, "
           f"hold = {meta.get('hold_seconds')} s, md5 `{meta.get('md5', '')[:8]}`", "",
           "**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private "
           "segment in the notes (over items with private content); Omit-Public = items missing a public "
           "segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.", "",
           "| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |",
           "|---|---|---|---|---|---|---|"]
    for n in names:
        a = results["systems"][n]["breakdown"]["ALL"]
        out.append(f"| {n} | {_cell(a['Leak'])} | {_cell(a['Omit-Public'])} | {_cell(a['Leak-or-Omit'])} | "
                   f"{_cell(a['Conveyance'])} | {_cell(a['seg_leak'])} | {_pct(a['committed_leak_rate'])} |")
    out += ["", "**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than "
            f"{metrics.DESCRIPTIVE_N} items are *descriptive only*, no ranking claims)", "",
            "| case type (n) | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for c in CASES:
        b0 = results["systems"][names[0]]["breakdown"].get(c)
        if not b0:
            continue
        flag = " descriptive only" if b0["n_items"] < metrics.DESCRIPTIVE_N else ""
        cells = []
        for n in names:
            b = results["systems"][n]["breakdown"][c]
            cells.append(f"{b['Leak']['k']}/{b['Leak']['n']} | {b['Omit-Public']['k']}/{b['Omit-Public']['n']}")
        out.append(f"| {c} ({b0['n_items']}){flag} | " + " | ".join(cells) + " |")
    if results.get("pairwise"):
        out += ["", "**Paired exact McNemar (b = first system has the outcome and second does not; "
                "c = the reverse; risk diff = (b - c)/n).**", "",
                "| first vs second | outcome | n | b | c | both | p | risk diff |", "|---|---|---|---|---|---|---|---|"]
        for pw in results["pairwise"]:
            out.append(f"| {pw['a']} vs {pw['b']} | {pw['key']} | {pw['n']} | {pw['b_count']} | {pw['c_count']} | "
                       f"{pw['both']} | {pw['p']:.4f} | {100 * pw['risk_diff']:+.1f} pts |")
    for n in names:
        st = results["systems"][n].get("stages")
        if st:
            out += ["", f"**Per-stage log for {n}** (stage = prefix of the pipeline audit reason; read-only from "
                    "`Pipeline.audit_log()`)", "", "| outcome | stage counts |", "|---|---|"]
            for k in ("private_blocked", "private_leaked", "public_lost"):
                out.append(f"| {k} | " + ", ".join(f"{s}: {c}" for s, c in sorted(st[k].items(), key=lambda x: -x[1])) + " |")
    by0 = results["systems"][names[0]].get("by")
    if by0:
        for dim in ("subtype", "group", "domain", "difficulty"):
            out += ["", f"**By {dim}: Leak k/n | Omit-Public k/n** (n < {metrics.DESCRIPTIVE_N}: descriptive only)", "",
                    f"| {dim} (n) | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
            for v, b0 in by0[dim].items():
                cells = []
                for n in names:
                    b = results["systems"][n]["by"][dim][v]
                    cells.append(f"{b['Leak']['k']}/{b['Leak']['n']} | {b['Omit-Public']['k']}/{b['Omit-Public']['n']}")
                out.append(f"| {v} ({b0['n_items']}) | " + " | ".join(cells) + " |")
    lat = [(n, results["systems"][n].get("latency_per_segment_s")) for n in names]
    if any(l for _, l in lat):
        out += ["", "**Wall-clock per segment (offline replay; includes LLM calls when used)**: " + "; ".join(
            f"{n} mean {1000 * l['mean']:.1f} ms, p95 {1000 * l['p95']:.1f} ms" for n, l in lat if l)]
    if meta.get("set") in V2_SETS:
        out += ["", f"_OTR-Bench v2 ({meta['n_items']} items): real QMSum meeting turns (AMI/ICSI/parliamentary "
                "committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, "
                "15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, "
                "not LLMs. Wilson 95% intervals; exact McNemar is paired over items._"]
    else:
        out += ["", f"_n={meta['n_items']} synthetic items written by the team that built the systems; early evidence only. "
                "-stub systems are heuristic stand-ins, not LLMs. Intervals are Wilson 95%; with this n they are wide._"]
    return "\n".join(out)


def scatter(results: dict, path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[note] matplotlib missing; skipped scatter")
        return False
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for n, r in results["systems"].items():
        a = r["breakdown"]["ALL"]
        x, y = a["Omit-Public"]["rate"], a["Leak"]["rate"]
        if x is None or y is None:
            continue
        ax.errorbar(100 * x, 100 * y,
                    xerr=[[100 * (x - a["Omit-Public"]["lo"])], [100 * (a["Omit-Public"]["hi"] - x)]],
                    yerr=[[100 * (y - a["Leak"]["lo"])], [100 * (a["Leak"]["hi"] - y)]],
                    fmt="o", capsize=2, alpha=0.8)
        ax.annotate(n, (100 * x, 100 * y), textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.set_xlabel("Omit-Public, % items (lower is better)")
    ax.set_ylabel("Leak, % items with private content (lower is better)")
    ax.set_xlim(-3, 103)
    ax.set_ylim(-3, 103)
    ax.set_title(f"{results['meta'].get('set')} (n={results['meta']['n_items']}); bars = Wilson 95%")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ----------------------------------------------------------------------------- main
def stratified_sample(items: list[dict], n: int, seed: int) -> list[dict]:
    """n items, proportional over subtype (or case_type), deterministic."""
    import random
    from collections import defaultdict
    by = defaultdict(list)
    for it in items:
        by[it.get("subtype", it["case_type"])].append(it)
    rng = random.Random(seed)
    exact = {k: len(v) * n / len(items) for k, v in by.items()}
    q = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: -(exact[k] - q[k]))[: n - sum(q.values())]:
        q[k] += 1
    out = []
    for k in sorted(by):
        out += rng.sample(by[k], q[k])
    return sorted(out, key=lambda it: it["id"])


def run_set(set_name: str, a, llm, bench_path: Path | None = None, out: Path | None = None) -> int:
    path = Path(bench_path) if bench_path else SETS[set_name]
    if not path.exists():
        print(f"[skip] {set_name}: {path} not found (sealed sets live only in the lead's tree)", file=sys.stderr)
        return 0
    items = load_items(path)
    if a.limit:
        items = items[:a.limit]
    if getattr(a, "sample", 0):
        items = stratified_sample(items, a.sample, a.seed)
    hold = [float(x) for x in a.hold_seconds.split(",")] if a.hold_seconds else [30.0]
    res = {"meta": {"set": set_name, "n_items": len(items), "llm": a.llm, "hold_seconds": hold,
                    "md5": md5_file(path), "bench_file": str(path), "limit": a.limit or None,
                    "sample": getattr(a, "sample", 0) or None, "seed": getattr(a, "seed", None),
                    "systems_requested": a.systems,
                    "note": "-stub = heuristic stand-in used when llm is none"}, "systems": {}}
    for name in [s.strip() for s in a.systems.split(",") if s.strip()]:
        if name not in systems.SYSTEMS:
            print(f"unknown system {name}", file=sys.stderr)
            return 2
        fn = systems.SYSTEMS[name]
        try:
            if name == "C" and a.hold_seconds and len(hold) > 1:
                for h in hold:
                    res["systems"][f"C@hold={h:g}s"] = evaluate(fn, items, llm, hold_seconds=h)
            else:
                res["systems"][systems.label(name, llm)] = evaluate(fn, items, llm, hold_seconds=hold[0])
        except ImportError as e:
            print(f"[skip] system {name}: {e}", file=sys.stderr)
    names = list(res["systems"])
    res["pairwise"] = []
    def _base(n):
        return n.split("/")[0].replace("-stub", "")
    for x, y in itertools.combinations(names, 2):
        # report: anything vs C, B vs B+ in the same mode, hindsight vs causal for the same base system
        same_mode = x.partition("/")[2] == y.partition("/")[2] and {_base(x), _base(y)} == {"B", "B+"}
        same_base = _base(x) == _base(y) and x != y
        if set_name not in V2_SETS and "C" not in (x, y) and not (same_mode or same_base):
            continue
        for key in ("leak", "leak_or_omit"):
            r = metrics.paired(res["systems"][x]["items"], res["systems"][y]["items"], key)
            res["pairwise"].append({"a": x, "b": y, "key": key, "n": r["n"], "b_count": r["b"], "c_count": r["c"],
                                    "both": r["both"], "neither": r["neither"], "p": r["p"],
                                    "risk_diff": r["risk_diff"] or 0.0,
                                    "discordant_prop_ci": r["discordant_prop_ci"]})
    out = Path(out or DEFAULT_OUT[set_name])
    if getattr(a, "sample", 0) and not a.out:
        out = out.with_name(out.stem + f"_sample{a.sample}" + out.suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    if set_name in SEALED_SETS:   # aggregates only: no per-item rows (ids, leaked ids) for the sealed split
        for r in res["systems"].values():
            r.pop("items", None)
        res["meta"]["note"] += "; sealed split: aggregates only"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = to_markdown(res)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    scatter(res, out.with_suffix(".png"))
    print(md)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev", choices=["dev", "heldout", "heldout_noisy", "all",
                                                     "dev2", "dev2_noisy", "sealed2", "sealed2_noisy", "all2"])
    ap.add_argument("--systems", default=None, help=f"default for dev: A,B,C; otherwise {DEFAULT_SYSTEMS}")
    ap.add_argument("--llm", default="none", help="none | ollama:<model>")
    ap.add_argument("--bench", default=None, help="override the jsonl path (single set only)")
    ap.add_argument("--out", default=None, help="results json path (single set only)")
    ap.add_argument("--limit", type=int, default=0, help="first N items only (smoke tests)")
    ap.add_argument("--sample", type=int, default=0, help="stratified (by subtype) random N items, e.g. for LLM runs")
    ap.add_argument("--seed", type=int, default=0, help="seed for --sample")
    ap.add_argument("--hold-seconds", default=None,
                    help="comma list for system C, e.g. 0,5,15,30 (default: single run at 30)")
    a = ap.parse_args(argv)
    if a.systems is None:
        a.systems = "A,B,C" if a.set == "dev" else "A,B,B+,C" if a.set.endswith("2") else DEFAULT_SYSTEMS
    llm = systems.make_llm(a.llm)
    sets = (["dev", "heldout", "heldout_noisy"] if a.set == "all" else
            ["dev2", "dev2_noisy", "sealed2", "sealed2_noisy"] if a.set == "all2" else [a.set])
    for s in sets:
        rc = run_set(s, a, llm, a.bench if len(sets) == 1 else None, a.out if len(sets) == 1 else None)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
