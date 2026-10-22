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


def run_A(item: dict, llm: Optional[LLM] = None) -> list[Segment]:
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


def run_B(item: dict, llm: Optional[LLM] = None) -> list[Segment]:
    if llm is None:
        return _b_stub(item)
    segs = to_segments(item)
    transcript = "\n".join(f"[{s.id}] {s.speaker}: {s.text}" for s in segs)
    raw = llm.complete(B_PROMPT.format(transcript=transcript))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        keep = set(json.loads(m.group(0))["keep"])  # type: ignore[union-attr]
    except Exception:
        return segs  # unparseable output: fail open (counts as leaks, which is honest)
    return [s for s in segs if s.id in keep]


# --------------------------------------------------------------------------- C


def run_C(item: dict, llm: Optional[LLM] = None, hold_seconds: float = 30.0) -> list[Segment]:
    from otr.pipeline import Pipeline  # lazy: may not exist yet

    pipe = Pipeline(llm=llm, hold_seconds=hold_seconds)

    def answer(events) -> None:
        for ev in events or []:
            if ev.kind == "pending_confirm" and ev.segment_id:
                answer(pipe.confirm(ev.segment_id, keep_out=True))  # 'user says yes' policy

    for seg in to_segments(item):
        answer(pipe.push(seg, now=seg.t_start))
        answer(pipe.tick(seg.t_start))
    answer(pipe.flush())
    return pipe.notes()


SYSTEMS: dict[str, Callable] = {"A": run_A, "B": run_B, "C": run_C}


def label(name: str, llm) -> str:
    return "B-stub" if (name == "B" and llm is None) else name


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
