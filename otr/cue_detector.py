"""Regex cue detection (explicit start, scope end, retroactive) with false-alarm
handling, plus pure-python TF-IDF-style retroactive target resolution."""
from __future__ import annotations

import difflib
import math
import re
import threading
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


_CONTRACTIONS = {"let's", "that's", "it's", "what's", "here's", "there's", "he's", "she's", "who's",
                 "how's", "where's", "when's", "one's"}


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_stems(text: str) -> list[str]:
    toks = re.findall(r"[A-Za-z0-9']+", text.replace("’", "'"))
    out = []
    for raw in toks:
        t = raw.lower()
        if t.endswith("'s") and t not in _CONTRACTIONS:
            t = t[:-2]                       # possessive: "elena's" -> "elena"
        if len(t) == 2 and raw.isupper() and raw.isalpha() and t not in _STOP:
            out.append(t)                    # acronym: "QA", "HR", "PM" are real topic words
            continue
        if t in _STOP or t in _CONTRACTIONS or len(t) <= 2 or t.endswith(("n't", "'ll", "'re", "'ve", "'d", "'m")):
            continue
        out.append(stem(t))
    return out


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
    r"|(?:i'?d|i\s+would)\s+rather\s+(?:this|that|it)\s+(?:not\s+)?(?:go|be\s+put|be\s+written)\s+(?:in|into|down)\s*(?:the\s+)?(?:notes|minutes|record)?"
    r"|hold\s+off\s+(?:on\s+)?(?:writing|noting|recording|taking\s+notes)"
    r"|(?:stop|pause)\s+(?:the\s+)?(?:recording|notes|note[\s\-]?taking|transcript)"
    r"|(?:please\s+)?(?:do\s*n[o']?t|do\s+not|don't)\s+(?:take\s+notes|record|transcribe|minute)\b"
    r"|(?:just\s+|strictly\s+)?between\s+(?:us|you\s+and\s+me|ourselves))\b", re.I)
_END = re.compile(
    r"\b(?:(?:ok(?:ay)?[,.]?\s+|alright[,.]?\s+)?(?:we(?:'re|\s+are)\s+)?back\s+on\s+the\s+record"
    r"|on\s+the\s+record\s+again"
    r"|you\s+can\s+(?:start\s+)?(?:write|writing|take\s+notes|record)\s*(?:again|now)?"
    r"|(?:ok(?:ay)?[,.]?\s+)?we(?:'re|\s+are)\s+back"
    r"|(?:ok(?:ay)?[,.]?\s+)?(?:you\s+can\s+)?resume\s+(?:the\s+)?(?:notes|recording)"
    r"|that(?:'s|\s+is)\s+(?:all\s+)?(?:the\s+)?off[\s\-]+the[\s\-]+record\s+(?:part|stuff)\s+(?:done|over)"
    r"|(?:that(?:'s|\s+is)|this\s+is|and)\s+(?:the\s+)?end\s+of\s+(?:the\s+)?off[\s\-]+(?:the[\s\-]+)?record(?:\s+(?:part|stuff|bit))?"
    r"|off[\s\-]+the[\s\-]+record\s+(?:part\s+|bit\s+)?(?:is\s+)?(?:over|done|finished|ended)"
    r"|(?:you\s+can\s+|we\s+can\s+|let's\s+)?(?:start|resume|continue|restart)\s+(?:taking\s+|the\s+)?(?:official\s+)?(?:notes|recording|minutes)(?:\s+again)?"
    r"|that(?:'s|\s+is)\s+(?:all|it)\s+(?:of\s+|for\s+)?(?:the\s+)?(?:sensitive|private|confidential)\s+(?:part|stuff|bit)"
    r"|(?:we(?:'re|\s+are)|i(?:'m|\s+am))\s+(?:now\s+)?on\s+the\s+record)\b", re.I)
_RETRO = re.compile(
    r"\b(?:strike\s+that|scratch\s+that|disregard\s+that|take\s+that\s+out|"
    r"forget\s+(?:that\s+)?i\s+(?:just\s+)?(?:said|mentioned)(?:\s+(?:that|it|anything))?|"
    r"(?:forget|ignore|disregard|delete|remove|erase|strike|scratch|take\s+back|take\s+out)\s+"
    r"(?:(?:what|everything)\s+i\s+(?:just\s+)?(?:said|mentioned|told\s+you)|(?:all\s+(?:of\s+)?)?that|the\s+last\s+(?:thing|bit|part)|"
    r"what\s+(?:i|we)\s+(?:just\s+)?(?:said|discussed)|"
    r"(?:the\s+|my\s+)?(?:last|previous)\s+(?:(?:one|two|three|four|five|\d)\s+)?(?:things?|comments?|sentences?|lines?|"
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
_ARTICLE_BEFORE = re.compile(r"\b(?:a|an|the)\s+$", re.I)
_MODIFIER_AFTER = re.compile(
    r"^\s+(?:pay|payments?|comments?|remarks?|statements?|conversations?|discussions?|agreements?|arrangements?|"
    r"deals?|briefings?|sources?|interviews?|quotes?|success|story|stories|tip|tips|chats?|bonus|bonuses|"
    r"information|material|guidance)\b", re.I)
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
    weak: bool = False              # structured match with partial evidence: ask the LLM when available
    accept_alone: bool = True       # a weak cue may still be acted on when no LLM can confirm it
    gate: bool = False              # no cue found, but the text has a cheap cue-related signal
    source: str = "regex"           # 'regex' | 'structured' | 'llm'
    span: tuple = ()                # (start, end) of the retract phrase in the text it was found in
    corrected: bool = False         # retract cue carries a correction marker ("I misspoke")
    keep_text: str = ""             # correction case: the utterance with the retract clause removed


def _is_false_alarm(text: str, m: re.Match) -> bool:
    before, after = text[: m.start()], text[m.end():]
    if before.rstrip()[-1:] in ('"', "“", "*", "_") or before.endswith(('"', "“")):
        return True
    if after[:1] in ('"', "”") or (after[:1] == "'" and "'" in before.replace("n't", "").replace("'s", "")):
        return True
    # noun-phrase use ("an off the record success story", "off the record pay"), not a command
    if _ARTICLE_BEFORE.search(before) or _MODIFIER_AFTER.search(after):
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
        if not cm and re.search(r"\b(?:both|those\s+two)\b", t, re.I):
            count = 2
            topic = ""
        if cm:
            g = cm.group(1).lower()
            count = _NUMW.get(g) or int(g)
            topic = ""        # "the last two things" is positional, not a topic
        if tm and _CORR.search(t) and "," in topic:
            topic = topic.split(",")[0].strip()          # "about Atlas, I misspoke, ..." -> "Atlas"
        end = m.end() + (tm.start(1) + len(topic) if tm else 0)
        return Cue("retro", "retro", topic, count=count, span=(m.start(), end))
    m = _START.search(t)
    e = _END.search(t)
    if m and e and e.start() <= m.start() < e.end():
        m = None                    # "that's the end of off the record": the start phrase is inside an end cue
    if m:
        if _is_false_alarm(t, m):
            return Cue(None, m.group(0).lower(), false_alarm=True)
        return Cue("start", re.sub(r"\W+", "_", m.group(0).lower()).strip("_"))
    if e:
        return Cue("end", "scope_end", remainder=t[e.end():].strip(" ,.;!"))
    return Cue()


# ======================================================================================
# Structured intent detector (generalises beyond fixed phrase lists)
#
# A cue is not matched as one fixed phrase but composed from independent features found in
# one sentence:
#   start   = OBJECT (notes / minutes / record / transcript / "write ... down")
#             + NEGATION-EXCLUSION (keep ... out, leave out, skip, omit, "not in", "don't write")
#             + FRAME (can we / let's / please / I'd rather) or TARGET (this / that / part / bit)
#   end     = a RESUME verb phrase about the record ("we can write things down again",
#             "back on the record", "okay, resume", "start taking notes again")
#   retract = a RETRACT verb (scratch / strike / disregard / forget / take back ...) + a
#             speech-act reference (the bit / what I said / that) [+ "about <topic>"],
#             or a correction marker ("I misspoke")
# Evidence is graded: all three start features = certain; OBJECT+NEGATION only = weak (the LLM
# is asked when there is one; without an LLM only weak cues with a strong negation are acted on).
# ASR noise: word-level fuzzy canonicalisation of the cue vocabulary runs as a second chance.
# ======================================================================================
_CANON = ["notes", "minutes", "record", "recording", "transcript", "scratch", "retract", "disregard",
          "forget", "delete", "remove", "resume", "confidential", "written", "exclude", "omit",
          "misspoke", "correction", "summary", "redact", "pause", "withdraw", "mention"]
_CANON_EXACT = {"nodes": "notes", "nots": "notes", "noats": "notes", "mints": "minutes", "recored": "record",
                "recrod": "record", "reckord": "record", "scrach": "scratch", "skratch": "scratch",
                "misspoken": "misspoke", "mispoke": "misspoke", "mis-spoke": "misspoke",
                "keap": "keep", "kepp": "keep", "keeb": "keep", "keeep": "keep", "leev": "leave",
                "skipp": "skip", "ommit": "omit", "exlude": "exclude"}
_CANON_SKIP = {"recorder", "recorders", "remote", "removal", "remover", "noted", "notice", "notion", "notable",
               "recoded", "recorded", "pausing", "paused", "mentions", "mentioned", "minute", "deleted",
               "removed", "removes", "forgot", "forgive", "forgave", "forgets", "summary", "summaries",
               "written", "wrote", "resumed", "resumes", "scratched", "scratches"}


def canon_words(text: str) -> tuple[str, bool]:
    """Word-level ASR repair of the cue vocabulary ('recored' -> 'record', 'nodes' -> 'notes')."""
    changed = False

    def fix(m: re.Match) -> str:
        nonlocal changed
        w = m.group(0)
        lw = w.lower()
        if lw in _CANON_EXACT:
            changed = True
            return _CANON_EXACT[lw]
        if len(lw) < 5 or lw in _CANON or lw in _CANON_SKIP:
            return w
        best, score = None, 0.0
        for c in _CANON:
            if c[0] != lw[0] or abs(len(c) - len(lw)) > 2:
                continue
            r = difflib.SequenceMatcher(None, c, lw).ratio()
            if r > score:
                best, score = c, r
        if best and score >= 0.84:
            changed = True
            return best
        return w

    return re.sub(r"[A-Za-z][A-Za-z\-]*", fix, text), changed


_SENT = re.compile(r"[^.!?;\n]+[.!?;]*")
_Q_START = re.compile(r"^\W*(?:did|was|were|has|have|had|who|what|why|how|when|where|which|does|do)\b", re.I)
_FRAME = re.compile(
    r"\b(?:can|could|may|might|shall|should|would|will)\s+(?:we|you|i|everyone|someone|y'?all|u)\b|\blet'?s\b|"
    r"\blet\s+us\b|\bplease\b|\bpls\b|\bkindly\b|\bwould\s+you\s+mind\b|"
    r"\bi(?:'d|\s+would|\s+will)\s+(?:rather|prefer|like|appreciate|ask)\b|\bi\s+(?:want|need|prefer|ask)\b|"
    r"\bwe\s+(?:should|need\s+to|must|ought)\b|\bhow\s+about\b|\bdo\s+me\s+a\s+favou?r\b|\bif\s+you\s+don'?t\s+mind\b", re.I)
_TARGET = re.compile(
    r"\b(?:this|that|it|these|those|the\s+(?:next|following|rest|last|upcoming)|part|bit|section|portion|stuff|"
    r"conversation|discussion|topic|piece|bits|what\s+i\s+say|what\s+follows)\b", re.I)
_OBJ = re.compile(r"\b(?:notes?|minutes|records?|recording|recorded|transcripts?|transcription|summary|"
                  r"write[\s\-]?up|written|logs?|minuted|noted)\b", re.I)
_OBJ_DOWN = re.compile(r"\b(?:write|writing|jot|type|put|note|log|put\s+it|take)\b(?:\W+\w+){0,3}?\W+down\b", re.I)
_OBJ_NOTES = r"(?:notes?|minutes|record|transcript|summary|write[\s\-]?up|log)"
# (regex, polarity_guard). A guard means "preceded by not / never / n't" flips the meaning.
_NEG_STRONG = [
    (re.compile(r"\b(?:keep|keeping|leave|leaving)\b(?:\W+\w+){0,6}?\W+(?:out|off)\b", re.I), True),
    (re.compile(r"\b(?:skip|skipping|omit|omitting|exclude|excluding|redact|redacting|pause|suspend|hide|hiding|"
                r"hold\s+off)\b", re.I), True),
    (re.compile(r"\b(?:stop|stopping)\b(?:\W+\w+){0,2}?\W+(?:notes?|taking|recording|writing|minut\w+|transcri\w+)\b",
                re.I), True),
    (re.compile(rf"\bout\s+of\s+(?:the\s+|our\s+|any\s+)?{_OBJ_NOTES}\b", re.I), True),
    (re.compile(r"\boff\s+(?:the\s+)?(?:notes|minutes|transcript|write[\s\-]?up)\b", re.I), True),
    (re.compile(r"(?:\b(?:not|never|no|dont)|n't)\b(?:\W+(?!forget\b|remember\b|hesitate\b|miss\b|neglect\b|fail\b|ever\b|just\b|need\b)\w+){0,2}?\W+"
                r"(?:write|record|note|minute|jot|log|transcribe|document|capture|type|put|include|mention|list|take|"
                r"taking|keep|writing|recording)\b", re.I), False),
]
_NEG_GENERIC = [
    (re.compile(rf"(?:\b(?:not|never|no)|n't)\b(?:\W+\w+){{0,2}}?\W+(?:in|into|on|from|for)\s+(?:\w+\s+)?(?:the\s+|our\s+|any\s+)?"
                rf"{_OBJ_NOTES}\b", re.I), False),
    (re.compile(r"(?:\b(?:not|never)|n't)\s+(?:\w+\s+){0,2}(?:written|recorded|noted|minuted|logged|transcribed|"
                r"captured)\b", re.I), False),
]
_FLIP = re.compile(r"(?:\bnot|n't|\bnever|\bno\s+need\s+to|\bwithout|\bdont)\W+(?:\w+\W+)?$", re.I)

_END_PATS = [
    re.compile(r"\b(?:write|writing|record|recording|note|noting|minute|minuting|jot|transcribe|transcribing|log|"
               r"take\s+notes|taking\s+notes)(?:\s+(?:things|it|this|stuff|everything|anything|down|up|the|notes?|"
               r"minutes|meeting|official(?:ly)?|normally|again|as\s+usual)){0,4}?\s+(?:again|now|as\s+usual)\b", re.I),
    re.compile(r"\b(?:you|we)\s+(?:can|could|may)\s+(?:go\s+ahead\s+and\s+|start\s+|begin\s+)?"
               r"(?:writing|recording|taking\s+notes|noting|minuting)\b", re.I),
    re.compile(r"\b(?:go\s+ahead\s+and|feel\s+free\s+to)\s+(?:write|record|take\s+notes|minute|note)\b", re.I),
    re.compile(r"\bback\s+(?:on|for|to|in|at)\s+(?:the\s+)?(?:record|notes|minutes|transcript|official)\b", re.I),
    re.compile(r"\b(?:resume|resuming|restart|continue|unpause|reactivate)\b(?:\s+\w+){0,3}?\s+"
               r"(?:notes|note[\s\-]?taking|recording|minutes|transcript|writing|record)\b", re.I),
    re.compile(r"^\W*(?:(?:ok(?:ay)?|alright|all\s+right|right|so|good)\W+)*(?:resume|unpause)\W*$", re.I),
    re.compile(r"\b(?:notes|recording|record|minutes)\s+(?:are|is)\s+(?:back\s+on|on\s+again|rolling\s+again|live\s+again)\b",
               re.I),
    re.compile(r"\b(?:we're|we\s+are|you're|you\s+are|i'm)\s+(?:now\s+)?(?:back\s+)?(?:on|in)\s+(?:the\s+)?record\b",
               re.I),
]
_END_NEG = re.compile(r"(?:\bnot|n't|\bnever|\bstop|\bwithout|\bdont|\bdon't)\W+(?:\w+\W+){0,2}$", re.I)

_R_VERB = (r"(?:scratch|strike|disregard|ignore|forget|delete|remove|erase|retract|withdraw|take\s+back|take\s+out|"
           r"cross\s+out|never\s*mind|cancel|undo|unsay)")
_SPEECH = re.compile(r"\b(?:said|says|mentioned|told|bit|part|thing|line|comment|remark|statement|point|earlier|"
                     r"number|figure|stuff|claim|update|estimate|sentence|that|those)\b", re.I)
_R_ABOUT = re.compile(rf"\b{_R_VERB}\b(?P<fill>(?:\s+[\w']+){{0,6}}?)\s+(?:about|on|regarding|re|concerning|around)"
                      rf"\s+(?P<topic>[^,.;!?]+)", re.I)
_R_NOUN = re.compile(rf"\b{_R_VERB}\b\s+(?:the\s+|that\s+|my\s+|those\s+)?(?P<topic>(?:[\w']+\s+){{1,3}}?)"
                     rf"(?:bit|part|thing|line|comment|remark|statement|point|figure|number|claim|update|estimate|"
                     rf"sentence)\b", re.I)
_CORR = re.compile(r"\b(?:i\s+mis[\s\-]?spoke|that\s+was\s+wrong|i\s+got\s+that\s+wrong|let\s+me\s+correct(?:\s+that)?|"
                   r"i\s+said\s+it\s+wrong|my\s+mistake|i\s+was\s+wrong|correction)\b", re.I)
_CORR_ONLY = re.compile(r"\b(?:i\s+mis[\s\-]?spoke|that\s+was\s+wrong|i\s+got\s+that\s+wrong|let\s+me\s+correct(?:\s+that)?|"
                        r"correction)\b", re.I)
_TOPIC_CUT = re.compile(r"\b(?:i\s+mis[\s\-]?spoke|because|since|i\s+meant|i\s+was|it\s+was|it's|they|he|she|"
                        r"which|but|actually)\b", re.I)
_TOPIC_DROP = {"the", "my", "that", "a", "an", "our", "this", "those", "what", "i", "said", "about", "on", "just"}


def _inside_quotes(t: str, pos: int) -> bool:
    return t[:pos].count('"') % 2 == 1 or t[:pos].count("“") > t[:pos].count("”")


def _neg_hit(s: str, rules) -> bool:
    for rx, guard in rules:
        for m in rx.finditer(s):
            if guard and _FLIP.search(s[max(0, m.start() - 30): m.start()]):
                continue
            return True
    return False


def _structured_start(t: str) -> Optional[Cue]:
    for s, off in ((m.group(0), m.start()) for m in _SENT.finditer(t)):
        if _Q_START.match(s) or _inside_quotes(t, off):
            continue
        if not (_OBJ.search(s) or _OBJ_DOWN.search(s)):
            continue
        strong, generic = _neg_hit(s, _NEG_STRONG), _neg_hit(s, _NEG_GENERIC)
        if not (strong or generic):
            continue
        certain = bool(_FRAME.search(s) or (strong and _TARGET.search(s)))
        return Cue("start", "intent_start", weak=not certain, accept_alone=certain or strong, source="structured")
    return None


def _structured_end(t: str) -> Optional[Cue]:
    for s, off in ((m.group(0), m.start()) for m in _SENT.finditer(t)):
        if _Q_START.match(s) or _inside_quotes(t, off):
            continue
        for rx in _END_PATS:
            m = rx.search(s)
            if m and not _END_NEG.search(s[max(0, m.start() - 24): m.start()]):
                rem = (s[m.end():] + t[off + len(s):]).strip(" ,.;!?")
                return Cue("end", "intent_end", remainder=rem, source="structured")
    return None


def _clean_topic(raw: str) -> str:
    raw = _TOPIC_CUT.split(raw)[0]
    words = re.findall(r"[\w'\-]+", raw)
    while words and words[0].lower() in _TOPIC_DROP:
        words.pop(0)
    return " ".join(words[:6])


def _structured_retract(t: str) -> Optional[Cue]:
    for rx in (_R_ABOUT, _R_NOUN):
        for m in rx.finditer(t):
            if _FLIP.search(t[max(0, m.start() - 24): m.start()]):
                continue
            corr = bool(_CORR.search(t))
            if rx is _R_ABOUT and not (corr or _SPEECH.search(m.group("fill") or "")):
                continue                       # "forget about the deadline": not a retraction
            topic = _clean_topic(m.group("topic"))
            if not topic:
                continue
            if rx is _R_ABOUT:
                cut = _TOPIC_CUT.search(m.group("topic"))
                end = m.start("topic") + (cut.start() if cut else len(m.group("topic").rstrip()))
            else:
                end = m.end()
            return Cue("retro", "intent_retract", topic=topic, source="structured", span=(m.start(), end))
    cm = _CORR_ONLY.search(t)
    if cm:
        tm = re.search(r"(?:misspoke|wrong|correct(?:ion)?)\s+(?:about|on|regarding|with)\s+([^,.;!?]+)", t, re.I)
        return Cue("retro", "intent_correction", topic=_clean_topic(tm.group(1)) if tm else "",
                   weak=True, accept_alone=True, source="structured", span=(cm.start(), cm.end()))
    return None


def _tidy(s: str) -> str:
    s = re.sub(r"\s+([,.;!?])", r"\1", s)
    s = re.sub(r"([,;])(?:\s*[,;])+", r"\1", s)
    s = re.sub(r"([.!?])\s*[,;]\s*", r"\1 ", s)
    s = re.sub(r"(^|[.!?]\s+)[,;\s]+", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ,;")


def _annotate_correction(cue: Cue, t: str) -> Cue:
    """Retraction policy hook: when the retract line also carries a correction ("scratch the bit
    about QA, I misspoke, they sign off Monday"), compute the utterance minus the retract clause.
    The pipeline keeps that remainder as a normal public line (the correction is information)."""
    if cue.kind != "retro" or not _CORR.search(t):
        return cue
    cue.corrected = True
    rest = t
    if cue.span:
        a, b = cue.span
        rest = rest[:a] + " " + rest[b:]
    rest = _CORR.sub(" ", rest)
    cue.keep_text = _tidy(rest)
    return cue


_GATE = re.compile(
    r"\b(?:notes?|minutes|records?|recording|transcripts?|confidential|between\s+us|between\s+you\s+and\s+me|"
    r"don'?t\s+share|do\s+not\s+share|not\s+share|written|write[\s\-]?up|write\s+(?:\w+\s+){0,2}down|"
    r"misspoke|mis-spoke|scratch|retract|disregard|take\s+back|take\s+out|never\s*mind|unofficial|"
    r"off\s+the\s+books|hush|keep\s+(?:this|that|it)\s+(?:quiet|private|secret)|our\s+secret|"
    r"(?:strike|forget|ignore)\s+(?:that|what|the))\b", re.I)


_GATE_SCOPE = re.compile(r"\b(?:again|resume|back|continue|go\s+ahead|private\s+part|sensitive|over|done|finished|"
                         r"carry\s+on|ok(?:ay)?\s+(?:so|now)|alright|all\s+right)\b", re.I)


def gate_in_scope(text: str) -> bool:
    """Extra gate while note-taking is paused: words that often signal the pause is over."""
    return bool(_GATE_SCOPE.search(text))


def gate_signal(text: str) -> bool:
    """Cheap lexical signal that an utterance might be about the record itself."""
    return bool(_GATE.search(text))


def detect_structured(t: str) -> Cue:
    """Composable-feature detector on normalised text. Priority: retract, start, end."""
    for fn in (_structured_retract, _structured_start, _structured_end):
        c = fn(t)
        if c is not None:
            return _annotate_correction(c, t)
    return Cue()


def detect(text: str) -> Cue:
    """Cue detection on one utterance: strict regexes, ASR-noise repair, then the structured
    feature detector (also on word-canonicalised text). Cheap, no LLM."""
    t = _norm(text)
    cue = _detect_strict(t)
    if cue.kind == "retro":
        return _annotate_correction(cue, t)
    if cue.kind is not None or cue.false_alarm:
        return cue
    fixed, changed = repair_asr(t)
    if changed:
        c2 = _detect_strict(fixed)
        if c2.kind is not None:
            c2.fuzzy = True
            return _annotate_correction(c2, fixed) if c2.kind == "retro" else c2
    canon, ch2 = canon_words(fixed)
    c3 = detect_structured(canon if ch2 else fixed)
    if c3.kind is not None and (changed or ch2):
        c3.fuzzy = True
    if c3.kind is not None:
        return c3
    cue.gate = gate_signal(t)
    return cue


# ------------------------------------------------------------------ LLM cue-intent fallback
CUE_PROMPT = """Does this meeting utterance ask to stop, resume, or retract note-taking (the written record)?
Utterance: "{text}"
Note-taking is currently: {state}.
- start: asks that what is said now / next / in this same sentence be kept out of the notes
- end: says note-taking can resume
- retract: withdraws or corrects an earlier statement (give the topic)
- none: anything else
Answer JSON only: {{"intent":"start|end|retract|none","topic":"<topic or empty>"}}"""


def call_with_timeout(fn, timeout: float):
    """Run fn() in a daemon thread. Returns (ok, value); a hang or exception gives (False, None)."""
    box: dict = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:      # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive() or "e" in box:
        return False, None
    return True, box.get("v")


def parse_cue_intent(reply) -> Optional[dict]:
    obj = extract_json(reply if isinstance(reply, str) else "")
    if not isinstance(obj, dict):
        return None
    intent = str(obj.get("intent", "")).strip().lower()
    if intent not in ("start", "end", "retract", "none"):
        return None
    return {"intent": intent, "topic": str(obj.get("topic") or "").strip()}


def merge_llm_intent(cue: Cue, res: dict, text: str) -> Cue:
    """Combine the structured/regex cue (possibly empty/weak) with the LLM's verdict."""
    intent = res["intent"]
    if intent == "none":
        return Cue(gate=cue.gate) if cue.weak else cue
    if intent == "start":
        return Cue("start", "llm_start", source="llm")
    if intent == "end":
        return Cue("end", "llm_end", source="llm", remainder=cue.remainder if cue.kind == "end" else "")
    topic = res["topic"] or (cue.topic if cue.kind == "retro" else "")
    c = Cue("retro", "llm_retract", topic=_clean_topic(topic) if topic else "", source="llm",
            span=cue.span if cue.kind == "retro" else ())
    return _annotate_correction(c, _norm(text))


_CATEGORY_WORDS = {
    "health": ("health", "medical", "medication", "illness", "diagnosis", "condition", "doctor", "therapy"),
    "salary": ("salary", "salaries", "pay", "compensation", "raise", "bonus", "money", "offer"),
    "hr": ("performance", "firing", "disciplinary", "complaint", "hr"),
    "legal": ("lawsuit", "legal", "lawyer", "settlement", "visa", "immigration"),
    "layoffs": ("layoffs", "layoff", "reorg", "severance", "redundancies"),
}


def _topic_category(topic: str) -> str:
    words = set(re.findall(r"[a-z]+", topic.lower()))
    for cat, ws in _CATEGORY_WORDS.items():
        if words & set(ws):
            return cat
    return ""


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
        # the topic may name a category ("my health", "the salary stuff") rather than repeat words
        cat = _topic_category(topic)
        if cat:
            from .llm import keyword_sensitivity
            ids = [i for i, _, t in candidates if keyword_sensitivity(t) == (True, cat)]
            if ids:
                return ids, "category"
        return [], "overlap"
    top = max(scores.values())
    return [i for i, _, _ in candidates if scores.get(i, 0) >= 0.5 * top], "overlap"
