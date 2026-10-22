"""LLM backends (stdlib only) and the implicit-sensitivity classifier."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import socket
import threading
import time
import urllib.request
from collections import OrderedDict
from typing import Callable, Optional, Union
from urllib.parse import urlparse


class LLMError(RuntimeError):
    """Raised by OllamaLLM when the server is unreachable, slow or returns garbage.
    Pipeline callers already catch Exception and fall back to keywords/overlap."""


DEFAULT_MODEL = "granite4.2:3b"


def default_model() -> str:
    return os.environ.get("OTR_LLM_MODEL") or DEFAULT_MODEL


def default_host() -> str:
    h = os.environ.get("OTR_LLM_HOST") or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if "://" not in h:
        h = "http://" + h
    return h


_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_THINK_CLOSE_RE = re.compile(r"</think(?:ing)?>", re.I)
_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\n?(.*?)```", re.S)


def clean_reply(text: str) -> str:
    """Strip <think> blocks and markdown code fences from a model reply."""
    if not text:
        return ""
    text = _THINK_RE.sub("", text)
    if _THINK_CLOSE_RE.search(text):            # opening tag missing: keep what follows the last close
        text = _THINK_CLOSE_RE.split(text)[-1]
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1)
    return text.strip()


class OllamaLLM:
    """Ollama client over one persistent HTTP connection. Satisfies otr.types.LLM.

    Latency settings: keep_alive keeps the model resident, small num_predict / num_ctx,
    temperature 0, think=False (no reasoning), format="json" for prompts that ask for JSON,
    and a prompt-hash cache. On failure raises LLMError; afterwards the client fails fast for
    `cooldown` seconds so a dead or slow server cannot stall a live meeting.
    """

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None,
                 timeout: float = 20.0, temperature: float = 0.0, keep_alive: str = "30m",
                 num_predict: int = 96, num_ctx: int = 2048, think: Optional[bool] = False,
                 json_mode: Optional[bool] = None, cache_size: int = 256, cooldown: float = 15.0):
        self.model = model or default_model()
        self.host = (host or default_host()).rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.keep_alive = keep_alive
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.think = think                 # sent as "think"; None = do not send
        self.json_mode = json_mode         # None = auto (prompt mentions JSON)
        self.cache_size = cache_size
        self.cooldown = cooldown
        self.last_latency = 0.0
        self.calls = 0
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()
        self._conn: Optional[http.client.HTTPConnection] = None
        self._down_until = 0.0
        u = urlparse(self.host)
        self._https = u.scheme == "https"
        self._hostname = u.hostname or "localhost"
        self._port = u.port or (443 if self._https else 80)

    # -- transport
    def _post(self, path: str, payload: dict) -> tuple[int, bytes]:
        body = json.dumps(payload).encode("utf-8")
        hdr = {"Content-Type": "application/json"}
        for attempt in (0, 1):                    # one retry covers a stale keep-alive socket
            if self._conn is None:
                cls = http.client.HTTPSConnection if self._https else http.client.HTTPConnection
                self._conn = cls(self._hostname, self._port, timeout=self.timeout)
            try:
                self._conn.request("POST", path, body, hdr)
                r = self._conn.getresponse()
                return r.status, r.read()
            except (http.client.HTTPException, OSError) as e:
                self.close()
                if attempt or isinstance(e, socket.timeout):
                    raise
        raise LLMError("unreachable")

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # -- API
    def complete(self, prompt: str, *, json_mode: Optional[bool] = None,
                 num_predict: Optional[int] = None, use_cache: bool = True) -> str:
        key = hashlib.sha1(f"{self.model}|{json_mode}|{num_predict}|{prompt}".encode("utf-8")).hexdigest()
        with self._lock:
            if use_cache and key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if time.monotonic() < self._down_until:
                raise LLMError("ollama recently failed; skipping (cooldown)")
            t0 = time.perf_counter()
            try:
                out = self._generate(prompt, json_mode, num_predict)
            except Exception as e:
                self._down_until = time.monotonic() + self.cooldown
                if isinstance(e, LLMError):
                    raise
                raise LLMError(f"ollama call failed: {e!r}") from e
            self.last_latency = time.perf_counter() - t0
            self.calls += 1
            if use_cache and self.cache_size:
                self._cache[key] = out
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return out

    def _generate(self, prompt, json_mode, num_predict) -> str:
        want_json = json_mode if json_mode is not None else self.json_mode
        if want_json is None:
            want_json = "json" in prompt.lower()
        payload = {
            "model": self.model, "prompt": prompt, "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature,
                        "num_predict": num_predict or self.num_predict, "num_ctx": self.num_ctx},
        }
        if want_json:
            payload["format"] = "json"
        if self.think is not None:
            payload["think"] = self.think
        status, raw = self._post("/api/generate", payload)
        if status == 400 and "think" in payload and b"think" in raw.lower():
            self.think = None                      # this model/server does not support the flag
            payload.pop("think")
            status, raw = self._post("/api/generate", payload)
        if status != 200:
            raise LLMError(f"HTTP {status}: {raw[:200]!r}")
        d = json.loads(raw.decode("utf-8"))
        text = d.get("response") or ""
        if not text.strip() and d.get("thinking"):
            text = d["thinking"]                    # reasoning-only reply; extract_json may still find JSON
        return clean_reply(text)

    def ps(self) -> list:
        """Models currently loaded (with size_vram) from /api/ps."""
        with urllib.request.urlopen(self.host + "/api/ps", timeout=3) as r:
            return json.loads(r.read().decode("utf-8")).get("models", [])

    def installed(self) -> list:
        with urllib.request.urlopen(self.host + "/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]

    def warmup(self) -> float:
        """Load the model into memory; seconds taken (inf on failure)."""
        t0 = time.perf_counter()
        try:
            self.complete('Reply with JSON: {"ok":true}', use_cache=False)
        except Exception:
            return float("inf")
        return time.perf_counter() - t0


def parse_llm_spec(spec: str):
    """'none' -> None; 'ollama' or 'ollama:MODEL' -> OllamaLLM (model defaults from env)."""
    if not spec or spec == "none":
        return None
    kind, _, model = spec.partition(":")
    if kind != "ollama":
        return None
    return OllamaLLM(model=model or None)


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
    text = clean_reply(text) or text
    for m in re.finditer(r"[\{\[]", text):
        s = text[m.start():]
        try:
            obj, _ = json.JSONDecoder().raw_decode(s)
            return obj
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- sensitivity
SENSITIVITY_PROMPT = """Task: flag private facts about a specific person or the company that should not appear in meeting notes shared with EVERYONE who reads them (the whole team and outsiders).
Categories: health, salary, hr, legal, layoffs, personal.
Sensitive = a concrete private fact (a named or implied person's condition, pay, discipline, case, unannounced layoff, family matter).
NOT sensitive = products, features, public policies, deadlines, generic or technical talk, even when they mention health, pay or legal words.

"Sarah told me she is starting chemo next month." -> {{"sensitive": true, "category": "health"}}
"Dan makes 140k and wants a raise." -> {{"sensitive": true, "category": "salary"}}
"We are putting Priya on a performance plan." -> {{"sensitive": true, "category": "hr"}}
"The company is being sued over the patent." -> {{"sensitive": true, "category": "legal"}}
"Leadership will cut 30 jobs in Q3, don't tell anyone." -> {{"sensitive": true, "category": "layoffs"}}
"His wife and he are getting a divorce." -> {{"sensitive": true, "category": "personal"}}
"The payroll software demo is on Tuesday and the vendor wants a legal review." -> {{"sensitive": false, "category": "none"}}
"Our new fitness app tracks sleep and heart rate for customers." -> {{"sensitive": false, "category": "none"}}

Reply with JSON like the examples.
Utterance: "{text}"
JSON:"""

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
