"""Convert ConfAIde Tier 4 (meeting secrets) into the OTR-Bench schema. OPTIONAL.

Expected input (you must clone https://github.com/skywalker023/confaide yourself):
    <confaide>/benchmark/tier_4.jsonl   -- one JSON object per line with (best effort) keys:
        "transcript" | "meeting"  : str, the meeting text, one utterance per line "Speaker: text"
        "secret" | "private_info" : str, the sentence/phrase that must not be disclosed
        "public_info" | "public"  : list[str] or str, information that may be shared (optional)
    The real file layout may differ; adjust KEYS below if so. Unrecognised items are skipped.

Usage:  python -m bench.import_confaide <confaide_dir> [--out bench/otr_bench_confaide.jsonl] [--limit 20]
Items are emitted as case_type 'implicit', source 'confaide'. A segment is private if it
contains the secret text (case-insensitive substring or >=60% token overlap), otherwise public.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KEYS = {"transcript": ("transcript", "meeting"),
        "secret": ("secret", "private_info"),
        "public": ("public_info", "public")}


def _get(d: dict, names):
    for n in names:
        if n in d and d[n]:
            return d[n]
    return None


def _overlap(a: str, b: str) -> float:
    ta, tb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(ta & tb) / len(tb) if tb else 0.0


def convert(rec: dict, idx: int):
    text, secret = _get(rec, KEYS["transcript"]), _get(rec, KEYS["secret"])
    if not text or not secret:
        return None
    pub = _get(rec, KEYS["public"]) or []
    pub = [pub] if isinstance(pub, str) else list(pub)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    segs, priv_ids, pub_ids, t = [], [], [], 0.0
    for n, ln in enumerate(lines, 1):
        spk, _, utt = ln.partition(":")
        if not utt:
            spk, utt = "SPEAKER_00", ln
        sid = f"cf-{idx:02d}-s{n:02d}"
        dur = max(1.5, len(utt.split()) * 0.4)
        segs.append({"id": sid, "speaker": spk.strip(), "text": utt.strip(),
                     "t_start": round(t, 2), "t_end": round(t + dur, 2)})
        t += dur + 0.6
        (priv_ids if secret.lower() in utt.lower() or _overlap(utt, secret) >= 0.6 else pub_ids).append(sid)
    if not priv_ids:
        return None
    return {"id": f"cf-{idx:02d}", "source": "confaide", "case_type": "implicit", "segments": segs,
            "private_ids": priv_ids, "public_ids": pub_ids, "public_facts": pub}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("confaide_dir")
    ap.add_argument("--out", default="bench/otr_bench_confaide.jsonl")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    src = Path(a.confaide_dir) / "benchmark" / "tier_4.jsonl"
    if not src.exists():
        raise SystemExit(f"not found: {src} (see module docstring)")
    out = []
    for i, line in enumerate(open(src, encoding="utf-8"), 1):
        it = convert(json.loads(line), i)
        if it:
            out.append(it)
        if len(out) >= a.limit:
            break
    Path(a.out).write_text("\n".join(json.dumps(x) for x in out) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} items to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
