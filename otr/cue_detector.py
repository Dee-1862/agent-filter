"""Regex cue detection (explicit start, scope end, retroactive) with false-alarm
handling, plus pure-python TF-IDF-style retroactive target resolution."""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from .llm import extract_json

# ------------------------------------------------------------------ text utils
_STOP = set("""a an the and or but if so of to in on at for from by with about as is are was were be been
being am do does did done have has had i me my we our us you your he she it they them their this that these
those there here what which who whom when where why how not no yes just also very really can could will
would should shall may might must then than too up out over into some any all more most said say says
told tell talk talked mention mentioned ok okay um uh like know think going gonna one thing stuff bit last
earlier before forget strike scratch delete remove disregard ignore take back please""".split())


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_stems(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))
    return [stem(t) for t in toks if t not in _STOP and len(t) > 2]


def tfidf_overlap(topic: str, candidates: dict[str, str]) -> dict[str, float]:
    """Score each candidate id by IDF-weighted overlap with the topic words."""
    q = set(content_stems(topic))
    docs = {i: set(content_stems(t)) for i, t in candidates.items()}
    n = len(docs) or 1
    df = Counter(s for d in docs.values() for s in d)
    scores = {}
    for i, d in docs.items():
        sc = sum(math.log(1 + n / df[s]) for s in q & d)
        if sc > 0:
            scores[i] = sc
    return scores


# ------------------------------------------------------------------ cue regexes
def _norm(t: str) -> str:
    return t.replace("’", "'").replace("‘", "'")


_START = re.compile(
    r"\b(?:off[\s\-]+the[\s\-]+record"
    r"|(?:please\s+)?(?:do\s*n[o']?t|do\s+not|don't)\s+(?:write|put|jot|note)\s+(?:this|that|it)\s+(?:down|in\s+the\s+notes)"
    r"|(?:keep|leave)\s+(?:this|that|it)\s+out\s+of\s+the\s+(?:notes|minutes|record)"
    r"|not\s+for\s+the\s+(?:notes|minutes|record)"
    r"|(?:just\s+|strictly\s+)?between\s+(?:us|you\s+and\s+me|ourselves))\b", re.I)
_END = re.compile(
    r"\b(?:(?:ok(?:ay)?[,.]?\s+|alright[,.]?\s+)?(?:we(?:'re|\s+are)\s+)?back\s+on\s+the\s+record"
    r"|on\s+the\s+record\s+again"
    r"|you\s+can\s+(?:start\s+)?(?:write|writing|take\s+notes|record)\s*(?:again|now)?"
    r"|(?:ok(?:ay)?[,.]?\s+)?we(?:'re|\s+are)\s+back"
    r"|(?:ok(?:ay)?[,.]?\s+)?(?:you\s+can\s+)?resume\s+(?:the\s+)?(?:notes|recording)"
    r"|that(?:'s|\s+is)\s+(?:all\s+)?(?:the\s+)?off[\s\-]+the[\s\-]+record\s+(?:part|stuff)\s+(?:done|over))\b", re.I)
_RETRO = re.compile(
    r"\b(?:strike\s+that|scratch\s+that|disregard\s+that|take\s+that\s+out|"
    r"forget\s+(?:that\s+)?i\s+(?:just\s+)?(?:said|mentioned)(?:\s+(?:that|it|anything))?|"
    r"(?:forget|ignore|disregard|delete|remove|erase|strike|scratch|take\s+back|take\s+out)\s+"
    r"(?:(?:what|everything)\s+i\s+(?:just\s+)?(?:said|mentioned|told\s+you)|(?:all\s+(?:of\s+)?)?that|the\s+last\s+(?:thing|bit|part)|"
    r"what\s+(?:i|we)\s+(?:just\s+)?(?:said|discussed)|"
    r"(?:the\s+)?(?:last|previous)\s+(?:one|two|three|four|five|\d)\s+(?:things?|comments?|sentences?|lines?|"
    r"statements?|remarks?|points?|bits?|parts?|utterances?)))\b", re.I)
_TOPIC = re.compile(r"\b(?:about|regarding|concerning|on|re)\s+(.+?)\s*(?:[.;!?]|,\s+(?:ok|okay|please)|$)", re.I)

_COUNT = re.compile(
    r"\b(?:last|previous)\s+(one|two|three|four|five|\d)\s+(?:things?|comments?|sentences?|lines?|"
    r"statements?|remarks?|points?|bits?|parts?|utterances?)\b", re.I)
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_TITLE_BEFORE = re.compile(
    r"\b(?:movie|film|documentary|book|song|album|episode|podcast|series|show|called|titled|named|"
    r"watched|watching|saw|seen|reading|novel|play|band|magazine|article|blog|track)\b[^.!?]{0,30}$", re.I)
_TITLE_AFTER = re.compile(
    r"^\W{0,3}(?:is|was|were|are|has|had|won|came|stars|starring|the\s+(?:movie|film|show|book|song|album|series)|"
    r"\(|by\s+[A-Z]|with\s+[A-Z])\b", re.I)
_NEG_BEFORE = re.compile(r"(?:\bnot|n't|\bnever|\bisn't|\bwasn't)\s+(?:really\s+|exactly\s+)?(?:going\s+|be\s+|being\s+)?$", re.I)


@dataclass
class Cue:
    kind: Optional[str] = None      # 'start' | 'end' | 'retro' | None
    name: str = ""                  # e.g. 'off_the_record'
    topic: str = ""                 # retro topic phrase ('' = previous utterance)
    false_alarm: bool = False       # matched a start phrase but judged a mention/title
    remainder: str = ""             # text after an end cue
    count: int = 0                  # retro: "the last two things" -> 2 (0 = not given)
    fuzzy: bool = False             # matched only after ASR-noise repair


def _is_false_alarm(text: str, m: re.Match) -> bool:
    before, after = text[: m.start()], text[m.end():]
    if before.rstrip()[-1:] in ('"', "“", "*", "_") or before.endswith(('"', "“")):
        return True
    if after[:1] in ('"', "”"):
        return True
    if _TITLE_BEFORE.search(before) or _TITLE_AFTER.search(after):
        return True
    if _NEG_BEFORE.search(before):
        return True
    if "between" in m.group(0).lower() and (
            re.search(r"\b(?:difference|gap|distance|split|divide|relationship|bond|competition|contract|"
                      r"deal|space|wall|agreement|tension|connection)s?\s+(?:\w+\s+)?$", before, re.I)
            or re.match(r"\s+and\s+(?:the|them|our|their|other|those|everyone)\b", after, re.I)):
        return True
    # Title Case in mid-sentence ("... Off the Record ...")
    raw = m.group(0)
    if re.search(r"Record", raw) and before.strip() and not re.search(r"[.!?]\s*$", before):
        return True
    return False


# ------------------------------------------------------------ ASR-noise repair
# Live STT garbles short cue phrases ("of the record", "strike dat") and drops case and
# punctuation. Strategy: find near-matches of a small set of canonical phrases at TOKEN
# level, rewrite them to the canonical text, then run the strict regexes + false-alarm
# logic on the repaired string. Short function words only match from explicit variant sets
# (so "on" can never be read as "off"); words of >= 5 letters also match by difflib ratio.
_TOK = re.compile(r"[A-Za-z0-9']+")
_VARIANTS = {
    "off": {"off", "of", "awf", "oph", "offf"},
    "the": {"the", "da", "de", "a", "thee", "th", "duh"},
    "that": {"that", "dat", "dhat", "tat", "thet", "thatt"},
    "on": {"on", "an", "un", "onn"},
    "back": {"back", "bak", "bac"},
    "again": {"again", "agen", "agin", "gain"},
    "out": {"out", "owt"},
    "take": {"take", "take", "tak"},
    "strike": {"strike", "striked", "strikes", "stryke", "strick", "stripe", "strikee"},
}
_FUZZY_PHRASES = [
    (("off", "the", "record"), "off the record", "start"),
    (("strike", "that"), "strike that", "retro"),
    (("scratch", "that"), "scratch that", "retro"),
    (("disregard", "that"), "disregard that", "retro"),
    (("take", "that", "out"), "take that out", "retro"),
    (("back", "on", "the", "record"), "back on the record", "end"),
    (("on", "the", "record", "again"), "on the record again", "end"),
]
# "<x> of the record" is ordinary English when preceded by these ("the rest of the record")
_OF_GUARD = {"rest", "end", "part", "copy", "all", "any", "most", "some", "one", "each", "both", "side",
             "top", "bottom", "kind", "sort", "out", "because", "instead", "state", "history", "copies",
             "whole", "half", "portion", "bulk", "majority", "length", "front", "back", "middle", "keeper"}


def _tok_match(want: str, got: str) -> bool:
    got = got.lower().replace("'", "")
    if got == want:
        return True
    if want in _VARIANTS:
        return got in _VARIANTS[want]
    if len(want) >= 5 and len(got) >= 4:
        return difflib.SequenceMatcher(None, want, got).ratio() >= 0.8
    return False


def repair_asr(text: str) -> tuple[str, bool]:
    """Rewrite near-miss cue phrases to canonical form. Returns (text, changed)."""
    toks = [(m.group(0), m.start(), m.end()) for m in _TOK.finditer(text)]
    edits: list[tuple[int, int, str]] = []
    i = 0
    while i < len(toks):
        hit = None
        for words, canon, _kind in _FUZZY_PHRASES:
            n = len(words)
            if i + n > len(toks):
                continue
            seg = [t[0] for t in toks[i:i + n]]
            if all(_tok_match(w, g) for w, g in zip(words, seg)):
                if [g.lower() for g in seg] == list(words):
                    continue            # already exact: strict regex handles it
                if canon == "off the record" and seg[0].lower() in ("of", "awf") and i > 0                         and toks[i - 1][0].lower() in _OF_GUARD:
                    continue
                hit = (n, canon)
                break
        if hit:
            n, canon = hit
            edits.append((toks[i][1], toks[i + n - 1][2], canon))
            i += n
        else:
            i += 1
    if not edits:
        return text, False
    out, pos = [], 0
    for a, b, c in edits:
        out += [text[pos:a], c]
        pos = b
    out.append(text[pos:])
    return "".join(out), True


def _detect_strict(t: str) -> Cue:
    m = _RETRO.search(t)
    if m:
        topic = ""
        tm = _TOPIC.search(t[m.end():])
        if tm:
            topic = tm.group(1).strip()
        cm = _COUNT.search(t)
        count = 0
        if cm:
            g = cm.group(1).lower()
            count = _NUMW.get(g) or int(g)
            topic = ""        # "the last two things" is positional, not a topic
        return Cue("retro", "retro", topic, count=count)
    m = _START.search(t)
    if m:
        if _is_false_alarm(t, m):
            return Cue(None, m.group(0).lower(), false_alarm=True)
        return Cue("start", re.sub(r"\W+", "_", m.group(0).lower()).strip("_"))
    m = _END.search(t)
    if m:
        return Cue("end", "scope_end", remainder=t[m.end():].strip(" ,.;!"))
    return Cue()


def detect(text: str) -> Cue:
    """Cue detection on one utterance: strict regexes first, then ASR-noise repair."""
    t = _norm(text)
    cue = _detect_strict(t)
    if cue.kind is not None or cue.false_alarm:
        return cue
    fixed, changed = repair_asr(t)
    if changed:
        c2 = _detect_strict(fixed)
        if c2.kind is not None:
            c2.fuzzy = True
            return c2
    return cue


# ------------------------------------------------------------ retro resolution
RETRO_PROMPT = """A meeting participant said: "{cue}"
They want earlier statements about that topic removed from the notes.
Candidate segments (id: text):
{cands}

Return JSON only: {{"ids": [<ids of segments that discuss the topic they want removed>]}}"""


def resolve_retro(topic: str, cue_text: str, candidates: list[tuple[str, str, str]],
                  llm=None, previous: Optional[list[str]] = None) -> tuple[list[str], str]:
    """candidates: [(id, speaker, text)] oldest -> newest, excluding the cue segment.
    Returns (segment_ids, method) where method is 'llm' or 'overlap' or 'previous'."""
    if not candidates:
        return [], "none"
    valid = {c[0] for c in candidates}
    if llm is not None:
        try:
            cands = "\n".join(f"{i}: {t}" for i, _, t in candidates)
            obj = extract_json(llm.complete(RETRO_PROMPT.format(cue=cue_text.replace('"', "'"), cands=cands)))
            ids = obj.get("ids") if isinstance(obj, dict) else obj if isinstance(obj, list) else None
            if ids is not None:
                return [str(i) for i in ids if str(i) in valid], "llm"
        except Exception:
            pass
    if not topic.strip():
        if previous is not None:        # caller applied the self-correction rule (same speaker, recent)
            return [i for i in previous if i in valid], "previous"
        return [candidates[-1][0]], "previous"
    scores = tfidf_overlap(topic, {i: t for i, _, t in candidates})
    if not scores:
        return [], "overlap"
    top = max(scores.values())
    return [i for i, _, _ in candidates if scores.get(i, 0) >= 0.5 * top], "overlap"
