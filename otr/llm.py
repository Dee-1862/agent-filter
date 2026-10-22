"""LLM backends (stdlib only) and the implicit-sensitivity classifier."""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable, Optional, Union


class OllamaLLM:
    """Minimal Ollama client over urllib. Satisfies otr.types.LLM."""

    def __init__(self, model: str = "qwen2.5:3b", host: str = "http://localhost:11434",
                 timeout: float = 60.0, temperature: float = 0.0):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model, "prompt": prompt, "stream": False,
            "options": {"temperature": self.temperature},
        }).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("response", "")


class MockLLM:
    """Deterministic LLM for tests.

    responses: dict {substring_of_prompt: reply}, or a callable(prompt)->str.
    First matching key wins. Every prompt is recorded in `.prompts`.
    """

    def __init__(self, responses: Union[dict, Callable[[str], str], None] = None,
                 default: str = "{}"):
        self.responses = responses or {}
        self.default = default
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if callable(self.responses):
            return self.responses(prompt)
        for key, reply in self.responses.items():
            if key in prompt:
                return reply
        return self.default


def extract_json(text: str):
    """Pull the first JSON object/array out of an LLM reply; None on failure."""
    if not text:
        return None
    for m in re.finditer(r"[\{\[]", text):
        s = text[m.start():]
        try:
            obj, _ = json.JSONDecoder().raw_decode(s)
            return obj
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- sensitivity
SENSITIVITY_PROMPT = """You are a privacy filter for meeting notes. Decide whether the utterance
below reveals information that its speaker would likely NOT want in shared meeting notes,
even though nobody said "off the record". Contextual-integrity categories:
- health: medical conditions, diagnoses, treatment, mental health, pregnancy
- salary: individual pay, raises, bonuses, compensation, offers
- hr: performance problems, disciplinary action, complaints, harassment, firing a person
- legal: lawsuits, investigations, settlements, immigration status
- layoffs: unannounced layoffs, reorgs, closures, acquisitions
- personal: family or relationship secrets
Ordinary business discussion (schedules, public plans, technical work) is NOT sensitive.

Utterance: "{text}"

Reply with JSON only: {{"sensitive": true|false, "category": "<category or none>"}}"""

_POSS = r"\b(?:my|his|her|their|your|(?!(?:let|that|it|what|there|here|he|she|who|how|where|when)'s\b)\w+'s)"
_AMT = r"(?:\$\s?\d[\d,.]*\s?(?:k|m|thousand|million)?\b|\d[\d,.]*\s?(?:k\b|thousand|grand|million))"

_KEYWORDS: dict[str, list[str]] = {
    "health": [r"diagnos", r"cancer", r"chemo", r"surgery", r"medication", r"prescri", r"therapy",
               r"therapist", r"depress", r"anxiety", r"pregnan", r"medical", r"illness",
               r"hospital", r"tumou?r", r"\bhiv\b", r"\bxanax", r"antidepress", r"\baddict", r"\bsobriety", r"\bbiops", r"panic attack", r"parental leave", r"maternity", r"paternity", r"\bdoctor", r"mental health", r"rehab", r"\bdiabet"],
    # Salary keywords need person-directed or confidential framing (a possessive, an amount, a
    # named person, "give him a raise"). A bare "salary calculator we launched" is public.
    "salary": [rf"{_POSS}\s+(?:\w+\s+){{0,2}}(?:salary|salaries|pay|bonus|bonuses|compensation|comp|raise)\b",
               rf"\b(?:salary|salaries|bonus|bonuses|raise|compensation|pay)\b[^.?!]{{0,25}}{_AMT}",
               rf"{_AMT}[^.?!]{{0,20}}\b(?:salary|salaries|bonus|raise|compensation|base pay)\b",
               r"\bpay raise\b", r"\b(?:underpaid|overpaid)\b",
               r"\b(?:give|giving|gave|get|getting|got|deserves?|wants?|asked?|asking|denied|promised?)\s+"
               r"(?:for\s+)?(?:\w+\s+){0,2}(?:a\s+|the\s+)?raise\b",
               r"\bcompensation\s+(?:for|of)\s+(?-i:[A-Z][a-z]+)", r"\bcompensation\s+package\b",
               rf"\b(?:is|are|am|was|were|being|getting|gets)\s+(?:only\s+|being\s+)?paid\s+(?:{_AMT}|less|more|way|much|too)",
               rf"\b(?:makes?|earns?|earning|making)\s+{_AMT}",
               rf"\boffer(?:ed|s)?\b[^.?!]{{0,30}}{_AMT}", r"\boffer(?:ed|s)?\b.*\$",
               r"equity grant", r"\bpay cut"],
    "hr": [r"performance review", r"\bpip\b", r"improvement plan", r"performance plan", r"harass", r"disciplin",
           r"\b(?:to|with|from|told|tell|telling|inform(?:ed)?|involve[ds]?|call(?:ed)?)\s+(?:the\s+)?hr\b",
           r"\bhr\s+(?:complaint|investigation|case|file|issue|doesn't|does not|will|knows?|found|wants?|asked|said|told|sent|needs?|requires?)\b",
           r"human resources", r"wrongful(ly)? terminat", r"\bterminat\w*\s+(him|her|them|his|\w+'s)\b",
           r"get(ting)? fired", r"\bwas fired\b", r"\bbeen fired\b", r"\bfire (him|her|them)\b",
           r"\bgrievance", r"underperform", r"written warning"],
    "legal": [r"lawsuit", r"\bsue\b", r"\bsued\b", r"settlement", r"subpoena", r"attorney",
              r"\blawyer", r"investigation", r"immigration", r"\bvisa status"],
    "personal": [r"\bdivorc", r"\bcustody\b", r"\bevict", r"\bbankrupt", r"\bfuneral"],
    "layoffs": [r"layoff", r"laid off", r"lay off", r"redundanc", r"\breorg", r"downsiz",
                r"headcount reduction", r"severance",
                r"\bcut(ting)?\s+\d+\s+(positions|jobs|roles|people)", r"\b(site|plant|office)\s+(closes|is closing|will close)\b", r"shut(ting)? down the (team|office)"],
}
_KW_RE = {c: [re.compile(p, re.I) for p in ps] for c, ps in _KEYWORDS.items()}


def keyword_sensitivity(text: str) -> tuple[bool, str]:
    """Rule-based fallback used when no LLM is available."""
    for cat, pats in _KW_RE.items():
        if any(p.search(text) for p in pats):
            return True, cat
    return False, "none"


def classify_sensitivity(llm, text: str) -> tuple[bool, str]:
    """(is_sensitive, category). Uses the LLM when given; falls back to keywords
    if llm is None or the call/parse fails."""
    if llm is None:
        return keyword_sensitivity(text)
    try:
        obj = extract_json(llm.complete(SENSITIVITY_PROMPT.format(text=text.replace('"', "'"))))
        if isinstance(obj, dict) and "sensitive" in obj:
            sens = obj["sensitive"]
            if isinstance(sens, str):
                sens = sens.strip().lower() in ("true", "yes")
            cat = str(obj.get("category", "none") or "none").lower()
            return bool(sens), (cat if sens else "none")
    except Exception:
        pass
    return keyword_sensitivity(text)
