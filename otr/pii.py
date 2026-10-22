"""Obvious-PII redaction.

Presidio (explicit spaCy config, en_core_web_lg then en_core_web_sm) is the primary
detector when usable; high-precision regexes always run too and are the full fallback
when Presidio or its model is missing or OTR_NO_PRESIDIO is set.

ASR output is normalised first ("four one five ..." -> "415...", "bob at acme dot com"
-> "bob@acme.com") with an offset map, so spans always refer to the original text.

API:
    redact_pii(text, use_presidio=True) -> (masked, labels)        # per segment
    find_pii(text, use_presidio=True)   -> [(label, start, end)]
    find_pii_window(texts)              -> one span list per segment (window-aware)
    redact_pii_window(texts)            -> [(masked, labels)] per segment
"""
from __future__ import annotations

import os
import re
import threading

# ---------------------------------------------------------------- regex fallback
_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,2}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\w)")),
]
_PRESIDIO_MAP = {"EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "US_SSN": "SSN",
                 "CREDIT_CARD": "CREDIT_CARD", "IBAN_CODE": "IBAN", "IP_ADDRESS": "IP",
                 "URL": "URL", "PERSON": "PERSON"}
_SCORE_MIN = 0.4

# PERSON is only masked when a sensitive context word is nearby (names are normal in meetings).
_SENSITIVE_CTX = re.compile(
    r"\b(diagnos\w*|patient|medical|medication|prescri\w+|therapy|therapist|cancer|"
    r"lawsuit|sued|fired|terminated|laid off|layoffs?|salary|pay cut|ssn|social security|"
    r"passport|password|date of birth|dob|home address|immigration|visa status|arrest\w*)\b", re.I)
_CTX_WINDOW = 80

# ---------------------------------------------------------------- spoken-number normaliser
_DIGITS = {"zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3", "four": "4",
           "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_DW = "|".join(sorted(_DIGITS, key=len, reverse=True))
_RUN = re.compile(rf"\b(?:{_DW})\b(?:[\s,\-]+\b(?:{_DW})\b)+", re.I)
_SPOKEN_EMAIL = re.compile(
    r"\b([A-Za-z0-9_.\-]+)\s+at\s+([A-Za-z0-9\-]+(?:\s+dot\s+[A-Za-z0-9\-]+)*)\s+dot\s+"
    r"(com|org|net|edu|gov|io|co|ai|us|uk|dev)\b", re.I)
_MIN_SPOKEN_DIGITS = 7


def _normalize(text: str) -> tuple[str, list[int], list[int]]:
    """Return (normalized, orig_start_per_char, orig_end_per_char)."""
    edits: list[tuple[int, int, str]] = []
    for m in _SPOKEN_EMAIL.finditer(text):
        host = re.sub(r"\s+dot\s+", ".", m.group(2), flags=re.I)
        edits.append((m.start(), m.end(), f"{m.group(1)}@{host}.{m.group(3)}"))
    for m in _RUN.finditer(text):
        words = re.findall(rf"\b(?:{_DW})\b", m.group(0), re.I)
        if len(words) >= _MIN_SPOKEN_DIGITS and any(w.lower() != "oh" for w in words):
            if not any(s < m.end() and m.start() < e for s, e, _ in edits):
                edits.append((m.start(), m.end(), "".join(_DIGITS[w.lower()] for w in words)))
    if not edits:
        n = len(text)
        return text, list(range(n)), list(range(1, n + 1))
    edits.sort()
    out: list[str] = []
    st: list[int] = []
    en: list[int] = []
    pos = 0
    for s, e, rep in edits:
        for i in range(pos, s):
            out.append(text[i]); st.append(i); en.append(i + 1)
        for ch in rep:
            out.append(ch); st.append(s); en.append(e)
        pos = e
    for i in range(pos, len(text)):
        out.append(text[i]); st.append(i); en.append(i + 1)
    return "".join(out), st, en


# ---------------------------------------------------------------- Presidio (lazy, thread-safe)
_analyzer = None
_analyzer_tried = False
_init_lock = threading.Lock()
_run_lock = threading.Lock()
_model_name = ""


def _build_analyzer():
    global _model_name
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    import spacy
    installed = set(spacy.util.get_installed_models())
    for name in ("en_core_web_lg", "en_core_web_sm"):
        if name in installed:
            break
    else:
        return None
    conf = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": name}]}
    nlp = NlpEngineProvider(nlp_configuration=conf).create_engine()
    _model_name = name
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])


def _get_presidio():
    global _analyzer, _analyzer_tried
    if _analyzer_tried:
        return _analyzer
    with _init_lock:
        if _analyzer_tried:
            return _analyzer
        if not os.environ.get("OTR_NO_PRESIDIO"):
            try:
                _analyzer = _build_analyzer()
            except Exception:
                _analyzer = None
        _analyzer_tried = True
    return _analyzer


def presidio_available() -> bool:
    return _get_presidio() is not None


def presidio_model() -> str:
    """Name of the spaCy model in use ('' when Presidio is off)."""
    _get_presidio()
    return _model_name if _analyzer is not None else ""


# ---------------------------------------------------------------- detection
def _luhn_ok(s: str) -> bool:
    d = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(d) <= 16:
        return False
    tot = 0
    for i, x in enumerate(reversed(d)):
        if i % 2:
            x = x * 2 - 9 if x > 4 else x * 2
        tot += x
    return tot % 10 == 0


def _detect(text: str, use_presidio: bool) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for label, rx in _PATTERNS:
        for m in rx.finditer(text):
            if label == "CREDIT_CARD" and not _luhn_ok(m.group(0)):
                continue
            spans.append((label, m.start(), m.end()))
    eng = _get_presidio() if use_presidio else None
    if eng is not None:
        try:
            with _run_lock:
                res = eng.analyze(text=text, language="en", entities=list(_PRESIDIO_MAP),
                                  score_threshold=_SCORE_MIN)
            for r in res:
                if r.entity_type == "PERSON":
                    lo, hi = max(0, r.start - _CTX_WINDOW), r.end + _CTX_WINDOW
                    if not _SENSITIVE_CTX.search(text[lo:hi]):
                        continue
                spans.append((_PRESIDIO_MAP[r.entity_type], r.start, r.end))
        except Exception:
            pass
    return spans


def _merge(spans: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    spans = sorted(spans, key=lambda s: (s[1], -(s[2] - s[1])))
    merged: list[tuple[str, int, int]] = []
    for lab, s, e in spans:
        if merged and s < merged[-1][2]:
            continue
        merged.append((lab, s, e))
    return merged


def find_pii(text: str, use_presidio: bool = True) -> list[tuple[str, int, int]]:
    """Return merged (label, start, end) spans in `text` coordinates."""
    norm, st, en = _normalize(text)
    spans = []
    for lab, s, e in _detect(norm, use_presidio):
        if e <= s or s >= len(st):
            continue
        spans.append((lab, st[s], en[min(e, len(en)) - 1]))
    return _merge(spans)


def _mask(text: str, spans) -> tuple[str, list[str]]:
    if not spans:
        return text, []
    out, pos = [], 0
    for lab, s, e in spans:
        out.append(text[pos:s])
        out.append(f"[{lab}]")
        pos = e
    out.append(text[pos:])
    return "".join(out), [s[0] for s in spans]


def redact_pii(text: str, use_presidio: bool = True) -> tuple[str, list[str]]:
    """Return (masked_text, labels). Spans become [LABEL]."""
    return _mask(text, find_pii(text, use_presidio))


def find_pii_window(texts: list[str], use_presidio: bool = True) -> list[list[tuple[str, int, int]]]:
    """Analyze the concatenation of `texts` (joined by one space) so identifiers split
    across segments are caught. Returns one span list per input text, in that text's own
    coordinates; a span crossing a boundary appears (clipped) in every segment it touches."""
    if not texts:
        return []
    joined = " ".join(texts)
    starts, p = [], 0
    for t in texts:
        starts.append(p)
        p += len(t) + 1
    spans = find_pii(joined, use_presidio)
    per: list[list[tuple[str, int, int]]] = [[] for _ in texts]
    for lab, s, e in spans:
        for i, t in enumerate(texts):
            a, b = starts[i], starts[i] + len(t)
            lo, hi = max(s, a), min(e, b)
            if lo < hi:
                per[i].append((lab, lo - a, hi - a))
    return per


def redact_pii_window(texts: list[str], use_presidio: bool = True) -> list[tuple[str, list[str]]]:
    """Window-aware redact_pii: [(masked_text, labels)] per input text."""
    return [_mask(t, sp) for t, sp in zip(texts, find_pii_window(texts, use_presidio))]
