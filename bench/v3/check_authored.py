"""Author self-check: python -I bench/v3/check_authored.py <brief.json> <output.json>
Prints validation errors per window (same rules the assembler applies). Reads only the two given files."""
import json
import sys
from pathlib import Path

LABELS = {"private", "public", "neutral"}
ROLES = {"cue_start", "cue_end", "secret", "reaction", "retraction", "repair", "confirmation", "objection",
         "pii", "lookalike", "filler", "transition"}
NO_PRIVATE = {"retro_other_refused", "repair", "fa_named_work", "fa_record_sense", "fa_quoted_cue",
              "fa_negated_cue", "fa_public_lookalike", "public_plain"}


def validate(w, a):
    errs, n = [], len(w["turns"])
    spk = {t["speaker"] for t in w["turns"]}
    prev, nl = -1, 0
    if a.get("subtype") != w["subtype"]:
        errs.append(f"subtype mismatch {a.get('subtype')}")
    for b in a.get("blocks", []):
        at = b.get("after_turn")
        if not isinstance(at, int) or not (2 <= at <= n - 3) or at <= prev:
            errs.append(f"bad after_turn {at} (n={n})")
        prev = at if isinstance(at, int) else prev
        for ln in b.get("lines", []):
            nl += 1
            if ln.get("speaker") not in spk:
                errs.append(f"unknown speaker {ln.get('speaker')!r}")
            if ln.get("label") not in LABELS:
                errs.append(f"bad label {ln.get('label')}")
            if ln.get("role") not in ROLES:
                errs.append(f"bad role {ln.get('role')}")
            if not str(ln.get("text", "")).strip():
                errs.append("empty text")
    if not 1 <= nl <= 10:
        errs.append(f"{nl} inserted lines")
    labs = [ln.get("label") for b in a.get("blocks", []) for ln in b.get("lines", [])]
    if w["subtype"] in NO_PRIVATE and "private" in labs:
        errs.append("private line in a no-private subtype")
    if w["subtype"] not in NO_PRIVATE and "private" not in labs:
        errs.append("no private line in a private subtype")
    if "public" not in labs:
        errs.append("no inserted public line")
    if n + nl > 40 or n + nl < 14:
        errs.append(f"length {n + nl} outside 14-40")
    return errs


def main():
    brief = {w["window_id"]: w for w in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}
    out = {x["window_id"]: x for x in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))}
    bad = 0
    for wid, w in brief.items():
        e = validate(w, out[wid]) if wid in out else ["missing"]
        if e:
            bad += 1
            print(wid, w["subtype"], e)
    print(f"{len(brief)} windows, {len(out)} authored, {bad} with errors")


main()
