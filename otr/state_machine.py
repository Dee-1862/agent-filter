"""ON / OFF / PENDING_CONFIRM state machine plus implicit-end (topic change) detection."""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from .cue_detector import content_stems
from .llm import extract_json

ON, OFF, PENDING = "ON", "OFF", "PENDING_CONFIRM"

_SHIFT = re.compile(
    r"^\W*(?:anyway|anyways|moving on|let's move on|let's get back|back to (?:the )?(?:agenda|topic|meeting|task)|"
    r"next (?:topic|item|up|agenda)|on another note|switching gears|changing (?:the )?subject|"
    r"ok(?:ay)?,?\s+so|alright,?\s+(?:so|let's)|so,? (?:the )?(?:next|agenda))", re.I)

TOPIC_PROMPT = """A private (off-the-record) part of a meeting was about:
"{scope}"
The next utterance is:
"{text}"
Has the conversation moved on to a different topic, so the private part is over?
Reply with JSON only: {{"topic_changed": true|false}}"""


class StateMachine:
    def __init__(self):
        self.state = ON
        self.history: list[tuple[str, str]] = []   # (new_state, reason)
        self._scope_vocab: Counter = Counter()
        self._scope_text: list[str] = []
        self._streak = 0

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
    def note_suppressed(self, text: str):
        """Record a suppressed utterance as part of the scope's topic. Utterances that
        already look off-topic (streak > 0) are not learned, so drift is detectable."""
        if self._streak == 0:
            self._scope_vocab.update(content_stems(text))
            self._scope_text.append(text)

    def topic_changed(self, text: str, llm=None) -> bool:
        """Implicit end of an OFF scope: has the conversation left the private topic?"""
        stems = content_stems(text)
        overlap = sum(1 for s in set(stems) if s in self._scope_vocab)
        if llm is not None and self._scope_text:
            try:
                p = TOPIC_PROMPT.format(scope=" ".join(self._scope_text[-3:]).replace('"', "'"),
                                        text=text.replace('"', "'"))
                obj = extract_json(llm.complete(p))
                if isinstance(obj, dict) and "topic_changed" in obj:
                    v = obj["topic_changed"]
                    return v if isinstance(v, bool) else str(v).lower() in ("true", "yes")
            except Exception:
                pass
        # heuristic: explicit pivot phrase with no topical overlap, or two unrelated utterances in a row
        if _SHIFT.search(text) and overlap == 0:
            return True
        if len(set(stems)) >= 3:
            if overlap == 0:
                self._streak += 1
                if self._streak >= 2:
                    return True
            else:
                self._streak = 0
        return False
