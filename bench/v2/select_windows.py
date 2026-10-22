"""Select real meeting windows from QMSum (ALL split jsonl) and assign subtypes, splits and authors.

Input : bench/data_v2/raw/qmsum/{train,val,test}.jsonl  (github.com/Yale-LILY/QMSum, MIT)
Output: bench/data_v2/work/windows.json         (all windows, with split/author/subtype)
        bench/data_v2/work/brief_<author>.json  (what each author agent sees: its windows only)

Deterministic (seed 20261022). Sealed windows come from meetings disjoint from dev meetings.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "bench" / "data_v2" / "raw" / "qmsum"
WORK = ROOT / "bench" / "data_v2" / "work"
SEED = 20261022

# (case_type, subtype, count). Coarse case_type stays within otr.types.CaseType.
PLAN = [
    ("explicit_start_end", "ese_short", 28),
    ("explicit_start_end", "ese_long_reactions", 28),
    ("explicit_start_implicit_end", "esie_short", 20),
    ("explicit_start_implicit_end", "esie_long", 20),
    ("retroactive", "retro_topic", 24),
    ("retroactive", "retro_count", 18),
    ("retroactive", "retro_other_confirmed", 16),
    ("retroactive", "retro_other_refused", 12),
    ("retroactive", "repair", 22),
    ("implicit", "implicit_health", 12),
    ("implicit", "implicit_salary", 12),
    ("implicit", "implicit_hr_performance", 12),
    ("implicit", "implicit_legal", 12),
    ("implicit", "implicit_layoffs", 12),
    ("implicit", "implicit_personal", 12),
    ("implicit", "cross_segment_pii", 20),
    ("false_alarm", "fa_named_work", 12),
    ("false_alarm", "fa_record_sense", 12),
    ("false_alarm", "fa_quoted_cue", 12),
    ("false_alarm", "fa_negated_cue", 12),
    ("false_alarm", "fa_public_lookalike", 12),
    ("public", "public_plain", 36),
]
SHARED_AUTHORS = ["P1", "P2", "P3", "P4", "P5", "P6"]   # write dev and part of sealed
SEALED_ONLY_AUTHORS = ["P7", "P8"]                      # never seen in dev
SEALED_FROM_SHARED = 8                                   # sealed windows per shared author

# Real turns that already contain privacy-cue-like language are excluded so background labels
# ("public") stay sound. Mentions of recording equipment / transcripts are kept (natural look-alikes).
CUEISH = re.compile(
    r"off the record|on the record|strike that|scratch that|between (?:us|you and me|ourselves)|"
    r"confidential|don't (?:write|put|note|minute)|do not (?:write|put|note|minute)|"
    r"forget (?:what|that|i said)|disregard|leave (?:that|this|it) out|keep (?:that|this|it) (?:out|quiet|private)|"
    r"salary|diagnos|pregnan|lawsuit|fired|layoff|redundan|divorce|password|phone number|social security",
    re.I)

AMI = {"Project Manager", "Marketing", "User Interface", "Industrial Designer"}
ICSI = re.compile(r"^(Grad|Professor|PhD|Postdoc|Undergrad)\b")


def clean(t: str) -> str:
    t = re.sub(r"\{[a-z_]+\}", " ", t)
    t = re.sub(r"\s+([.,?!;:])", r"\1", t)
    t = re.sub(r"\s+(n't|'s|'re|'ve|'ll|'d|'m)\b", r"\1", t)
    t = re.sub(r"(\w) - (?=\w)", lambda m: m.group(1) + "-", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[,.\s-]+", "", t)
    return t


def cap_words(t: str, n: int = 70) -> tuple[str, bool]:
    w = t.split()
    if len(w) <= n:
        return t, False
    sents = re.findall(r"[^.?!]+[.?!]*", t)
    out = ""
    for s in sents:
        if len((out + s).split()) > n:
            break
        out += s
    if len(out.split()) < 12:
        out = " ".join(w[:n])
    return out.strip(), True


def domain(speakers: set[str]) -> str:
    if speakers & AMI:
        return "ami"
    if any(ICSI.match(s) for s in speakers):
        return "icsi"
    return "committee"


def load_meetings() -> list[dict]:
    ms = []
    for split in ("train", "val", "test"):
        with open(RAW / f"{split}.jsonl", encoding="utf-8") as f:
            for i, line in enumerate(f):
                r = json.loads(line)
                turns = []
                for k, u in enumerate(r["meeting_transcripts"]):
                    tx = clean(u["content"])
                    if tx and re.search(r"\w", tx):
                        turns.append({"speaker": u["speaker"].strip(), "text": tx, "orig_idx": k})
                mid = f"qmsum-{split}-{i:03d}"
                ms.append({"meeting": mid, "domain": domain({t["speaker"] for t in turns}), "turns": turns,
                           "topics": [t["topic"] for t in r.get("topic_list", [])][:6]})
    return ms


def windows_for(m: dict, rng: random.Random, k: int) -> list[dict]:
    T = m["turns"]
    out, used = [], []
    tries = 0
    while len(out) < k and tries < 400:
        tries += 1
        n = rng.randint(13, 28)
        if len(T) < n + 2:
            break
        s = rng.randrange(0, len(T) - n)
        if any(not (s + n + 10 <= a or b + 10 <= s) for a, b in used):
            continue
        w = T[s:s + n]
        if len({t["speaker"] for t in w}) < 2:
            continue
        if sum(len(t["text"].split()) >= 4 for t in w) < 0.6 * n:
            continue
        if any(CUEISH.search(t["text"]) for t in w):
            continue
        turns, trunc = [], []
        for j, t in enumerate(w):
            tx, cut = cap_words(t["text"])
            if cut:
                trunc.append(j)
            turns.append({"speaker": t["speaker"], "text": tx, "orig_idx": t["orig_idx"]})
        if sum(len(t["text"].split()) for t in turns) > 900:
            continue
        used.append((s, s + n))
        out.append({"meeting": m["meeting"], "domain": m["domain"], "topics": m["topics"],
                    "start": s, "turns": turns, "truncated_turns": trunc})
    return out


def main() -> int:
    rng = random.Random(SEED)
    meetings = load_meetings()
    slots = [(ct, st) for ct, st, n in PLAN for _ in range(n)]
    rng.shuffle(slots)
    total = len(slots)
    n_sealed = 47 * len(SEALED_ONLY_AUTHORS) + SEALED_FROM_SHARED * len(SHARED_AUTHORS)
    # stratify sealed slots by subtype (proportional), the rest are dev
    by_sub = defaultdict(list)
    for i, (ct, st) in enumerate(slots):
        by_sub[st].append(i)
    sealed_idx = set()
    exact = {st: len(idxs) * n_sealed / total for st, idxs in by_sub.items()}
    quota = {st: int(x) for st, x in exact.items()}
    for st in sorted(exact, key=lambda s: -(exact[s] - quota[s]))[: n_sealed - sum(quota.values())]:
        quota[st] += 1   # largest-remainder allocation
    for st, idxs in by_sub.items():
        sealed_idx.update(idxs[:quota[st]])
    # meetings: split disjointly, stratified by domain (~40% sealed)
    by_dom = defaultdict(list)
    for m in meetings:
        by_dom[m["domain"]].append(m)
    pool = {"dev": [], "sealed": []}
    for d, ms in sorted(by_dom.items()):
        rng.shuffle(ms)
        cut = round(len(ms) * 0.42)
        pool["sealed"] += ms[:cut]
        pool["dev"] += ms[cut:]
    wins = {}
    for sp in ("dev", "sealed"):
        need = sum(1 for i in range(total) if (i in sealed_idx) == (sp == "sealed"))
        cand = []
        for m in pool[sp]:
            cand += windows_for(m, rng, 2)
        rng.shuffle(cand)
        # balance domains: round-robin by domain
        dq = defaultdict(list)
        for w in cand:
            dq[w["domain"]].append(w)
        order, doms = [], sorted(dq)
        while any(dq.values()):
            for d in doms:
                if dq[d]:
                    order.append(dq[d].pop())
        if len(order) < need:
            raise SystemExit(f"not enough windows for {sp}: {len(order)} < {need}")
        wins[sp] = order[:need]
    # authors
    sealed_slots = [i for i in range(total) if i in sealed_idx]
    dev_slots = [i for i in range(total) if i not in sealed_idx]
    rng.shuffle(sealed_slots)
    author_of = {}
    k = 0
    for a in SEALED_ONLY_AUTHORS:
        for _ in range(47):
            author_of[sealed_slots[k]] = a
            k += 1
    for j, i in enumerate(sealed_slots[k:]):
        author_of[i] = SHARED_AUTHORS[j % len(SHARED_AUTHORS)]
    for j, i in enumerate(dev_slots):
        author_of[i] = SHARED_AUTHORS[j % len(SHARED_AUTHORS)]
    allw = []
    it = {"dev": iter(wins["dev"]), "sealed": iter(wins["sealed"])}
    for i, (ct, st) in enumerate(slots):
        sp = "sealed" if i in sealed_idx else "dev"
        w = dict(next(it[sp]))
        w.update({"window_id": f"w{i:03d}", "split": sp, "case_type": ct, "subtype": st,
                  "author": author_of[i]})
        allw.append(w)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "windows.json").write_text(json.dumps(allw, indent=1, ensure_ascii=False), encoding="utf-8")
    for a in SHARED_AUTHORS + SEALED_ONLY_AUTHORS:
        mine = [{"window_id": w["window_id"], "subtype": w["subtype"], "domain": w["domain"],
                 "meeting_topics": w["topics"],
                 "turns": [{"i": j, "speaker": t["speaker"], "text": t["text"]} for j, t in enumerate(w["turns"])]}
                for w in allw if w["author"] == a]
        (WORK / f"brief_{a}.json").write_text(json.dumps(mine, indent=1, ensure_ascii=False), encoding="utf-8")
    print("windows", len(allw), Counter(w["split"] for w in allw), Counter(w["author"] for w in allw))
    print("domains", Counter((w["split"], w["domain"]) for w in allw))
    print("meetings", {sp: len({w["meeting"] for w in allw if w["split"] == sp}) for sp in ("dev", "sealed")})
    print("sealed subtypes", Counter(w["subtype"] for w in allw if w["split"] == "sealed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
