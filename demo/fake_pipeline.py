"""Tiny stand-in for otr.pipeline.Pipeline (same interface, trivial rules).

Rules: "off the record" -> OFF (cue redacted, following lines redacted);
"back on the record" -> ON; "strike that"/"scratch that" -> redact the latest held line
(or retro-remove the latest committed line); salary/comp mentions -> pending_confirm;
emails/phone numbers -> redacted. Everything else is held, then committed by tick().
"""
from __future__ import annotations

import re
from otr.types import Event, Segment

OFF_RE = re.compile(r"off the record", re.I)
ON_RE = re.compile(r"back on the record|on the record again", re.I)
STRIKE_RE = re.compile(r"strike that|scratch that|forget (that|what i just said)", re.I)
SALARY_RE = re.compile(r"\b(salary|salaries|compensation|raise|bonus)\b|\$\s?\d[\d,]{3,}", re.I)
PII_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")


class Pipeline:
    def __init__(self, llm=None, hold_seconds: float = 30.0):
        self.hold_seconds = hold_seconds
        self._state = "ON"
        self._now = 0.0
        self._held: dict[str, tuple[Segment, float]] = {}  # id -> (seg, t_held)
        self._pending: dict[str, Segment] = {}
        self._notes: list[Segment] = []
        self._audit: list[Event] = []

    def _ev(self, kind, seg, reason="", now=None):
        e = Event(kind=kind, segment_id=seg.id if seg else None,
                  text=seg.text if seg else "", speaker=seg.speaker if seg else "",
                  t=self._now if now is None else now, state=self._state, reason=reason)
        self._audit.append(e)
        return e

    @property
    def state(self):
        return self._state

    def set_room_scope(self, off, reason="room"):
        new = "OFF" if off else "ON"
        changed = self._state != new and (off or self._state == "OFF")
        if changed:
            self._state = new
        return changed

    def _set_state(self, s, seg=None, reason=""):
        self._state = s
        return self._ev("state_change", seg, reason)

    def _commit(self, seg):
        self._notes.append(seg)
        return self._ev("committed", seg)

    def push(self, seg, now=None):
        if now is not None:
            self._now = now
        out = []
        if ON_RE.search(seg.text):
            out.append(self._ev("redacted", seg, "cue:back_on_record"))
            out.append(self._set_state("ON", seg, "cue:back_on_record"))
        elif OFF_RE.search(seg.text):
            out.append(self._ev("redacted", seg, "cue:off_the_record"))
            out.append(self._set_state("OFF", seg, "cue:off_the_record"))
        elif STRIKE_RE.search(seg.text):
            out.append(self._ev("redacted", seg, "cue:strike_that"))
            if self._held:
                sid = list(self._held)[-1]  # most recent held line only
                s, _ = self._held.pop(sid)
                out.append(self._ev("redacted", s, "retro:held"))
            elif self._notes:
                s = self._notes.pop()
                out.append(self._ev("retro_removed", s, "retro:match"))
        elif self._state == "OFF":
            out.append(self._ev("redacted", seg, "state:off"))
        elif PII_RE.search(seg.text):
            out.append(self._ev("redacted", seg, "regex:PII"))
        elif SALARY_RE.search(seg.text):
            self._pending[seg.id] = seg
            out.append(self._ev("held", seg))
            out.append(self._set_state("PENDING_CONFIRM", seg, "llm:salary"))
            out.append(self._ev("pending_confirm", seg, "llm:salary"))
        else:
            self._held[seg.id] = (seg, self._now)
            out.append(self._ev("held", seg))
        return out

    def tick(self, now):
        self._now = now
        out = []
        for sid, (s, t0) in list(self._held.items()):
            if now - t0 >= self.hold_seconds:
                del self._held[sid]
                out.append(self._commit(s))
        return out

    def confirm(self, segment_id, keep_out):
        seg = self._pending.pop(segment_id, None)
        if seg is None:
            return []
        out = []
        if keep_out:
            out.append(self._ev("redacted", seg, "confirmed:keep_out"))
        else:
            out.append(self._commit(seg))
        if not self._pending:
            out.append(self._set_state("ON", seg, "confirm"))
        return out

    def flush(self):
        out = []
        for sid, (s, _) in list(self._held.items()):
            del self._held[sid]
            out.append(self._commit(s))
        return out

    def notes(self):
        return list(self._notes)

    def audit_log(self):
        return list(self._audit)
