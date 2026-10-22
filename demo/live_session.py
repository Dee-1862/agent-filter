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
import os
import re
import secrets
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

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

    def __init__(self, pipeline_cls, kind, source, hold_seconds=10.0):
        self.pipeline_cls, self.kind, self.source = pipeline_cls, kind, source
        self.hold_seconds = hold_seconds
        self.messages = [{"type": "reset", "mode": "livekit", "pipeline": kind}]
        self.sessions: dict[str, str] = {}  # opaque browser session -> identity
        self.names: dict[str, str] = {}
        self.pipes: dict[str, object] = {}
        self.sensitive_paused: set[str] = set()
        self.approved: dict[str, dict] = {}
        self.line_owner: dict[str, str] = {}  # approved line id -> owner identity
        self.finalized: set[str] = set()
        self.redactions: dict[str, dict[str, set[str]]] = {}
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
        return message

    def publish_participants(self):
        self.messages.append({"type": "participants", "participants": self.snapshot()})

    def set_consent(self, identity: str, enabled: bool, *, sensitive_pause: bool = False):
        if enabled and identity in self.finalized:
            raise HTTPException(409, "Notes already finalized")
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
        self.names.pop(identity, None)
        for sid, owner in list(self.sessions.items()):
            if owner == identity:
                del self.sessions[sid]
        self.publish_participants()

    def _pipe(self, identity: str):
        if identity not in self.pipes:
            self.pipes[identity] = self.pipeline_cls(hold_seconds=self.hold_seconds)
        return self.pipes[identity]

    def _publish_events(self, identity: str, events):
        if self.closed:
            return
        # A sensitive hold must never turn into a user-approved publication in
        # this prototype. Stop the source first, discard its private pipeline,
        # and publish only a text-free status. Other speakers keep recording.
        if identity in self.finalized:
            return
        if any(event.kind == "pending_confirm" for event in events):
            for event in events:
                if event.kind in {"pending_confirm", "redacted"}:
                    self.count_redaction(identity, event.segment_id, "suppressed")
            self.set_consent(identity, False, sensitive_pause=True)
            return
        safe = []
        for event in events:
            if event.kind == "redacted":
                self.count_redaction(identity, event.segment_id, "suppressed")
            if event.kind == "committed" and self.source.consent_snapshot().get(identity, False):
                line = {"id": event.segment_id, "speaker": identity, "name": self.names.get(identity, identity),
                        "text": event.text}
                self.approved[event.segment_id] = line
                self.line_owner[event.segment_id] = identity
                safe.append({"kind": "committed", "line": line, "owner": identity})
            elif event.kind == "retro_removed":
                self.count_redaction(identity, event.segment_id, "removed")
                self.approved.pop(event.segment_id, None)
                self.line_owner.pop(event.segment_id, None)
                safe.append({"kind": "removed", "id": event.segment_id, "owner": identity})
            elif event.kind == "state_change" and event.state == "OFF":
                self.set_consent(identity, False)
        if safe:
            self.messages.append({"type": "transcript", "changes": safe})

    def push(self, segment: Segment):
        if self.closed:
            return
        identity = segment.speaker
        if not self.source.consent_snapshot().get(identity, False):
            return
        if SPOKEN_STOP_RE.search(segment.text):
            self.set_consent(identity, False)
            return
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



def create_live_app(cls, kind, live_source=None, hold_seconds=10.0, autostart=True):
    from contextlib import asynccontextmanager
    if live_source is None:
        from otr.ingest.livekit_source import LiveKitSource
        live_source = LiveKitSource()
    session = LiveSession(cls, kind, live_source, hold_seconds=hold_seconds)

    @asynccontextmanager
    async def lifespan(app):
        if autostart:
            session.start()
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

    def sid_for(request: Request, room_id: str | None = None) -> str:
        if room_id is None:
            # Same-origin browser requests to /api/me and /stream carry their
            # meeting page as Referer. Use its room-specific cookie so a second
            # tab creating a different meeting cannot evict this host session.
            referer = request.headers.get("referer", "")
            prefix = str(request.base_url).rstrip("/") + "/m/"
            if referer.startswith(prefix):
                room_id = referer[len(prefix):].split("?", 1)[0].split("/", 1)[0]
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
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Origin mismatch")

    def person(body: dict):
        name = str(body.get("name", "")).strip()[:60]
        email = str(body.get("email", "")).strip()[:254]
        if not name:
            raise HTTPException(400, "Display name required")
        if not email or "@" not in email or " " in email:
            raise HTTPException(400, "Valid email required")
        return name, email

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "live.html")

    @app.get("/m/{room_id}")
    async def meeting_page(room_id: str):
        if room_id not in meetings:
            raise HTTPException(404, "Meeting not found")
        return FileResponse(STATIC / "live.html")

    @app.post("/api/meetings")
    async def create_meeting(request: Request, body: dict):
        validate_origin(request)
        name, email = person(body)
        room_id = secrets.token_urlsafe(9)
        while room_id in meetings:
            room_id = secrets.token_urlsafe(9)
        live = LiveSession(cls, kind, source_for(room_id), hold_seconds=hold_seconds)
        identity = "person-" + uuid.uuid4().hex
        sid = secrets.token_urlsafe(32)
        live.sessions[sid] = identity
        live.names[identity] = name
        live.set_consent(identity, False)
        meetings[room_id] = {"session": live, "host": identity, "requests": {}, "email": email}
        browser_sessions[sid] = (room_id, "host", None)
        if autostart:
            live.start()
        public_origin = os.environ.get("MEETING_PUBLIC_ORIGIN", str(request.base_url).rstrip("/"))
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
        live.messages.clear()
        room["requests"].clear()
        room.clear()
        response = JSONResponse({"ok": True, "transport_disconnected": transport_disconnected},
                                headers={"Cache-Control": "no-store"})
        response.delete_cookie(meeting_cookie(room_id))
        if request.cookies.get("otr_session") == sid_for(request, room_id):
            response.delete_cookie("otr_session")
        return response

    @app.get("/static/{asset}")
    async def static_asset(asset: str):
        if asset not in {"live.js", "livekit-client.umd.js", "live.css"}:
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
                "room": live.source.room_name}

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
    async def me(request: Request):
        _, live, identity = room_for(request)
        owners = live.finishers()
        return JSONResponse({"identity": identity,
                "participants": live.public_participants(identity),
                "lines": live.own_lines(identity),
                "redaction_counts": live.redaction_counts(identity),
                "finalized": identity in live.finalized,
                "ready_for_final": live.ready_for_final(),
                "finalized_count": sum(1 for o in owners if o in live.finalized),
                "contributor_count": len(owners)}, headers={"Cache-Control": "no-store"})

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
        _, live, identity = room_for(request)
        line_id = body.get("id")
        if not isinstance(line_id, str) or not line_id.strip():
            raise HTTPException(400, "id required")
        live.remove_line(identity, line_id)
        return {"ok": True}

    @app.post("/api/notes/finalize")
    async def notes_finalize(request: Request, body: dict | None = None):
        _, live, identity = room_for(request)
        live.finalize(identity)
        return {"ok": True, "finalized": True}

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
            yield f"data: {json.dumps({'type': 'snapshot', 'lines': live.own_lines(identity)})}\n\n"
            yield f"data: {json.dumps({'type': 'redaction_counts', 'redaction_counts': live.redaction_counts(identity)})}\n\n"
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
