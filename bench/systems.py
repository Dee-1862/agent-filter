"""Systems under evaluation. Each exposes run(item, llm=None) -> list[Segment] (the notes).

A      keyword/cue rules + regex PII (no LLM).
B      one LLM pass over the whole transcript; with llm=None a crude heuristic stand-in
       labelled 'B-stub' (NOT a real measurement of an LLM baseline).
C      our pipeline (otr.pipeline.Pipeline), imported lazily.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from otr.types import LLM, Segment

# --------------------------------------------------------------------------- helpers


def to_segments(item: dict) -> list[Segment]:
    return [Segment(**s) for s in item["segments"]]


START_CUE = re.compile(
    r"off[\s-]the[\s-]record|don'?t (?:write|put|record|take) (?:this|that|the next)|"
    r"keep this (?:out|between)|between (?:us|you and me)|not for the notes", re.I)
END_CUE = re.compile(
    r"back on the record|end of (?:the )?off the record|resume the recording|"
    r"you can put it back|we can resume|on the record again", re.I)
RETRO_CUE = re.compile(
    r"strike (?:that|all)|take (?:that|it|what|the last)[^.]*out|remove (?:what|the last|my last|that)|"
    r"delete (?:that|what|the last)|scratch (?:that|all)|forget i said|"
    r"(?:don'?t|do not) (?:put|include|record)[^.]*(?:notes|record)|(?:don'?t|do not) (?:include|record) that",
    re.I)
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4}

PII_RE = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                                   # email
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                                     # SSN
    re.compile(r"\b(?:\+?1[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),      # phone
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),                                    # card-ish
]
SENSITIVE_KW = re.compile(
    r"\b(salary|bonus|diagnos\w*|chemo\w*|tumor|cancer|therap\w+|antidepressant\w*|depression|"
    r"medical leave|pregnan\w+|hiv|layoffs?|lay off|laid off|severance|fired|terminat\w+|"
    r"lawsuit|sued|settlement|performance (?:plan|review)|pip|resign\w*|password|"
    r"confidential|divorce\w*|custody|visa)\b", re.I)


def _own_pii(text: str) -> bool:
    return any(r.search(text) for r in PII_RE)


def has_pii(text: str) -> bool:
    """Use otr.pii if present and compatible, else our own regex. Imported lazily."""
    try:
        import otr.pii as p  # type: ignore
        for name in ("has_pii", "contains_pii", "detect_pii"):
            fn = getattr(p, name, None)
            if callable(fn):
                return bool(fn(text)) or _own_pii(text)
    except Exception:
        pass
    return _own_pii(text)


def _retro_count(text: str) -> int:
    m = re.search(r"last (one|two|three|four)|(two|three|four) (?:things|comments|sentences)", text, re.I)
    if m:
        return NUMWORDS[(m.group(1) or m.group(2)).lower()]
    return 1


# --------------------------------------------------------------------------- A


def run_A(item: dict, llm: Optional[LLM] = None, **_) -> list[Segment]:
    """Cue regexes with explicit-only scope (ends only on an explicit end cue) + PII + keywords."""
    kept: list[Segment] = []
    in_scope = False
    prev_was_retro = False
    for seg in to_segments(item):
        t = seg.text
        if END_CUE.search(t):
            in_scope = False
            prev_was_retro = False
            continue
        if START_CUE.search(t):
            in_scope = True
            prev_was_retro = False
            continue
        if RETRO_CUE.search(t):
            if not prev_was_retro:
                for _ in range(_retro_count(t)):
                    if kept:
                        kept.pop()
            prev_was_retro = True
            continue
        prev_was_retro = False
        if in_scope or has_pii(t) or SENSITIVE_KW.search(t):
            continue
        kept.append(seg)
    return kept


# --------------------------------------------------------------------------- B

B_PROMPT = """You are cleaning meeting notes. Below is a transcript, one line per segment as [id] speaker: text.
Remove anything that is off the record, private or sensitive (health, salary, HR/performance,
layoffs, legal, personal secrets, credentials), including lines the speakers asked to be removed.
Keep everything else, including control talk that is not itself sensitive.
Reply with ONLY JSON: {{"keep": ["<id>", ...]}} listing the segment ids to KEEP.

Transcript:
{transcript}
"""


def _b_stub(item: dict) -> list[Segment]:
    """B-stub: deliberately simple stand-in for 'one LLM pass'. Drops lines with sensitive
    keywords/PII, and the 3 lines after any off-the-record cue. Not a real LLM measurement."""
    kept, budget = [], 0
    for seg in to_segments(item):
        if START_CUE.search(seg.text):
            budget = 3
            continue
        if END_CUE.search(seg.text) or RETRO_CUE.search(seg.text):
            budget = 0
            continue
        if budget > 0:
            budget -= 1
            continue
        if has_pii(seg.text) or SENSITIVE_KW.search(seg.text):
            continue
        kept.append(seg)
    return kept


# ---- causal driver: a decision for segment i may only use text up to t_end_i + lag (same lag as C's hold)


def _visible(segs: list[Segment], i: int, lag: float) -> list[Segment]:
    cutoff = segs[i].t_end + lag
    return [s for s in segs if s.t_end <= cutoff or s is segs[i]]


def _parse_json(raw: str):
    try:
        from otr.llm import extract_json
        return extract_json(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None


def _fmt(segs: list[Segment]) -> str:
    return "\n".join(f"[{s.id}] {s.speaker}: {s.text}" for s in segs)


def _causal(segs: list[Segment], lag: float, decide: Callable[[list[Segment], Segment], bool]) -> list[Segment]:
    return [s for i, s in enumerate(segs) if decide(_visible(segs, i, lag), s)]


def run_B(item: dict, llm: Optional[LLM] = None, mode: str = "hindsight",
          hold_seconds: float = 30.0, **_) -> list[Segment]:
    """B: one-pass LLM filter. mode='hindsight' sees the whole transcript at once;
    mode='causal' decides each segment seeing only text up to t_end + hold_seconds."""
    segs = to_segments(item)
    if llm is None:
        if mode == "hindsight":
            return _b_stub(item)
        return _causal(segs, hold_seconds,
                       lambda vis, t: t.id in {k.id for k in _b_stub({"segments": [v.to_dict() for v in vis]})})
    if mode == "hindsight":
        raw = llm.complete(B_PROMPT.format(transcript=_fmt(segs)))
        obj = _parse_json(raw)
        try:
            keep = set(obj["keep"])  # type: ignore[index]
        except Exception:
            return segs  # unparseable output: fail open (counts as leaks, which is honest)
        return [s for s in segs if s.id in keep]

    def decide(vis: list[Segment], t: Segment) -> bool:
        obj = _parse_json(llm.complete(B_TARGET_PROMPT.format(transcript=_fmt(vis), target=t.id)))
        try:
            return str(obj["keep"]).lower() not in ("false", "0", "no")  # type: ignore[index]
        except Exception:
            return True
    return _causal(segs, hold_seconds, decide)


# --------------------------------------------------------------------------- B+ (contextual-integrity extract-then-judge)

BPLUS_RULES = """For EACH segment, first extract (1) information type, (2) subject (whose information),
(3) recipient: ALL readers of the shared meeting notes (attendees, absent colleagues, anyone later
given the notes), and (4) transmission principle: under what norm was it said (for example: said
inside a span the speaker asked to keep out of the notes, retracted by the speaker, said in
confidence, ordinary business). Then judge whether putting this segment in the notes is an
appropriate flow for that recipient. DROP segments that are health, pay, HR/discipline, legal,
layoff/reorg, credentials or personal identifiers about a person, said in confidence or inside a
requested private span, or later retracted. KEEP ordinary business, public information (for
example a public tool, policy or deadline that merely mentions a sensitive topic), a titled work or
a database 'record', quoted or negated cue words, and self-corrections that only fix a fact."""

BPLUS_PROMPT = """You are preparing shared meeting notes with a contextual-integrity check.
{rules}

Transcript, one line per segment as [id] speaker: text:
{transcript}

Reply with ONLY JSON: {{"segments": [{{"id": "<id>", "information_type": "...", "subject": "...",
"recipient": "all readers of the notes", "transmission_principle": "...", "decision": "keep" or "drop"}}, ...]}}
"""

BPLUS_TARGET_PROMPT = """You are preparing shared meeting notes with a contextual-integrity check.
{rules}

You can only see the transcript so far (no future text). Judge ONLY segment {target}.
Transcript, one line per segment as [id] speaker: text:
{transcript}

Reply with ONLY JSON: {{"information_type": "...", "subject": "...", "recipient": "all readers of the notes",
"transmission_principle": "...", "decision": "keep" or "drop"}}
"""

B_TARGET_PROMPT = """You are cleaning meeting notes. You can only see the transcript so far (no future text).
Remove anything that is off the record, private or sensitive (health, salary, HR/performance,
layoffs, legal, personal secrets, credentials), including lines the speakers asked to be removed.
Decide ONLY for segment {target}. Reply with ONLY JSON: {{"keep": true}} or {{"keep": false}}.

Transcript (one line per segment as [id] speaker: text):
{transcript}
"""

# Generic category lexicon for the B+ heuristic stub (information types, not dataset-specific).
CI_TYPES = {
    "health": re.compile(r"\b(diagnos\w*|treatment|chemo\w*|surgery|medication|illness|therap\w+|mental health|"
                         r"pregnan\w+|cancer|tumou?r|depress\w+|hospital)\b", re.I),
    "pay": re.compile(r"\b(salary|raise|bonus|compensation|pay cut|paid (?:less|more)|makes? .{0,20}more than)\b", re.I),
    "hr": re.compile(r"\b(performance (?:plan|improvement)|complaint|disciplin\w+|fired|let (?:him|her|them) go|"
                     r"harass\w+|terminat\w+)\b", re.I),
    "legal": re.compile(r"\b(lawsuit|sued|settlement|subpoena|regulator|attorney|legal action|counsel says)\b", re.I),
    "layoff": re.compile(r"\b(layoffs?|lay off|laid off|downsiz\w+|restructur\w+|reorg\w*|cut \w+ percent of staff)\b", re.I),
    "credential": re.compile(r"\b(password|passcode|api key|secret key)\b", re.I),
}
CI_PUBLIC_MARKERS = re.compile(
    r"\b(calculator|portal|deadline|enrol\w+|training|policy|feature|tool|schedule|instances?|jobs?|"
    r"servers?|documentary|podcast|band|film|database|crm)\b", re.I)


def _bplus_stub(segs: list[Segment]) -> list[Segment]:
    """B+-stub: heuristic stand-in for extract-then-judge. Categorises each segment into a CI
    information type, treats the recipient as everyone who reads the notes, drops sensitive
    types unless a public-artifact marker is present, drops a span after a start cue until an end
    cue (max 6 segments), and retracts previous kept segments on a retraction cue
    (only text inside the visible window can be retracted). NOT a measurement of an LLM."""
    kept: list[Segment] = []
    scope = 0
    for seg in segs:
        t = seg.text
        if END_CUE.search(t):
            scope = 0
            continue
        if START_CUE.search(t):
            scope = 6
            continue
        if RETRO_CUE.search(t):
            if not re.search(r"\bi meant\b", t, re.I):       # a repair, not a retraction
                for _ in range(_retro_count(t)):
                    if kept:
                        kept.pop()
            continue
        if scope > 0:
            scope -= 1
            continue
        sensitive = has_pii(t) or any(rx.search(t) for rx in CI_TYPES.values())
        if sensitive and not CI_PUBLIC_MARKERS.search(t):
            continue
        kept.append(seg)
    return kept


def run_Bplus(item: dict, llm: Optional[LLM] = None, mode: str = "hindsight",
              hold_seconds: float = 30.0, **_) -> list[Segment]:
    segs = to_segments(item)
    if llm is None:
        if mode == "hindsight":
            return _bplus_stub(segs)
        return _causal(segs, hold_seconds, lambda vis, t: t.id in {k.id for k in _bplus_stub(vis)})
    if mode == "hindsight":
        obj = _parse_json(llm.complete(BPLUS_PROMPT.format(rules=BPLUS_RULES, transcript=_fmt(segs))))
        try:
            drop = {d["id"] for d in obj["segments"] if str(d.get("decision", "")).lower().startswith("drop")}
        except Exception:
            return segs  # fail open
        return [s for s in segs if s.id not in drop]

    def decide(vis: list[Segment], t: Segment) -> bool:
        obj = _parse_json(llm.complete(BPLUS_TARGET_PROMPT.format(
            rules=BPLUS_RULES, target=t.id, transcript=_fmt(vis))))
        try:
            return not str(obj["decision"]).lower().startswith("drop")  # type: ignore[index]
        except Exception:
            return True
    return _causal(segs, hold_seconds, decide)


# --------------------------------------------------------------------------- C


class Notes(list):
    """Final notes plus the ids that were EVER committed (incl. ones later retro-removed)."""
    ever_committed_ids: set


def run_C(item: dict, llm: Optional[LLM] = None, hold_seconds: float = 30.0, **_) -> list[Segment]:
    """Replay the item as a live stream: each segment is pushed when it ends (now = t_end),
    the clock is ticked at that time, and after the last segment the clock runs on to
    t_end + hold_seconds so held text is released by tick() (not just by flush())."""
    from otr.pipeline import Pipeline

    pipe = Pipeline(llm=llm, hold_seconds=hold_seconds)

    def answer(events) -> None:
        for ev in events or []:
            if ev.kind == "pending_confirm" and ev.segment_id:
                answer(pipe.confirm(ev.segment_id, keep_out=True))  # 'user says yes' policy

    segs = to_segments(item)
    for seg in segs:
        answer(pipe.push(seg, now=seg.t_end))
        answer(pipe.tick(seg.t_end))
    if segs:
        answer(pipe.tick(max(s.t_end for s in segs) + hold_seconds))
    answer(pipe.flush())
    out = Notes(pipe.notes())
    audit = pipe.audit_log()
    out.ever_committed_ids = {e.segment_id for e in audit if e.kind == "committed"}
    out.audit = [(e.segment_id, e.kind, e.reason) for e in audit if e.segment_id]   # copy, for per-stage logging
    return out


def _causal_variant(fn):
    def run(item, llm=None, **kw):
        return fn(item, llm, mode="causal", **kw)
    return run


SYSTEMS: dict[str, Callable] = {
    "A": run_A, "B": run_B, "B+": run_Bplus,
    "B/causal": _causal_variant(run_B), "B+/causal": _causal_variant(run_Bplus), "C": run_C}


def label(name: str, llm) -> str:
    """Display name; B and B+ are tagged '-stub' when llm is None (heuristic stand-in, not an LLM)."""
    base, _, mode = name.partition("/")
    if base in ("B", "B+") and llm is None:
        base += "-stub"
    return base + ("/" + mode if mode else "")


def make_llm(spec: str):
    """'none' -> None; 'ollama:qwen2.5:3b' -> OllamaLLM from otr.llm (None if unavailable)."""
    if not spec or spec == "none":
        return None
    kind, _, model = spec.partition(":")
    if kind != "ollama":
        raise SystemExit(f"unknown --llm {spec!r}")
    try:
        from otr.llm import OllamaLLM
    except Exception as e:
        print(f"[warn] otr.llm.OllamaLLM unavailable ({e}); using llm=None")
        return None
    try:
        return OllamaLLM(model=model)
    except TypeError:
        return OllamaLLM(model)
