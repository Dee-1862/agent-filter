"""Agreement between author labels and the blind labeller on the 15% sample.

  python -m bench.v2.agreement   -> bench/data_v2/agreement.json (+ prints disagreements)
Kappa is Cohen's kappa over segments, 3 classes (private / public / neutral). Reported over all
segments and over inserted segments only (real background turns are almost always public, which
inflates the all-segment kappa). Item-level: exact agreement on the set of private ids, and on
"item has any private segment".
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data_v2"
WORK = DATA / "work"


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return None if pe == 1 else (po - pe) / (1 - pe)


def main() -> int:
    items = {}
    for f in [DATA / "dev" / "otr2_dev.jsonl", DATA / "sealed" / "otr2_sealed.jsonl"]:
        for l in open(f, encoding="utf-8"):
            it = json.loads(l)
            items[it["id"]] = it
    lab = {}
    for f in sorted(WORK.glob("label_out_*.json")):
        lab.update(json.loads(f.read_text(encoding="utf-8")))
    allp, insp, item_exact, item_any, dis = [], [], [], [], {}
    for iid, L in lab.items():
        it = items[iid]
        ins = set(it["provenance"].get("inserted_ids", [])) if it["source"].startswith("qmsum") else {
            s["id"] for s in it["segments"]}   # ConfAIde: whole meeting is authored text
        P, N = set(L.get("private", [])), set(L.get("neutral", []))
        gp, gpub = set(it["private_ids"]), set(it["public_ids"])
        rows = []
        for s in it["segments"]:
            g = "private" if s["id"] in gp else "public" if s["id"] in gpub else "neutral"
            h = "private" if s["id"] in P else "neutral" if s["id"] in N else "public"
            allp.append((g, h))
            if s["id"] in ins:
                insp.append((g, h))
            if g != h:
                rows.append({"seg": s["id"], "speaker": s["speaker"], "text": s["text"][:160], "author": g,
                             "labeller": h, "unsure": s["id"] in set(L.get("unsure", []))})
        item_exact.append(P == gp)
        item_any.append(bool(P) == bool(gp))
        if rows:
            dis[iid] = {"subtype": it["subtype"], "author": it["inserted_by"], "rows": rows}
    out = {"n_items": len(lab), "n_segments": len(allp), "n_inserted_segments": len(insp),
           "kappa_all_segments": kappa(allp), "kappa_inserted_segments": kappa(insp),
           "raw_agreement_all": sum(a == b for a, b in allp) / len(allp),
           "raw_agreement_inserted": sum(a == b for a, b in insp) / len(insp),
           "kappa_private_vs_rest_inserted": kappa([(a == "private", b == "private") for a, b in insp]),
           "item_private_set_exact": f"{sum(item_exact)}/{len(item_exact)}",
           "item_has_private_agree": f"{sum(item_any)}/{len(item_any)}",
           "confusion_inserted": {f"{a}->{b}": c for (a, b), c in Counter(insp).items()},
           "disagreements": dis}
    (DATA / "work" / "agreement_full.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    summ = {k: v for k, v in out.items() if k != "disagreements"}
    summ["n_items_with_disagreement"] = len(dis)
    PRE = {"stage": "pre-adjudication (author labels vs blind labeller, before applying work/fixes.json)",
           "n_items": 61, "n_segments": 1417, "n_inserted_segments": 287, "kappa_all_segments": 0.982,
           "kappa_inserted_segments": 0.975, "kappa_private_vs_rest_inserted": 0.992,
           "raw_agreement_inserted": 0.986, "item_private_set_exact": "60/61", "item_has_private_agree": "61/61",
           "n_items_with_disagreement": 3,
           "confusion_inserted": {"private->private": 87, "public->public": 164, "public->private": 1,
                                  "neutral->neutral": 32, "neutral->public": 3},
           "adjudication": "lead adopted the labeller label for all 4 disagreeing segments (all marked unsure "
                           "by the labeller); no item dropped",
           "caveat": "labeller and authors are the same model family (Claude Sonnet) reading the same written "
                     "rules; agreement measures rule consistency, not human judgement. No human has checked "
                     "these labels."}   # recorded from the first run of this script, before fixes were applied
    (DATA / "agreement.json").write_text(json.dumps({"pre_adjudication": PRE, "post_adjudication": summ}, indent=1),
                                         encoding="utf-8")
    print(json.dumps(summ, indent=1))
    for iid, d in dis.items():
        print(f"\n{iid} {d['subtype']} {d['author']}")
        for r in d["rows"]:
            print(f"  {r['seg'][-3:]} {r['author']:>7}->{r['labeller']:<7}{' ?' if r['unsure'] else '  '} {r['speaker']}: {r['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
