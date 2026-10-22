"""Deterministic ASR-style corruption for OTR-Bench v2 noisy variants.

Applied to EVERY segment of a selected item (not only cue lines, unlike bench/heldout):
  1. lowercase; 2. homophone / mishearing substitutions (word-level, seeded per segment id);
  3. drop ~4% of short function words (never negations, never digits, never the only word);
  4. drop all punctuation except apostrophes and hyphens; collapse whitespace.
Gold labels are unchanged; public_facts are filtered to those still present in the public text.
"""
from __future__ import annotations

import copy
import hashlib
import random
import re

HOMO = {"write": "right", "right": "write", "record": "recored", "notes": "nodes", "minutes": "minits",
        "off": "of", "strike": "strike", "there": "their", "their": "there", "to": "too", "for": "four",
        "know": "no", "weight": "wait", "here": "hear", "pause": "paws", "scratch": "scratched",
        "between": "be tween", "transcript": "transcripts", "bit": "but", "that": "dat", "then": "than",
        "salary": "celery", "leave": "leaf", "health": "help", "board": "bored", "meeting": "meating"}
DROPPABLE = {"the", "a", "an", "and", "of", "to", "that", "just", "so", "uh", "um", "is", "it", "in", "for"}
NEG = {"not", "no", "never", "don't", "dont", "do", "nothing", "n't", "won't", "can't", "isn't", "didn't"}


def corrupt_text(text: str, key: str) -> str:
    r = random.Random(int(hashlib.md5(key.encode()).hexdigest(), 16))
    toks = text.lower().split()
    out = []
    for t in toks:
        core = re.sub(r"[^\w'-]", "", t)
        if core in DROPPABLE and core not in NEG and len(toks) > 3 and r.random() < 0.04:
            continue
        if core in HOMO and r.random() < 0.35:
            t = t.replace(core, HOMO[core])
        out.append(t)
    s = " ".join(out)
    s = re.sub(r"[^\w\s'-]", " ", s)
    return re.sub(r"\s+", " ", s).strip() or text.lower()


def corrupt_item(item: dict) -> dict:
    it = copy.deepcopy(item)
    it["id"] = item["id"] + "-n"
    it["source"] = item["source"] + "-noisy"
    idmap = {}
    for s in it["segments"]:
        new = s["id"] + "-n"
        idmap[s["id"]] = new
        s["text"] = corrupt_text(s["text"], s["id"])
        s["id"] = new
    for k in ("private_ids", "public_ids", "cue_ids"):
        it[k] = [idmap[i] for i in it.get(k, [])]
    prov = it.get("provenance", {})
    for k in ("inserted_ids", "truncated_real_ids"):
        if k in prov:
            prov[k] = [idmap[i] for i in prov[k]]
    if "inserted_roles" in prov:
        prov["inserted_roles"] = {idmap[k]: v for k, v in prov["inserted_roles"].items()}
    pub = " ".join(s["text"] for s in it["segments"] if s["id"] in it["public_ids"])
    norm = (re.sub(r"\s+", " ", re.sub(r"[^\w\s'-]", " ", f.lower())).strip() for f in item["public_facts"])
    it["public_facts"] = [f for f in norm if f and f in pub]
    it["noise"] = "asr-v1: lowercase, homophones, ~4% function-word drops, punctuation removed"
    return it
