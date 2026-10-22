"""The ONE taxonomy of "what was kept out", shared by the server and both pages.

Event.reason codes (``cue:*``, ``scope:off``, ``retro:match(...)``, ``kw:<topic>``, ``llm:<topic>``,
``presidio:<labels>``, ``implicit_end:*``, ``hold_elapsed``, ``flush:*``, ``confirm:*`` ...) are mapped to
a small set of user-facing kinds. Only category KEYS and counts ever leave the server in consent mode;
never text, never the reason tail (which can carry a topic word or matched span).

``js_source()`` renders the same table as ``window.OTR_TAXONOMY`` and is served at
``/static/categories.js`` so the pages cannot drift from this file. The matching rules are plain
regular expressions that behave the same in Python ``re`` and JavaScript ``RegExp`` (no lookbehind,
no inline flags); matching is case-insensitive.
"""
from __future__ import annotations

import json
import re

# Ordered: the first category whose pattern matches the reason code wins.
# Each: key, label, short label, plain-language rule, regex over the reason code, rule families that feed it.
CATEGORIES: list[dict] = [
    {"key": "retracted", "families": ['retro', 'cue'], "label": "Retracted by the speaker (strike that)",
     "short": "Retracted",
     "rule": "A later \"strike that\" or \"forget what I said about...\" removed the line, and the retraction request itself is never kept.",
     "pattern": r"^(retro:|cue:(retro|retro_meta|strike\w*|scratch\w*|intent_retract|intent_correction|llm_retract))"},
    {"key": "off_record", "families": ['cue', 'scope', 'implicit_end', 'state', 'flush'], "label": "Off the record (you asked)",
     "short": "Off the record",
     "rule": "A spoken cue such as \"off the record\" or \"between us\" switched recording off. Everything after it stays out until someone says the stretch is over (or the conversation clearly moves on).",
     "pattern": r"^(cue:|scope:|implicit_end:|state:|flush:unresolved_scope)"},
    {"key": "contact", "families": ['presidio', 'regex'], "label": "Contact details masked",
     "short": "Contact details",
     "rule": "A detector for emails, phone numbers, ID and card numbers masked them before the line could enter the notes.",
     "pattern": r"^(presidio:|regex:)"},
    {"key": "personal_health", "families": ['kw', 'llm'], "label": "Personal and health",
     "short": "Personal and health",
     "rule": "A keyword rule or the local language model judged the topic to be personal or medical (health, family, finances of a person).",
     "pattern": r"^(kw|llm):(health|medical|mental\w*|personal|family|private|sensitive_personal|divorce|custody|illness)\b"},
    {"key": "pay_hr", "families": ['kw', 'llm'], "label": "Pay and HR",
     "short": "Pay and HR",
     "rule": "A keyword rule or the local language model judged the topic to be pay, performance, hiring or firing, or other HR matters.",
     "pattern": r"^(kw|llm):(salary|salaries|pay|compensation|bonus|raise|hr|layoffs?|firing|performance|benefits|hiring|equity)\b"},
    {"key": "legal_business", "families": ['kw', 'llm'], "label": "Legal and confidential business",
     "short": "Legal and business",
     "rule": "A keyword rule or the local language model judged the topic to be legal, financial or otherwise confidential company business.",
     "pattern": r"^(kw|llm):(legal|lawsuit|confidential|business|contract|financial|finance|strategy|trade_secret|nda|acquisition|merger|security)\b"},
    {"key": "other", "families": ['confirm', 'flush', 'kw', 'llm', 'other'], "label": "Other sensitive",
     "short": "Other",
     "rule": "Anything else that was held back: a topic the filter flagged under another name, an unanswered confirmation, or a code the page does not recognise.",
     "pattern": r".*"},
]

KEYS = [c["key"] for c in CATEGORIES]
LABELS = {c["key"]: c["label"] for c in CATEGORIES}
_COMPILED = [(c["key"], re.compile(c["pattern"], re.I)) for c in CATEGORIES]

# Rule FAMILY = the head of a reason code. Generic and safe to show: it names the mechanism, never the content.
FAMILIES: dict[str, dict] = {
    "cue": {"label": "Spoken cue", "engine": "rule",
            "text": "A cue phrase in what was said changed the recording state."},
    "scope": {"label": "Private stretch", "engine": "rule",
              "text": "An earlier cue had switched recording off and nothing had ended it yet."},
    "implicit_end": {"label": "Stretch ended on its own", "engine": "rule",
                     "text": "No explicit cue; the conversation moved on, so the private stretch closed."},
    "retro": {"label": "Retraction", "engine": "rule",
              "text": "A later retraction request matched this line."},
    "kw": {"label": "Keyword rule", "engine": "rule",
           "text": "A keyword rule flagged the topic."},
    "llm": {"label": "Language-model judgement", "engine": "llm",
            "text": "The local language model classified the line as sensitive."},
    "presidio": {"label": "Personal-details detector", "engine": "rule",
                 "text": "A detector found contact or ID details and masked them."},
    "regex": {"label": "Pattern detector", "engine": "rule",
              "text": "A pattern rule found contact or ID details."},
    "confirm": {"label": "Confirmation answer", "engine": "rule",
                "text": "Decided by an answer to the keep-it-out question."},
    "flush": {"label": "End of meeting", "engine": "rule",
              "text": "The meeting ended while a decision was still open, so the line stayed out."},
    "state": {"label": "Recording state", "engine": "rule",
              "text": "The recording state was off when the line arrived."},
    "hold_elapsed": {"label": "Hold window", "engine": "rule",
                     "text": "Nothing flagged the line while it waited, so it was released."},
    "other": {"label": "Other rule", "engine": "rule", "text": "A rule this page does not recognise."},
}


def categorize(reason: str | None, kind: str | None = None) -> str:
    """Map a reason code (and optionally the event kind) to a category key. Unknown -> 'other'."""
    r = (reason or "").strip()
    if kind == "retro_removed" and not r:
        return "retracted"
    for key, rx in _COMPILED:
        if rx.search(r):
            return key
    return "other"


def family(reason: str | None) -> str:
    """Rule family = the reason head (before ':' or '('). Text-free and generic."""
    r = (reason or "").strip().lower()
    head = re.split(r"[:(]", r, 1)[0]
    return head if head in FAMILIES else "other"


def taxonomy() -> dict:
    """The JSON-able table the pages use. Contains no meeting data."""
    return {"categories": [{k: c[k] for k in ("key", "label", "short", "rule", "pattern", "families")} for c in CATEGORIES],
            "families": FAMILIES}


def js_source() -> str:
    return "window.OTR_TAXONOMY = " + json.dumps(taxonomy(), indent=1) + ";\n"
