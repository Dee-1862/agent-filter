"""Build bench/otr_bench.jsonl from the hand-written synthetic items.

Run:  python -m bench.build_bench
Each output line: {id, source, case_type, segments, private_ids, public_ids, public_facts}.
Segments not in private_ids or public_ids are neutral (cue / control lines) and are not scored.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ._items_a import ITEMS_A
from ._items_b import ITEMS_B

OUT = Path(__file__).with_name("otr_bench.jsonl")
PREFIX = {"explicit_start_end": "ese", "explicit_start_implicit_end": "esi",
          "retroactive": "ret", "implicit": "imp", "false_alarm": "fa"}


def build() -> list[dict]:
    counters: dict[str, int] = {}
    out = []
    for it in ITEMS_A + ITEMS_B:
        ct = it["case"]
        counters[ct] = counters.get(ct, 0) + 1
        iid = f"{PREFIX[ct]}-{counters[ct]:02d}"
        t, segs, priv, pub = 0.0, [], [], []
        for n, (spk, flag, text) in enumerate(it["segs"], 1):
            sid = f"{iid}-s{n:02d}"
            dur = max(1.5, len(text.split()) * 0.4)
            segs.append({"id": sid, "speaker": spk, "text": text,
                         "t_start": round(t, 2), "t_end": round(t + dur, 2)})
            t += dur + 0.6
            if flag == "x":
                priv.append(sid)
            elif flag == "u":
                pub.append(sid)
        pub_text = " ".join(s["text"] for s in segs if s["id"] in pub).lower()
        for f in it["facts"]:
            assert f.lower() in pub_text, f"{iid}: fact not in public text: {f!r}"
        out.append({"id": iid, "source": "synthetic", "case_type": ct, "segments": segs,
                    "private_ids": priv, "public_ids": pub, "public_facts": it["facts"]})
    return out


def main() -> None:
    items = build()
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"wrote {len(items)} items to {OUT}", dict(Counter(i["case_type"] for i in items)))


if __name__ == "__main__":
    main()
