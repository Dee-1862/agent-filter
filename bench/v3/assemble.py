"""Assemble the NEW OTR-Bench v3 items (v3 = v2 + these) from real windows + authored insertions.

  python -m bench.v3.assemble [--fixes bench/data_v3/work/fixes.json]

Writes
  bench/data_v3/dev/otr3_dev.jsonl, otr3_dev_noisy.jsonl               (committable)
  bench/data_v3/sealed/otr3_sealed.jsonl, otr3_sealed_noisy.jsonl      (gitignored, never commit)
  bench/data_v3/{dev,sealed}_manifest.json, bench/data_v3/build_report.json (counts / md5 only for sealed)
Reuses the v2 builders (bench/v2/assemble.py). Deterministic given the inputs.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from bench.v2 import assemble as v2
from bench.v2.noise import corrupt_item

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data_v3"
WORK = DATA / "work"
SEED = 20261023
SHARED = {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}
SEALED_ONLY = {"S1", "S2", "S3", "S4", "S5", "S6", "S7"}


def validate(w, a):
    errs = v2.validate(w, a)
    labs = [ln.get("label") for b in a.get("blocks", []) for ln in b.get("lines", [])]
    if "public" not in labs:
        errs.append("no inserted public line")
    return errs


def build(w, a, rng):
    it = v2.build_item(w, a, rng)
    s = json.dumps(it, ensure_ascii=False).replace('"v2-', '"v3-')
    it = json.loads(s)
    it["id"] = it["id"].replace("v2-", "v3-", 1) if it["id"].startswith("v2-") else it["id"]
    src = w["source"]
    it["source"] = f"{src}+llm-insert"
    it["provenance"]["background"] = f"real-{src}:{w['meeting']}"
    it["provenance"]["domain"] = w["domain"] if w["domain"].startswith("council-") else v2.domain_of(w)
    if src == "meetingbank":
        it["provenance"]["speaker_labels"] = "synthetic placeholders (Speaker A/B/C), not diarization"
    return it


def md5(p): return v2.md5(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixes", default=str(WORK / "fixes.json"))
    a = ap.parse_args(argv)
    windows = {w["window_id"]: w for w in json.loads((WORK / "windows.json").read_text(encoding="utf-8"))}
    authored = {}
    for p in sorted((WORK / "authored").glob("*_part*.json")):
        for x in json.loads(p.read_text(encoding="utf-8")):
            authored[x["window_id"]] = x
    fixes = json.loads(Path(a.fixes).read_text(encoding="utf-8")) if Path(a.fixes).exists() else {}
    rw = WORK / "rewrite_done.json"
    rewritten = defaultdict(list)
    for r in (json.loads(rw.read_text(encoding="utf-8")) if rw.exists() else []):
        authored[r["window_id"]]["blocks"][r["block"]]["lines"][r["line"]]["text"] = r["new_text"]
        rewritten[r["window_id"]].append(f"{r['block']}:{r['line']}")
    rng = random.Random(SEED)
    items = {"dev": [], "sealed": []}
    drops = {}
    for wid, w in sorted(windows.items()):
        if wid not in authored:
            drops[wid] = ["not authored"]
            continue
        x = authored[wid]
        fx = fixes.get(wid, {})
        if "drop" in fx:
            drops[wid] = [f"labeller/lead: {fx['drop']}"]
            continue
        for k, lab in fx.get("relabel", {}).items():
            bi, li = map(int, k.split(":"))
            x["blocks"][bi]["lines"][li]["label"] = lab
        errs = validate(w, x)
        if errs:
            drops[wid] = errs
            continue
        it = build(w, x, rng)
        if rewritten.get(wid):
            it["provenance"]["diversity_rewrites"] = rewritten[wid]
        if fx.get("relabel"):
            it["provenance"]["relabelled"] = fx["relabel"]
        e2 = v2.check_item(it)
        if e2:
            drops[wid] = e2
            continue
        items[w["split"]].append(it)
    noisy = {}
    for sp, its in items.items():
        by = defaultdict(list)
        for it in its:
            by[it["subtype"]].append(it)
        sel = []
        for st, lst in sorted(by.items()):
            r = random.Random(f"{SEED}-{sp}-{st}")
            sel += r.sample(lst, max(1, round(len(lst) * 0.25)))
        noisy[sp] = [corrupt_item(it) for it in sorted(sel, key=lambda i: i["id"])]
    paths = {"dev": DATA / "dev" / "otr3_dev.jsonl", "dev_noisy": DATA / "dev" / "otr3_dev_noisy.jsonl",
             "sealed": DATA / "sealed" / "otr3_sealed.jsonl", "sealed_noisy": DATA / "sealed" / "otr3_sealed_noisy.jsonl"}
    for k, sp in (("dev", "dev"), ("sealed", "sealed")):
        v2.write_jsonl(paths[k], items[sp])
        v2.write_jsonl(paths[k + "_noisy"], noisy[sp])
    allit = items["dev"] + items["sealed"]
    # contamination also against all v2 items (committed dev and local sealed): counts only
    contam = v2.contamination(allit)
    v2txt = ""
    for p in (ROOT / "bench/data_v2/dev/otr2_dev.jsonl", ROOT / "bench/data_v2/sealed/otr2_sealed.jsonl"):
        if p.exists():
            v2txt += p.read_text(encoding="utf-8").lower()
    import re
    dup_v2 = 0
    for it in allit:
        ins = set(it["provenance"]["inserted_ids"])
        for s in it["segments"]:
            t = re.sub(r"\s+", " ", s["text"].lower()).strip()
            if s["id"] in ins and len(t) >= 25 and t in v2txt:
                dup_v2 += 1
    dv_all = v2.diversity(allit)
    report = {"drops": drops, "n_authored": len(authored), "n_windows": len(windows),
              "contamination": {"inserted_lines_checked": contam["inserted_lines_checked"],
                                "verbatim_in_tests_or_otr": len(contam["verbatim_in_tests_or_otr"]),
                                "verbatim_in_old_bench_sets": len(contam["verbatim_in_old_bench_sets"]),
                                "verbatim_in_v2_items": dup_v2},
              "diversity_all": {k: v for k, v in dv_all.items() if not k.startswith("top_")},
              "diversity_sealed": {k: v for k, v in v2.diversity(items["sealed"]).items() if not k.startswith("top_")},
              "diversity_dev": v2.diversity(items["dev"]),
              "max_cue_3gram_rate_all": max([r for _, _, r in dv_all["top_3grams"]] or [0]),
              "max_cue_4gram_rate_all": max([r for _, _, r in dv_all["top_4grams"]] or [0]),
              "noisy_check_errors": {it["id"]: v2.check_item(it) for sp in noisy for it in noisy[sp] if v2.check_item(it)}}
    (DATA / "build_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    for sp in ("dev", "sealed"):
        c = v2.counts(items[sp])
        c["source"] = dict(Counter(i["source"] for i in items[sp]))
        man = {"split": sp, "files": {k: {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "md5": md5(p),
                                          "n_items": sum(1 for _ in open(p, encoding="utf-8"))}
                                      for k, p in paths.items() if k.startswith(sp)},
               "counts": c, "noisy_counts": v2.counts(noisy[sp]),
               "seen_author_items": sum(i["inserted_by"] in SHARED for i in items[sp]),
               "unseen_author_items": sum(i["inserted_by"] in SEALED_ONLY for i in items[sp])}
        (DATA / f"{sp}_manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(sp, json.dumps({k: v for k, v in c.items() if k not in ("subtype",)}))
    print("drops", len(drops), Counter(e[0].split(" ")[0] for e in drops.values()).most_common(8))
    print("contamination", report["contamination"])
    print("diversity", json.dumps({k: v for k, v in report["diversity_all"].items() if not k.startswith("per_")})[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
