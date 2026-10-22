"""Select NEW real meeting windows for OTR-Bench v3 and assign subtypes, splits, authors, batches.

Sources
  * MeetingBank (huuuyeah/meetingbank, CC BY-NC-SA 4.0): US city council transcripts, no speaker labels.
    Raw: bench/data_v3/raw/meetingbank/{train,validation,test}.json (jsonl). Sentences are grouped into
    turns; speaker labels A/B/C are SYNTHETIC placeholders (sticky random alternation, more likely to
    switch after a question or a "thank you"), NOT real diarization.
  * QMSum (MIT; AMI CC BY 4.0, ICSI, parliamentary committees): extra windows from the 232 meetings
    already used by v2, non-overlapping with every v2 window. A meeting keeps the split it had in v2.
Output: bench/data_v3/work/windows.json, brief_<author>_<k>.json   (gitignored)
Deterministic (seed 20261023).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from bench.v2.select_windows import CUEISH, cap_words, clean, domain, load_meetings

ROOT = Path(__file__).resolve().parents[2]
RAWMB = ROOT / "bench" / "data_v3" / "raw" / "meetingbank"
V2W = ROOT / "bench" / "data_v2" / "work" / "windows.json"
WORK = ROOT / "bench" / "data_v3" / "work"
SEED = 20261023

# same 22 subtypes as v2, twice over, public_plain a little higher: 764 new windows
PLAN = [
    ("explicit_start_end", "ese_short", 56), ("explicit_start_end", "ese_long_reactions", 56),
    ("explicit_start_implicit_end", "esie_short", 40), ("explicit_start_implicit_end", "esie_long", 40),
    ("retroactive", "retro_topic", 48), ("retroactive", "retro_count", 36),
    ("retroactive", "retro_other_confirmed", 32), ("retroactive", "retro_other_refused", 24),
    ("retroactive", "repair", 44),
    ("implicit", "implicit_health", 24), ("implicit", "implicit_salary", 24),
    ("implicit", "implicit_hr_performance", 24), ("implicit", "implicit_legal", 24),
    ("implicit", "implicit_layoffs", 24), ("implicit", "implicit_personal", 24),
    ("implicit", "cross_segment_pii", 40),
    ("false_alarm", "fa_named_work", 24), ("false_alarm", "fa_record_sense", 24),
    ("false_alarm", "fa_quoted_cue", 24), ("false_alarm", "fa_negated_cue", 24),
    ("false_alarm", "fa_public_lookalike", 24),
    ("public", "public_plain", 84),
]
N_SEALED = 260
SHARED = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]            # write dev and some sealed
SEALED_ONLY = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]  # never seen in dev
PERSONAS = {
    "Q1": "sales lead who talks in jargon (pipeline, ARR, circle back, take it offline, bandwidth, align)",
    "Q2": "nurse manager: practical, warm, clipped clinical shorthand, talks about shifts, staffing and patients in general terms",
    "Q3": "city council member: measured public-speaking register, constituents, procedure, 'I would just say'",
    "Q4": "startup founder who rambles: tangents, restarts sentences, enthusiasm, mixes the secret into a story",
    "Q5": "lawyer who qualifies everything: 'to the extent that', 'without prejudice', careful hedges, conditional phrasing",
    "Q6": "junior analyst who over-apologises: 'sorry', 'this may be a silly question', minimises, trails off",
    "S1": "teenager-style casual speaker in a school board meeting: slangy, short, 'like', 'literally', 'kinda', lowercase feel",
    "S2": "quiet person who speaks in fragments: very short utterances, ellipses, incomplete sentences, long pauses implied",
    "S3": "Spanish-English code-switcher: mixes Spanish phrases naturally mid-sentence (pues, o sea, no se, ahorita, ya sabes)",
    "S4": "stakeholder who deflects: answers sideways, changes the subject, indirect speech acts, never says the thing directly",
    "S5": "safety officer: procedural, incident-report phrasing, 'for the record' used literally, numbers and regulations",
    "S6": "finance controller: precise numbers, budget lines, variance language, dry understatement",
    "S7": "retired volunteer, folksy and wordy: anecdotes, 'back in my day', polite circumlocution, repeats himself",
}
MB_SHARE = 0.75
HOLD = 0.40   # fraction of meetings (hash) assigned to the sealed pool for new meetings


def h01(s: str) -> float:
    return int(hashlib.md5(("v3-split-" + s).encode()).hexdigest(), 16) % 10000 / 10000


# ----------------------------------------------------------------------------- MeetingBank
SENT = re.compile(r"[^.?!]+[.?!]+(?:\s|$)|[^.?!]+$")


def mb_turns(text: str, rng: random.Random) -> list[dict]:
    text = re.sub(r"\s+", " ", text).strip()
    sents = [s.strip() for s in SENT.findall(text) if s.strip()]
    turns, cur = [], []
    for s in sents:
        cur.append(s)
        n = sum(len(x.split()) for x in cur)
        if n >= 18 and rng.random() < 0.7 or n >= 45:
            turns.append(" ".join(cur))
            cur = []
    if cur:
        turns.append(" ".join(cur))
    out, spk, last = [], "A", ""
    for t in turns:
        if last and (last.endswith("?") or re.match(r"(thank you|thanks|okay|all right)", t, re.I) or
                     rng.random() < 0.18):
            spk = rng.choice([x for x in "ABC" if x != spk])
        out.append({"speaker": f"Speaker {spk}", "text": t})
        last = t
    return out


def mb_meetings() -> list[dict]:
    mt = defaultdict(list)
    for f in ("test", "train", "validation"):
        with open(RAWMB / f"{f}.json", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                m = re.match(r"(.*?_\d{8})", r["uid"])
                mt[m.group(1) if m else r["uid"]].append(r)
    return [{"meeting": f"mb-{k}", "city": k.split("_")[0], "items": sorted(v, key=lambda r: r["uid"])}
            for k, v in sorted(mt.items())]


def mb_window(m: dict, rng: random.Random) -> dict | None:
    items = [r for r in m["items"] if len(r["transcript"].split()) >= 450]
    rng.shuffle(items)
    for r in items[:6]:
        T = mb_turns(r["transcript"], rng)
        n = rng.randint(13, 26)
        if len(T) < n + 4:
            continue
        for _ in range(12):
            s = rng.randrange(1, len(T) - n)
            w = T[s:s + n]
            if any(CUEISH.search(t["text"]) for t in w):
                continue
            turns, trunc = [], []
            for j, t in enumerate(w):
                tx, cut = cap_words(t["text"])
                if cut:
                    trunc.append(j)
                turns.append({"speaker": t["speaker"], "text": tx, "orig_idx": s + j})
            if len({t["speaker"] for t in turns}) < 2 or sum(len(t["text"].split()) for t in turns) > 900:
                continue
            if sum(len(t["text"].split()) >= 4 for t in turns) < 0.6 * n:
                continue
            return {"meeting": m["meeting"], "domain": "council-" + m["city"], "topics": [],
                    "start": s, "turns": turns, "truncated_turns": trunc, "source": "meetingbank",
                    "item_uid": r["uid"]}
    return None


# ----------------------------------------------------------------------------- QMSum extras
def qm_windows(m: dict, rng: random.Random, used: list[tuple[int, int]], k: int) -> list[dict]:
    T = m["turns"]
    out, mine = [], list(used)
    for _ in range(300):
        if len(out) >= k:
            break
        n = rng.randint(13, 28)
        if len(T) < n + 2:
            break
        s = rng.randrange(0, len(T) - n)
        if any(not (s + n + 10 <= a or b + 10 <= s) for a, b in mine):
            continue
        w = T[s:s + n]
        if len({t["speaker"] for t in w}) < 2 or sum(len(t["text"].split()) >= 4 for t in w) < 0.6 * n:
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
        mine.append((s, s + n))
        out.append({"meeting": m["meeting"], "domain": m["domain"], "topics": m["topics"], "start": s,
                    "turns": turns, "truncated_turns": trunc, "source": "qmsum"})
    return out


def main() -> int:
    rng = random.Random(SEED)
    v2w = json.loads(V2W.read_text(encoding="utf-8"))
    v2_split = {}
    v2_used = defaultdict(list)
    for w in json.loads((ROOT / "bench/data_v2/work/windows.json").read_text(encoding="utf-8")):
        v2_split[w["meeting"]] = w["split"]
        v2_used[w["meeting"]].append((w["start"], w["start"] + len(w["turns"])))
    slots = [(ct, st) for ct, st, n in PLAN for _ in range(n)]
    rng.shuffle(slots)
    total = len(slots)
    by_sub = defaultdict(list)
    for i, (_, st) in enumerate(slots):
        by_sub[st].append(i)
    exact = {st: len(ix) * N_SEALED / total for st, ix in by_sub.items()}
    quota = {st: int(x) for st, x in exact.items()}
    for st in sorted(exact, key=lambda s: -(exact[s] - quota[s]))[: N_SEALED - sum(quota.values())]:
        quota[st] += 1
    sealed_idx = set()
    for st, ix in by_sub.items():
        sealed_idx.update(ix[:quota[st]])
    need = {"sealed": len(sealed_idx), "dev": total - len(sealed_idx)}
    need_qm = {sp: round(need[sp] * (1 - MB_SHARE)) for sp in need}
    need_mb = {sp: need[sp] - need_qm[sp] for sp in need}

    # QMSum extra windows: a meeting keeps its v2 split; meetings unused by v2 are split by hash
    qms = load_meetings()
    qpool = {"dev": [], "sealed": []}
    for m in qms:
        sp = v2_split.get(m["meeting"]) or ("sealed" if h01(m["meeting"]) < HOLD else "dev")
        m["domain"] = domain({t["speaker"] for t in m["turns"]})
        qpool[sp].append(m)
    qm_sel = {}
    for sp in ("dev", "sealed"):
        cand = []
        for cap in (1, 2):
            cand = []
            for m in qpool[sp]:
                cand += qm_windows(m, rng, v2_used.get(m["meeting"], []), cap)
            if len(cand) >= need_qm[sp]:
                break
        rng.shuffle(cand)
        dq = defaultdict(list)
        for w in cand:
            dq[w["domain"]].append(w)
        order, doms = [], sorted(dq)
        while any(dq.values()):
            for d in doms:
                if dq[d]:
                    order.append(dq[d].pop())
        qm_sel[sp] = order[:need_qm[sp]]
        print("qmsum", sp, len(cand), "->", len(qm_sel[sp]))
    # MeetingBank: one window per meeting, split by hash, round-robin over cities
    mbs = mb_meetings()
    mbpool = {"dev": [], "sealed": []}
    for m in mbs:
        mbpool["sealed" if h01(m["meeting"]) < HOLD else "dev"].append(m)
    mb_sel = {}
    for sp in ("dev", "sealed"):
        ms = mbpool[sp]
        rng.shuffle(ms)
        bycity = defaultdict(list)
        for m in ms:
            bycity[m["city"]].append(m)
        order, cities = [], sorted(bycity)
        while any(bycity.values()):
            for c in cities:
                if bycity[c]:
                    order.append(bycity[c].pop())
        got = []
        for m in order:
            w = mb_window(m, rng)
            if w:
                got.append(w)
            if len(got) >= need_mb[sp]:
                break
        if len(got) < need_mb[sp]:
            raise SystemExit(f"not enough MeetingBank windows for {sp}: {len(got)}")
        mb_sel[sp] = got
        print("meetingbank", sp, len(ms), "meetings ->", len(got))
    wins = {}
    for sp in ("dev", "sealed"):
        allw = qm_sel[sp] + mb_sel[sp]
        rng.shuffle(allw)
        wins[sp] = allw
    # authors
    sealed_slots = sorted(sealed_idx)
    dev_slots = [i for i in range(total) if i not in sealed_idx]
    rng.shuffle(sealed_slots)
    author_of, k = {}, 0
    per_s = len(sealed_slots) * 3 // 4 // len(SEALED_ONLY)
    for a in SEALED_ONLY:
        for _ in range(per_s):
            author_of[sealed_slots[k]] = a
            k += 1
    for j, i in enumerate(sealed_slots[k:]):
        author_of[i] = SHARED[j % len(SHARED)]
    for j, i in enumerate(dev_slots):
        author_of[i] = SHARED[j % len(SHARED)]
    allw, it = [], {"dev": iter(wins["dev"]), "sealed": iter(wins["sealed"])}
    for i, (ct, st) in enumerate(slots):
        sp = "sealed" if i in sealed_idx else "dev"
        w = dict(next(it[sp]))
        w.update({"window_id": f"x{i:03d}", "split": sp, "case_type": ct, "subtype": st, "author": author_of[i]})
        allw.append(w)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "windows.json").write_text(json.dumps(allw, indent=1, ensure_ascii=False), encoding="utf-8")
    # briefs: <= 24 windows per batch
    nb = {}
    for a in SHARED + SEALED_ONLY:
        mine = [w for w in allw if w["author"] == a]
        rng.shuffle(mine)
        nbatch = max(1, -(-len(mine) // 24))
        for b in range(nbatch):
            part = mine[b::nbatch]
            brief = [{"window_id": w["window_id"], "subtype": w["subtype"], "setting": w["domain"],
                      "turns": [{"i": j, "speaker": t["speaker"], "text": t["text"]} for j, t in enumerate(w["turns"])]}
                     for w in part]
            (WORK / f"brief_{a}_{b + 1}.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False),
                                                          encoding="utf-8")
        nb[a] = nbatch
    print("batches", nb, "total", sum(nb.values()))
    print("windows", len(allw), Counter(w["split"] for w in allw))
    print("source", Counter((w["split"], w["source"]) for w in allw))
    print("meetings", {sp: len({w["meeting"] for w in allw if w["split"] == sp}) for sp in ("dev", "sealed")})
    print("authors", Counter(w["author"] for w in allw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
