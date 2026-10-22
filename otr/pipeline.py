"""System C: hold buffer + cue detector + state machine + LLM context check.

Streaming behaviour (live STT input):
  * thread-safe: every public method takes one re-entrant lock.
  * `hold_seconds` is a live attribute, read at release time (changing it affects held segments).
  * `now` is monotonic (`max` of everything seen); a clock that does not advance is fine.
  * duplicate segment ids are ignored (idempotent push).
  * out-of-order arrival: segments are logged in (t_start, arrival) order. If a segment arrives
    whose t_start is earlier than segments that are already processed but not yet committed, the
    pipeline rolls the state machine back and re-processes those segments in time order, so a cue
    spoken earlier by another speaker still governs text that was transcribed first. Already
    committed text cannot be recalled (it can still be retro-removed by a later cue).
"""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field, replace
from typing import Optional

from . import cue_detector as cd
from .hold_buffer import HoldBuffer, Item
from .llm import classify_sensitivity
from .pii import redact_pii
from .state_machine import CONTINUE, END, ON, OFF, PENDING, TENTATIVE, StateMachine
from .types import LLM, Event, Segment

STRIKE_WINDOW = 8.0   # seconds: "strike that" w/o topic only targets an utterance this recent


@dataclass
class _Rec:
    seg: Segment                       # raw (unmasked) segment as received
    seq: int
    arrival: float
    sm_before: Optional[dict] = None   # state machine snapshot taken before processing
    item: Optional[Item] = None
    victims: list = field(default_factory=list)   # ids this record's retro cue removed (not committed)
    committed: bool = False
    locked: bool = False               # a confirm() touched it: do not roll back
    was_in_buf: bool = False


class Pipeline:
    def __init__(self, llm: Optional[LLM] = None, hold_seconds: float = 30.0,
                 use_presidio: bool = True, strike_window: float = STRIKE_WINDOW):
        self.llm = llm
        self.use_presidio = use_presidio
        self.strike_window = strike_window
        self.sm = StateMachine()
        self.buf = HoldBuffer(hold_seconds)
        self._lock = threading.RLock()
        self._notes: list[Item] = []
        self._audit: list[Event] = []
        self._now = 0.0
        self._seq = 0
        self._seen: set[str] = set()
        self._log: list[_Rec] = []
        self._recs: dict[str, _Rec] = {}
        self._utter: list[list] = []     # [t_start, seq, id, is_meta] of recent utterances, time ordered

    # ------------------------------------------------------------ public API
    @property
    def hold_seconds(self) -> float:
        return self.buf.hold_seconds

    @hold_seconds.setter
    def hold_seconds(self, v: float):
        with self._lock:
            self.buf.hold_seconds = float(v)

    @property
    def state(self) -> str:
        return self.sm.state

    def push(self, seg: Segment, now: Optional[float] = None) -> list[Event]:
        with self._lock:
            now = seg.t_end if now is None else now
            self._now = max(self._now, now)
            if seg.id in self._seen:
                return []                      # duplicate delivery
            self._seen.add(seg.id)
            ev = self._release(self._now)
            self._seq += 1
            rec = _Rec(seg=seg, seq=self._seq, arrival=self._now)
            self._note_utterance(rec)
            plan = self._plan_replay(rec)
            self._insert_log(rec)
            if plan is None:
                ev += self._process(rec, first=True)
            else:
                ev += self._replay(plan, rec)
            return ev

    def tick(self, now: float) -> list[Event]:
        with self._lock:
            self._now = max(self._now, now)
            ev = self._release(self._now)
            self._prune_log()
            return ev

    def confirm(self, segment_id: str, keep_out: bool) -> list[Event]:
        with self._lock:
            item = self.buf.get(segment_id)
            if item is None or not item.pending:
                return []
            self._lock_rec(segment_id)
            ev: list[Event] = []
            item.pending = False
            self.buf.remove(segment_id)
            if keep_out:
                ev.append(self._ev("redacted", item, reason="confirm:keep_out"))
            else:
                ev.append(self._commit(item, "confirm:keep_in"))
            followers = [i for i in self.buf.items() if i.after_pending == segment_id]
            others_pending = bool(self.buf.pending_items())
            if self.sm.state == PENDING and not others_pending:
                ev += self._to_state(ON, item, "confirm")
            if keep_out and not others_pending:
                # the thread this line belongs to stays out until it provably moves on
                self.sm.begin_soft_scope(item.seg.text, item.seg.t_start)
            for f in followers:
                f.after_pending = None
                self._lock_rec(f.seg.id)
                if not keep_out:
                    continue
                if self.sm.soft:
                    ev += self._off_step(f, f.seg.text, f.seg.t_start)
                elif (classify_sensitivity(self.llm, f.seg.text)[0]
                      or cd.tfidf_overlap(item.seg.text, {"x": f.seg.text})):
                    self.buf.remove(f.seg.id)
                    ev.append(self._ev("redacted", f, reason="confirm:related"))
            return ev

    def flush(self) -> list[Event]:
        with self._lock:
            ev: list[Event] = []
            # Undecided OFF-scope lines at end of meeting. Two or more consecutive off-topic lines is
            # real drift evidence: release them (sensitivity check still applies). One is not: fail safe.
            drifted = self.sm.streak >= 2
            for it in self.buf.tentative_items():
                it.tentative = False
                if drifted:
                    ev += self._check_implicit(it)
                else:
                    self.buf.remove(it.seg.id)
                    ev.append(self._ev("redacted", it, reason="flush:unresolved_scope"))
            for it in self.buf.drain():
                ev.append(self._commit(it, "flush"))
            for it in self.buf.pending_items():      # unanswered question: fail safe, keep out
                self.buf.remove(it.seg.id)
                ev.append(self._ev("redacted", it, reason="flush:unconfirmed"))
            self._prune_log()
            return ev

    def notes(self) -> list[Segment]:
        with self._lock:
            return [i.seg for i in self._notes]

    def audit_log(self) -> list[Event]:
        """Every event emitted, in order (full trail incl. retro removals)."""
        with self._lock:
            return list(self._audit)

    # --------------------------------------------------------------- internals
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

    def _lock_rec(self, sid: str):
        r = self._recs.get(sid)
        if r:
            r.locked = True

    def _commit(self, item: Item, reason: str = "") -> Event:
        self._notes.append(item)
        r = self._recs.get(item.seg.id)
        if r:
            r.committed = True
        return self._ev("committed", item, reason=reason)

    def _release(self, now: float) -> list[Event]:
        return [self._commit(i, "hold_elapsed") for i in self.buf.release_due(now)]

    def _insert_log(self, rec: _Rec):
        key = (rec.seg.t_start, rec.seq)
        pos = len(self._log)
        while pos > 0 and (self._log[pos - 1].seg.t_start, self._log[pos - 1].seq) > key:
            pos -= 1
        self._log.insert(pos, rec)
        self._recs[rec.seg.id] = rec

    def _note_utterance(self, rec: _Rec):
        key = [rec.seg.t_start, rec.seq, rec.seg.id, False, rec.seg.speaker,
               len(cd.content_stems(rec.seg.text)), rec.seg.t_end]
        pos = len(self._utter)
        while pos > 0 and self._utter[pos - 1][:2] > key[:2]:
            pos -= 1
        self._utter.insert(pos, key)
        del self._utter[:-200]

    def _mark_meta(self, sid: str):
        for u in self._utter:
            if u[2] == sid:
                u[3] = True

    def _prune_log(self):
        keep = []
        for r in self._log:
            in_buf = r.item is not None and self.buf.get(r.seg.id) is r.item
            if not r.committed and (in_buf or self._now - r.arrival < self.buf.hold_seconds):
                keep.append(r)
            else:
                self._recs.pop(r.seg.id, None)
        self._log = keep

    # ------------------------------------------------------- out-of-order replay
    def _plan_replay(self, rec: _Rec) -> Optional[list[_Rec]]:
        """Records that must be re-processed after `rec` is slotted in by time, or None."""
        t = rec.seg.t_start
        live = [r for r in self._log if not r.committed]
        later = [r for r in live if r.seg.t_start > t]
        if not later:
            return None
        chosen = {r.seg.id: r for r in later}
        changed = True
        while changed:
            changed = False
            min_t = min(r.seg.t_start for r in chosen.values())
            for r in live:
                if r.seg.id not in chosen and r.seg.t_start >= min_t:
                    chosen[r.seg.id] = r
                    changed = True
            for r in list(chosen.values()):
                for vid in r.victims:
                    v = self._recs.get(vid)
                    if v is not None and not v.committed and v.seg.id not in chosen:
                        chosen[v.seg.id] = v
                        changed = True
        plan = sorted(chosen.values(), key=lambda r: (r.seg.t_start, r.seq))
        if any(r.locked for r in plan):
            return None            # user already answered a prompt in this window: process in place
        return plan

    def _replay(self, plan: list[_Rec], new: _Rec) -> list[Event]:
        for r in plan:
            r.was_in_buf = r.item is not None and self.buf.get(r.seg.id) is r.item
            if r.was_in_buf:
                self.buf.remove(r.seg.id)
            r.item = None
        self.sm.__dict__.clear()
        self.sm.__dict__.update(copy.deepcopy(plan[0].sm_before))
        order = sorted(plan + [new], key=lambda r: (r.seg.t_start, r.seq))
        ev: list[Event] = []
        for r in order:
            ev += self._process(r, first=(r is new))
        return ev

    # ---------------------------------------------------------------- processing
    def _process(self, rec: _Rec, first: bool) -> list[Event]:
        seg = rec.seg
        rec.sm_before = copy.deepcopy(self.sm.__dict__)
        masked, labels = redact_pii(seg.text, self.use_presidio)
        item = self.buf.add(replace(seg, text=masked), rec.arrival, seq=rec.seq)
        rec.item = item
        rec.victims = []
        ev: list[Event] = []
        if first or not rec.was_in_buf:
            pii_reason = ("presidio:" + ",".join(sorted(set(labels)))) if labels else ""
            ev.append(self._ev("held", item, reason=pii_reason))
        rec.was_in_buf = True

        cue = cd.detect(seg.text)   # on raw text; masked PII never contains cue words
        sm = self.sm
        if cue.kind == "retro":
            ev += self._handle_retro(rec, cue)
            if sm.soft:
                sm.end_scope()      # the participants are retracting the thread: it is handled
        elif cue.kind == "start":
            ev += self._settle_tentatives(release=False, reason="cue:" + cue.name)
            ev += self._to_state(OFF, item, "cue:" + cue.name)
            sm.start_scope(seg.text, seg.t_start)
            ev += self._suppress(item, "cue:" + cue.name)
        elif cue.kind == "end" and sm.in_scope:
            ev += self._settle_tentatives(release=False, reason="scope:off")
            ev += self._to_state(ON, item, "cue:scope_end")
            sm.end_scope()
            if len(cd.content_stems(cue.remainder)) >= 3:
                item.seg = replace(item.seg, text=redact_pii(cue.remainder, self.use_presidio)[0])
            else:
                self.buf.remove(item.seg.id)
                ev.append(self._ev("redacted", item, reason="cue:scope_end_meta"))
        elif sm.in_scope:
            ev += self._off_step(item, seg.text, seg.t_start)
        elif sm.state == PENDING:
            pend = self.buf.pending_items()
            item.after_pending = pend[0].seg.id if pend else None
        else:
            ev += self._check_implicit(item)
        return ev

    def _off_step(self, item: Item, text: str, t: float) -> list[Event]:
        """One utterance arriving inside a kept-out scope (no explicit cue in it)."""
        sm = self.sm
        ev: list[Event] = []
        verdict, why = sm.assess(text, t, self.llm)
        if verdict == CONTINUE:
            for tent in self.buf.tentative_items():
                sm.note_suppressed(tent.seg.text)
            ev += self._settle_tentatives(release=False, reason="scope:off")
            ev += self._suppress(item, "scope:off")
        elif verdict == TENTATIVE:
            item.tentative = True          # held, undecided; resolved by later utterances
        else:                              # END
            release = (why == "drift")     # sustained drift: the streak itself was public chat
            if not release:
                ev += self._settle_tentatives(release=False, reason="scope:off")
            ev += self._to_state(ON, item, "implicit_end:" + why)
            sm.end_scope()
            if release:
                ev += self._settle_tentatives(release=True, reason="")
            ev += self._check_implicit(item)
        return ev

    def _settle_tentatives(self, release: bool, reason: str) -> list[Event]:
        """Resolve undecided OFF-scope utterances: suppress them (part of the private run) or
        release them into normal ON handling (they turned out to be public)."""
        ev: list[Event] = []
        for it in self.buf.tentative_items():
            it.tentative = False
            if release:
                ev += self._check_implicit(it)
            else:
                ev += self._suppress(it, reason)
        return ev

    def _check_implicit(self, item: Item) -> list[Event]:
        sens, cat = classify_sensitivity(self.llm, item.seg.text)
        if not sens:
            return []
        item.pending = True
        src = "llm" if self.llm is not None else "kw"
        ev = self._to_state(PENDING, item, f"{src}:{cat}")
        ev.append(self._ev("pending_confirm", item, reason=f"{src}:{cat}"))
        return ev

    def _self_correction_target(self, pool: list[Item], cue_seg: Segment, seq: int) -> list[str]:
        """Rule for a bare "strike that" (no topic, no count). Look at the latest line (a short
        backchannel from ANOTHER speaker such as "right" is skipped). Remove it only if
          * it is by the SAME speaker and ended within `strike_window` s of the cue, or
          * it is by another speaker and ended within strike_window/2 s (a moderator reacting to
            what was just said).
        Otherwise remove nothing: an ordinary self-correction ("the meeting is Tuesday, strike
        that, Wednesday") must not delete unrelated older text."""
        key = (cue_seg.t_start, seq)
        in_pool = {i.seg.id for i in pool}
        for u in reversed(self._utter):
            if (u[0], u[1]) >= key or u[3]:
                continue                       # later than the cue, or a cue line itself
            if u[4] != cue_seg.speaker and u[5] < 2:
                continue                       # other speaker's backchannel ("right", "got it")
            limit = self.strike_window if u[4] == cue_seg.speaker else self.strike_window / 2
            # if that line was already kept out (suppressed/redacted) there is nothing left to strike
            return [u[2]] if (cue_seg.t_start - u[6] <= limit and u[2] in in_pool) else []
        return []

    def _handle_retro(self, rec: _Rec, cue: cd.Cue) -> list[Event]:
        item, seg = rec.item, rec.seg
        ev: list[Event] = []
        self.buf.remove(item.seg.id)
        ev.append(self._ev("redacted", item, reason="cue:retro_meta"))
        pool = sorted((i for i in self._notes + self.buf.items()
                       if i.seg.id != seg.id and i.seg.t_start <= seg.t_start),
                      key=lambda i: (i.seg.t_start, i.seq))
        by_id = {i.seg.id: i for i in pool}
        cands = [(i.seg.id, i.seg.speaker, i.seg.text) for i in pool]
        if cue.count:
            # "the last two things I said" counts spoken utterances, including ones already suppressed
            self._mark_meta(seg.id)
            key = (seg.t_start, rec.seq)
            spoken = [u[2] for u in self._utter if (u[0], u[1]) < key and not u[3]][-cue.count:]
            ids, method = [i for i in spoken if i in by_id], "count"
        else:
            self._mark_meta(seg.id)
            ids, method = cd.resolve_retro(cue.topic, seg.text, cands, self.llm,
                                           previous=self._self_correction_target(pool, seg, rec.seq))
        for sid in ids:
            t = by_id[sid]
            if t in self._notes:
                self._notes.remove(t)
                ev.append(self._ev("retro_removed", t, reason=f"retro:match({method})"))
            else:
                was_pending = t.pending
                self.buf.remove(sid)
                rec.victims.append(sid)
                ev.append(self._ev("redacted", t, reason=f"retro:match({method})"))
                if was_pending and self.sm.state == PENDING and not self.buf.pending_items():
                    ev += self._to_state(ON, t, "retro_resolved_pending")
        return ev
