"""Shared contract for the OTR agent. Every module codes against this file.

Data flow:  ingest -> Segment -> Pipeline.push() -> Event -> demo UI / eval
Do not change these definitions without telling the lead.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, Protocol

EventKind = Literal[
    "held",             # segment entered the hold buffer (grey in UI)
    "committed",        # segment released into the notes (green)
    "redacted",         # segment suppressed / removed from notes (red)
    "pending_confirm",  # implicit-sensitive flag, agent asks "Keep that out of the notes?" (amber)
    "state_change",     # ON / OFF / PENDING_CONFIRM transition
    "retro_removed",    # a retroactive request removed already-committed text
]
State = Literal["ON", "OFF", "PENDING_CONFIRM"]
CaseType = Literal[
    "explicit_start_end", "explicit_start_implicit_end", "retroactive",
    "implicit", "false_alarm", "public",
]


@dataclass
class Segment:
    """One confirmed utterance. `speaker` is a LiveKit participant identity
    (free diarization) or a diarization label like SPEAKER_00."""
    id: str
    speaker: str
    text: str
    t_start: float
    t_end: float

    def to_dict(self): return asdict(self)


@dataclass
class Event:
    kind: EventKind
    segment_id: Optional[str]
    text: str = ""
    speaker: str = ""
    t: float = 0.0           # pipeline clock (seconds) when the event fired
    state: str = "ON"        # pipeline state after this event
    reason: str = ""         # e.g. "cue:off_the_record", "presidio:EMAIL", "llm:salary", "retro:match"
    def to_dict(self): return asdict(self)


class LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


# Pipeline interface (implemented in otr/pipeline.py):
#
#   class Pipeline:
#       def __init__(self, llm: LLM | None = None, hold_seconds: float = 30.0): ...
#       def push(self, seg: Segment, now: float | None = None) -> list[Event]
#       def tick(self, now: float) -> list[Event]            # release segments older than hold_seconds
#       def confirm(self, segment_id: str, keep_out: bool) -> list[Event]   # answer to a pending_confirm
#       def flush(self) -> list[Event]                       # end of meeting: release everything not suppressed
#       def notes(self) -> list[Segment]                     # committed, non-redacted segments, in order
#       def audit_log(self) -> list[Event]
#
# With llm=None the pipeline must still work using rules + regex only.
