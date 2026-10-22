"""Build bench/heldout/heldout.jsonl and heldout_noisy.jsonl from _items.py.  Deterministic.

    python -m bench.heldout.build_heldout
Rules for the noisy variant are listed in bench/heldout/README.md.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ._items import H

HERE = Path(__file__).parent
PREFIX = {"explicit_start_end": "ho-ese", "explicit_start_implicit_end": "ho-esi", "retroactive": "ho-ret",
          "implicit": "ho-imp", "false_alarm": "ho-fa", "public": "ho-pub"}


def build() -> list[dict]:
    counters: dict[str, int] = {}
    out = []
    for it in H:
        ct = it["case"]
        counters[ct] = counters.get(ct, 0) + 1
        iid = f"{PREFIX[ct]}-{counters[ct]:02d}"
        t, segs, priv, pub, cues = 0.0, [], [], [], []
        for n, (spk, flag, text) in enumerate(it["segs"], 1):
            sid = f"{iid}-s{n:02d}"
            dur = max(1.5, len(text.split()) * 0.4)
            segs.append({"id": sid, "speaker": spk, "text": text,
                         "t_start": round(t, 2), "t_end": round(t + dur, 2)})
            t += dur + 0.6
            if flag.startswith("x"):
                priv.append(sid)
            elif flag.startswith("u"):
                pub.append(sid)
            if flag.endswith("c"):
                cues.append(sid)
        pub_text = " ".join(s["text"] for s in segs if s["id"] in pub).lower()
        for f in it["facts"]:
            assert f.lower() in pub_text, f"{iid}: fact not in public text: {f!r}"
        out.append({"id": iid, "source": "synthetic-heldout", "case_type": ct, "cluster": it["cluster"],
                    "segments": segs, "private_ids": priv, "public_ids": pub,
                    "public_facts": it["facts"], "cue_ids": cues})
    return out


# ------------------------------------------------------------------ noisy-ASR corruption
NEG = re.compile(r"\b(?:don't|do not|not|never|nothing|no)\b\s*", re.I)
SUBS = [  # applied in order, after lowercasing
    (re.compile(r"\boff the record\b"), "of the record"),
    (re.compile(r"\b(strike|scratch) that\b"), r"\1 dat"),
    (re.compile(r"\bwrite\b"), "right"),
    (re.compile(r"\bpause\b"), "paws"),
]


def _h(sid: str) -> int:
    return int(hashlib.md5(sid.encode()).hexdigest(), 16)


def corrupt(sid: str, text: str) -> str:
    t = text.lower()
    if _h(sid) % 10 == 0:                              # R4: drop a negation on 10% of cue lines
        t = NEG.sub("", t, count=1)
    for rx, rep in SUBS:                               # R2, R3
        t = rx.sub(rep, t)
    if _h(sid) % 2 == 0:                               # R3b: "notes" -> "nodes" on even-hash lines
        t = re.sub(r"\bnotes\b", "nodes", t)
    t = re.sub(r"[^\w\s'\-]", "", t)                   # R1: drop punctuation
    return re.sub(r"\s+", " ", t).strip()


def noisy(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        c = json.loads(json.dumps(it))
        c["id"] = it["id"] + "-n"
        c["source"] = "synthetic-heldout-noisy"
        idmap = {s["id"]: s["id"] + "-n" for s in it["segments"]}
        for s in c["segments"]:
            old = s["id"]
            if old in it["cue_ids"]:
                s["text"] = corrupt(old, s["text"])
            s["id"] = idmap[old]
        c["private_ids"] = [idmap[i] for i in it["private_ids"]]
        c["public_ids"] = [idmap[i] for i in it["public_ids"]]
        c["cue_ids"] = [idmap[i] for i in it["cue_ids"]]
        # facts must still be found in (possibly corrupted) public text; cue-bearing public lines
        # are lowercased by corruption and fact matching is case-insensitive, but punctuation-free
        # variants may differ, so keep only facts still present.
        pub_text = " ".join(s["text"] for s in c["segments"] if s["id"] in c["public_ids"]).lower()
        c["public_facts"] = [f for f in c["public_facts"] if f.lower() in pub_text]
        out.append(c)
    return out


def write(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def main() -> None:
    items = build()
    write(HERE / "heldout.jsonl", items)
    nz = noisy(items)
    write(HERE / "heldout_noisy.jsonl", nz)
    from collections import Counter
    print(len(items), dict(Counter(i["case_type"] for i in items)))
    changed = sum(1 for a, b in zip(items, nz) for s, u in zip(a["segments"], b["segments"]) if s["text"] != u["text"])
    print("noisy segments changed:", changed)


if __name__ == "__main__":
    main()
