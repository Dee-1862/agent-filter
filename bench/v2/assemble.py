"""Assemble OTR-Bench v2 from real windows + authored insertions (+ ConfAIde Tier 4 sub-source).

  python -m bench.v2.assemble [--labeller-fixes bench/data_v2/work/fixes.json]

Writes
  bench/data_v2/dev/otr2_dev.jsonl, otr2_dev_noisy.jsonl               (committable)
  bench/data_v2/sealed/otr2_sealed.jsonl, otr2_sealed_noisy.jsonl      (gitignored, never commit)
  bench/data_v2/sealed_manifest.json   (md5, counts, per-type counts only; committable)
  bench/data_v2/dev_manifest.json, bench/data_v2/build_report.json (checks, diversity, drops)
Deterministic given the inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from .noise import corrupt_item

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "bench" / "data_v2"
WORK = DATA / "work"
SEED = 20261022
LABELS = {"private", "public", "neutral"}
ROLES = {"cue_start", "cue_end", "secret", "reaction", "retraction", "repair", "confirmation", "objection",
         "pii", "lookalike", "filler", "transition"}
CUE_ROLES = {"cue_start", "cue_end", "retraction", "repair", "confirmation", "objection"}
NO_PRIVATE = {"retro_other_refused", "repair", "fa_named_work", "fa_record_sense", "fa_quoted_cue",
              "fa_negated_cue", "fa_public_lookalike", "public_plain"}
DIFFICULTY = {  # a-priori tier by construction (not measured)
    "ese_short": "easy", "ese_long_reactions": "medium", "esie_short": "medium", "esie_long": "hard",
    "retro_topic": "medium", "retro_count": "medium", "retro_other_confirmed": "hard",
    "retro_other_refused": "hard", "repair": "medium", "cross_segment_pii": "hard",
    "public_plain": "easy", "contextual_confidential": "medium"}


def _difficulty(st: str) -> str:
    if st.startswith("implicit_"):
        return "hard"
    if st.startswith("fa_"):
        return "medium"
    return DIFFICULTY.get(st, "medium")


def domain_of(w: dict) -> str:
    """Corrected domain tag (select_windows.domain mis-tagged committee meetings with a 'Professor <Name>'
    witness as icsi; that tag was only used to balance the split, so windows are unchanged)."""
    sp = {t["speaker"] for t in w["turns"]}
    if sp & {"Project Manager", "Marketing", "User Interface", "Industrial Designer"}:
        return "ami"
    if any(re.match(r"^(Grad|Professor|PhD|Postdoc|Undergrad) [A-Z]$", x) for x in sp):
        return "icsi"
    return "committee"


def wps_duration(text: str, rng: random.Random) -> float:
    w = max(1, len(text.split()))
    return round(max(0.6, w / 2.5 * rng.uniform(0.85, 1.15)), 2)


def pick_facts(segs: list[dict], public_ids: set[str], real_ids: set[str], rng: random.Random, k: int = 3):
    cands = [s for s in segs if s["id"] in public_ids and s["id"] in real_ids and len(s["text"].split()) >= 8]
    rng.shuffle(cands)
    facts = []
    stop = set("the a an and or but so to of in on it is that this i you we uh um yeah well like just i'm it's".split())
    for s in cands[:k]:
        toks = list(re.finditer(r"[A-Za-z0-9][A-Za-z0-9'-]*", s["text"]))
        starts = [i for i in range(len(toks) - 3) if toks[i].group().lower() not in stop
                  and not re.search(r"[.?!]", s["text"][toks[i].start():toks[i + 3].end()])]
        if not starts:
            continue
        i = starts[rng.randrange(len(starts))]
        facts.append(s["text"][toks[i].start():toks[i + 3].end()])
    return facts


def validate(w: dict, a: dict) -> list[str]:
    errs = []
    n = len(w["turns"])
    spk = {t["speaker"] for t in w["turns"]}
    prev = -1
    nlines = 0
    if a.get("subtype") != w["subtype"]:
        errs.append(f"subtype mismatch {a.get('subtype')}")
    for b in a.get("blocks", []):
        at = b.get("after_turn")
        if not isinstance(at, int) or not (2 <= at <= n - 3) or at <= prev:
            errs.append(f"bad after_turn {at} (n={n})")
        prev = at if isinstance(at, int) else prev
        for ln in b.get("lines", []):
            nlines += 1
            if ln.get("speaker") not in spk:
                errs.append(f"unknown speaker {ln.get('speaker')!r}")
            if ln.get("label") not in LABELS:
                errs.append(f"bad label {ln.get('label')}")
            if ln.get("role") not in ROLES:
                errs.append(f"bad role {ln.get('role')}")
            if not str(ln.get("text", "")).strip():
                errs.append("empty text")
    if not 1 <= nlines <= 10:
        errs.append(f"{nlines} inserted lines")
    labs = [ln.get("label") for b in a.get("blocks", []) for ln in b.get("lines", [])]
    if w["subtype"] in NO_PRIVATE and "private" in labs:
        errs.append("private line in a no-private subtype")
    if w["subtype"] not in NO_PRIVATE and "private" not in labs:
        errs.append("no private line in a private subtype")
    if n + nlines > 40 or n + nlines < 14:
        errs.append(f"length {n + nlines} outside 14-40")
    return errs


def build_item(w: dict, a: dict, rng: random.Random) -> dict:
    iid = f"v2-{w['window_id']}"
    rows = []
    blocks = {b["after_turn"]: b["lines"] for b in a["blocks"]}
    for j, t in enumerate(w["turns"]):
        rows.append(("real", t["speaker"], t["text"], "public", None, j))
        for ln in blocks.get(j, []):
            rows.append(("ins", ln["speaker"], ln["text"].strip(), ln["label"], ln["role"], None))
    segs, priv, pub, real_ids, ins_ids, cue_ids, roles, trunc = [], [], [], set(), [], [], {}, []
    t = round(rng.uniform(0.0, 3.0), 2)
    for k, (kind, sp, tx, lab, role, j) in enumerate(rows, 1):
        sid = f"{iid}-s{k:02d}"
        d = wps_duration(tx, rng)
        segs.append({"id": sid, "speaker": sp, "text": tx, "t_start": round(t, 2), "t_end": round(t + d, 2)})
        t += d + rng.uniform(0.15, 1.2)
        (priv if lab == "private" else pub if lab == "public" else []).append(sid)
        if kind == "real":
            real_ids.add(sid)
            if j in w.get("truncated_turns", []):
                trunc.append(sid)
        else:
            ins_ids.append(sid)
            roles[sid] = role
            if role in CUE_ROLES or (role == "lookalike" and w["subtype"].startswith("fa_")):
                cue_ids.append(sid)
    item = {"id": iid, "source": "qmsum+llm-insert", "case_type": w["case_type"], "subtype": w["subtype"],
            "segments": segs, "private_ids": priv, "public_ids": pub,
            "public_facts": pick_facts(segs, set(pub), real_ids, rng),
            "cluster": w["meeting"], "inserted_by": w["author"], "difficulty": _difficulty(w["subtype"]),
            "provenance": {"background": f"real-qmsum:{w['meeting']}", "domain": domain_of(w),
                           "window_start_turn": w["start"], "inserted_ids": ins_ids, "inserted_roles": roles,
                           "truncated_real_ids": trunc},
            "cue_ids": cue_ids}
    return item


# ----------------------------------------------------------------------------- ConfAIde Tier 4
CONF_SECRET = re.compile(r"this reminds me", re.I)


def confaide_items(rng: random.Random) -> list[dict]:
    path = DATA / "raw" / "confaide" / "tier_4.txt"
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\\’", "’").replace("\\'", "'")
    out = []
    for n, (hdr, body) in enumerate(re.findall(r"<BEGIN><([^>]*)>\n(.*?)<END>", raw, re.S)):
        secret, public = [x.strip() for x in hdr.split(",", 1)]
        lines = [l.strip() for l in body.splitlines() if l.strip() and not re.match(r"^\(.*\)$", l.strip())]
        lines = [l for l in lines if ":" in l]
        iid = f"v2-cf{n:02d}"
        segs, priv, pub = [], [], []
        t = round(rng.uniform(0.0, 3.0), 2)
        si = next(i for i, l in enumerate(lines) if CONF_SECRET.search(l))
        for k, l in enumerate(lines[:40], 1):
            sp, tx = l.split(":", 1)
            sid = f"{iid}-s{k:02d}"
            d = wps_duration(tx, rng)
            segs.append({"id": sid, "speaker": sp.strip(), "text": tx.strip(), "t_start": round(t, 2),
                         "t_end": round(t + d, 2)})
            t += d + rng.uniform(0.15, 1.2)
            # secret line and the immediate reaction line (which also asks a question) are private
            (priv if k - 1 in (si, si + 1) else pub).append(sid)
        facts = [public] if any(public.lower() in s["text"].lower() for s in segs if s["id"] in pub) else []
        out.append({"id": iid, "source": "confaide-tier4", "case_type": "implicit",
                    "subtype": "contextual_confidential", "segments": segs, "private_ids": priv, "public_ids": pub,
                    "public_facts": facts, "cluster": f"confaide:{secret}", "inserted_by": "confaide-authors",
                    "difficulty": "medium",
                    "provenance": {"background": f"confaide-tier4:{hdr}", "note": "whole meeting is LLM-generated "
                                   "by the ConfAIde authors; private = secret line + immediate reaction line"},
                    "cue_ids": [segs[si]["id"]]})
    return out


# ----------------------------------------------------------------------------- checks
def ngrams(text: str, n: int) -> set:
    t = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(t[i:i + n]) for i in range(len(t) - n + 1)}


def check_item(it: dict) -> list[str]:
    errs = []
    ids = [s["id"] for s in it["segments"]]
    if len(ids) != len(set(ids)):
        errs.append("dup ids")
    if set(it["private_ids"]) & set(it["public_ids"]):
        errs.append("private/public overlap")
    if not set(it["private_ids"]) | set(it["public_ids"]) <= set(ids):
        errs.append("unknown id in labels")
    prev = -1.0
    for s in it["segments"]:
        if not (s["t_end"] > s["t_start"] >= prev):
            errs.append(f"non-monotone time at {s['id']}")
        prev = s["t_end"]
    if not it["public_ids"]:
        errs.append("no public ids")
    pub_text = " ".join(s["text"] for s in it["segments"] if s["id"] in it["public_ids"]).lower()
    for f in it["public_facts"]:
        if f.lower() not in pub_text:
            errs.append(f"fact not in public text: {f}")
    pubg = set().union(*[ngrams(s["text"], 8) for s in it["segments"] if s["id"] in it["public_ids"]] or [set()])
    for s in it["segments"]:
        if s["id"] in it["private_ids"] and ngrams(s["text"], 8) & pubg:
            errs.append(f"private 8-gram duplicated in public text: {s['id']}")
    return errs


def contamination(items: list[dict]) -> dict:
    corpus = []
    for d in ("tests", "otr"):
        for p in (ROOT / d).rglob("*.py"):
            corpus.append(p.read_text(encoding="utf-8", errors="ignore").lower())
    old = []
    for p in [ROOT / "bench" / "otr_bench.jsonl", ROOT / "bench" / "heldout" / "heldout.jsonl"]:
        if p.exists():
            old.append(p.read_text(encoding="utf-8", errors="ignore").lower())
    big = "\n".join(corpus)
    oldt = "\n".join(old)
    hits, old_hits, n = [], [], 0
    for it in items:
        ins = set(it["provenance"].get("inserted_ids", []))
        for s in it["segments"]:
            if s["id"] not in ins:
                continue
            n += 1
            t = re.sub(r"\s+", " ", s["text"].lower()).strip()
            if len(t) >= 25 and t in big:
                hits.append(s["id"])
            if len(t) >= 25 and t in oldt:
                old_hits.append(s["id"])
    return {"inserted_lines_checked": n, "verbatim_in_tests_or_otr": hits, "verbatim_in_old_bench_sets": old_hits}


STOCK = ["off the record", "on the record", "strike that", "scratch that", "don't write", "do not write",
         "between us", "forget what i said", "disregard", "don't put", "keep this out", "keep that out"]


def diversity(items: list[dict]) -> dict:
    lines, by_author = [], defaultdict(list)
    for it in items:
        roles = it["provenance"].get("inserted_roles", {})
        for s in it["segments"]:
            if roles.get(s["id"]) in {"cue_start", "cue_end", "retraction"}:
                lines.append(s["text"])
                by_author[it["inserted_by"]].append(s["text"])
    stopw = set("the a an and or to of i you we it that this is so uh um just be in on for what me my our".split())
    res = {"n_cue_lines": len(lines)}
    for n in (2, 3, 4):
        df = Counter()
        for l in lines:
            df.update({g for g in ngrams(l, n) if not set(g.split()) <= stopw})
        top = df.most_common(8)
        res[f"distinct_{n}grams"] = len(df)
        res[f"top_{n}grams"] = [(g, c, round(c / max(1, len(lines)), 4)) for g, c in top]
    norm = Counter(re.sub(r"[^a-z ]", "", l.lower()).strip() for l in lines)
    res["max_exact_line_repeat"] = norm.most_common(1)[0][1] if norm else 0
    res["stock_phrase_line_rate"] = {p: round(sum(p in l.lower() for l in lines) / max(1, len(lines)), 4) for p in STOCK}
    res["any_stock_phrase_rate"] = round(sum(any(p in l.lower() for p in STOCK) for l in lines) / max(1, len(lines)), 4)
    res["per_author_cue_lines"] = {a: len(v) for a, v in sorted(by_author.items())}
    res["per_author_distinct_3grams"] = {a: len(set().union(*[ngrams(l, 3) for l in v])) for a, v in sorted(by_author.items())}
    return res


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def write_jsonl(p: Path, items: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def counts(items: list[dict]) -> dict:
    return {"n_items": len(items), "n_with_private": sum(bool(i["private_ids"]) for i in items),
            "n_no_private": sum(not i["private_ids"] for i in items),
            "n_segments": sum(len(i["segments"]) for i in items),
            "n_clusters": len({i["cluster"] for i in items}),
            "case_type": dict(sorted(Counter(i["case_type"] for i in items).items())),
            "subtype": dict(sorted(Counter(i["subtype"] for i in items).items())),
            "author": dict(sorted(Counter(i["inserted_by"] for i in items).items())),
            "domain": dict(sorted(Counter(i["provenance"].get("domain", "confaide") for i in items).items()))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixes", default=str(WORK / "fixes.json"),
                    help="optional JSON {window_id: {'drop': reason} | {'relabel': {inserted_index: label}}}")
    a = ap.parse_args(argv)
    windows = {w["window_id"]: w for w in json.loads((WORK / "windows.json").read_text(encoding="utf-8"))}
    authored = {}
    for p in sorted((WORK / "authored").glob("P*_part*.json")):
        for x in json.loads(p.read_text(encoding="utf-8")):
            authored[x["window_id"]] = x
    fixes = json.loads(Path(a.fixes).read_text(encoding="utf-8")) if Path(a.fixes).exists() else {}
    # diversity pass: over-used cue phrasings (>3% of cue lines) paraphrased by a separate editor agent
    rewritten = defaultdict(list)
    rw = WORK / "rewrite_done.json"
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
        for k, lab in fx.get("relabel", {}).items():   # k = "block:line"
            bi, li = map(int, k.split(":"))
            x["blocks"][bi]["lines"][li]["label"] = lab
        errs = validate(w, x)
        if errs:
            drops[wid] = errs
            continue
        it = build_item(w, x, rng)
        if rewritten.get(wid):
            it["provenance"]["diversity_rewrites"] = rewritten[wid]
        if fx.get("relabel"):
            it["provenance"]["relabelled"] = fx["relabel"]
        e2 = check_item(it)
        if e2:
            drops[wid] = e2
            continue
        items[w["split"]].append(it)
    conf = confaide_items(rng)
    # ConfAIde: cluster by secret; 3 secrets dev, 2 sealed (fixed choice)
    sealed_secrets = {"confaide:maternity leave", "confaide:health concerns"}
    for it in conf:
        errs = check_item(it)
        if errs:
            drops[it["id"]] = errs
            continue
        items["sealed" if it["cluster"] in sealed_secrets else "dev"].append(it)
    # noisy variants: stratified 25% per subtype
    noisy = {}
    for sp, its in items.items():
        by = defaultdict(list)
        for it in its:
            by[it["subtype"]].append(it)
        sel = []
        for st, lst in sorted(by.items()):
            r = random.Random(f"{SEED}-{sp}-{st}")
            k = max(1, round(len(lst) * 0.25))
            sel += r.sample(lst, k)
        noisy[sp] = [corrupt_item(it) for it in sorted(sel, key=lambda i: i["id"])]
    paths = {"dev": DATA / "dev" / "otr2_dev.jsonl", "dev_noisy": DATA / "dev" / "otr2_dev_noisy.jsonl",
             "sealed": DATA / "sealed" / "otr2_sealed.jsonl", "sealed_noisy": DATA / "sealed" / "otr2_sealed_noisy.jsonl"}
    write_jsonl(paths["dev"], items["dev"])
    write_jsonl(paths["dev_noisy"], noisy["dev"])
    write_jsonl(paths["sealed"], items["sealed"])
    write_jsonl(paths["sealed_noisy"], noisy["sealed"])
    allit = items["dev"] + items["sealed"]
    report = {"drops": drops, "n_authored": len(authored), "n_windows": len(windows),
              "contamination": contamination(allit),
              # all/sealed: numbers only (no n-gram text from the sealed split); dev: full detail
              "diversity_all": {k: v for k, v in diversity(allit).items() if not k.startswith("top_")},
              "diversity_sealed": {k: v for k, v in diversity(items["sealed"]).items() if not k.startswith("top_")},
              "diversity_dev": diversity(items["dev"]),
              "max_cue_4gram_rate_all": max([r for _, _, r in diversity(allit)["top_4grams"]] or [0]),
              "max_cue_3gram_rate_all": max([r for _, _, r in diversity(allit)["top_3grams"]] or [0]),
              "noisy_check_errors": {it["id"]: check_item(it) for sp in noisy for it in noisy[sp] if check_item(it)}}
    (DATA / "build_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    for sp in ("dev", "sealed"):
        man = {"split": sp, "files": {k: {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "md5": md5(p),
                                          "n_items": sum(1 for _ in open(p, encoding="utf-8"))}
                                      for k, p in paths.items() if k.startswith(sp)},
               "counts": counts(items[sp]), "noisy_counts": counts(noisy[sp]),
               "seen_author_items": sum(i["inserted_by"] in {"P1", "P2", "P3", "P4", "P5", "P6"} for i in items[sp]),
               "unseen_author_items": sum(i["inserted_by"] in {"P7", "P8"} for i in items[sp])}
        (DATA / f"{sp}_manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(sp, json.dumps(man["counts"]))
    print("drops", len(drops), Counter(e[0].split(" ")[0] for e in drops.values()).most_common(8))
    print("contamination", {k: (v if isinstance(v, int) else len(v)) for k, v in report["contamination"].items()})
    print("diversity", json.dumps({k: v for k, v in report["diversity_all"].items() if not k.startswith("per_")})[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
