"""Consent-gated LiveKit demo mode (from the per-person-consent branch).

Each speaker has their own policy pipeline; a participant sees only their own
approved lines. Once every contributor has explicitly finalized, any
participant may request the combined final transcript. Used by
`python -m demo.server --source livekit`. The shared-view StreamRunner mode is
`--source livekit-stream`.
"""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
import math
import os
import re
import secrets
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from demo.categories import categorize, family as rule_family, js_source, taxonomy
from otr.types import Segment

STATIC = Path(__file__).parent / "static"

SPOKEN_STOP_RE = re.compile(
    # Match a direct opening request. Whisper may mishear the last pronoun in
    # "please stop recording me"; the unambiguous imperative is sufficient.
    # Anchoring avoids stopping for "he said stop recording me" or
    # "don't stop recording me" in ordinary conversation.
    r"^\s*(?:hey[,.]?\s+)?(?:please[,.]?\s+)?(?:stop\s+recording\b"
    r"|(?:don't|do\s+not)\s+record\s+me\b"
    r"|i\s+(?:don't|do\s+not)\s+want\s+(?:this|that|my\s+voice|me)\s+(?:to\s+be\s+)?recorded\b)",
    re.I,
)
EMAIL_LOCAL_RE = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*\Z")
EMAIL_DOMAIN_LABEL_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")


def valid_delivery_email(value: object) -> str:
    """Accept ordinary mailbox addresses without controls or mailto header injection."""
    if not isinstance(value, str) or len(value) > 254 or value != value.strip():
        raise HTTPException(400, "Valid email required")
    parts = value.split("@")
    if len(parts) != 2:
        raise HTTPException(400, "Valid email required")
    local, domain = parts
    labels = domain.split(".")
    if (not local or len(local) > 64 or len(domain) > 253 or len(labels) < 2
            or not EMAIL_LOCAL_RE.fullmatch(local)
            or any(not EMAIL_DOMAIN_LABEL_RE.fullmatch(label) for label in labels)):
        raise HTTPException(400, "Valid email required")
    return value

LINE_RE = re.compile(r"^([^:]{1,40}):\s*(.+)$")


# ---------------------------------------------------------------- helpers
def parse_script(path) -> list[tuple[str, str, float]]:
    """Parse 'Speaker: text' lines -> [(speaker, text, delay_before_seconds)].
    '# comment' and blank lines are skipped; '@pause N' adds N seconds before the next line.
    (Own parser; the demo does not depend on otr.ingest.replay_source.)"""
    out, extra = [], 0.0
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@pause"):
            try:
                extra += float(line.split()[1])
            except (IndexError, ValueError):
                pass
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        speaker, text = m.group(1), m.group(2)
        delay = max(1.5, len(text.split()) * 0.33) + extra
        out.append((speaker, text, delay))
        extra = 0.0
    return out


def load_pipeline_class(kind: str):
    """kind: real | fake | auto. Lazy import of the real pipeline."""
    if kind in ("real", "auto"):
        try:
            return importlib.import_module("otr.pipeline").Pipeline, "real"
        except Exception as e:  # ImportError or a broken module
            print(f"[demo] otr.pipeline unavailable ({e!r}); falling back to fake", file=sys.stderr)
    from demo.fake_pipeline import Pipeline
    return Pipeline, "fake"


def mint_join_token(source, identity: str, name: str):
    """LiveKit room token for one participant, or None when the SDK is absent
    (identity issuance and consent still work without it)."""
    try:
        from datetime import timedelta
        from livekit import api
    except ImportError:
        print("[demo] livekit-api not installed; join token omitted", file=sys.stderr)
        return None
    return (api.AccessToken(source.api_key, source.api_secret)
            .with_identity(identity).with_name(name)
            .with_ttl(timedelta(minutes=10))
            .with_grants(api.VideoGrants(room_join=True, room=source.room_name,
                                         can_publish=True, can_subscribe=True))
            .to_jwt())


# ---------------------------------------------------------------- session
class Session:
    def __init__(self, pipeline_cls, kind, script=None, speed=1.0, hold_seconds=10.0, llm=None):
        self.pipeline_cls, self.kind = pipeline_cls, kind
        self.script, self.speed, self.hold_seconds, self.llm = script, speed, hold_seconds, llm
        self.messages: list[dict] = []
        self.done = False
        self.tasks: list = []
        self._reset()

    def _reset(self):
        self.pipe = self.pipeline_cls(llm=self.llm, hold_seconds=self.hold_seconds)
        self.t0 = time.monotonic()
        self.n = 0
        self.done = False
        self.messages.append({"type": "reset", "hold_seconds": self.hold_seconds, "pipeline": self.kind})

    def now(self) -> float:
        return time.monotonic() - self.t0

    def _emit(self, events):
        if not events:
            return
        self.messages.append({
            "type": "events",
            "events": [e.to_dict() for e in events],
            "notes": [s.to_dict() for s in self.pipe.notes()],
            "audit": [e.to_dict() for e in self.pipe.audit_log()],
        })

    def say(self, speaker: str, text: str):
        self.n += 1
        t = self.now()
        seg = Segment(id=f"u{self.n}", speaker=speaker, text=text, t_start=t, t_end=t)
        self.messages.append({"type": "segment", "segment": seg.to_dict()})
        self._emit(self.pipe.push(seg, now=t))
        return seg

    def tick(self):
        self._emit(self.pipe.tick(self.now()))

    def confirm(self, segment_id: str, keep_out: bool):
        evs = self.pipe.confirm(segment_id, keep_out)
        self._emit(evs)
        return evs

    def set_hold(self, seconds: float):
        self.hold_seconds = seconds
        if hasattr(self.pipe, "hold_seconds"):
            self.pipe.hold_seconds = seconds
        self.messages.append({"type": "config", "hold_seconds": seconds})

    def flush(self):
        self._emit(self.pipe.flush())

    # -- background work
    async def _ticker(self):
        while True:
            await asyncio.sleep(0.2)
            self.tick()

    async def _replay(self, lines):
        for speaker, text, delay in lines:
            await asyncio.sleep(delay / self.speed)
            self.say(speaker, text)
        # let the last lines age out, then end of meeting
        await asyncio.sleep(self.hold_seconds + 0.5)
        self.flush()
        self.done = True
        self.messages.append({"type": "done"})

    def start(self, replay=True):
        self.stop()
        self.tasks.append(asyncio.ensure_future(self._ticker()))
        if self.script and replay:
            self.tasks.append(asyncio.ensure_future(self._replay(parse_script(self.script))))

    def stop(self):
        for t in self.tasks:
            t.cancel()
        self.tasks = []

    def restart(self):
        self.stop()
        self._reset()
        self.start()


class LiveSession:
    """Consent-gated LiveKit input, per-viewer approved lines, explicit finalize.

    Each speaker has their own policy pipeline. The temporary text and full
    audit trail stay in process memory and are never placed in ``messages``.
    Viewers receive only their own approved lines; the combined final
    transcript is returned only on explicit request after every contributor
    whose lines remain has finalized.
    """

    def __init__(self, pipeline_cls, kind, source, hold_seconds=10.0, llm=None):
        self.pipeline_cls, self.kind, self.source = pipeline_cls, kind, source
        self.hold_seconds = hold_seconds
        self.llm = llm
        self.messages = [{"type": "reset", "mode": "livekit", "pipeline": kind}]
        self.sessions: dict[str, str] = {}  # opaque browser session -> identity
        self.names: dict[str, str] = {}
        self.pipes: dict[str, object] = {}
        self.sensitive_paused: set[str] = set()
        self.approved: dict[str, dict] = {}
        self.line_owner: dict[str, str] = {}  # approved line id -> owner identity
        self.finalized: set[str] = set()
        self.redactions: dict[str, dict[str, set[str]]] = {}
        # Server-side only, per owner: segment id -> {"category", "family", "before", "after", "held_s", "seq"}.
        # Messages carry category KEYS and counts (and these text-free trails to the owner), never text.
        self.kept_out: dict[str, dict[str, dict]] = {}
        self.timeline: dict[str, list[dict]] = {}   # owner -> [{"t", "state"}], state in STATE_LABELS
        self.last_state: dict[str, str] = {}        # owner -> last pipeline state (ON/OFF/PENDING_CONFIRM)
        self.arrival: dict[tuple[str, str], float] = {}  # (owner, segment id) -> pipeline time it arrived
        self.seq = 0
        # Unverified address labels and explicit final-report delivery choice.
        # Kept only in local room memory, never broadcast through SSE.
        self.delivery: dict[str, dict[str, object]] = {}
        self.closed = False
        self.tasks: list[asyncio.Task] = []
        self.t0 = time.monotonic()
        if hasattr(source, "on_participant_left"):
            source.on_participant_left = self.leave

    def identity_for(self, request: Request) -> str:
        sid = request.cookies.get("otr_session", "")
        identity = self.sessions.get(sid)
        if not identity:
            raise HTTPException(401, "Join the meeting first")
        return identity

    def snapshot(self) -> dict:
        consent = self.source.consent_snapshot()
        return {identity: {"name": name, "recording": bool(consent.get(identity, False)),
                           "sensitive_paused": identity in self.sensitive_paused}
                for identity, name in self.names.items()}

    def public_participants(self, viewer: str | None) -> dict:
        """Participant statuses safe to send to `viewer`: name + notes on/off,
        plus the viewer's own sensitive-pause flag (never anyone else's)."""
        consent = self.source.consent_snapshot()
        out = {}
        for identity, name in self.names.items():
            entry = {"name": name, "recording": bool(consent.get(identity, False))}
            if identity == viewer:
                entry["sensitive_paused"] = identity in self.sensitive_paused
            out[identity] = entry
        return out

    def own_lines(self, identity: str) -> list[dict]:
        return [self.approved[lid] for lid, owner in self.line_owner.items() if owner == identity]

    def redaction_counts(self, identity: str | None = None) -> dict[str, int]:
        groups = ([(identity, self.redactions.get(identity, {}))] if identity is not None
                  else list(self.redactions.items()))
        suppressed = sum(len(group.get("suppressed", ())) for _, group in groups)
        removed = sum(len(group.get("removed", ())) for _, group in groups)
        unique = {(owner, sid) for owner, group in groups
                  for category in ("suppressed", "removed")
                  for sid in group.get(category, ())}
        return {"suppressed": suppressed, "removed": removed,
                "total": len(unique)}

    def count_redaction(self, identity: str, line_id: str | None, category: str):
        if not line_id or category not in {"suppressed", "removed"}:
            return
        groups = self.redactions.setdefault(identity, {"suppressed": set(), "removed": set()})
        before = len(groups[category])
        groups[category].add(line_id)
        if len(groups[category]) != before:
            # The event log carries only a count. SSE filters it to the owner.
            self.messages.append({"type": "redaction_counts", "owner": identity,
                                  "redaction_counts": self.redaction_counts(identity)})

    # ---- text-free insights: category KEYS and counts only
    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def mark_state(self, identity: str, state: str) -> bool:
        """Append a recording-state change to this person's own timeline. Returns True if it changed."""
        tl = self.timeline.setdefault(identity, [])
        if tl and tl[-1]["state"] == state:
            return False
        tl.append({"t": round(self.now(), 1), "state": state})
        return True

    def insights_for(self, identity: str) -> dict:
        """What the owner's Insights view shows. Category keys and numbers only: no text, no ids."""
        counts: dict[str, int] = {}
        steps = self.timeline.get(identity, [])
        base = steps[0]["t"] if steps else self.now()   # the timeline starts when this person joined
        for rec in self.kept_out.get(identity, {}).values():
            counts[rec["category"]] = counts.get(rec["category"], 0) + 1
        return {"approved": sum(1 for owner in self.line_owner.values() if owner == identity),
                "kept_out": counts, "total": sum(counts.values()),
                "removed": self.redaction_counts(identity)["removed"],
                "timeline": [{"t": round(step["t"] - base, 1), "state": step["state"]} for step in steps],
                "now": round(max(0.0, self.now() - base), 1), "hold_seconds": self.hold_seconds}

    def own_kept_out(self, identity: str) -> list[dict]:
        """Placeholder chips for the owner's captions: id + category + generic trail, never text."""
        out = [{"id": sid, "category": rec["category"], "seq": rec["seq"],
                "trail": {k: rec[k] for k in ("family", "before", "after", "held_s")}}
               for sid, rec in self.kept_out.get(identity, {}).items()]
        return sorted(out, key=lambda c: c["seq"])

    # ---- text-free detail for the transcript and the pop-out page (owner only; never text)
    def _stamp(self, identity: str, key: str) -> float:
        """Seconds since this person's timeline began, noted the first time a detail payload sees `key`."""
        stamps = self.__dict__.setdefault("detail_stamps", {})
        steps = self.timeline.get(identity, [])
        base = steps[0]["t"] if steps else self.now()
        return stamps.setdefault((identity, key), round(max(0.0, self.now() - base), 1))

    def waiting_count(self, identity: str) -> int:
        """How many lines are in this person's hold buffer. A number only."""
        pipe = self.pipes.get(identity)
        try:
            if getattr(pipe, "buf", None) is not None:
                return len(pipe.buf.items())
            return len(getattr(pipe, "_held", ()) or ()) + len(getattr(pipe, "_pending", ()) or ())
        except Exception:  # noqa: BLE001 - a status number must never break /api/me
            return 0

    def kept_out_events(self, identity: str) -> list[dict]:
        """One row per kept-out line for the owner: kinds, rule family, states, timing, action. No text.
        `code` is family:kind built here, never the raw reason (whose tail can carry a topic word or a span)."""
        out = []
        for sid, rec in self.kept_out.get(identity, {}).items():
            fam = rec["family"]
            action = ("removed_after_approval" if fam == "retro"
                      else "masked" if fam in ("presidio", "regex") else "kept_out")
            out.append({"id": sid, "seq": rec["seq"], "t": self._stamp(identity, "k:" + sid),
                        "category": rec["category"], "family": fam, "before": rec["before"],
                        "after": rec["after"], "held_s": rec["held_s"], "action": action,
                        "code": f"{fam}:{rec['category']}"})
        return sorted(out, key=lambda e: e["seq"])

    def detail_for(self, identity: str) -> dict:
        return {"kept_out_events": self.kept_out_events(identity),
                "line_times": {lid: self._stamp(identity, "l:" + lid)
                               for lid, owner in self.line_owner.items() if owner == identity},
                "waiting": self.waiting_count(identity)}

    def publish_status(self, identity: str):
        # The log holds only an owner marker; the payload is built per viewer in visible_message.
        self.messages.append({"type": "status", "owner": identity})

    def note_kept_out(self, identity: str, event, before: str, after: str) -> dict | None:
        """Record that a segment was kept out. Returns the (text-free) transcript change for the owner."""
        if not event.segment_id:
            return None
        arrived = self.arrival.pop((identity, event.segment_id), None)
        held = round(max(0.0, event.t - arrived), 1) if arrived is not None else 0.0
        old = self.kept_out.setdefault(identity, {}).get(event.segment_id)
        rec = {"category": categorize(event.reason, event.kind), "family": rule_family(event.reason),
               "before": before, "after": after, "held_s": held,
               "seq": old["seq"] if old else self.next_seq()}
        self.kept_out[identity][event.segment_id] = rec
        return {"kind": "kept_out", "id": event.segment_id, "owner": identity, "category": rec["category"],
                "seq": rec["seq"], "trail": {k: rec[k] for k in ("family", "before", "after", "held_s")}}

    def contributors(self) -> set[str]:
        return set(self.line_owner.values())

    def finishers(self) -> set[str]:
        # People still present must finish, even if their live audio has not
        # produced an approved line yet. Keep departed, finalized owners too.
        return self.contributors() | set(self.names)

    def ready_for_final(self) -> bool:
        owners = self.finishers()
        # Do not export while an admitted person could still enable notes or
        # while a speaker is actively recording but has no approved line yet.
        return bool(self.contributors()) and all(owner in self.finalized for owner in owners)

    def visible_message(self, viewer: str, message: dict) -> dict | None:
        """Filter one event for SSE. Test this directly: TestClient buffers endless streams."""
        if message.get("type") == "participants":
            return {"type": "participants", "participants": self.public_participants(viewer)}
        if message.get("type") == "transcript":
            changes = [change for change in message["changes"]
                       if change.get("owner") == viewer
                       and (change["kind"] != "committed"
                            or change["line"]["id"] in self.approved)]
            return {"type": "transcript", "changes": changes} if changes else None
        if message.get("type") == "redaction_counts":
            if message.get("owner") != viewer:
                return None
            return {"type": "redaction_counts", "redaction_counts": message["redaction_counts"]}
        if message.get("type") == "status":
            if message.get("owner") != viewer:
                return None
            return {"type": "status", **self.insights_for(viewer)}
        return message

    def diagnostics_for(self, identity: str) -> dict:
        """The caller's own capture health: numbers and short status words only, never text."""
        src = self.source
        notes_on = bool(src.consent_snapshot().get(identity, False))
        d = src.diagnostics() if hasattr(src, "diagnostics") else {"bot": {"state": "n/a", "error": ""}, "participants": {}}
        bot, mine = d["bot"], d["participants"].get(identity, {})
        rms = float(mine.get("rms") or 0.0)
        age = mine.get("last_frame_age_s")
        floor = float(mine.get("noise_floor") or 0.0)
        subscribed = bool(mine.get("subscribed", False))
        error = bot.get("error") or None
        if bot.get("state") == "failed":
            state = "error"
        elif not notes_on or not subscribed:
            state = "not_subscribed"
        elif not mine.get("frames") or age is None or age > 2.0:
            state = "waiting_for_audio"
        elif rms >= max(200.0, 2.5 * floor):
            state = "hearing_you"
        else:
            state = "silent"
        if state != "error":
            error = None
        # dBFS mapped -60..0 to 0..1 (speech at rms 2000 is about 0.6)
        level = 0.0 if rms < 1 else max(0.0, min(1.0, (20 * math.log10(rms / 32768.0) + 60.0) / 60.0))
        return {"subscribed": subscribed, "notes_on": notes_on, "audio_rms": round(rms, 1),
                "audio_level": round(level, 3), "last_frame_age_s": age,
                "stt_last_activity_age_s": mine.get("stt_last_age_s"), "state": state, "error": error}

    def publish_participants(self):
        self.messages.append({"type": "participants", "participants": self.snapshot()})

    def set_consent(self, identity: str, enabled: bool, *, sensitive_pause: bool = False,
                    state_label: str | None = None):
        if enabled and identity in self.finalized:
            raise HTTPException(409, "Notes already finalized")
        label = "recording" if enabled else "paused" if sensitive_pause else (state_label or "off")
        if self.mark_state(identity, label):
            self.publish_status(identity)
        if sensitive_pause:
            self.sensitive_paused.add(identity)
        else:
            self.sensitive_paused.discard(identity)
        self.source.set_consent(identity, enabled)
        if not enabled:
            # Drop buffered/private text. Previously approved lines remain until
            # an explicit retroactive removal is supported by the policy engine.
            self.pipes.pop(identity, None)
        self.publish_participants()

    def _drop_lines_of(self, identity: str):
        """Fail closed: a departed, unfinalized contributor keeps no approved lines."""
        changes = []
        for line_id in [lid for lid, owner in self.line_owner.items() if owner == identity]:
            self.approved.pop(line_id, None)
            self.line_owner.pop(line_id, None)
            self.count_redaction(identity, line_id, "removed")
            changes.append({"kind": "removed", "id": line_id, "owner": identity})
        if changes:
            self.messages.append({"type": "transcript", "changes": changes})

    def remove_line(self, identity: str, line_id: str):
        if self.line_owner.get(line_id) != identity:
            raise HTTPException(404, "Line not found")
        self.approved.pop(line_id, None)
        self.line_owner.pop(line_id, None)
        self.count_redaction(identity, line_id, "removed")
        self.messages.append({"type": "transcript",
                              "changes": [{"kind": "removed", "id": line_id, "owner": identity}]})

    def finalize(self, identity: str):
        """Stop capture, discard held text, mark this contribution finalized. Idempotent."""
        self.finalized.add(identity)
        self.set_consent(identity, False)
        self.publish_participants()

    def leave(self, identity: str):
        self.set_consent(identity, False)
        if identity not in self.finalized:
            self._drop_lines_of(identity)
            self.delivery.pop(identity, None)
        self.names.pop(identity, None)
        self.kept_out.pop(identity, None)
        self.timeline.pop(identity, None)
        self.last_state.pop(identity, None)
        for key in [k for k in self.arrival if k[0] == identity]:
            del self.arrival[key]
        for sid, owner in list(self.sessions.items()):
            if owner == identity:
                del self.sessions[sid]
        self.publish_participants()

    def _pipe(self, identity: str):
        if identity not in self.pipes:
            kwargs = {"llm": self.llm} if self.llm is not None else {}
            self.pipes[identity] = self.pipeline_cls(hold_seconds=self.hold_seconds, **kwargs)
        return self.pipes[identity]

    def _publish_events(self, identity: str, events):
        if self.closed:
            return
        # A sensitive hold must never turn into a user-approved publication in
        # this prototype. Stop the source first, discard its private pipeline,
        # and publish only text-free status. Other speakers keep recording.
        if identity in self.finalized:
            return
        before = self.last_state.get(identity, "ON")
        after_by_seg = {e.segment_id: e.state for e in events if e.segment_id}
        if events:
            self.last_state[identity] = events[-1].state
        pausing = any(event.kind == "pending_confirm" for event in events)
        safe = []
        for event in events:
            suppressed_kinds = {"pending_confirm", "redacted"} if pausing else {"redacted"}
            if event.kind in suppressed_kinds:
                self.count_redaction(identity, event.segment_id, "suppressed")
            if event.kind in suppressed_kinds or (event.kind == "retro_removed" and not pausing):
                change = self.note_kept_out(identity, event, before, after_by_seg.get(event.segment_id, event.state))
                if change:
                    safe.append(change)
            if pausing:
                continue
            if event.kind == "committed" and self.source.consent_snapshot().get(identity, False):
                self.arrival.pop((identity, event.segment_id), None)
                line = {"id": event.segment_id, "speaker": identity, "name": self.names.get(identity, identity),
                        "text": event.text, "seq": self.next_seq()}
                self.approved[event.segment_id] = line
                self.line_owner[event.segment_id] = identity
                safe.append({"kind": "committed", "line": line, "owner": identity})
            elif event.kind == "retro_removed":
                self.count_redaction(identity, event.segment_id, "removed")
                self.approved.pop(event.segment_id, None)
                self.line_owner.pop(event.segment_id, None)
                safe.append({"kind": "removed", "id": event.segment_id, "owner": identity})
            elif event.kind == "state_change" and event.state == "OFF":
                self.set_consent(identity, False, state_label="off_record")
        if pausing:
            self.set_consent(identity, False, sensitive_pause=True)
        if safe:
            self.messages.append({"type": "transcript", "changes": safe})
            self.publish_status(identity)

    def push(self, segment: Segment):
        if self.closed:
            return
        identity = segment.speaker
        if not self.source.consent_snapshot().get(identity, False):
            return
        if SPOKEN_STOP_RE.search(segment.text):
            self.set_consent(identity, False)
            return
        self.arrival[(identity, segment.id)] = self.now()
        pipe = self._pipe(identity)
        self._publish_events(identity, pipe.push(segment, now=self.now()))

    def now(self):
        return time.monotonic() - self.t0

    async def _consume(self):
        try:
            async for segment in self.source.segments():
                self.push(segment)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[demo] LiveKit capture stopped: {exc}", file=sys.stderr)
            for identity in list(self.names):
                self.set_consent(identity, False)
            self.messages.append({"type": "service", "status": "Capture unavailable"})

    async def _ticker(self):
        while True:
            await asyncio.sleep(0.2)
            for identity, pipe in list(self.pipes.items()):
                if self.source.consent_snapshot().get(identity, False):
                    self._publish_events(identity, pipe.tick(self.now()))

    def start(self):
        self.tasks = [asyncio.create_task(self._consume()), asyncio.create_task(self._ticker())]

    def stop(self):
        for task in self.tasks:
            task.cancel()
        self.tasks = []



def warm_llm(llm, state: dict | None = None):
    """Load the local model in a background thread so the first real decision is not a cold start."""
    if llm is None or not hasattr(llm, "warmup"):
        return None
    import threading

    def work():
        secs = llm.warmup()
        if state is not None:
            state["warm"] = state["reachable"] = secs != float("inf")
    thread = threading.Thread(target=work, name="llm-warmup", daemon=True)
    thread.start()
    return thread


def create_live_app(cls, kind, live_source=None, hold_seconds=10.0, autostart=True, llm=None):
    from contextlib import asynccontextmanager
    if live_source is None:
        from otr.ingest.livekit_source import LiveKitSource
        live_source = LiveKitSource()
    session = LiveSession(cls, kind, live_source, hold_seconds=hold_seconds, llm=llm)
    llm_state = {"warm": False, "reachable": False}

    @asynccontextmanager
    async def lifespan(app):
        if autostart:
            session.start()
            warm_llm(llm, llm_state)
            if hasattr(live_source, "preload"):
                # Load and warm Whisper now so the first sentence does not pay for it.
                async def preload():
                    try:
                        await live_source.preload()
                    except Exception as exc:  # noqa: BLE001 - surfaced through /api/diagnostics
                        print(f"[demo] speech model failed to load: {exc}", file=sys.stderr)
                app.state.preload = asyncio.create_task(preload())
        yield
        session.stop()
        for room in meetings.values():
            room["session"].stop()

    app = FastAPI(title="OTR demo (consent mode)", lifespan=lifespan)
    app.state.session = session
    meetings: dict[str, dict] = {}
    app.state.meetings = meetings
    browser_sessions: dict[str, tuple[str, str, str | None]] = {}

    def meeting_cookie(room_id: str) -> str:
        return "otr_session_" + room_id

    def allowed_origins(request: Request) -> set[str]:
        origins = {str(request.base_url).rstrip("/")}
        # A static public frontend may proxy API requests to this local host.
        # Only its explicitly configured origin may submit state-changing calls.
        public_origin = os.environ.get("OTR_PUBLIC_ORIGIN", "").rstrip("/")
        if public_origin:
            origins.add(public_origin)
        return origins

    def sid_for(request: Request, room_id: str | None = None) -> str:
        if room_id is None:
            # /api/me and /stream carry their meeting page as Referer. A public
            # frontend's origin may differ from the local backend's base URL.
            # Use its room-specific cookie so another tab does not evict this one.
            referer = request.headers.get("referer", "")
            try:
                parts = urlsplit(referer)
                referer_origin = f"{parts.scheme}://{parts.netloc}"
                if referer_origin in allowed_origins(request) and parts.path.startswith("/m/"):
                    room_id = parts.path[len("/m/"):].split("/", 1)[0]
            except ValueError:
                pass  # malformed Referer; fall back to the legacy session cookie
        if room_id:
            specific = request.cookies.get(meeting_cookie(room_id), "")
            if specific:
                return specific
        return request.cookies.get("otr_session", "")

    def source_for(room_id: str):
        # One local capture pipeline per room. No participant data is stored on disk.
        from otr.ingest.livekit_source import LiveKitSource
        if isinstance(live_source, LiveKitSource):
            return LiveKitSource(room=room_id, url=live_source.url,
                                 api_key=live_source.api_key, api_secret=live_source.api_secret,
                                 model=live_source.model, transcribe=live_source._transcribe)
        cloned = copy.deepcopy(live_source)
        cloned.room_name = room_id
        return cloned

    def room_for(request: Request, room_id: str | None = None, *, host=False):
        sid = sid_for(request, room_id)
        entry = browser_sessions.get(sid)
        if entry is None:
            if room_id is None and sid in session.sessions:
                return None, session, session.sessions[sid]
            raise HTTPException(401, "Join the meeting first")
        bound_room, role, request_id = entry
        if room_id is not None and bound_room != room_id:
            raise HTTPException(403, "Wrong meeting")
        room = meetings.get(bound_room)
        if room is None:
            raise HTTPException(404, "Meeting not found")
        if host and role != "host":
            raise HTTPException(403, "Host access required")
        if role == "host":
            return room, room["session"], room["host"]
        guest = room["requests"].get(request_id)
        if guest is None or guest["sid"] != sid:
            raise HTTPException(401, "Session expired")
        if guest["status"] != "admitted":
            raise HTTPException(403, "Waiting for host admission")
        return room, room["session"], guest["identity"]

    def validate_origin(request: Request):
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins(request):
            raise HTTPException(403, "Origin mismatch")

    def person(body: dict):
        name = str(body.get("name", "")).strip()[:60]
        email = valid_delivery_email(body.get("email"))
        if not name:
            raise HTTPException(400, "Display name required")
        return name, email

    def demo_limit(env_name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(env_name, default)))
        except ValueError:
            return default

    # One page for everyone in consent mode: lobby, admission, video, and the side panel views
    # (Realtime, Insights, Explainability). `/live` is kept as an alias.
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "live.html", headers={"Cache-Control": "no-store"})

    @app.get("/live")
    @app.get("/live.html")
    async def classic_page():
        return FileResponse(STATIC / "live.html")

    # The pop-out Insights and Explanation page. Same strict CSP (a meta tag in the file) and no-store as `/`.
    # The room-scoped path lets /api/me and /stream pick this meeting's cookie from the Referer.
    @app.get("/insights")
    @app.get("/insights.html")
    @app.get("/m/{room_id}/insights")
    async def insights_page(room_id: str | None = None):
        return FileResponse(STATIC / "insights.html", headers={"Cache-Control": "no-store"})

    @app.get("/m/{room_id}")
    async def meeting_page(room_id: str):
        if room_id not in meetings:
            raise HTTPException(404, "Meeting not found")
        return FileResponse(STATIC / "live.html")

    @app.post("/api/meetings")
    async def create_meeting(request: Request, body: dict):
        validate_origin(request)
        name, email = person(body)
        if len(meetings) >= demo_limit("OTR_MAX_ACTIVE_MEETINGS", 4):
            raise HTTPException(429, "Meeting capacity reached")
        room_id = secrets.token_urlsafe(9)
        while room_id in meetings:
            room_id = secrets.token_urlsafe(9)
        live = LiveSession(cls, kind, source_for(room_id), hold_seconds=hold_seconds, llm=llm)
        identity = "person-" + uuid.uuid4().hex
        sid = secrets.token_urlsafe(32)
        live.sessions[sid] = identity
        live.names[identity] = name
        live.delivery[identity] = {"name": name, "email": email, "enabled": False}
        live.set_consent(identity, False)
        meetings[room_id] = {"session": live, "host": identity, "requests": {}, "email": email}
        browser_sessions[sid] = (room_id, "host", None)
        if autostart:
            live.start()
        public_origin = (os.environ.get("MEETING_PUBLIC_ORIGIN")
                         or os.environ.get("OTR_PUBLIC_ORIGIN")
                         or str(request.base_url).rstrip("/"))
        response = JSONResponse({"room_id": room_id, "join_url": public_origin.rstrip("/") + "/m/" + room_id,
                                 "identity": identity, "name": name, "role": "host",
                                 "token": mint_join_token(live.source, identity, name),
                                 "url": os.environ.get("LIVEKIT_PUBLIC_URL", live.source.url),
                                 "room": room_id}, headers={"Cache-Control": "no-store"})
        response.set_cookie("otr_session", sid, httponly=True, samesite="lax", max_age=7200)
        response.set_cookie(meeting_cookie(room_id), sid, httponly=True, samesite="lax", max_age=7200)
        return response

    @app.post("/api/meetings/{room_id}/request")
    async def request_admission(room_id: str, request: Request, body: dict):
        validate_origin(request)
        room = meetings.get(room_id)
        if room is None:
            raise HTTPException(404, "Meeting not found")
        name, email = person(body)
        if sum(guest["status"] == "waiting" for guest in room["requests"].values()) >= demo_limit(
                "OTR_MAX_PENDING_JOIN_REQUESTS", 20):
            raise HTTPException(429, "Too many pending join requests")
        request_id = secrets.token_urlsafe(12)
        identity = "person-" + uuid.uuid4().hex
        sid = secrets.token_urlsafe(32)
        room["requests"][request_id] = {"sid": sid, "identity": identity, "name": name,
                                        "email": email, "status": "waiting"}
        browser_sessions[sid] = (room_id, "guest", request_id)
        response = JSONResponse({"request_id": request_id, "status": "waiting"},
                                headers={"Cache-Control": "no-store"})
        response.set_cookie("otr_session", sid, httponly=True, samesite="lax", max_age=7200)
        response.set_cookie(meeting_cookie(room_id), sid, httponly=True, samesite="lax", max_age=7200)
        return response

    @app.get("/api/meetings/{room_id}/status")
    async def admission_status(room_id: str, request: Request):
        sid = sid_for(request, room_id)
        entry = browser_sessions.get(sid)
        if entry is None or entry[0] != room_id:
            raise HTTPException(401, "Request to join first")
        room = meetings.get(room_id)
        if room is None:
            raise HTTPException(404, "Meeting not found")
        if entry[1] == "host":
            pending = [{"request_id": rid, "name": guest["name"], "email": guest["email"]}
                       for rid, guest in room["requests"].items() if guest["status"] == "waiting"]
            return JSONResponse({"status": "admitted", "role": "host", "pending": pending,
                                 "identity": room["host"], "room": room_id,
                                 "name": room["session"].names[room["host"]],
                                 "token": mint_join_token(room["session"].source, room["host"],
                                                          room["session"].names[room["host"]]),
                                 "url": os.environ.get("LIVEKIT_PUBLIC_URL", room["session"].source.url)},
                                headers={"Cache-Control": "no-store"})
        guest = room["requests"].get(entry[2])
        if guest is None or guest["sid"] != sid:
            raise HTTPException(401, "Session expired")
        response = {"status": guest["status"], "role": "guest", "request_id": entry[2]}
        if guest["status"] == "admitted":
            response.update({"identity": guest["identity"], "name": guest["name"],
                             "token": mint_join_token(room["session"].source, guest["identity"], guest["name"]),
                             "url": os.environ.get("LIVEKIT_PUBLIC_URL", room["session"].source.url),
                             "room": room_id})
        return JSONResponse(response, headers={"Cache-Control": "no-store"})

    @app.post("/api/meetings/{room_id}/admit")
    async def admit(room_id: str, request: Request, body: dict):
        validate_origin(request)
        room, live, _ = room_for(request, room_id, host=True)
        guest = room["requests"].get(body.get("request_id"))
        if guest is None or guest["status"] != "waiting":
            raise HTTPException(404, "Pending request not found")
        guest["status"] = "admitted"
        live.sessions[guest["sid"]] = guest["identity"]
        live.names[guest["identity"]] = guest["name"]
        live.delivery[guest["identity"]] = {"name": guest["name"], "email": guest["email"],
                                            "enabled": False}
        live.set_consent(guest["identity"], False)
        return {"ok": True}

    @app.post("/api/meetings/{room_id}/deny")
    async def deny(room_id: str, request: Request, body: dict):
        validate_origin(request)
        room, _, _ = room_for(request, room_id, host=True)
        guest = room["requests"].get(body.get("request_id"))
        if guest is None or guest["status"] != "waiting":
            raise HTTPException(404, "Pending request not found")
        guest["status"] = "denied"
        return {"ok": True}

    @app.post("/api/meetings/{room_id}/cancel")
    async def cancel_request(room_id: str, request: Request):
        validate_origin(request)
        sid = sid_for(request, room_id)
        entry = browser_sessions.get(sid)
        if entry is None or entry[0] != room_id or entry[1] != "guest":
            raise HTTPException(403, "No pending request")
        room = meetings.get(room_id)
        guest = room["requests"].get(entry[2]) if room else None
        if guest is None or guest["sid"] != sid or guest["status"] != "waiting":
            raise HTTPException(409, "Request is no longer pending")
        room["requests"].pop(entry[2])
        browser_sessions.pop(sid, None)
        response = JSONResponse({"ok": True})
        response.delete_cookie(meeting_cookie(room_id))
        if request.cookies.get("otr_session") == sid:
            response.delete_cookie("otr_session")
        return response

    @app.post("/api/meetings/{room_id}/end")
    async def end_meeting(room_id: str, request: Request):
        validate_origin(request)
        room, live, _ = room_for(request, room_id, host=True)
        # Revoke web access before yielding to task cancellation. A stream that
        # already holds this session also checks `closed` before sending data.
        live.closed = True
        meetings.pop(room_id, None)
        for sid, (bound_room, _, _) in list(browser_sessions.items()):
            if bound_room == room_id:
                browser_sessions.pop(sid, None)
        for identity in list(live.names):
            try:
                live.source.set_consent(identity, False)
            except Exception:
                # Cancelling the capture task below disconnects the local bot
                # even if an individual track subscription already failed.
                pass
        tasks = list(live.tasks)
        live.stop()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # The server-side recorder is local, and the local LiveKit API closes
        # the transport room so admitted browsers are disconnected as well.
        # A previously minted JWT can still be used until it expires; the web
        # app cannot revoke it, so room tokens should remain short-lived.
        transport_disconnected = True
        from otr.ingest.livekit_source import LiveKitSource
        if isinstance(live.source, LiveKitSource):
            lk = None
            try:
                from livekit import api
                lk = api.LiveKitAPI(url=live.source.url, api_key=live.source.api_key,
                                    api_secret=live.source.api_secret)
                await lk.room.delete_room(api.DeleteRoomRequest(room=room_id))
            except Exception as exc:
                transport_disconnected = False
                print(f"[demo] room disconnect failed: {type(exc).__name__}", file=sys.stderr)
            finally:
                if lk is not None:
                    await lk.aclose()
        if hasattr(live.source, "on_participant_left"):
            live.source.on_participant_left = None
        live.sessions.clear()
        live.names.clear()
        live.pipes.clear()
        live.approved.clear()
        live.line_owner.clear()
        live.sensitive_paused.clear()
        live.finalized.clear()
        live.redactions.clear()
        live.kept_out.clear()
        live.timeline.clear()
        live.last_state.clear()
        live.arrival.clear()
        live.delivery.clear()
        live.messages.clear()
        room["requests"].clear()
        room.clear()
        response = JSONResponse({"ok": True, "transport_disconnected": transport_disconnected},
                                headers={"Cache-Control": "no-store"})
        response.delete_cookie(meeting_cookie(room_id))
        if request.cookies.get("otr_session") == sid_for(request, room_id):
            response.delete_cookie("otr_session")
        return response

    @app.get("/static/categories.js")
    async def categories_js():
        # The one category taxonomy (demo/categories.py), rendered for the page. Contains no meeting data.
        return Response(js_source(), media_type="text/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/api/categories")
    async def categories_json():
        return taxonomy()

    @app.get("/static/{asset}")
    async def static_asset(asset: str):
        if asset not in {"live.js", "livekit-client.umd.js", "live.css", "views.js", "views.css",
                         "insights.js", "insights.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / asset)

    @app.get("/api/config")
    async def config(request: Request):
        try:
            _, live, _ = room_for(request)
        except HTTPException:
            live = session
        # The LiveKit URL is public room transport configuration; secrets
        # are used only on the server to mint short-lived participant tokens.
        return {"mode": "livekit", "url": os.environ.get("LIVEKIT_PUBLIC_URL", live.source.url),
                "room": live.source.room_name, "categories": taxonomy()["categories"]}

    @app.post("/api/join")
    async def join(body: dict):
        name = str(body.get("name", "")).strip()[:60]
        if not name:
            raise HTTPException(400, "Display name required")
        identity = "person-" + uuid.uuid4().hex
        sid = secrets.token_urlsafe(32)
        token = mint_join_token(session.source, identity, name)
        session.sessions[sid] = identity
        session.names[identity] = name
        session.set_consent(identity, False)
        response = JSONResponse({"identity": identity, "name": name, "token": token})
        response.set_cookie("otr_session", sid, httponly=True, samesite="strict",
                            secure=False, max_age=7200)
        return response

    @app.get("/api/me")
    async def me(request: Request, summary: bool = False):
        _, live, identity = room_for(request)
        owners = live.finishers()
        delivery = live.delivery.get(identity, {})
        payload = {"identity": identity,
                "participants": live.public_participants(identity),
                "kept_out": live.own_kept_out(identity),
                "insights": live.insights_for(identity),
                "redaction_counts": live.redaction_counts(identity),
                "finalized": identity in live.finalized,
                "delivery_email": delivery.get("email", ""),
                "email_opted_in": bool(delivery.get("enabled", False)),
                "ready_for_final": live.ready_for_final(),
                "finalized_count": sum(1 for o in owners if o in live.finalized),
                "contributor_count": len(owners)}
        payload.update(live.detail_for(identity))   # text-free: kept_out_events, line_times, waiting
        if not summary:
            payload["lines"] = live.own_lines(identity)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    def model_info() -> dict:
        stats = getattr(getattr(live_source, "_transcribe", None), "stats", None) or {}
        try:
            from otr import pii
            ok = pii.presidio_available()
            presidio = {"model": pii.presidio_model() if ok else None, "available": bool(ok)}
        except Exception:  # noqa: BLE001
            presidio = {"model": None, "available": False}
        return {"whisper": {"name": getattr(live_source, "model", None),
                            "loaded": getattr(live_source, "_transcribe", None) is not None,
                            "load_seconds": stats.get("load_seconds"), "rtf": stats.get("rtf")},
                "llm": {"name": getattr(llm, "model", None), "reachable": llm_state["reachable"],
                        "warm": llm_state["warm"]},
                "presidio": presidio}

    @app.get("/api/diagnostics")
    async def diagnostics(request: Request):
        """Capture health, text-free. A signed-in caller sees only their own audio status;
        a loopback caller without a session (scripts/mic_check.py) sees status for everyone,
        still numbers and state words only."""
        headers = {"Cache-Control": "no-store"}
        try:
            _, live, identity = room_for(request)
        except HTTPException:
            if not (request.client and request.client.host in ("127.0.0.1", "::1", "localhost")):
                raise
            people = {}
            for lv in [session, *[m["session"] for m in meetings.values()]]:
                src_diag = lv.source.diagnostics() if hasattr(lv.source, "diagnostics") else {"bot": {}, "participants": {}}
                for ident in lv.names:
                    me = lv.diagnostics_for(ident)
                    me["name"] = lv.names[ident]
                    me["room"] = getattr(lv.source, "room_name", "")
                    me["bot"] = src_diag["bot"]
                    people[ident] = me
            return JSONResponse({"models": model_info(), "hold_seconds": hold_seconds,
                                 "bot": session.source.diagnostics()["bot"] if hasattr(session.source, "diagnostics") else {},
                                 "participants": people}, headers=headers)
        mine = live.diagnostics_for(identity)
        mine["waiting_lines"] = live.waiting_count(identity)   # a count of lines in the hold buffer, never text
        return JSONResponse({"models": model_info(), "me": mine,
                             "hold_seconds": live.hold_seconds}, headers=headers)

    @app.post("/api/consent")
    async def consent(request: Request, body: dict):
        _, live, identity = room_for(request)
        if body.get("recording") is not True and body.get("recording") is not False:
            raise HTTPException(400, "recording must be a boolean")
        if body["recording"] and identity in live.finalized:
            raise HTTPException(409, "Notes already finalized")
        validate_origin(request)
        live.set_consent(identity, body["recording"])
        return {"identity": identity, "recording": body["recording"]}

    @app.post("/api/notes/remove")
    async def notes_remove(request: Request, body: dict):
        validate_origin(request)
        _, live, identity = room_for(request)
        line_id = body.get("id")
        if not isinstance(line_id, str) or not line_id.strip():
            raise HTTPException(400, "id required")
        live.remove_line(identity, line_id)
        return {"ok": True}

    @app.post("/api/notes/finalize")
    async def notes_finalize(request: Request, body: dict | None = None):
        validate_origin(request)
        _, live, identity = room_for(request)
        live.finalize(identity)
        return {"ok": True, "finalized": True}

    @app.post("/api/notes/email-opt-in")
    async def email_opt_in(request: Request, body: dict):
        validate_origin(request)
        _, live, identity = room_for(request)
        if identity not in live.finalized:
            raise HTTPException(409, "Finalize your notes first")
        if type(body.get("enabled")) is not bool:
            raise HTTPException(400, "enabled must be a boolean")
        email = valid_delivery_email(body.get("email"))
        entry = live.delivery.setdefault(identity, {"name": live.names.get(identity, ""),
                                                    "email": "", "enabled": False})
        entry["email"] = email
        entry["enabled"] = body["enabled"]
        return JSONResponse({"email": email, "enabled": body["enabled"]},
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/meetings/{room_id}/mail-recipients")
    async def mail_recipients(room_id: str, request: Request):
        _, live, _ = room_for(request, room_id, host=True)
        if not live.ready_for_final():
            raise HTTPException(409, "Final transcript is not ready")
        seen = set()
        recipients = []
        for identity, entry in live.delivery.items():
            if identity not in live.finalized or not entry.get("enabled"):
                continue
            email = str(entry["email"])
            key = email.casefold()
            if key in seen:
                continue
            seen.add(key)
            recipients.append({"name": str(entry["name"]), "email": email})
        return JSONResponse({"recipients": recipients}, headers={"Cache-Control": "no-store"})

    @app.get("/api/notes/final")
    async def notes_final(request: Request):
        _, live, _ = room_for(request)
        if not live.ready_for_final():
            raise HTTPException(409, "Final transcript is not ready")
        lines = [{"id": line["id"], "name": line["name"], "text": line["text"]}
                 for line in live.approved.values()]
        return JSONResponse({"ready": True, "lines": lines,
                             "redaction_counts": live.redaction_counts()},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/leave")
    async def leave(request: Request):
        validate_origin(request)
        room, live, identity = room_for(request)
        live.leave(identity)
        room_id = live.source.room_name if room is not None else None
        sid = sid_for(request, room_id)
        browser_sessions.pop(sid, None)
        response = JSONResponse({"ok": True})
        if room_id:
            response.delete_cookie(meeting_cookie(room_id))
        if request.cookies.get("otr_session") == sid:
            response.delete_cookie("otr_session")
        return response

    @app.get("/stream")
    async def live_stream(request: Request):
        room, live, identity = room_for(request)
        sid = sid_for(request, live.source.room_name if room is not None else None)

        async def gen():
            # Do not replay earlier approved text after retroactive deletion.
            # A fresh connection gets only the current approved snapshot.
            # Everything is filtered by the authenticated viewer: only their
            # own line text, line ids, and their own sensitive status leave
            # this process.
            if live.closed:
                return
            i = len(live.messages)
            yield f"data: {json.dumps({'type': 'participants', 'participants': live.public_participants(identity)})}\n\n"
            yield f"data: {json.dumps({'type': 'snapshot', 'lines': live.own_lines(identity), 'kept_out': live.own_kept_out(identity)})}\n\n"
            yield f"data: {json.dumps({'type': 'redaction_counts', 'redaction_counts': live.redaction_counts(identity)})}\n\n"
            yield f"data: {json.dumps({'type': 'status', **live.insights_for(identity)})}\n\n"
            while True:
                if live.closed:
                    return
                if sid not in live.sessions:
                    return
                while i < len(live.messages):
                    message = live.messages[i]
                    i += 1
                    message = live.visible_message(identity, message)
                    if message is None:
                        continue
                    yield f"data: {json.dumps(message)}\n\n"
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.2)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


    return app
