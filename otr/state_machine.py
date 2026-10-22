"""ON / OFF / PENDING_CONFIRM state machine plus implicit-end (topic drift) detection.

Scope-end policy (conservative: an OFF scope is private until proven over):
  1. explicit end cue ("back on the record")        -> handled by the pipeline, always wins
  2. LLM says the topic changed                     -> end (when an LLM is available)
  3. no-LLM heuristic, either
       a. pivot phrase ("anyway", "moving on", "on the topic of", ...) AND zero content-word
          overlap with the whole OFF-scope text, or
       b. DRIFT_STREAK (3) consecutive substantive utterances, each with zero overlap with the
          whole OFF-scope text
  4. timeout: SCOPE_TIMEOUT seconds of stream time since the last utterance that belonged to the scope

Utterances that look off-topic but have not yet reached an end condition are "tentative": the
pipeline keeps them held (not committed) and later either suppresses them (scope continued, or the
end was signalled by a pivot/timeout, i.e. they were part of the private run) or releases them
(3b: sustained drift, they were public).
"""
from __future__ import annotations

import re
from collections import Counter

from .cue_detector import content_stems
from .llm import extract_json

ON, OFF, PENDING = "ON", "OFF", "PENDING_CONFIRM"

DRIFT_STREAK = 3
SCOPE_TIMEOUT = 90.0

CONTINUE, TENTATIVE, END = "continue", "tentative", "end"

_SHIFT = re.compile(
    r"^\W*(?:anyway|anyways|moving on|let's move on|let's get back|back to (?:the )?(?:agenda|topic|meeting|task)|"
    r"next (?:topic|item|up|agenda)|on another note|switching gears|changing (?:the )?subject|"
    r"on (?:the )?(?:topic|subject) of|now (?:let's|for|on to)|let's (?:talk|turn|look|discuss|go) (?:about|to|at|over)|"
    r"ok(?:ay)?,?\s+so|alright,?\s+(?:so|let's)|so,? (?:the )?(?:next|agenda))", re.I)

# words that belong to the cue itself, not to the private topic
_CUE_WORDS = {"off", "record", "second", "minute", "moment", "quick", "please", "hold"}

TOPIC_PROMPT = """A private (off-the-record) part of a meeting was about:
"{scope}"
The next utterance is:
"{text}"
Has the conversation moved on to a different topic, so the private part is over?
Reply with JSON only: {{"topic_changed": true|false}}"""


class StateMachine:
    def __init__(self, drift_streak: int = DRIFT_STREAK, scope_timeout: float = SCOPE_TIMEOUT):
        self.state = ON
        self.history: list[tuple[str, str]] = []   # (new_state, reason)
        self.drift_streak = drift_streak
        self.scope_timeout = scope_timeout
        self._scope_vocab: Counter = Counter()
        self._scope_text: list[str] = []
        self._streak = 0
        self._last_t = None
        self.last_end_reason = ""

    def set(self, new: str, reason: str = "") -> bool:
        """Transition; returns True if the state actually changed."""
        if new == self.state:
            return False
        self.state = new
        self.history.append((new, reason))
        if new == OFF:
            self._streak = 0
        elif new == ON:
            self._scope_vocab.clear()
            self._scope_text.clear()
            self._streak = 0
        return True

    # --- OFF scope tracking -------------------------------------------------
    def note_suppressed(self, text: str, t: float = None):
        """Record an utterance as part of the scope's topic (whole-scope vocabulary)."""
        self._scope_vocab.update(s for s in content_stems(text) if s not in _CUE_WORDS)
        self._scope_text.append(text)
        self._streak = 0
        self._touch(t)

    def _touch(self, t):
        if t is not None:
            self._last_t = t if self._last_t is None else max(self._last_t, t)

    def start_scope(self, text: str, t: float):
        """Called with the cue utterance that opened (or re-opened) the scope."""
        self.note_suppressed(text, t)

    def _overlap(self, stems: list[str]) -> int:
        return sum(1 for s in set(stems) if s in self._scope_vocab)

    def assess(self, text: str, t: float, llm=None) -> tuple[str, str]:
        """Classify an utterance arriving while OFF (no explicit cue in it).

        Returns (verdict, reason): (CONTINUE, ""), (TENTATIVE, ""), or (END, why) with why in
        {"llm", "pivot", "drift", "timeout"}. CONTINUE updates the scope vocabulary itself."""
        stems = content_stems(text)
        uniq = set(stems)
        overlap = self._overlap(stems)

        if llm is not None and self._scope_text:
            try:
                p = TOPIC_PROMPT.format(scope=" ".join(self._scope_text[-4:]).replace('"', "'"),
                                        text=text.replace('"', "'"))
                obj = extract_json(llm.complete(p))
                if isinstance(obj, dict) and "topic_changed" in obj:
                    v = obj["topic_changed"]
                    changed = v if isinstance(v, bool) else str(v).lower() in ("true", "yes")
                    if changed:
                        return END, "llm"
                    self.note_suppressed(text, t)
                    return CONTINUE, ""
            except Exception:
                pass

        if self._last_t is not None and t - self._last_t > self.scope_timeout:
            return END, "timeout"
        if _SHIFT.search(text) and overlap == 0 and uniq:
            return END, "pivot"
        if len(uniq) >= 3:
            if overlap == 0:
                self._streak += 1
                if self._streak >= self.drift_streak:
                    return END, "drift"
                return TENTATIVE, ""
            self.note_suppressed(text, t)       # on-topic: learn it, streak resets
            return CONTINUE, ""
        # too short to judge (e.g. "Agreed."): stays with whatever is going on
        if self._streak > 0:
            return TENTATIVE, ""
        self._touch(t)
        return CONTINUE, ""

    def topic_changed(self, text: str, llm=None, t: float = 0.0) -> bool:
        """Back-compat boolean wrapper around assess()."""
        return self.assess(text, t, llm)[0] == END
