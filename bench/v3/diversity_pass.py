"""Pick over-used cue lines (n-gram in > 2.5% of cue lines, n=3,4, stopword-only grams ignored) to be paraphrased.
Writes work/rewrite_todo.json (list of {window_id, block, line, text, speaker, label, role, context}). Local only."""
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bench.v2.assemble import ngrams

W = Path("bench/data_v3/work")
STOP = set("the a an and or to of i you we it that this is so uh um just be in on for what me my our".split())
CUE = {"cue_start", "cue_end", "retraction"}
CAP = 0.025


def lines():
    out = []
    for p in sorted((W / "authored").glob("*_part*.json")):
        for x in json.load(open(p, encoding="utf-8")):
            for bi, b in enumerate(x["blocks"]):
                for li, ln in enumerate(b["lines"]):
                    if ln["role"] in CUE:
                        out.append({"window_id": x["window_id"], "block": bi, "line": li, "text": ln["text"],
                                    "speaker": ln["speaker"], "label": ln["label"], "role": ln["role"]})
    return out


def main():
    ls = lines()
    # replacements already done
    done = {(r["window_id"], r["block"], r["line"]): r["new_text"] for r in
            (json.load(open(W / "rewrite_done.json")) if (W / "rewrite_done.json").exists() else [])}
    for l in ls:
        k = (l["window_id"], l["block"], l["line"])
        if k in done:
            l["text"] = done[k]
    N = len(ls)
    cap = int(CAP * N)
    todo = {}
    rng = random.Random(1)
    for rnd in range(6):
        cur = [dict(l, text=todo[(l["window_id"], l["block"], l["line"])]["text"]) if (l["window_id"], l["block"], l["line"]) in todo else l for l in ls]
        flagged = defaultdict(list)
        for n in (3, 4):
            df = defaultdict(list)
            for i, l in enumerate(cur):
                for g in ngrams(l["text"], n):
                    if not set(g.split()) <= STOP:
                        df[g].append(i)
            for g, ix in df.items():
                if len(ix) > cap:
                    flagged[g] = ix
        if not flagged:
            break
        pick = set()
        for g, ix in sorted(flagged.items(), key=lambda kv: -len(kv[1])):
            already = [i for i in ix if i in pick]
            keep = len(ix) - len(already)
            ix2 = [i for i in ix if i not in pick]
            rng.shuffle(ix2)
            need = len(ix) - len(already) - cap
            for i in ix2[:max(0, need)]:
                pick.add(i)
        for i in pick:
            l = ls[i]
            todo[(l["window_id"], l["block"], l["line"])] = dict(l)
        break
    out = [v for v in todo.values()]
    print(N, "cue lines; cap", cap, "; to rewrite", len(out))
    json.dump(out, open(W / "rewrite_todo.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)


main()
