"""System C: hold buffer + cue detector + state machine + LLM context check."""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from . import cue_detector as cd
from .hold_buffer import HoldBuffer, Item
from .llm import classify_sensitivity
from .pii import redact_pii
from .state_machine import ON, OFF, PENDING, StateMachine
from .types import LLM, Event, Segment


class Pipeline:
    def __init__(self, llm: Optional[LLM] = None, hold_seconds: float = 30.0,
                 use_presidio: bool = True):
        self.llm = llm
        self.hold_seconds = hold_seconds
        self.use_presidio = use_presidio
        self.sm = StateMachine()
        self.buf = HoldBuffer(hold_seconds)
        self._notes: list[Item] = []
        self._audit: list[Event] = []
        self._now = 0.0

    # ------------------------------------------------------------ public API
    @property
    def state(self) -> str:
        return self.sm.state

    def push(self, seg: Segment, now: Optional[float] = None) -> list[Event]:
        now = seg.t_end if now is None else now
        self._now = max(self._now, now)
        ev: list[Event] = []
        ev += self._release(self._now)

        masked, labels = redact_pii(seg.text, self.use_presidio)
        item = self.buf.add(replace(seg, text=masked), self._now)
        pii_reason = ("presidio:" + ",".join(sorted(set(labels)))) if labels else ""
        ev.append(self._ev("held", item, reason=pii_reason))

        cue = cd.detect(seg.text)   # on raw text; masked PII never contains cue words
        if cue.kind == "retro":
            ev += self._handle_retro(item, cue)
        elif cue.kind == "start":
            ev += self._to_state(OFF, item, "cue:" + cue.name)
            self.sm.note_suppressed(seg.text)
            ev += self._suppress(item, "cue:" + cue.name)
        elif cue.kind == "end" and self.sm.state == OFF:
            ev += self._to_state(ON, item, "cue:scope_end")
            if len(cd.content_stems(cue.remainder)) >= 3:
                item.seg = replace(item.seg, text=redact_pii(cue.remainder, self.use_presidio)[0])
            else:
                self.buf.remove(item.seg.id)
                ev.append(self._ev("redacted", item, reason="cue:scope_end_meta"))
        elif self.sm.state == OFF:
            if self.sm.topic_changed(seg.text, self._llm_or_none()):
                ev += self._to_state(ON, item, "implicit_end:topic_change")
                ev += self._check_implicit(item)
            else:
                self.sm.note_suppressed(seg.text)
                ev += self._suppress(item, "scope:off")
        elif self.sm.state == PENDING:
            pend = self.buf.pending_items()
            item.after_pending = pend[0].seg.id if pend else None
        else:
            ev += self._check_implicit(item)
        return ev

    def tick(self, now: float) -> list[Event]:
        self._now = max(self._now, now)
        return self._release(self._now)

    def confirm(self, segment_id: str, keep_out: bool) -> list[Event]:
        item = self.buf.get(segment_id)
        if item is None or not item.pending:
            return []
        ev: list[Event] = []
        item.pending = False
        if keep_out:
            self.buf.remove(segment_id)
            ev.append(self._ev("redacted", item, reason="confirm:keep_out"))
        else:
            self.buf.remove(segment_id)
            ev.append(self._commit(item, "confirm:keep_in"))
        # segments queued behind it
        followers = [i for i in self.buf.items() if i.after_pending == segment_id]
        for f in followers:
            f.after_pending = None
            if keep_out and (classify_sensitivity(self._llm_or_none(), f.seg.text)[0]
                             or cd.tfidf_overlap(item.seg.text, {"x": f.seg.text})):
                self.buf.remove(f.seg.id)
                ev.append(self._ev("redacted", f, reason="confirm:related"))
        if self.sm.state == PENDING and not self.buf.pending_items():
            ev += self._to_state(ON, item, "confirm")
        return ev

    def flush(self) -> list[Event]:
        ev: list[Event] = []
        for it in self.buf.drain():
            ev.append(self._commit(it, "flush"))
        for it in self.buf.pending_items():      # unanswered question: fail safe, keep out
            self.buf.remove(it.seg.id)
            ev.append(self._ev("redacted", it, reason="flush:unconfirmed"))
        return ev

    def notes(self) -> list[Segment]:
        return [i.seg for i in self._notes]

    def audit_log(self) -> list[Event]:
        """Every event emitted, in order (full trail incl. retro removals)."""
        return list(self._audit)

    # --------------------------------------------------------------- internals
    def _llm_or_none(self):
        return self.llm

    def _ev(self, kind, item: Item, reason: str = "", text: Optional[str] = None) -> Event:
        e = Event(kind=kind, segment_id=item.seg.id, text=item.seg.text if text is None else text,
                  speaker=item.seg.speaker, t=self._now, state=self.sm.state, reason=reason)
        self._audit.append(e)
        return e

    def _to_state(self, new: str, item: Item, reason: str) -> list[Event]:
        if self.sm.set(new, reason):
            return [self._ev("state_change", item, reason=reason, text="")]
        return []

    def _suppress(self, item: Item, reason: str) -> list[Event]:
        self.buf.remove(item.seg.id)
        return [self._ev("redacted", item, reason=reason)]

    def _commit(self, item: Item, reason: str = "") -> Event:
        self._notes.append(item)
        return self._ev("committed", item, reason=reason)

    def _release(self, now: float) -> list[Event]:
        return [self._commit(i, "hold_elapsed") for i in self.buf.release_due(now)]

    def _check_implicit(self, item: Item) -> list[Event]:
        sens, cat = classify_sensitivity(self.llm, item.seg.text)
        if not sens:
            return []
        item.pending = True
        src = "llm" if self.llm is not None else "kw"
        ev = self._to_state(PENDING, item, f"{src}:{cat}")
        ev.append(self._ev("pending_confirm", item, reason=f"{src}:{cat}"))
        return ev

    def _handle_retro(self, item: Item, cue: cd.Cue) -> list[Event]:
        ev: list[Event] = []
        self.buf.remove(item.seg.id)
        ev.append(self._ev("redacted", item, reason="cue:retro_meta"))
        pool = sorted(self._notes + self.buf.items(), key=lambda i: i.seq)
        by_id = {i.seg.id: i for i in pool}
        ids, method = cd.resolve_retro(cue.topic, item.seg.text,
                                       [(i.seg.id, i.seg.speaker, i.seg.text) for i in pool],
                                       self._llm_or_none())
        for sid in ids:
            t = by_id[sid]
            if t in self._notes:
                self._notes.remove(t)
                ev.append(self._ev("retro_removed", t, reason=f"retro:match({method})"))
            else:
                was_pending = t.pending
                self.buf.remove(sid)
                ev.append(self._ev("redacted", t, reason=f"retro:match({method})"))
                if was_pending and self.sm.state == PENDING and not self.buf.pending_items():
                    ev += self._to_state(ON, t, "retro_resolved_pending")
        return ev
