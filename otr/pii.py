"""Obvious-PII redaction. Presidio if importable and usable, else regex fallback."""
from __future__ import annotations

import os
import re

_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,2}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\w)")),
]
_PRESIDIO_MAP = {"EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "US_SSN": "SSN",
                 "CREDIT_CARD": "CREDIT_CARD"}

_analyzer = None
_analyzer_tried = False


def _get_presidio():
    global _analyzer, _analyzer_tried
    if _analyzer_tried:
        return _analyzer
    _analyzer_tried = True
    if os.environ.get("OTR_NO_PRESIDIO"):
        return None
    try:
        from presidio_analyzer import AnalyzerEngine  # needs a spacy model too
        _analyzer = AnalyzerEngine()
    except Exception:
        _analyzer = None
    return _analyzer


def presidio_available() -> bool:
    return _get_presidio() is not None


def find_pii(text: str, use_presidio: bool = True) -> list[tuple[str, int, int]]:
    """Return merged (label, start, end) spans."""
    spans: list[tuple[str, int, int]] = []
    for label, rx in _PATTERNS:
        spans += [(label, m.start(), m.end()) for m in rx.finditer(text)]
    eng = _get_presidio() if use_presidio else None
    if eng is not None:
        try:
            for r in eng.analyze(text=text, language="en", entities=list(_PRESIDIO_MAP)):
                spans.append((_PRESIDIO_MAP[r.entity_type], r.start, r.end))
        except Exception:
            pass
    spans.sort(key=lambda s: (s[1], -(s[2] - s[1])))
    merged: list[tuple[str, int, int]] = []
    for lab, s, e in spans:
        if merged and s < merged[-1][2]:
            continue
        merged.append((lab, s, e))
    return merged


def redact_pii(text: str, use_presidio: bool = True) -> tuple[str, list[str]]:
    """Return (masked_text, labels). Spans become [LABEL]."""
    spans = find_pii(text, use_presidio)
    if not spans:
        return text, []
    out, pos = [], 0
    for lab, s, e in spans:
        out.append(text[pos:s])
        out.append(f"[{lab}]")
        pos = e
    out.append(text[pos:])
    return "".join(out), [s[0] for s in spans]
